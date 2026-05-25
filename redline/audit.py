from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import append_jsonl, iter_jsonl


AUDIT_VERSION = "0.1"
DEFAULT_AUDIT_PATH = ".redline/audit.jsonl"

SUMMARY_KEYS = (
    "cases",
    "regression",
    "changed",
    "improved",
    "accepted",
    "ignored",
    "missing",
    "neutral",
)


def append_audit_event(path: str | Path | None, event: dict[str, Any]) -> dict[str, Any] | None:
    if path is None:
        return None
    row = {
        "version": AUDIT_VERSION,
        "timestamp": _utc_now(),
        "operator": current_operator(),
        **event,
    }
    append_jsonl(path, [row])
    return row


def read_audit_events(path: str | Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    return [row for _, row in iter_jsonl(path)]


def format_audit_events(events: list[dict[str, Any]], *, limit: int | None = None) -> str:
    rows = events[-limit:] if limit is not None and limit > 0 else events
    lines = ["redline audit", ""]
    if not rows:
        lines.append("No audit events.")
        return "\n".join(lines).rstrip() + "\n"

    for row in rows:
        timestamp = str(row.get("timestamp") or "-")
        event = str(row.get("event") or "unknown")
        lines.append(f"{timestamp}  {event:<24} {_audit_summary(row)}")
    return "\n".join(lines).rstrip() + "\n"


def file_reference(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    target = Path(path)
    reference: dict[str, Any] = {"path": str(path)}
    if target.is_file():
        reference["sha256"] = _sha256_file(target)
    return reference


def result_summary(result: dict[str, object]) -> dict[str, int]:
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return {}
    counts: dict[str, int] = {}
    for key in SUMMARY_KEYS:
        value = summary.get(key)
        if value is not None:
            counts[key] = int(value)
    return counts


def decision_summary(result: dict[str, object]) -> dict[str, str]:
    decision = result.get("decision")
    if not isinstance(decision, dict):
        return {}
    output: dict[str, str] = {}
    for key in ("confidence", "recommended_action"):
        value = decision.get(key)
        if value is not None:
            output[key] = str(value)
    return output


def current_operator() -> str:
    for key in ("REDLINE_OPERATOR", "GITHUB_ACTOR", "USER", "USERNAME"):
        value = os.environ.get(key)
        if value:
            return value
    return "unknown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_summary(row: dict[str, Any]) -> str:
    parts: list[str] = []
    case_id = row.get("case_id")
    if case_id:
        parts.append(f"case={case_id}")
    case_ids = row.get("case_ids")
    if isinstance(case_ids, list) and case_ids:
        parts.append(f"cases={len(case_ids)}")
    summary = row.get("summary")
    if isinstance(summary, dict):
        for key in ("cases", "regression", "changed", "missing", "neutral"):
            if key in summary:
                parts.append(f"{key}={summary[key]}")
    if "records" in row:
        parts.append(f"records={row['records']}")
    if "redactions" in row:
        parts.append(f"redactions={row['redactions']}")
    if "exit_code" in row:
        parts.append(f"exit={row['exit_code']}")
    return " ".join(parts)
