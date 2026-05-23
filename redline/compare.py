from __future__ import annotations

from typing import Any


_ACTIONABLE = {"regression", "missing", "changed"}
_SEVERITY = {
    "ignored": 0,
    "accepted": 0,
    "neutral": 0,
    "improved": 1,
    "changed": 2,
    "regression": 3,
    "missing": 3,
}
COMPARE_DIRECTIONS = {
    "worse",
    "better",
    "new",
    "resolved",
    "removed",
    "unchanged",
    "changed",
}


def compare_reports(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    previous_path: str = "",
    current_path: str = "",
) -> dict[str, Any]:
    previous_diffs = _diff_index(previous)
    current_diffs = _diff_index(current)
    case_ids = sorted(set(previous_diffs) | set(current_diffs))
    changes = []

    for case_id in case_ids:
        before = previous_diffs.get(case_id)
        after = current_diffs.get(case_id)
        if before is None and after is not None:
            direction = "new"
        elif before is not None and after is None:
            direction = "removed"
        elif before is None or after is None:
            direction = "changed"
        else:
            direction = _direction(str(before.get("status", "")), str(after.get("status", "")))

        changes.append(
            {
                "case_id": case_id,
                "direction": direction,
                "previous_status": _status(before),
                "current_status": _status(after),
                "prompt": _prompt(after, before),
                "reason": _reason(after, before),
            }
        )

    summary = {
        "cases": len(changes),
        "worse": _count(changes, "worse"),
        "better": _count(changes, "better"),
        "new": _count(changes, "new"),
        "resolved": _count(changes, "resolved"),
        "removed": _count(changes, "removed"),
        "unchanged": _count(changes, "unchanged"),
        "changed": _count(changes, "changed"),
    }
    return {
        "version": "0.1",
        "previous": previous_path,
        "current": current_path,
        "summary": summary,
        "changes": changes,
    }


def format_report_comparison(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "redline compare",
        "",
    ]
    previous = str(result.get("previous") or "")
    current = str(result.get("current") or "")
    if previous:
        lines.append(f"Previous: {previous}")
    if current:
        lines.append(f"Current:  {current}")
    if previous or current:
        lines.append("")
    lines.extend(
        [
            f"Cases:     {summary['cases']}",
            f"Worse:     {summary['worse']}",
            f"Better:    {summary['better']}",
            f"Resolved:  {summary['resolved']}",
            f"New:       {summary['new']}",
            f"Removed:   {summary['removed']}",
            f"Unchanged: {summary['unchanged']}",
            f"Changed:   {summary['changed']}",
        ]
    )

    notable = [
        item
        for item in result.get("changes", [])
        if isinstance(item, dict) and item.get("direction") != "unchanged"
    ]
    if not notable:
        return "\n".join(lines).rstrip() + "\n"

    lines.append("")
    for item in notable:
        direction = str(item.get("direction", "changed")).upper()
        case_id = str(item.get("case_id", "unknown"))
        before = str(item.get("previous_status") or "-")
        after = str(item.get("current_status") or "-")
        reason = _preview(str(item.get("reason") or ""), limit=96)
        prompt = _preview(str(item.get("prompt") or ""), limit=64)
        lines.append(f"{direction:<8} {case_id}: {before} -> {after}: {reason} | {prompt}")

    return "\n".join(lines).rstrip() + "\n"


def parse_compare_fail_on(value: str | None) -> set[str]:
    if value is None or value == "":
        return set()
    if value.strip().lower() == "none":
        return set()
    directions = {item.strip().lower() for item in value.split(",") if item.strip()}
    unknown = sorted(directions - COMPARE_DIRECTIONS)
    if unknown:
        allowed = ", ".join(sorted(COMPARE_DIRECTIONS | {"none"}))
        raise ValueError(f"compare --fail-on must use: {allowed}")
    return directions


def should_fail_comparison(result: dict[str, Any], fail_on: set[str]) -> bool:
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return False
    return any(int(summary.get(direction, 0) or 0) > 0 for direction in fail_on)


def _diff_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diffs = report.get("diffs")
    if not isinstance(diffs, list):
        return {}
    indexed = {}
    for item in diffs:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if isinstance(case_id, str) and case_id:
            indexed[case_id] = item
    return indexed


def _direction(previous_status: str, current_status: str) -> str:
    if previous_status == current_status:
        return "unchanged"
    if previous_status in _ACTIONABLE and current_status not in _ACTIONABLE:
        return "resolved"
    previous_severity = _SEVERITY.get(previous_status, 1)
    current_severity = _SEVERITY.get(current_status, 1)
    if current_severity > previous_severity:
        return "worse"
    if current_severity < previous_severity:
        return "better"
    return "changed"


def _status(item: dict[str, Any] | None) -> str | None:
    if item is None:
        return None
    return str(item.get("status") or "unknown")


def _prompt(*items: dict[str, Any] | None) -> str:
    for item in items:
        if item is not None and item.get("prompt"):
            return str(item["prompt"])
    return ""


def _reason(*items: dict[str, Any] | None) -> str:
    for item in items:
        if item is None:
            continue
        reasons = item.get("reasons")
        if isinstance(reasons, list) and reasons:
            return str(reasons[0])
    return ""


def _count(changes: list[dict[str, Any]], direction: str) -> int:
    return sum(1 for change in changes if change["direction"] == direction)


def _preview(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."
