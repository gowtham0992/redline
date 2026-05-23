from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import iter_jsonl


SUMMARY_KEYS = (
    "cases",
    "regression",
    "changed",
    "improved",
    "accepted",
    "ignored",
    "missing",
    "neutral",
    "worse",
    "better",
    "resolved",
    "new",
    "removed",
    "unchanged",
)


def history_entry(
    report: dict[str, Any],
    *,
    report_path: str = "",
    label: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("report missing summary object")
    return {
        "version": "0.1",
        "timestamp": timestamp or _utc_now(),
        "label": label,
        "report": report_path,
        "summary": _summary_counts(summary),
    }


def read_history(path: str | Path) -> list[dict[str, Any]]:
    entries = []
    for line_number, row in iter_jsonl(path):
        summary = row.get("summary")
        if not isinstance(summary, dict):
            raise ValueError(f"{path}:{line_number} missing summary object")
        entries.append(row)
    return entries


def format_history(entries: list[dict[str, Any]], *, limit: int | None = None) -> str:
    rows = entries[-limit:] if limit is not None and limit > 0 else entries
    lines = ["redline history", ""]
    if not rows:
        lines.append("No history entries.")
        return "\n".join(lines).rstrip() + "\n"

    for entry in rows:
        timestamp = str(entry.get("timestamp") or "-")
        label = str(entry.get("label") or "-")
        report = str(entry.get("report") or "-")
        summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
        lines.append(f"{timestamp}  {label}  {report}  {_summary_text(summary)}")
    return "\n".join(lines).rstrip() + "\n"


def format_markdown_history(entries: list[dict[str, Any]], *, limit: int | None = None) -> str:
    rows = entries[-limit:] if limit is not None and limit > 0 else entries
    lines = ["# redline history", ""]
    if not rows:
        lines.append("No history entries.")
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "| Timestamp | Label | Report | Summary |",
            "| --- | --- | --- | --- |",
        ]
    )
    for entry in rows:
        summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
        cells = [
            _markdown_cell(entry.get("timestamp") or "-"),
            _markdown_cell(entry.get("label") or "-"),
            _markdown_cell(entry.get("report") or "-"),
            _markdown_cell(_summary_text(summary) or "-"),
        ]
        lines.append(f"| {' | '.join(cells)} |")
    return "\n".join(lines).rstrip() + "\n"


def _summary_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {}
    for key in SUMMARY_KEYS:
        if key in summary:
            counts[key] = _int_count(summary[key], key)
    for key, value in summary.items():
        if key not in counts:
            counts[str(key)] = _int_count(value, str(key))
    return counts


def _summary_text(summary: dict[str, Any]) -> str:
    parts = []
    for key in SUMMARY_KEYS:
        if key in summary:
            parts.append(f"{key}={int(summary.get(key) or 0)}")
    for key in sorted(str(item) for item in summary if str(item) not in SUMMARY_KEYS):
        parts.append(f"{key}={int(summary.get(key) or 0)}")
    return " ".join(parts)


def _int_count(value: Any, key: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"summary.{key} must be an integer") from exc


def _markdown_cell(value: Any) -> str:
    text = str(value).replace("\n", " ").strip()
    if not text:
        return "-"
    return text.replace("|", r"\|")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
