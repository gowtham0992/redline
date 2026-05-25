from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .diff import TRUST_SCOPE
from .history import history_trend, read_history
from .io import read_json


def build_dashboard(
    *,
    reports_dir: str | Path = ".redline/reports",
    history_path: str | Path = ".redline/history.jsonl",
    limit: int = 20,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("dashboard --limit must be 0 or greater")
    reports, report_errors = _collect_reports(Path(reports_dir), limit=limit)
    history, history_errors = _collect_history(Path(history_path), limit=limit)
    trend = history_trend(list(reversed(history))) if history else history_trend([])
    return {
        "version": "0.1",
        "reports_dir": str(reports_dir),
        "history_path": str(history_path),
        "reports": reports,
        "history": history,
        "trend": trend,
        "owners": _dashboard_owner_review(reports),
        "errors": report_errors + history_errors,
        "scope": TRUST_SCOPE,
    }


def format_dashboard_html(
    dashboard: dict[str, Any],
    *,
    title: str = "redline dashboard",
    output_path: str | Path | None = None,
) -> str:
    reports = dashboard.get("reports")
    if not isinstance(reports, list):
        reports = []
    history = dashboard.get("history")
    if not isinstance(history, list):
        history = []
    errors = dashboard.get("errors")
    if not isinstance(errors, list):
        errors = []
    owners = dashboard.get("owners")
    if not isinstance(owners, list):
        owners = _dashboard_owner_review([report for report in reports if isinstance(report, dict)])
    raw_trend = dashboard.get("trend")
    trend = raw_trend if isinstance(raw_trend, dict) else history_trend(list(reversed(history)))
    latest = reports[0] if reports and isinstance(reports[0], dict) else {}
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_h(title)}</title>",
            "<style>",
            _DASHBOARD_CSS,
            "</style>",
            "</head>",
            "<body>",
            '<main class="page">',
            "<header>",
            f"<h1>{_h(title)}</h1>",
            '<p class="lede">Local prompt regression review center.</p>',
            "</header>",
            _overview(latest, len(reports), len(history)),
            _trend_panel(trend),
            _scope(str(dashboard.get("scope") or TRUST_SCOPE)),
            _owners_panel(owners),
            _errors(errors),
            _reports_table(reports, output_path=output_path),
            _history_table(history, output_path=output_path),
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _collect_reports(reports_dir: Path, *, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not reports_dir.exists():
        return [], []
    report_paths = sorted(
        (path for path in reports_dir.glob("*.json") if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    if limit:
        report_paths = report_paths[:limit]

    reports = []
    errors = []
    for path in report_paths:
        try:
            report = read_json(path)
        except ValueError as exc:
            errors.append({"path": str(path), "message": str(exc)})
            continue
        summary = report.get("summary")
        if not isinstance(summary, dict):
            errors.append({"path": str(path), "message": "missing summary object"})
            continue
        reports.append(
            {
                "path": str(path),
                "name": path.name,
                "kind": _report_kind(report, path),
                "summary": _summary_counts(summary),
                "decision": report.get("decision") if isinstance(report.get("decision"), dict) else {},
                "owners": _report_owner_review(report.get("diffs")),
                "html_path": _existing_sibling(path, ".html"),
                "markdown_path": _existing_sibling(path, ".md"),
            }
        )
    return reports, errors


def _collect_history(history_path: Path, *, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not history_path.exists():
        return [], []
    try:
        entries = read_history(history_path)
    except ValueError as exc:
        return [], [{"path": str(history_path), "message": str(exc)}]
    if limit:
        entries = entries[-limit:]
    return list(reversed(entries)), []


def _report_kind(report: dict[str, Any], path: Path) -> str:
    if isinstance(report.get("changes"), list):
        return "compare"
    if isinstance(report.get("replay"), dict):
        return "eval"
    if isinstance(report.get("diffs"), list):
        return "diff"
    return path.stem


def _existing_sibling(path: Path, suffix: str) -> str:
    sibling = path.with_suffix(suffix)
    return str(sibling) if sibling.exists() else ""


def _summary_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {}
    for key, value in summary.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return counts


def _report_owner_review(diffs: Any) -> list[dict[str, int | str]]:
    if not isinstance(diffs, list):
        return []
    rows: dict[str, dict[str, int | str]] = {}
    for item in diffs:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("owner") or "").strip()
        if not owner:
            continue
        status = str(item.get("status") or "")
        row = rows.setdefault(
            owner,
            {
                "owner": owner,
                "blocking": 0,
                "changed": 0,
                "total": 0,
            },
        )
        row["total"] = int(row["total"]) + 1
        if status in {"regression", "missing"}:
            row["blocking"] = int(row["blocking"]) + 1
        elif status == "changed":
            row["changed"] = int(row["changed"]) + 1
    return _sort_owner_rows(rows.values())


def _dashboard_owner_review(reports: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    rows: dict[str, dict[str, int | str]] = {}
    for report in reports:
        owner_rows = report.get("owners")
        if not isinstance(owner_rows, list):
            continue
        for owner_row in owner_rows:
            if not isinstance(owner_row, dict):
                continue
            owner = str(owner_row.get("owner") or "").strip()
            if not owner:
                continue
            row = rows.setdefault(owner, {"owner": owner, "blocking": 0, "changed": 0, "total": 0})
            row["blocking"] = int(row["blocking"]) + int(owner_row.get("blocking") or 0)
            row["changed"] = int(row["changed"]) + int(owner_row.get("changed") or 0)
            row["total"] = int(row["total"]) + int(owner_row.get("total") or 0)
    return _sort_owner_rows(rows.values())


def _sort_owner_rows(rows: Any) -> list[dict[str, int | str]]:
    return sorted(
        rows,
        key=lambda row: (
            -int(row["blocking"]),
            -int(row["changed"]),
            -int(row["total"]),
            str(row["owner"]).lower(),
        ),
    )


def _overview(latest: dict[str, Any], report_count: int, history_count: int) -> str:
    raw_summary = latest.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    cards = [
        ("Reports", report_count),
        ("History", history_count),
        ("Regressions", summary.get("regression", 0)),
        ("Changed", summary.get("changed", 0)),
        ("Missing", summary.get("missing", 0)),
    ]
    cells = "\n".join(
        f'<div class="card"><span>{_h(label)}</span><strong>{int(value or 0)}</strong></div>'
        for label, value in cards
    )
    latest_name = _h(str(latest.get("name") or "No reports yet"))
    latest_kind = _h(str(latest.get("kind") or ""))
    return (
        '<section class="panel">'
        '<div class="section-title">'
        "<div>"
        "<h2>Overview</h2>"
        f'<p>Latest report: <strong>{latest_name}</strong>{f" ({latest_kind})" if latest_kind else ""}</p>'
        "</div>"
        "</div>"
        f'<div class="cards">{cells}</div>'
        "</section>"
    )


def _owners_panel(owners: list[Any]) -> str:
    if not owners:
        return ""
    rows = []
    for item in owners:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_h(str(item.get('owner') or '-'))}</td>"
            f"<td>{int(item.get('blocking') or 0)}</td>"
            f"<td>{int(item.get('changed') or 0)}</td>"
            f"<td>{int(item.get('total') or 0)}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<section class="panel owner-review">'
        "<h2>Owner Review</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Owner</th><th>Blocking</th><th>Changed</th><th>Total</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _scope(scope: str) -> str:
    return (
        '<section class="notice">'
        "<h2>Trust Scope</h2>"
        f"<p>{_h(scope)}</p>"
        "</section>"
    )


def _trend_panel(trend: dict[str, Any]) -> str:
    direction = str(trend.get("direction") or "unknown").replace("_", " ").title()
    summary = str(trend.get("summary") or "-")
    recommendation = str(trend.get("recommendation") or "-")
    return (
        f'<section class="notice trend {_trend_class(direction)}">'
        "<h2>Trend</h2>"
        f"<p><strong>{_h(direction)}</strong>: {_h(summary)}</p>"
        f"<p>{_h(recommendation)}</p>"
        "</section>"
    )


def _trend_class(direction: str) -> str:
    normalized = direction.lower().replace(" ", "-")
    if normalized in {"worse", "better", "flat", "baseline", "more-changed", "less-changed"}:
        return normalized
    return "unknown"


def _errors(errors: list[Any]) -> str:
    rows = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        path = str(error.get("path") or "-")
        message = str(error.get("message") or "unknown error")
        rows.append(f"<li><code>{_h(path)}</code>: {_h(message)}</li>")
    if not rows:
        return ""
    return (
        '<section class="panel warning">'
        "<h2>Skipped Files</h2>"
        "<p>Some local files could not be rendered as redline reports.</p>"
        f"<ul>{''.join(rows)}</ul>"
        "</section>"
    )


def _reports_table(reports: list[Any], *, output_path: str | Path | None) -> str:
    if not reports:
        return _empty_section("Reports", "No report JSON files found yet.")
    rows = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        raw_summary = report.get("summary")
        summary = raw_summary if isinstance(raw_summary, dict) else {}
        raw_decision = report.get("decision")
        decision = raw_decision if isinstance(raw_decision, dict) else {}
        links = _links(
            [
                ("HTML", str(report.get("html_path") or "")),
                ("Markdown", str(report.get("markdown_path") or "")),
                ("JSON", str(report.get("path") or "")),
            ],
            output_path=output_path,
        )
        rows.append(
            "<tr>"
            f"<td><strong>{_h(str(report.get('name') or '-'))}</strong><span>{_h(str(report.get('kind') or '-'))}</span></td>"
            f"<td>{_summary_pills(summary)}</td>"
            f"<td>{_h(str(decision.get('recommended_action') or '-'))}</td>"
            f"<td>{links}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Reports</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Report</th><th>Summary</th><th>Decision</th><th>Links</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _history_table(history: list[Any], *, output_path: str | Path | None) -> str:
    if not history:
        return _empty_section("History", "No history entries found yet.")
    rows = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        raw_summary = entry.get("summary")
        summary = raw_summary if isinstance(raw_summary, dict) else {}
        report = str(entry.get("report") or "")
        rows.append(
            "<tr>"
            f"<td>{_h(str(entry.get('timestamp') or '-'))}</td>"
            f"<td>{_h(str(entry.get('label') or '-'))}</td>"
            f"<td>{_summary_pills(summary)}</td>"
            f"<td>{_links([('Report', report)], output_path=output_path)}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>History</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Time</th><th>Label</th><th>Summary</th><th>Report</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _empty_section(title: str, message: str) -> str:
    return (
        '<section class="panel empty">'
        f"<h2>{_h(title)}</h2>"
        f"<p>{_h(message)}</p>"
        "</section>"
    )


def _summary_pills(summary: dict[str, Any]) -> str:
    keys = ("cases", "regression", "changed", "missing", "neutral", "worse", "better", "resolved")
    pills = []
    for key in keys:
        if key in summary:
            pills.append(f'<span class="pill {key}">{_h(key)} {int(summary.get(key) or 0)}</span>')
    return "".join(pills) if pills else "-"


def _links(items: list[tuple[str, str]], *, output_path: str | Path | None) -> str:
    links = []
    for label, path in items:
        if not path:
            continue
        href = _href(path, output_path)
        links.append(f'<a href="{_h(href)}">{_h(label)}</a>')
    return " ".join(links) if links else "-"


def _href(path: str, output_path: str | Path | None) -> str:
    target = Path(path)
    if output_path is not None:
        try:
            value = os.path.relpath(target, Path(output_path).parent)
        except ValueError:
            value = str(target)
    else:
        value = str(target)
    return quote(value.replace(os.sep, "/"), safe="/:#?&=%")


def _h(value: str) -> str:
    return escape(value, quote=True)


_DASHBOARD_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2937;
  --muted: #5b6472;
  --line: #d7dce3;
  --accent: #0f766e;
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
.panel, .notice {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 18px;
}
.notice { border-left: 4px solid var(--accent); }
.warning { border-left: 4px solid var(--warn); }
.warning p { color: var(--muted); margin-bottom: 8px; }
.warning ul { margin: 0; padding-left: 20px; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.card {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: #fbfcfd;
}
.card span, td span { display: block; color: var(--muted); font-size: 12px; }
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
a { color: var(--accent); font-weight: 600; margin-right: 10px; }
.pill {
  display: inline-block;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
  margin: 0 6px 6px 0;
  background: #f8fafc;
  font-size: 12px;
}
.regression, .missing, .worse { color: var(--danger); border-color: #fecaca; background: #fff1f2; }
.changed { color: var(--warn); border-color: #fde68a; background: #fffbeb; }
.better, .resolved { color: var(--ok); border-color: #bbf7d0; background: #f0fdf4; }
.empty p { color: var(--muted); }
@media (max-width: 640px) {
  .page { width: min(100% - 24px, 1180px); padding-top: 24px; }
  h1 { font-size: 28px; }
  th, td { padding: 10px 8px; }
}
"""
