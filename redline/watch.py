from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from .features import behavior_signature
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


def watch_stats(
    path: str | Path,
    *,
    input_field: str = "prompt",
    output_field: str = "response",
) -> dict[str, Any]:
    records = read_jsonl_records(path, input_field, output_field)
    observed_at = sorted(
        str(record.raw["observed_at"])
        for record in records
        if isinstance(record.raw.get("observed_at"), str)
    )
    signatures = {
        behavior_signature(record.prompt, record.response)
        for record in records
    }
    sources = {
        str(record.raw.get("source"))
        for record in records
        if record.raw.get("source")
    }
    return {
        "log": str(path),
        "records": len(records),
        "sources": len(sources),
        "behavior_patterns": len(signatures),
        "first_observed_at": observed_at[0] if observed_at else None,
        "last_observed_at": observed_at[-1] if observed_at else None,
    }


def format_watch_stats(stats: dict[str, Any]) -> str:
    lines = [
        "redline watch",
        "",
        f"Log:               {stats['log']}",
        f"Records:           {stats['records']}",
        f"Sources:           {stats['sources']}",
        f"Behavior patterns: {stats['behavior_patterns']}",
    ]
    if stats["first_observed_at"] or stats["last_observed_at"]:
        lines.append(f"First observed:    {stats['first_observed_at'] or '<unknown>'}")
        lines.append(f"Last observed:     {stats['last_observed_at'] or '<unknown>'}")
    return "\n".join(lines) + "\n"


def follow_log(
    source: str | Path,
    *,
    output: str | Path,
    input_field: str = "prompt",
    output_field: str = "response",
    poll_interval: float = 1.0,
    max_records: int | None = None,
    idle_timeout: float | None = None,
    dedupe: bool = True,
    replace: bool = False,
) -> dict[str, Any]:
    if poll_interval < 0:
        raise ValueError("poll_interval must be at least 0")
    if max_records is not None and max_records < 1:
        raise ValueError("max_records must be at least 1")
    if idle_timeout is not None and idle_timeout < 0:
        raise ValueError("idle_timeout must be at least 0")

    collected = 0
    seen = 0
    skipped = 0
    iterations = 0
    idle_started: float | None = None
    append = not replace

    while True:
        result = collect_log(
            source,
            output=output,
            input_field=input_field,
            output_field=output_field,
            append=append,
            dedupe=dedupe,
        )
        append = True
        iterations += 1
        collected += int(result["records"])
        seen += int(result["records_seen"])
        skipped += int(result["skipped_duplicates"])

        if max_records is not None and collected >= max_records:
            break

        if result["records"]:
            idle_started = None
        elif idle_timeout is not None:
            if idle_started is None:
                idle_started = monotonic()
            if monotonic() - idle_started >= idle_timeout:
                break

        sleep(poll_interval)

    return {
        "source": str(source),
        "output": str(output),
        "records": collected,
        "records_seen": seen,
        "skipped_duplicates": skipped,
        "dedupe": dedupe,
        "mode": "followed",
        "iterations": iterations,
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
