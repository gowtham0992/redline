#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert exported app logs into redline prompt/response JSONL."
    )
    parser.add_argument("path", nargs="?", help="input JSONL file; defaults to stdin")
    parser.add_argument("--input-field", required=True, help="field path containing prompt text")
    parser.add_argument("--output-field", required=True, help="field path containing response text")
    parser.add_argument("--out", help="output JSONL file; defaults to stdout")
    args = parser.parse_args()

    rows = list(_convert_rows(_read_rows(args.path), args.input_field, args.output_field))
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
    input_field: str,
    output_field: str,
) -> Iterable[dict[str, Any]]:
    for line_number, row in rows:
        prompt = _get_field(row, input_field)
        response = _get_field(row, output_field)
        missing = []
        if prompt is _MISSING:
            missing.append(input_field)
        if response is _MISSING:
            missing.append(output_field)
        if missing:
            raise SystemExit(f"line {line_number} missing field(s): {', '.join(missing)}")
        yield {
            "prompt": _stringify(prompt),
            "response": _stringify(response),
            "source_line": line_number,
        }


def _write_rows(rows: Iterable[dict[str, Any]], handle: TextIO) -> None:
    for row in rows:
        json.dump(row, handle, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def _get_field(row: dict[str, Any], path: str) -> Any:
    if path in row:
        return row[path]
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


_MISSING = object()


if __name__ == "__main__":
    raise SystemExit(main())
