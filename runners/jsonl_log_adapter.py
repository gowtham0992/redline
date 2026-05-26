#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO


PRESETS = {
    "langfuse": {
        "input_fields": ("input", "request.input", "trace.input", "inputs"),
        "output_fields": ("output", "response.output", "trace.output", "outputs"),
        "description": "Langfuse enriched observations and trace/observation JSONL exports",
    },
    "helicone": {
        "input_fields": ("prompt", "request.prompt", "requestBody.prompt", "request.body.prompt"),
        "output_fields": ("responseBody", "response.body", "response.text", "response"),
        "description": "Helicone export rows with request/response bodies included",
    },
    "langsmith": {
        "input_fields": ("inputs", "input", "example.inputs", "run.inputs"),
        "output_fields": ("outputs", "output", "run.outputs", "feedback.output"),
        "description": "LangSmith dataset, run, or trace exports with input/output objects",
    },
    "braintrust": {
        "input_fields": ("input", "inputs", "example.input", "span.input"),
        "output_fields": ("output", "expected", "outputs", "span.output"),
        "description": "Braintrust experiment or dataset rows with input/output fields",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert exported app logs into redline prompt/response JSONL."
    )
    parser.add_argument("path", nargs="?", help="input JSONL file; defaults to stdin")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="known export shape to map automatically")
    parser.add_argument("--list-presets", action="store_true", help="print known presets and exit")
    parser.add_argument("--input-field", help="field path containing prompt text")
    parser.add_argument("--output-field", help="field path containing response text")
    parser.add_argument("--out", help="output JSONL file; defaults to stdout")
    args = parser.parse_args()

    if args.list_presets:
        sys.stdout.write(format_presets())
        return 0

    input_fields, output_fields = _fields(args, parser)
    rows = list(
        _convert_rows(
            _read_rows(args.path),
            input_fields,
            output_fields,
            preset=args.preset,
        )
    )
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            _write_rows(rows, handle)
    else:
        _write_rows(rows, sys.stdout)
    return 0


def _read_rows(path: str | None) -> Iterable[tuple[int, dict[str, Any]]]:
    if path:
        with Path(path).open("r", encoding="utf-8") as handle:
            yield from _iter_rows(handle, label=path)
        return
    yield from _iter_rows(sys.stdin, label="<stdin>")


def _iter_rows(handle: TextIO, *, label: str) -> Iterable[tuple[int, dict[str, Any]]]:
    for line_number, line in enumerate(handle, 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{label}:{line_number} invalid JSON: {exc.msg}")
        if not isinstance(row, dict):
            raise SystemExit(f"{label}:{line_number} expected a JSON object")
        yield line_number, row


def _convert_rows(
    rows: Iterable[tuple[int, dict[str, Any]]],
    input_fields: tuple[str, ...],
    output_fields: tuple[str, ...],
    *,
    preset: str | None = None,
) -> Iterable[dict[str, Any]]:
    for line_number, row in rows:
        prompt_field, prompt = _first_field(row, input_fields)
        response_field, response = _first_field(row, output_fields)
        missing = []
        if prompt is _MISSING:
            missing.append("prompt field: " + ", ".join(input_fields))
        if response is _MISSING:
            missing.append("response field: " + ", ".join(output_fields))
        if missing:
            raise SystemExit(f"line {line_number} missing field(s): {', '.join(missing)}")
        converted = {
            "prompt": _stringify(prompt),
            "response": _stringify_response(response),
            "source_line": line_number,
        }
        if preset:
            converted["metadata"] = {
                "adapter_preset": preset,
                "adapter_prompt_field": prompt_field,
                "adapter_response_field": response_field,
            }
        yield converted


def _write_rows(rows: Iterable[dict[str, Any]], handle: TextIO) -> None:
    for row in rows:
        json.dump(row, handle, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def format_presets() -> str:
    lines = ["redline JSONL log adapter presets", ""]
    for name in sorted(PRESETS):
        preset = PRESETS[name]
        lines.extend(
            [
                name,
                f"  {preset['description']}",
                f"  input:  {', '.join(preset['input_fields'])}",
                f"  output: {', '.join(preset['output_fields'])}",
                (
                    "  use:    python runners/jsonl_log_adapter.py logs/export.jsonl "
                    f"--preset {name} --out .redline/logs/prompts.jsonl"
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _get_field(row: dict[str, Any], path: str) -> Any:
    if path in row:
        return row[path]
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _first_field(row: dict[str, Any], paths: tuple[str, ...]) -> tuple[str, Any]:
    for path in paths:
        value = _get_field(row, path)
        if value is not _MISSING:
            return path, value
    return "", _MISSING


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _stringify_response(value: Any) -> str:
    extracted = _extract_response_text(value)
    if extracted is not None:
        return extracted
    if isinstance(value, str):
        parsed = _parse_json_string(value)
        if parsed is not _MISSING:
            if isinstance(parsed, str):
                return parsed
            extracted = _extract_response_text(parsed)
            if extracted is not None:
                return extracted
        return value
    return _stringify(value)


def _parse_json_string(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return _MISSING


def _extract_response_text(value: Any) -> str | None:
    if isinstance(value, dict):
        choices = value.get("choices")
        if isinstance(choices, list):
            parts = [_extract_choice_text(choice) for choice in choices]
            text_parts = [part for part in parts if part is not None]
            if text_parts:
                return "\n".join(text_parts)
        for path in (
            "output_text",
            "completion",
            "message.content",
            "delta.content",
            "content",
            "text",
            "output",
        ):
            field = _get_field(value, path)
            if field is _MISSING:
                continue
            text = _coerce_text(field)
            if text is not None:
                return text
    if isinstance(value, list):
        return _coerce_text(value)
    return None


def _extract_choice_text(choice: Any) -> str | None:
    if isinstance(choice, str):
        return choice
    if not isinstance(choice, dict):
        return None
    for path in ("message.content", "delta.content", "text", "content"):
        field = _get_field(choice, path)
        if field is _MISSING:
            continue
        text = _coerce_text(field)
        if text is not None:
            return text
    return None


def _coerce_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            text = _extract_response_text(item)
            if text is not None:
                parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return "\n".join(parts)
    if isinstance(value, dict):
        for key in ("text", "content"):
            text = value.get(key)
            if isinstance(text, str):
                return text
            if isinstance(text, list):
                return _coerce_text(text)
    return None


def _fields(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[tuple[str, ...], tuple[str, ...]]:
    preset = PRESETS.get(args.preset or "")
    input_fields = (args.input_field,) if args.input_field else tuple((preset or {}).get("input_fields") or ())
    output_fields = (args.output_field,) if args.output_field else tuple((preset or {}).get("output_fields") or ())
    if not input_fields or not output_fields:
        parser.error("use --preset or pass both --input-field and --output-field")
    return tuple(str(field) for field in input_fields), tuple(str(field) for field in output_fields)


_MISSING = object()


if __name__ == "__main__":
    raise SystemExit(main())
