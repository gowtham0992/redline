from __future__ import annotations

from html import escape
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


def format_markdown_comparison(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# redline compare",
        "",
        "| Direction | Count |",
        "| --- | ---: |",
        f"| Worse | {summary.get('worse', 0)} |",
        f"| Better | {summary.get('better', 0)} |",
        f"| Resolved | {summary.get('resolved', 0)} |",
        f"| New | {summary.get('new', 0)} |",
        f"| Removed | {summary.get('removed', 0)} |",
        f"| Unchanged | {summary.get('unchanged', 0)} |",
        f"| Changed | {summary.get('changed', 0)} |",
        "",
    ]
    previous = str(result.get("previous") or "")
    current = str(result.get("current") or "")
    if previous or current:
        lines.append(f"Previous: {_inline_code(previous or '-')}")
        lines.append("")
        lines.append(f"Current: {_inline_code(current or '-')}")
        lines.append("")

    notable = [
        item
        for item in result.get("changes", [])
        if isinstance(item, dict) and item.get("direction") != "unchanged"
    ]
    if not notable:
        return "\n".join(lines).rstrip() + "\n"

    lines.append("## Notable Changes")
    lines.append("")
    for item in notable:
        direction = str(item.get("direction", "changed")).title()
        case_id = str(item.get("case_id", "unknown"))
        before = str(item.get("previous_status") or "-")
        after = str(item.get("current_status") or "-")
        reason = str(item.get("reason") or "")
        prompt = str(item.get("prompt") or "")
        lines.append(f"### `{case_id}`")
        lines.append("")
        lines.append(f"- Direction: **{direction}**")
        lines.append(f"- Status: `{before}` -> `{after}`")
        if reason:
            lines.append(f"- Reason: {reason}")
        if prompt:
            lines.append(f"- Prompt: {_inline_code(prompt)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_html_comparison(result: dict[str, Any]) -> str:
    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    changes = result.get("changes")
    if not isinstance(changes, list):
        changes = []
    previous = str(result.get("previous") or "")
    current = str(result.get("current") or "")
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>redline compare</title>",
            "<style>",
            _COMPARE_CSS,
            "</style>",
            "</head>",
            "<body>",
            '<main class="page">',
            "<header>",
            "<h1>redline compare</h1>",
            '<p class="lede">Trend comparison between two redline reports.</p>',
            "</header>",
            _html_compare_context(previous, current),
            _html_compare_summary(summary),
            _html_compare_changes(changes),
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


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


def _inline_code(value: str) -> str:
    compact = " ".join(value.split())
    fence = "`"
    while fence in compact:
        fence += "`"
    return f"{fence}{compact}{fence}"


def _html_compare_context(previous: str, current: str) -> str:
    if not previous and not current:
        return ""
    return (
        '<section class="panel context">'
        "<h2>Inputs</h2>"
        f"<p><strong>Previous:</strong> <code>{_h(previous or '-')}</code></p>"
        f"<p><strong>Current:</strong> <code>{_h(current or '-')}</code></p>"
        "</section>"
    )


def _html_compare_summary(summary: dict[str, Any]) -> str:
    cards = [
        ("Cases", "cases"),
        ("Worse", "worse"),
        ("Better", "better"),
        ("Resolved", "resolved"),
        ("New", "new"),
        ("Removed", "removed"),
        ("Changed", "changed"),
    ]
    cells = "\n".join(
        f'<div class="card {key}"><span>{_h(label)}</span><strong>{_count_value(summary, key)}</strong></div>'
        for label, key in cards
    )
    return (
        '<section class="panel">'
        "<h2>Summary</h2>"
        f'<div class="cards">{cells}</div>'
        "</section>"
    )


def _html_compare_changes(changes: list[Any]) -> str:
    notable = [
        item
        for item in changes
        if isinstance(item, dict) and item.get("direction") != "unchanged"
    ]
    if not notable:
        return '<section class="panel empty"><h2>Changes</h2><p>No notable changes.</p></section>'
    rows = []
    for item in notable:
        direction = str(item.get("direction") or "changed")
        case_id = str(item.get("case_id") or "unknown")
        before = str(item.get("previous_status") or "-")
        after = str(item.get("current_status") or "-")
        reason = str(item.get("reason") or "")
        prompt = str(item.get("prompt") or "")
        rows.append(
            "<tr>"
            f'<td><span class="badge {direction}">{_h(direction)}</span></td>'
            f"<td><strong>{_h(case_id)}</strong></td>"
            f"<td><code>{_h(before)}</code> -> <code>{_h(after)}</code></td>"
            f"<td>{_h(reason or '-')}</td>"
            f"<td>{_h(prompt or '-')}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Notable Changes</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Direction</th><th>Case</th><th>Status</th><th>Reason</th><th>Prompt</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _count_value(summary: dict[str, Any], key: str) -> int:
    try:
        return int(summary.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _h(value: str) -> str:
    return escape(value, quote=True)


_COMPARE_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2937;
  --muted: #5b6472;
  --line: #d7dce3;
  --danger: #b91c1c;
  --warn: #a16207;
  --ok: #166534;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.page {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
  padding: 36px 0 48px;
}
header { margin-bottom: 24px; }
h1, h2, p { margin: 0; }
h1 { font-size: 34px; line-height: 1.1; }
h2 { font-size: 18px; margin-bottom: 12px; }
.lede { color: var(--muted); margin-top: 8px; }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 18px;
}
.context p + p { margin-top: 8px; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
}
.card {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: #fbfcfd;
}
.card span { display: block; color: var(--muted); font-size: 12px; }
.card strong { display: block; font-size: 26px; margin-top: 4px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td {
  text-align: left;
  vertical-align: top;
  padding: 12px;
  border-top: 1px solid var(--line);
}
th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #f1f5f9;
  border-radius: 4px;
  padding: 1px 4px;
}
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  background: #f8fafc;
  border: 1px solid var(--line);
}
.worse, .new { color: var(--danger); border-color: #fecaca; background: #fff1f2; }
.changed, .removed { color: var(--warn); border-color: #fde68a; background: #fffbeb; }
.better, .resolved { color: var(--ok); border-color: #bbf7d0; background: #f0fdf4; }
.empty p { color: var(--muted); }
@media (max-width: 640px) {
  .page { width: min(100% - 24px, 1180px); padding-top: 24px; }
  h1 { font-size: 28px; }
  th, td { padding: 10px 8px; }
}
"""
