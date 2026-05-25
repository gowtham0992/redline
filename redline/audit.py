from __future__ import annotations

import hashlib
import json
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
    row = {key: value for key, value in row.items() if value is not None}
    previous_hash = _last_entry_hash(path)
    if previous_hash:
        row["previous_hash"] = previous_hash
    row["entry_hash"] = audit_entry_hash(row)
    append_jsonl(path, [row])
    return row


def read_audit_events(path: str | Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    return [row for _, row in iter_jsonl(path)]


def verify_audit_events(
    events: list[dict[str, Any]],
    *,
    expected_last_hash: str | None = None,
    expected_entries: int | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    signed_entries = 0
    unsigned_entries = 0
    previous_hash: str | None = None

    if expected_entries is not None and expected_entries != len(events):
        errors.append(f"expected {expected_entries} entries, found {len(events)}")

    for index, row in enumerate(events, start=1):
        entry_hash = row.get("entry_hash")
        if not entry_hash:
            unsigned_entries += 1
            if previous_hash:
                errors.append(f"line {index}: unsigned entry breaks signed audit chain")
            continue
        if not isinstance(entry_hash, str):
            errors.append(f"line {index}: entry_hash must be a string")
            continue

        expected_hash = audit_entry_hash({key: value for key, value in row.items() if key != "entry_hash"})
        if entry_hash != expected_hash:
            errors.append(f"line {index}: entry_hash mismatch")

        row_previous = row.get("previous_hash")
        if row_previous != previous_hash:
            if previous_hash is None:
                errors.append(f"line {index}: previous_hash should be omitted on first signed entry")
            else:
                errors.append(f"line {index}: previous_hash does not match prior entry_hash")

        signed_entries += 1
        previous_hash = entry_hash

    if expected_last_hash is not None and previous_hash != expected_last_hash:
        errors.append("last_hash does not match expected hash")
    if expected_last_hash is None and expected_entries is None:
        warnings.append(
            "local hash chains cannot prove the log tail was not truncated; compare last_hash "
            "or entry count against an external checkpoint for stronger evidence"
        )

    return {
        "ok": not errors,
        "entries": len(events),
        "signed_entries": signed_entries,
        "unsigned_entries": unsigned_entries,
        "last_hash": previous_hash,
        "errors": errors,
        "warnings": warnings,
    }


def verify_audit_log(
    path: str | Path,
    *,
    expected_last_hash: str | None = None,
    expected_entries: int | None = None,
) -> dict[str, Any]:
    return verify_audit_events(
        read_audit_events(path),
        expected_last_hash=expected_last_hash,
        expected_entries=expected_entries,
    )


def audit_entry_hash(row: dict[str, Any]) -> str:
    encoded = _json_dumps_canonical(row).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def format_audit_verification(result: dict[str, Any]) -> str:
    status = "OK" if result.get("ok") else "FAILED"
    lines = [
        "redline audit verify",
        "",
        f"Status:   {status}",
        f"Entries:  {int(result.get('entries', 0))}",
        f"Signed:   {int(result.get('signed_entries', 0))}",
        f"Unsigned: {int(result.get('unsigned_entries', 0))}",
    ]
    last_hash = result.get("last_hash")
    if last_hash:
        lines.append(f"Last hash: {last_hash}")
        lines.append(
            "Checkpoint: redline audit --verify "
            f"--expect-last-hash {last_hash} --expect-entries {int(result.get('entries', 0))}"
        )
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        lines.extend(["", "Errors:"])
        for error in errors:
            lines.append(f"- {error}")
    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "Warnings:"])
        for warning in warnings:
            lines.append(f"- {warning}")
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


def _json_dumps_canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _last_entry_hash(path: str | Path) -> str | None:
    if not Path(path).exists():
        return None
    last_hash: str | None = None
    for _, row in iter_jsonl(path):
        value = row.get("entry_hash")
        if isinstance(value, str) and value:
            last_hash = value
        else:
            last_hash = None
    return last_hash


def _audit_summary(row: dict[str, Any]) -> str:
    parts: list[str] = []
    operator = row.get("operator")
    if operator:
        parts.append(f"operator={operator}")
    approver = row.get("approver")
    if approver:
        parts.append(f"approver={approver}")
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
