from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


JUDGMENT_STATUSES = ("expected", "ignored", "regression")


def mark_suite_case(
    suite: dict[str, Any],
    case_id: str,
    *,
    status: str,
    note: str = "",
) -> None:
    if status not in JUDGMENT_STATUSES:
        allowed = ", ".join(JUDGMENT_STATUSES)
        raise ValueError(f"judgment status must be one of: {allowed}")

    case_ids = {str(case["id"]) for case in suite.get("cases", [])}
    if case_id not in case_ids:
        raise ValueError(f"case not found in suite: {case_id}")

    judgments = suite.setdefault("judgments", {})
    judgments[case_id] = {
        "status": status,
        "note": note,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def clear_suite_case_judgment(suite: dict[str, Any], case_id: str) -> bool:
    judgments = suite.get("judgments")
    if not isinstance(judgments, dict):
        return False
    return judgments.pop(case_id, None) is not None
