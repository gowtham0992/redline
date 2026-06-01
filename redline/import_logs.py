from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import iter_jsonl, write_jsonl
from .redact import DEFAULT_PLACEHOLDER, redact_object


_MISSING = object()

IMPORT_PRESETS: dict[str, dict[str, object]] = {
    "datadog": {
        "input_field": "attributes.input",
        "output_field": "attributes.output",
        "metadata_fields": ["service", "trace_id", "attributes.model"],
    },
    "dolly": {
        "input_field": "instruction",
        "output_field": "response",
        "context_field": "context",
        "metadata_fields": ["category"],
    },
    "helicone": {
        "input_field": "request.prompt",
        "output_field": "response.text",
        "metadata_fields": ["request.model", "response.model", "user_id"],
    },
    "langfuse": {
        "input_field": "input",
        "output_field": "output",
        "metadata_fields": ["name", "traceId", "userId"],
    },
    "openai-chat": {
        "input_field": "request.messages",
        "output_field": "response.choices.0.message.content",
        "metadata_fields": ["request.model", "response.model"],
    },
}

_PROMPT_FIELD_CANDIDATES = (
    "prompt",
    "input",
    "instruction",
    "request.prompt",
    "request.input",
    "request.messages",
    "messages",
    "ticket.text",
    "attributes.input",
)

_RESPONSE_FIELD_CANDIDATES = (
    "response",
    "output",
    "completion",
    "response.text",
    "response.output_text",
    "response.choices.0.message.content",
    "assistant.reply",
    "attributes.output",
)


def import_preset(name: str) -> dict[str, object]:
    try:
        return dict(IMPORT_PRESETS[name])
    except KeyError as exc:
        choices = ", ".join(sorted(IMPORT_PRESETS))
        raise ValueError(f"unknown import preset: {name}; choose one of: {choices}") from exc


def import_preset_rows() -> list[dict[str, Any]]:
    rows = []
    for name, preset in sorted(IMPORT_PRESETS.items()):
        rows.append(
            {
                "id": name,
                "input_field": str(preset.get("input_field") or ""),
                "output_field": str(preset.get("output_field") or ""),
                "context_field": str(preset.get("context_field") or ""),
                "metadata_fields": [str(value) for value in _preset_list(preset.get("metadata_fields"))],
            }
        )
    return rows


def format_import_presets() -> str:
    lines = [
        "redline import presets",
        "",
        f"{'PRESET':<12} {'PROMPT FIELD':<28} {'RESPONSE FIELD':<38} METADATA",
        f"{'-' * 12} {'-' * 28} {'-' * 38} {'-' * 24}",
    ]
    for row in import_preset_rows():
        metadata = ", ".join(row["metadata_fields"])
        lines.append(
            f"{row['id']:<12} {row['input_field']:<28} {row['output_field']:<38} {metadata}"
        )
    lines.extend(
        [
            "",
            "Use: redline import raw.jsonl --preset langfuse --out .redline/logs/prompts.jsonl",
            "Override any preset field with --input-field, --output-field, --context-field, or --metadata-field.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def detect_import_fields(path: str | Path, *, limit: int = 20) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("--limit must be 1 or greater")
    source = Path(path)
    rows = [row for _, row in iter_jsonl(source)][:limit]
    if not rows:
        raise ValueError(f"{path} contains no JSONL records")
    suggestions = _detect_suggestions(rows)
    return {
        "source": str(path),
        "records_scanned": len(rows),
        "suggestions": suggestions,
        "top_level_fields": sorted({str(key) for row in rows for key in row})[:20],
    }


def format_import_detection(result: dict[str, Any]) -> str:
    suggestions = result.get("suggestions")
    rows = suggestions if isinstance(suggestions, list) else []
    lines = [
        "redline import detection",
        "",
        f"Source:          {result.get('source')}",
        f"Records scanned: {result.get('records_scanned')}",
        f"Top fields:      {', '.join(str(value) for value in result.get('top_level_fields', []))}",
        "",
    ]
    if not rows:
        lines.extend(
            [
                "No confident prompt/response mapping found.",
                "Next: run `redline import --list-presets` or pass --input-field and --output-field manually.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"
    lines.append(f"{'SCORE':<7} {'PRESET':<12} {'PROMPT FIELD':<28} RESPONSE FIELD")
    lines.append(f"{'-' * 7} {'-' * 12} {'-' * 28} {'-' * 28}")
    for row in rows[:8]:
        lines.append(
            f"{str(row.get('score', '')):<7} "
            f"{str(row.get('preset', '')):<12} "
            f"{str(row.get('input_field', '')):<28} "
            f"{str(row.get('output_field', ''))}"
        )
    best = rows[0]
    lines.extend(
        [
            "",
            "Preview the best mapping:",
            (
                f"redline import {result.get('source')} "
                f"--input-field {best.get('input_field')} "
                f"--output-field {best.get('output_field')} "
                "--preview 3"
            ),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def import_jsonl_log(
    path: str | Path,
    *,
    output: str | Path,
    input_field: str = "prompt",
    output_field: str = "response",
    context_field: str | None = None,
    id_field: str | None = None,
    metadata_fields: list[str] | None = None,
    limit: int | None = None,
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    rows, redaction_counts = _collect_import_rows(
        path,
        input_field=input_field,
        output_field=output_field,
        context_field=context_field,
        id_field=id_field,
        metadata_fields=metadata_fields,
        limit=limit,
        redact=redact,
        placeholder=placeholder,
    )
    if not rows:
        raise ValueError(f"{path} contains no JSONL records")
    write_jsonl(output, rows)
    redactions = sum(redaction_counts.values())
    return {
        "source": str(path),
        "output": str(output),
        "records": len(rows),
        "input_field": input_field,
        "output_field": output_field,
        "context_field": context_field or "",
        "id_field": id_field or "",
        "metadata_fields": metadata_fields or [],
        "redacted": redact,
        "redactions": redactions,
        "redaction_patterns": dict(sorted(redaction_counts.items())),
    }


def preview_jsonl_import(
    path: str | Path,
    *,
    input_field: str = "prompt",
    output_field: str = "response",
    context_field: str | None = None,
    id_field: str | None = None,
    metadata_fields: list[str] | None = None,
    limit: int = 3,
    redact: bool = True,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    rows, redaction_counts = _collect_import_rows(
        path,
        input_field=input_field,
        output_field=output_field,
        context_field=context_field,
        id_field=id_field,
        metadata_fields=metadata_fields,
        limit=limit,
        redact=redact,
        placeholder=placeholder,
    )
    if not rows:
        raise ValueError(f"{path} contains no JSONL records")
    redactions = sum(redaction_counts.values())
    return {
        "source": str(path),
        "previewed": len(rows),
        "input_field": input_field,
        "output_field": output_field,
        "context_field": context_field or "",
        "id_field": id_field or "",
        "metadata_fields": metadata_fields or [],
        "redacted": redact,
        "redactions": redactions,
        "redaction_patterns": dict(sorted(redaction_counts.items())),
        "rows": rows,
    }


def _detect_suggestions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
    for preset_name, preset in IMPORT_PRESETS.items():
        input_field = str(preset.get("input_field") or "")
        output_field = str(preset.get("output_field") or "")
        if input_field and output_field:
            _score_mapping(rows, candidates, input_field, output_field, preset_name)
    for input_field in _PROMPT_FIELD_CANDIDATES:
        for output_field in _RESPONSE_FIELD_CANDIDATES:
            _score_mapping(rows, candidates, input_field, output_field, "")
    return sorted(
        candidates.values(),
        key=lambda row: (-int(row["score"]), str(row["preset"] or "zzzz"), str(row["input_field"])),
    )


def _score_mapping(
    rows: list[dict[str, Any]],
    candidates: dict[tuple[str, str, str], dict[str, Any]],
    input_field: str,
    output_field: str,
    preset: str,
) -> None:
    matches = 0
    for row in rows:
        prompt = _get_field(row, input_field)
        response = _get_field(row, output_field)
        if prompt is _MISSING or response is _MISSING:
            continue
        if not _stringify(prompt).strip() or not _stringify_response(response).strip():
            continue
        matches += 1
    if not matches:
        return
    score = round(100 * matches / len(rows))
    key = (input_field, output_field, preset)
    candidates[key] = {
        "input_field": input_field,
        "output_field": output_field,
        "preset": preset,
        "matches": matches,
        "records_scanned": len(rows),
        "score": score,
    }


def _collect_import_rows(
    path: str | Path,
    *,
    input_field: str,
    output_field: str,
    context_field: str | None,
    id_field: str | None,
    metadata_fields: list[str] | None,
    limit: int | None,
    redact: bool,
    placeholder: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if limit is not None and limit < 1:
        raise ValueError("--limit must be 1 or greater")
    metadata_paths = metadata_fields or []
    rows: list[dict[str, Any]] = []
    redaction_counts: dict[str, int] = {}
    source = Path(path)
    for line_number, row in iter_jsonl(source):
        if limit is not None and len(rows) >= limit:
            break
        if redact:
            row = redact_object(row, placeholder=placeholder, counts=redaction_counts)
        prompt = _required_field(source, line_number, row, input_field, "input")
        response = _required_field(source, line_number, row, output_field, "output")
        imported: dict[str, Any] = {
            "prompt": _prompt_with_context(
                _stringify(prompt),
                _optional_string(row, context_field),
            ),
            "response": _stringify_response(response),
            "source_line": line_number,
        }
        if id_field:
            identifier = _get_field(row, id_field)
            if identifier is not _MISSING:
                imported["id"] = _stringify(identifier)
        metadata = _metadata(row, metadata_paths)
        if metadata:
            imported["metadata"] = metadata
        rows.append(imported)
    return rows, redaction_counts


def _required_field(
    source: Path,
    line_number: int,
    row: dict[str, Any],
    path: str,
    label: str,
) -> Any:
    value = _get_field(row, path)
    if value is _MISSING:
        fields = ", ".join(sorted(str(key) for key in row)[:8]) or "<none>"
        raise ValueError(
            f"{source}:{line_number} missing {label} field: {path}. "
            f"Available top-level fields: {fields}. "
            "Run `redline import --list-presets` or override the field path."
        )
    return value


def _metadata(row: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for path in paths:
        value = _get_field(row, path)
        if value is not _MISSING:
            metadata[path] = value
    return metadata


def _optional_string(row: dict[str, Any], path: str | None) -> str:
    if not path:
        return ""
    value = _get_field(row, path)
    if value is _MISSING:
        return ""
    return _stringify(value).strip()


def _prompt_with_context(prompt: str, context: str) -> str:
    stripped_prompt = prompt.strip()
    if not context:
        return stripped_prompt
    return f"{stripped_prompt}\n\nContext:\n{context}"


def _get_field(row: dict[str, Any], path: str) -> Any:
    if path in row:
        return row[path]
    current: Any = row
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return _MISSING
            current = current[index]
            continue
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _stringify_response(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return _stringify(value)


def _preset_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value
