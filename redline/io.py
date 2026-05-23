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
        missing = [field for field in (input_field, output_field) if field not in obj]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{path}:{line_number} missing required field(s): {joined}")
        records.append(
            LogRecord(
                line_number=line_number,
                prompt=_stringify(obj[input_field]),
                response=_stringify(obj[output_field]),
                raw=obj,
            )
        )
    if not records:
        raise ValueError(f"{path} contains no JSONL records")
    return records


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
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} invalid JSON: {exc.msg}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{line_number} expected a JSON object")
            yield line_number, obj


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


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        handle.write(text)


def read_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"{path} not found") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} expected a JSON object")
    return data


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
