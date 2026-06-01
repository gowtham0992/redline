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


def import_preset(name: str) -> dict[str, object]:
    try:
        return dict(IMPORT_PRESETS[name])
    except KeyError as exc:
        choices = ", ".join(sorted(IMPORT_PRESETS))
        raise ValueError(f"unknown import preset: {name}; choose one of: {choices}") from exc


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
        "metadata_fields": metadata_paths,
        "redacted": redact,
        "redactions": redactions,
        "redaction_patterns": dict(sorted(redaction_counts.items())),
    }


def _required_field(
    source: Path,
    line_number: int,
    row: dict[str, Any],
    path: str,
    label: str,
) -> Any:
    value = _get_field(row, path)
    if value is _MISSING:
        raise ValueError(f"{source}:{line_number} missing {label} field: {path}")
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
