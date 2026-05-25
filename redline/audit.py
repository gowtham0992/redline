from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import append_jsonl


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
