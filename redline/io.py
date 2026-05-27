from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class LogRecord:
    line_number: int
    prompt: str
    response: str
    raw: dict[str, Any]


def read_jsonl_records(path: str | Path, input_field: str, output_field: str) -> list[LogRecord]:
    records: list[LogRecord] = []
    for line_number, obj in iter_jsonl(path):
        missing = [field for field in (input_field, output_field) if _get_field(obj, field) is _MISSING]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{path}:{line_number} missing required field(s): {joined}")
        prompt = _get_field(obj, input_field)
        response = _get_field(obj, output_field)
        records.append(
            LogRecord(
                line_number=line_number,
                prompt=_stringify(prompt),
                response=_stringify(response),
                raw=obj,
            )
        )
    if not records:
        raise ValueError(f"{path} contains no JSONL records")
    return records


def read_jsonl_records_from_offset(
    path: str | Path,
    input_field: str,
    output_field: str,
    *,
    offset: int = 0,
    start_line_number: int = 1,
    max_records: int | None = None,
) -> tuple[list[LogRecord], int, int]:
    records: list[LogRecord] = []
    target = Path(path)
    try:
        handle = target.open("r", encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"{path} not found") from exc
    with handle:
        handle.seek(offset)
        line_number = start_line_number
        while True:
            line = handle.readline()
            if line == "":
                break
            stripped = line.strip()
            if stripped:
                obj = _parse_jsonl_object(path, line_number, stripped)
                missing = [field for field in (input_field, output_field) if _get_field(obj, field) is _MISSING]
                if missing:
                    joined = ", ".join(missing)
                    raise ValueError(f"{path}:{line_number} missing required field(s): {joined}")
                prompt = _get_field(obj, input_field)
                response = _get_field(obj, output_field)
                records.append(
                    LogRecord(
                        line_number=line_number,
                        prompt=_stringify(prompt),
                        response=_stringify(response),
                        raw=obj,
                    )
                )
                if max_records is not None and len(records) >= max_records:
                    line_number += 1
                    break
            line_number += 1
        return records, handle.tell(), line_number


def iter_jsonl(path: str | Path) -> Iterable[tuple[int, dict[str, Any]]]:
    target = Path(path)
    try:
        handle = target.open("r", encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"{path} not found") from exc
    with handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            yield line_number, _parse_jsonl_object(path, line_number, stripped)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            json.dump(row, handle, sort_keys=True, ensure_ascii=False)
            handle.write("\n")


def append_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for row in rows:
            json.dump(row, handle, sort_keys=True, ensure_ascii=False)
            handle.write("\n")


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        handle.write(text)


def append_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(text)


def read_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"{path} not found") from exc
    except json.JSONDecodeError as exc:
        if exc.msg == "Extra data":
            raise ValueError(
                f"{path} expected one JSON object, but found extra data. "
                "If this is a JSONL prompt log, run "
                f"`redline suite {path} --out redline-suite.json` first."
            ) from exc
        raise ValueError(f"{path} invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} expected a JSON object")
    return data


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


_MISSING = object()


def _parse_jsonl_object(path: str | Path, line_number: int, stripped: str) -> dict[str, Any]:
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{line_number} invalid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"{path}:{line_number} expected a JSON object")
    return obj


def _get_field(obj: dict[str, Any], field: str) -> Any:
    if field in obj:
        return obj[field]
    current: Any = obj
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current
