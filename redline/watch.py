from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import LogRecord, append_jsonl, iter_jsonl, read_jsonl_records, write_jsonl


def collect_log(
    source: str | Path,
    *,
    output: str | Path,
    input_field: str = "prompt",
    output_field: str = "response",
    append: bool = True,
    dedupe: bool = True,
) -> dict[str, Any]:
    records = read_jsonl_records(source, input_field, output_field)
    rows = [
        _observed_row(
            record,
            source,
            input_field=input_field,
            output_field=output_field,
        )
        for record in records
    ]
    skipped_duplicates = 0
    if dedupe:
        existing_keys = _existing_keys(output) if append else set()
        pending = []
        for row in rows:
            key = _row_key(row)
            if key and key in existing_keys:
                skipped_duplicates += 1
                continue
            if key:
                existing_keys.add(key)
            pending.append(row)
        rows = pending

    if append:
        append_jsonl(output, rows)
        mode = "appended"
    else:
        write_jsonl(output, rows)
        mode = "wrote"
    return {
        "source": str(source),
        "output": str(output),
        "records": len(rows),
        "records_seen": len(records),
        "skipped_duplicates": skipped_duplicates,
        "dedupe": dedupe,
        "mode": mode,
    }


def _observed_row(
    record: LogRecord,
    source: str | Path,
    *,
    input_field: str,
    output_field: str,
) -> dict[str, Any]:
    row = {
        "prompt": record.prompt,
        "response": record.response,
        "source": str(source),
        "source_line": record.line_number,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    row.setdefault(input_field, record.prompt)
    row.setdefault(output_field, record.response)
    return row


def _existing_keys(path: str | Path) -> set[tuple[str, str]]:
    target = Path(path)
    if not target.exists():
        return set()
    keys = set()
    for _, row in iter_jsonl(target):
        key = _row_key(row)
        if key:
            keys.add(key)
    return keys


def _row_key(row: dict[str, Any]) -> tuple[str, str] | None:
    source = row.get("source")
    source_line = row.get("source_line")
    if source is None or source_line is None:
        return None
    return str(source), str(source_line)
