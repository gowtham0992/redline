from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import LogRecord, append_jsonl, read_jsonl_records, write_jsonl


def collect_log(
    source: str | Path,
    *,
    output: str | Path,
    input_field: str = "prompt",
    output_field: str = "response",
    append: bool = True,
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
