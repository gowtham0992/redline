from __future__ import annotations

from typing import Any


FAIL_STATUSES = (
    "regression",
    "missing",
    "changed",
    "improved",
    "accepted",
    "ignored",
    "neutral",
)
DEFAULT_FAIL_ON = ("regression", "missing")


def parse_fail_on(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_FAIL_ON

    raw = value.strip().lower()
    if not raw:
        return DEFAULT_FAIL_ON
    if raw == "none":
        return ()

    statuses = tuple(part.strip() for part in raw.split(",") if part.strip())
    invalid = [status for status in statuses if status not in FAIL_STATUSES]
    if invalid:
        allowed = ", ".join(("none",) + FAIL_STATUSES)
        raise ValueError(f"invalid --fail-on status: {', '.join(invalid)}; allowed: {allowed}")
    return statuses


def should_fail(result: dict[str, Any], fail_on: tuple[str, ...]) -> bool:
    summary = result.get("summary", {})
    if not isinstance(summary, dict):
        return False
    return any(int(summary.get(status, 0)) > 0 for status in fail_on)
