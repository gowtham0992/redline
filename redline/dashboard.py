from __future__ import annotations

import os
from html import escape
from pathlib import Path
from shlex import quote as shell_quote
from typing import Any
from urllib.parse import quote

from .diff import TRUST_SCOPE
from .history import history_trend, read_history
from .io import read_json


def build_dashboard(
    *,
    reports_dir: str | Path = ".redline/reports",
    history_path: str | Path = ".redline/history.jsonl",
    checkpoint_path: str | Path = ".redline/audit-checkpoint.json",
    limit: int = 20,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("dashboard --limit must be 0 or greater")
    reports, report_errors = _collect_reports(Path(reports_dir), limit=limit)
    benchmarks = _collect_benchmarks(Path(reports_dir), limit=limit)
    history, history_errors = _collect_history(Path(history_path), limit=limit)
    checkpoint, checkpoint_errors = _collect_checkpoint(Path(checkpoint_path))
    trend = history_trend(list(reversed(history))) if history else history_trend([])
    notices = _dashboard_notices(reports, benchmarks)
    return {
        "version": "0.1",
        "reports_dir": str(reports_dir),
        "history_path": str(history_path),
        "checkpoint_path": str(checkpoint_path),
        "reports": reports,
        "benchmarks": benchmarks,
        "history": history,
        "checkpoint": checkpoint,
        "trend": trend,
        "notices": notices,
        "owners": _dashboard_owner_review(reports),
        "trust": _dashboard_trust_summary(reports),
        "errors": report_errors + history_errors + checkpoint_errors,
        "scope": TRUST_SCOPE,
    }


def format_dashboard_html(
    dashboard: dict[str, Any],
    *,
    title: str = "redline dashboard",
    output_path: str | Path | None = None,
    style: str = "classic",
) -> str:
    reports = dashboard.get("reports")
    if not isinstance(reports, list):
        reports = []
    history = dashboard.get("history")
    if not isinstance(history, list):
        history = []
    benchmarks = dashboard.get("benchmarks")
    if not isinstance(benchmarks, list):
        benchmarks = []
    errors = dashboard.get("errors")
    if not isinstance(errors, list):
        errors = []
    notices = dashboard.get("notices")
    if not isinstance(notices, list):
        notices = []
    owners = dashboard.get("owners")
    if not isinstance(owners, list):
        owners = _dashboard_owner_review([report for report in reports if isinstance(report, dict)])
    trust = dashboard.get("trust")
    if not isinstance(trust, dict):
        trust = _dashboard_trust_summary([report for report in reports if isinstance(report, dict)])
    checkpoint = dashboard.get("checkpoint")
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    raw_trend = dashboard.get("trend")
    trend = raw_trend if isinstance(raw_trend, dict) else history_trend(list(reversed(history)))
    latest = reports[0] if reports and isinstance(reports[0], dict) else {}
    if style == "app":
        return _format_dashboard_app_html(
            dashboard,
            title=title,
            output_path=output_path,
            reports=reports,
            history=history,
            benchmarks=benchmarks,
            errors=errors,
            notices=notices,
            owners=owners,
            trust=trust,
            checkpoint=checkpoint,
            trend=trend,
            latest=latest,
        )
    if style != "classic":
        raise ValueError(f"unknown dashboard style: {style}")
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
            _overview(latest, len(reports), len(benchmarks), len(history)),
            _evidence_panel(latest, benchmarks, history, checkpoint, output_path=output_path),
            _notices(notices),
            _ship_panel(latest),
            _trend_panel(trend),
            _benchmark_panel(benchmarks, output_path=output_path),
            _scope(str(dashboard.get("scope") or TRUST_SCOPE)),
            _checkpoint_panel(checkpoint),
            _trust_panel(trust),
            _owners_panel(owners),
            _errors(errors),
            _prompt_groups_panel(latest.get("prompt_groups") if isinstance(latest, dict) else []),
            _prompt_evals_panel(latest.get("prompt_evals") if isinstance(latest, dict) else []),
            _review_queue_panel(latest.get("review_cases") if isinstance(latest, dict) else []),
            _reports_table(reports, output_path=output_path),
            _history_table(history, output_path=output_path),
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _format_dashboard_app_html(
    dashboard: dict[str, Any],
    *,
    title: str,
    output_path: str | Path | None,
    reports: list[Any],
    history: list[Any],
    benchmarks: list[Any],
    errors: list[Any],
    notices: list[Any],
    owners: list[Any],
    trust: dict[str, Any],
    checkpoint: dict[str, Any],
    trend: dict[str, Any],
    latest: dict[str, Any],
) -> str:
    summary = _app_dict(latest.get("summary"))
    suite_summary = _app_dict(latest.get("suite_summary"))
    decision = _app_dict(latest.get("decision"))
    active = _blocking_count(summary)
    changed = _changed_count(summary)
    status_class = "red" if active else "amber" if changed else "green"
    status_text = "Regressions" if active else "Review" if changed else "Clear"
    review_cases = _app_list(latest.get("review_cases"))
    warnings = _app_list(latest.get("warnings"))
    if notices:
        warnings = [*(str(item.get("message") or "") for item in notices if isinstance(item, dict)), *warnings]
    alert_count = active + len([warning for warning in warnings if str(warning).strip()])
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_h(title)}</title>",
            "<style>",
            _APP_DASHBOARD_CSS,
            "</style>",
            "</head>",
            "<body>",
            '<div class="app" data-redline-dashboard="app">',
            _app_sidebar(active=active, changed=changed, alerts=alert_count),
            '<main class="main">',
            _app_topbar(title=title, status_class=status_class, status_text=status_text, reports=len(reports)),
            '<div class="pane">',
            _app_workflow_screen(
                dashboard=dashboard,
                latest=latest,
                reports=reports,
                benchmarks=benchmarks,
                history=history,
                checkpoint=checkpoint,
                review_cases=review_cases,
            ),
            _app_dashboard_screen(
                summary=summary,
                suite_summary=suite_summary,
                decision=decision,
                reports=reports,
                benchmarks=benchmarks,
                history=history,
                review_cases=review_cases,
                warnings=[warning for warning in warnings if str(warning).strip()],
                status_class=status_class,
                output_path=output_path,
            ),
            _app_regressions_screen(review_cases=review_cases, summary=summary, decision=decision),
            _app_suites_screen(suite_summary=suite_summary, owners=owners, trust=trust, checkpoint=checkpoint, reports=reports),
            _app_logs_screen(reports=reports, suite_summary=suite_summary),
            _app_compare_screen(latest=latest, output_path=output_path),
            _app_history_screen(history=history, trend=trend, reports=reports),
            _app_alerts_screen(review_cases=review_cases, warnings=warnings, summary=summary),
            _app_integrations_screen(benchmarks=benchmarks),
            _app_settings_screen(errors=errors, dashboard=dashboard),
            "</div>",
            "</main>",
            "</div>",
            _APP_DASHBOARD_SCRIPT,
            "</body>",
            "</html>",
            "",
        ]
    )


def _app_sidebar(*, active: int, changed: int, alerts: int) -> str:
    alert_badge = f'<span class="badge red">{active}</span>' if active else ""
    changed_badge = f'<span class="badge amber">{changed}</span>' if changed else ""
    alerts_badge = f'<span class="badge red">{alerts}</span>' if alerts else ""
    return (
        '<aside class="sidebar">'
        f'<div class="sb-logo"><div class="sb-logo-icon">{_app_icon("compare")}</div><div><div class="sb-logo-name">redline</div><div class="sb-logo-version">local dashboard</div></div></div>'
        f'<button type="button" class="sb-item active" data-nav="dashboard">{_app_icon("dashboard")}<span>Dashboard</span></button>'
        f'<button type="button" class="sb-item" data-nav="workflow">{_app_icon("workflow")}<span>Workflow</span></button>'
        f'<button type="button" class="sb-item" data-nav="regressions">{_app_icon("alert")}<span>Regressions</span> {alert_badge}</button>'
        f'<button type="button" class="sb-item" data-nav="suites">{_app_icon("suite")}<span>Eval suites</span></button>'
        f'<button type="button" class="sb-item" data-nav="logs">{_app_icon("logs")}<span>Log import</span></button>'
        '<div class="sb-section">Analysis</div>'
        f'<button type="button" class="sb-item" data-nav="compare">{_app_icon("diff")}<span>Prompt diff</span> {changed_badge}</button>'
        f'<button type="button" class="sb-item" data-nav="history">{_app_icon("history")}<span>Run history</span></button>'
        f'<button type="button" class="sb-item" data-nav="alerts">{_app_icon("bell")}<span>Alerts</span> {alerts_badge}</button>'
        '<div class="sb-section">System</div>'
        f'<button type="button" class="sb-item" data-nav="integrations">{_app_icon("plug")}<span>Integrations</span></button>'
        f'<button type="button" class="sb-item" data-nav="settings">{_app_icon("settings")}<span>Settings</span></button>'
        '<div class="sb-spacer"></div>'
        '<div class="sb-bottom"><div class="sb-avatar">RL</div><div><div class="sb-user-name">Local project</div><div class="sb-user-role">Local-first, no telemetry</div></div></div>'
        "</aside>"
    )


def _app_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _app_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _app_topbar(*, title: str, status_class: str, status_text: str, reports: int) -> str:
    badge_class = {"red": "badge-crit", "amber": "badge-warn", "green": "badge-pass"}.get(status_class, "badge-blue")
    return (
        '<header class="topbar">'
        '<div class="topbar-left">'
        f'<div class="crumb" id="crumb"><b>{_h(title)}</b></div>'
        f'<span class="top-badge {badge_class}" id="top-badge">{_h(status_text)}</span>'
        "</div>"
        '<div class="topbar-right">'
        f'<span class="chip chip-blue">{reports} report(s)</span>'
        '<a class="btn" href="#reports">Open reports</a>'
        '<a class="btn btn-primary" href="#s-regressions" data-nav-link="regressions">Review</a>'
        "</div>"
        "</header>"
    )


def _app_workflow_screen(
    *,
    dashboard: dict[str, Any],
    latest: dict[str, Any],
    reports: list[Any],
    benchmarks: list[Any],
    history: list[Any],
    checkpoint: dict[str, Any],
    review_cases: list[Any],
) -> str:
    items = _app_workflow_items(
        dashboard=dashboard,
        latest=latest,
        reports=reports,
        benchmarks=benchmarks,
        history=history,
        checkpoint=checkpoint,
        review_cases=review_cases,
    )
    blocking = _blocking_count(_app_dict(latest.get("summary")))
    next_item = next((item for item in items if item["tone"] != "green"), items[-1])
    cards = "".join(_app_workflow_card(item) for item in items)
    return (
        '<section class="screen" id="s-workflow">'
        '<div class="metric-row">'
        f'{_app_metric("Next command", str(next_item["stage"]), next_item["title"], "amber" if next_item["tone"] == "amber" else "red" if next_item["tone"] == "red" else "green")}'
        f'{_app_metric("Reports", str(len(reports)), "local evidence files", "green" if reports else "amber")}'
        f'{_app_metric("Blocking", str(blocking), "cases to inspect", "red" if blocking else "green")}'
        f'{_app_metric("Automation", "copy-only", "dashboard never runs shell commands", "blue")}'
        "</div>"
        f'{_app_alert("blue", "Command center.", "Copy a command, run it in your terminal, then refresh this dashboard. redline stays local-first and does not execute shell commands from the browser.")}'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("workflow")} Next best action</span><span class="card-meta">state-aware</span></div><div class="card-body">{_app_workflow_card(next_item, featured=True)}</div></div>'
        f'<div class="command-grid">{cards}</div>'
        "</section>"
    )


def _app_workflow_items(
    *,
    dashboard: dict[str, Any],
    latest: dict[str, Any],
    reports: list[Any],
    benchmarks: list[Any],
    history: list[Any],
    checkpoint: dict[str, Any],
    review_cases: list[Any],
) -> list[dict[str, str]]:
    reports_dir = str(dashboard.get("reports_dir") or ".redline/reports")
    history_path = str(dashboard.get("history_path") or ".redline/history.jsonl")
    checkpoint_path = str(dashboard.get("checkpoint_path") or ".redline/audit-checkpoint.json")
    latest_report = str(latest.get("path") or f"{reports_dir}/eval.json")
    suite = _app_latest_suite(latest=latest, benchmarks=benchmarks)
    first_case = next((item for item in review_cases if isinstance(item, dict)), {})
    case_id = str(first_case.get("case_id") or first_case.get("suite_case_id") or "<case_id>")
    case_suite = str(first_case.get("suite") or suite)
    blocking = _blocking_count(_app_dict(latest.get("summary")))
    changed = _changed_count(_app_dict(latest.get("summary")))
    has_reports = bool(reports)
    has_history = bool(history)
    has_benchmarks = bool(benchmarks)
    has_checkpoint = bool(checkpoint)
    return [
        {
            "stage": "0",
            "title": "Prove the loop",
            "body": "Run the bundled regression proof before connecting private logs.",
            "command": "redline demo --public --compact",
            "tone": "green" if has_reports else "amber",
        },
        {
            "stage": "1",
            "title": "Get logs in",
            "body": "Detect fields first. Redaction is on by default when writing normalized JSONL.",
            "command": "redline import path/to/export.jsonl --detect",
            "tone": "green" if has_reports else "amber",
        },
        {
            "stage": "2",
            "title": "Preview import",
            "body": "Check a few mapped rows before creating a baseline log.",
            "command": "redline import path/to/export.jsonl --auto-map --preview 3",
            "tone": "green" if has_reports else "amber",
        },
        {
            "stage": "3",
            "title": "Generate suite",
            "body": "Turn normalized baseline logs into representative regression cases.",
            "command": f"redline suite .redline/logs/baseline.jsonl --out {shell_quote(suite)}",
            "tone": "green" if has_reports else "amber",
        },
        {
            "stage": "4",
            "title": "Run eval",
            "body": "Replay your changed prompt or runner and write reports for the dashboard.",
            "command": "redline eval --compact",
            "tone": "green" if has_reports else "amber",
        },
        {
            "stage": "5",
            "title": "Review first case",
            "body": "Inspect the exact baseline, candidate, and concrete regression reason.",
            "command": f"redline case {shell_quote(case_suite)} {shell_quote(case_id)}",
            "tone": "red" if blocking else "amber" if changed else "green",
        },
        {
            "stage": "6",
            "title": "Record trend",
            "body": "Add this run to history so prompt quality is visible over time.",
            "command": f"redline history {shell_quote(latest_report)} --label prompt-v2 --out {shell_quote(history_path)} --out-md .redline/history.md",
            "tone": "green" if has_history else "amber",
        },
        {
            "stage": "7",
            "title": "Add runtime evidence",
            "body": "Estimate worst-case eval time and attach local benchmark evidence.",
            "command": f"redline budget {shell_quote(suite)} --measure-local --out-json {shell_quote(reports_dir + '/benchmark.json')} --out-md {shell_quote(reports_dir + '/benchmark.md')}",
            "tone": "green" if has_benchmarks else "amber",
        },
        {
            "stage": "8",
            "title": "Verify audit trail",
            "body": "Write a checkpoint for stronger evidence that local run history was not silently changed.",
            "command": f"redline audit --verify --out-checkpoint {shell_quote(checkpoint_path)}",
            "tone": "green" if has_checkpoint else "amber",
        },
        {
            "stage": "9",
            "title": "Refresh dashboard",
            "body": "Regenerate the app dashboard after each run.",
            "command": f"redline app --reports-dir {shell_quote(reports_dir)} --history {shell_quote(history_path)}",
            "tone": "green",
        },
    ]


def _app_latest_suite(*, latest: dict[str, Any], benchmarks: list[Any]) -> str:
    suite = str(latest.get("suite") or "").strip()
    if suite:
        return suite
    prompt_evals = latest.get("prompt_evals")
    if isinstance(prompt_evals, list):
        for item in prompt_evals:
            if isinstance(item, dict) and str(item.get("suite") or "").strip():
                return str(item.get("suite"))
    for item in benchmarks:
        if isinstance(item, dict) and str(item.get("suite") or "").strip() and str(item.get("suite")) != "-":
            return str(item.get("suite"))
    return "redline-suite.json"


def _app_workflow_card(item: dict[str, str], *, featured: bool = False) -> str:
    tone = item.get("tone") or "blue"
    command = item.get("command") or ""
    featured_class = " featured" if featured else ""
    return (
        f'<div class="command-card command-{_h(tone)}{featured_class}">'
        '<div class="command-head">'
        f'<span class="command-stage">{_h(item.get("stage") or "")}</span>'
        f'<div><div class="command-title">{_h(item.get("title") or "")}</div><div class="command-body">{_h(item.get("body") or "")}</div></div>'
        f'<span class="chip chip-{_chip_tone(tone)}">{_h(_workflow_status(tone))}</span>'
        "</div>"
        '<div class="command-row">'
        f'<code>{_h(command)}</code>'
        f'<button type="button" class="copy-btn" data-copy="{_h(command)}">Copy</button>'
        "</div>"
        "</div>"
    )


def _workflow_status(tone: str) -> str:
    if tone == "green":
        return "ready"
    if tone == "red":
        return "blocking"
    return "next"


def _app_dashboard_screen(
    *,
    summary: dict[str, Any],
    suite_summary: dict[str, Any],
    decision: dict[str, Any],
    reports: list[Any],
    benchmarks: list[Any],
    history: list[Any],
    review_cases: list[Any],
    warnings: list[Any],
    status_class: str,
    output_path: str | Path | None,
) -> str:
    blocking = _blocking_count(summary)
    changed = _changed_count(summary)
    neutral = _safe_int(summary.get("neutral"))
    cases = _safe_int(summary.get("cases"))
    action = str(decision.get("recommended_action") or "Run a diff or eval to populate ship guidance.")
    warning_html = _app_warning_banner(warnings, status_class=status_class)
    pass_text = _pass_rate_label(summary)
    return (
        '<section class="screen active" id="s-dashboard">'
        '<div class="metric-row">'
        f'{_app_metric("Active regressions", str(blocking), "regression + missing", "red" if blocking else "green")}'
        f'{_app_metric("Review changes", str(changed), "changed cases", "amber" if changed else "green")}'
        f'{_app_metric("Eval cases", str(cases), f"{neutral} neutral", "")}'
        f'{_app_metric("Pass rate", pass_text, f"{len(reports)} reports, {len(history)} history rows", "green" if not blocking else "red")}'
        "</div>"
        f"{warning_html}"
        '<div class="two-col hero-grid">'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("alert")} Recent regressions</span><span class="card-meta">latest report</span></div>'
        f'<div class="card-body">{_app_review_rows(review_cases)}</div></div>'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("health")} Suite health</span><span class="card-meta">local evidence</span></div>'
        f'<div class="card-body"><div class="decision">{_h(action)}</div>{_app_suite_health(suite_summary, benchmarks)}</div></div>'
        "</div>"
        '<div class="card">'
        f'<div class="card-head"><span class="card-title">{_app_icon("trend")} Regression trend</span><span class="card-meta">latest local reports</span></div>'
        f'<div class="card-body">{_app_report_chart(reports)}{_app_trust_strip(summary, suite_summary)}</div>'
        "</div>"
        f'{_app_reports_table(reports, output_path=output_path)}'
        "</section>"
    )


def _app_regressions_screen(*, review_cases: list[Any], summary: dict[str, Any], decision: dict[str, Any]) -> str:
    blocking = _blocking_count(summary)
    action = str(decision.get("recommended_action") or "Review blocking cases before shipping.")
    return (
        '<section class="screen" id="s-regressions">'
        f'{_app_alert("red" if blocking else "green", f"{blocking} blocking case(s).", action)}'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("alert")} Active regressions</span><span class="card-meta">blocking and changed</span></div>'
        f'<div class="card-body">{_app_review_rows(review_cases, empty="No review cases in the latest report.")}</div></div>'
        '<div class="two-col">'
        f'{_app_breakdown_card("Blocking status", summary)}'
        f'{_app_fix_card(review_cases)}'
        "</div>"
        "</section>"
    )


def _app_suites_screen(
    *,
    suite_summary: dict[str, Any],
    owners: list[Any],
    trust: dict[str, Any],
    checkpoint: dict[str, Any],
    reports: list[Any],
) -> str:
    rows = [
        ("Cases", _safe_int(suite_summary.get("cases"))),
        ("Unique pairs", _safe_int(suite_summary.get("unique_prompt_response_pairs"))),
        ("Behavior groups", _safe_int(suite_summary.get("clusters"))),
        ("Stochastic prompts", _safe_int(suite_summary.get("stochastic_prompt_groups"))),
        ("Non-ASCII records", _safe_int(suite_summary.get("non_ascii_records"))),
    ]
    health_rows = "".join(
        f'<div class="kv-row"><span class="kv-key">{_h(label)}</span><strong class="kv-val">{value}</strong></div>'
        for label, value in rows
    )
    owner_rows = _app_owner_rows(owners)
    trust_text = str(trust.get("scope") or TRUST_SCOPE)
    checkpoint_text = "verified" if checkpoint else "not loaded"
    return (
        '<section class="screen" id="s-suites">'
        '<div class="metric-row">'
        f'{_app_metric("Reports", str(len(reports)), "loaded locally", "")}'
        f'{_app_metric("Suite coverage", _coverage_label(suite_summary), "behavior groups", "")}'
        f'{_app_metric("Owners", str(len(owners)), "review routing rows", "")}'
        f'{_app_metric("Audit", checkpoint_text, "checkpoint status", "green" if checkpoint else "amber")}'
        "</div>"
        '<div class="two-col">'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("suite")} Suite health</span></div><div class="card-body">{health_rows}</div></div>'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("owner")} Owners</span></div><div class="card-body">{owner_rows}</div></div>'
        "</div>"
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("shield")} Trust boundary</span></div><div class="card-body"><p>{_h(trust_text)}</p><p class="muted">Audit checkpoint: {_h(checkpoint_text)}</p></div></div>'
        "</section>"
    )


def _app_logs_screen(*, reports: list[Any], suite_summary: dict[str, Any]) -> str:
    return (
        '<section class="screen" id="s-logs">'
        '<div class="metric-row">'
        f'{_app_metric("Reports loaded", str(len(reports)), "JSON report files", "")}'
        f'{_app_metric("Cases generated", str(_safe_int(suite_summary.get("cases"))), "from baseline logs", "")}'
        f'{_app_metric("Import presets", "5", "Langfuse, Helicone, Datadog, OpenAI, custom", "")}'
        f'{_app_metric("Redaction", "on", "default import posture", "green")}'
        "</div>"
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("upload")} Import log file</span></div>'
        '<div class="card-body">'
        '<div class="upload-zone"><strong>Drop exported JSONL into the project, then detect fields locally.</strong><p>Use <code>redline import --detect</code>, then <code>--auto-map --preview 3</code> before writing normalized logs.</p></div>'
        '<div class="log-row"><span>1</span><p>Detect fields from Langfuse, Helicone, Datadog, OpenAI chat, or custom JSONL exports.</p></div>'
        '<div class="log-row"><span>2</span><p>Redaction is best-effort pattern matching, not a privacy boundary. Inspect private logs locally.</p></div>'
        '<div class="log-row"><span>3</span><p>Run <code>redline quick-check baseline.jsonl candidate.jsonl --open</code> for the fastest first pass.</p></div>'
        "</div></div>"
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("preset")} Import presets</span></div><div class="card-body">'
        f'{_app_integration_row("Langfuse export", "redline import langfuse.jsonl --preset langfuse --out logs/baseline.jsonl", "Available")}'
        f'{_app_integration_row("Helicone export", "redline import helicone.jsonl --preset helicone --out logs/baseline.jsonl", "Available")}'
        f'{_app_integration_row("Datadog logs", "redline import datadog.jsonl --preset datadog --out logs/baseline.jsonl", "Available")}'
        "</div></div>"
        "</section>"
    )


def _app_compare_screen(*, latest: dict[str, Any], output_path: str | Path | None) -> str:
    diffs = _app_list(latest.get("review_cases"))
    links = _links(
        [
            ("HTML", str(latest.get("html_path") or "")),
            ("Markdown", str(latest.get("markdown_path") or "")),
            ("JSON", str(latest.get("path") or "")),
        ],
        output_path=output_path,
    )
    return (
        '<section class="screen" id="s-compare">'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("report")} Latest report links</span></div><div class="card-body">{links}</div></div>'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("diff")} Concrete reasons</span></div>'
        f'<div class="card-body">{_app_review_rows(diffs, empty="No changed or blocking cases in the latest report.")}</div></div>'
        "</section>"
    )


def _app_history_screen(*, history: list[Any], trend: dict[str, Any], reports: list[Any]) -> str:
    direction = str(trend.get("direction") or "unknown").replace("_", " ").title()
    rows = _app_history_rows(history)
    return (
        '<section class="screen" id="s-history">'
        '<div class="metric-row">'
        f'{_app_metric("Total reports", str(len(reports)), "loaded from reports dir", "")}'
        f'{_app_metric("History rows", str(len(history)), "recorded runs", "")}'
        f'{_app_metric("Trend", direction, "latest local direction", "red" if direction.lower() == "worse" else "")}'
        f'{_app_metric("Latest blocking", str(_latest_blocking(reports)), "regression + missing", "red" if _latest_blocking(reports) else "green")}'
        "</div>"
        f'{_app_alert("blue", f"Trend: {direction}", str(trend.get("summary") or "Record history entries to see whether prompt quality is improving or regressing."))}'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("history")} Run history</span><span class="card-meta">latest 20 runs</span></div><div class="card-body">{rows}</div></div>'
        "</section>"
    )


def _app_alerts_screen(*, review_cases: list[Any], warnings: list[Any], summary: dict[str, Any]) -> str:
    blocking = _blocking_count(summary)
    warning_count = len([warning for warning in warnings if str(warning).strip()])
    alert_rows = _app_review_rows(review_cases, empty="No blocking report alerts.")
    warning_rows = "".join(
        f'<div class="t-row"><div class="t-icon amber">W</div><div class="t-info"><div class="t-name">Calibration warning</div><div class="t-sub">{_h(_preview(str(warning), 160))}</div></div><span class="chip chip-warn">review</span></div>'
        for warning in warnings[:6]
        if str(warning).strip()
    )
    warnings_body = warning_rows or '<p class="muted">No dashboard warnings.</p>'
    return (
        '<section class="screen" id="s-alerts">'
        '<div class="metric-row">'
        f'{_app_metric("Open alerts", str(blocking + warning_count), "derived from local reports", "red" if blocking else "amber" if warning_count else "green")}'
        f'{_app_metric("Blocking", str(blocking), "regression + missing", "red" if blocking else "green")}'
        f'{_app_metric("Warnings", str(warning_count), "notices and calibration", "amber" if warning_count else "green")}'
        f'{_app_metric("Channels", "local", "CLI, HTML, MCP, CI artifacts", "")}'
        "</div>"
        '<div class="two-col">'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("bell")} Report alerts</span></div><div class="card-body">{alert_rows}</div></div>'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("warning")} Warnings</span></div><div class="card-body">{warnings_body}</div></div>'
        "</div>"
        "</section>"
    )


def _app_integrations_screen(*, benchmarks: list[Any]) -> str:
    content = (
        _app_integration_row("MCP", "redline-mcp", "Ready")
        + _app_integration_row("GitHub Action", "uses: gowtham0992/redline@v0", "Ready")
        + _app_integration_row("Runner adapters", "redline runners --copy all", "Ready")
        + _app_integration_row("Judge templates", "redline judges --copy support-rubric", "Optional")
        + _app_integration_row("Benchmark evidence", f"{len(benchmarks)} local benchmark artifact(s)", "Local")
    )
    return (
        '<section class="screen" id="s-integrations">'
        '<div class="metric-row">'
        f'{_app_metric("Connected surfaces", "4", "CLI, MCP, Action, local HTML", "")}'
        f'{_app_metric("Benchmarks", str(len(benchmarks)), "runtime evidence artifacts", "green" if benchmarks else "amber")}'
        f'{_app_metric("Runner adapters", "7", "stdio, HTTP, SDK, chains, logs", "")}'
        f'{_app_metric("Judge templates", "4", "optional semantic review", "")}'
        "</div>"
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("plug")} Developer workflow integrations</span></div><div class="card-body">{content}</div></div>'
        "</section>"
    )


def _app_settings_screen(*, errors: list[Any], dashboard: dict[str, Any]) -> str:
    error_html = _errors(errors) if errors else '<p class="muted">No skipped local report files.</p>'
    reports_dir = str(dashboard.get("reports_dir") or ".redline/reports")
    history_path = str(dashboard.get("history_path") or ".redline/history.jsonl")
    checkpoint_path = str(dashboard.get("checkpoint_path") or ".redline/audit-checkpoint.json")
    return (
        '<section class="screen" id="s-settings">'
        '<div class="two-col">'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("settings")} Local settings</span></div>'
        f'<div class="card-body"><div class="setting-row"><div><div class="setting-label">Runtime</div><div class="setting-sub">All data is read from local files</div></div><span class="chip chip-pass">local</span></div><div class="setting-row"><div><div class="setting-label">Telemetry</div><div class="setting-sub">Dashboard does not transmit report data</div></div><span class="chip chip-pass">off</span></div><div class="setting-row"><div><div class="setting-label">Reports dir</div><div class="setting-sub">{_h(reports_dir)}</div></div></div><div class="setting-row"><div><div class="setting-label">History path</div><div class="setting-sub">{_h(history_path)}</div></div></div><div class="setting-row"><div><div class="setting-label">Checkpoint path</div><div class="setting-sub">{_h(checkpoint_path)}</div></div></div></div></div>'
        f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("warning")} Skipped files</span></div><div class="card-body">{error_html}</div></div>'
        "</div>"
        "</section>"
    )


def _app_metric(label: str, value: str, sub: str, tone: str) -> str:
    tone_class = f" {tone}" if tone else ""
    return (
        '<div class="metric-card">'
        f'<div class="metric-label">{_h(label)}</div>'
        f'<div class="metric-val{tone_class}">{_h(value)}</div>'
        f'<div class="metric-sub">{_h(sub)}</div>'
        "</div>"
    )


def _app_warning_banner(warnings: list[Any], *, status_class: str) -> str:
    if warnings:
        text = " ".join(_preview(str(warning), 160) for warning in warnings[:2])
        return _app_alert("amber", "Calibration warning.", text)
    if status_class == "red":
        return _app_alert("red", "Blocking regressions detected.", "Fix or mark expected changes before shipping.")
    return _app_alert("green", "No blocking structural regressions in latest report.", "Review semantic risks separately.")


def _app_review_rows(items: list[Any], *, empty: str = "No review cases found.") -> str:
    rows = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("kind") or "review")
        case_id = str(item.get("case_id") or item.get("suite_case_id") or "-")
        prompt = _preview(str(item.get("prompt") or item.get("reason") or "Review case"), 96)
        reason = _preview(str(item.get("reason") or "; ".join(str(value) for value in item.get("reasons", []) if value) or ""), 120)
        tone = "red" if status in {"regression", "missing"} else "amber" if status == "changed" else "green"
        rows.append(
            '<div class="reg-row">'
            f'<div class="reg-icon {tone}">{_h(status[:1].upper())}</div>'
            f'<div class="reg-info"><div class="reg-name">{_h(case_id)} - {_h(prompt)}</div><div class="reg-sub">{_h(reason or status)}</div><div class="prog-bar"><div class="prog-fill {tone}" style="width:{_status_width(status)}%"></div></div></div>'
            f'<span class="chip chip-{_chip_tone(tone)}">{_h(status)}</span>'
            "</div>"
        )
    if not rows:
        return f'<p class="muted">{_h(empty)}</p>'
    overflow = len(items) - 8
    if overflow > 0:
        rows.append(f'<p class="muted row-note">Showing the first 8 cases. Open the HTML report for {overflow} more.</p>')
    return "".join(rows)


def _app_suite_health(suite_summary: dict[str, Any], benchmarks: list[Any]) -> str:
    rows = [
        ("Cases", _safe_int(suite_summary.get("cases"))),
        ("Groups", _safe_int(suite_summary.get("clusters"))),
        ("Benchmarks", len(benchmarks)),
    ]
    return "".join(f'<div class="kv-row"><span class="kv-key">{_h(label)}</span><strong class="kv-val">{value}</strong></div>' for label, value in rows)


def _app_owner_rows(owners: list[Any]) -> str:
    rows = []
    for owner in owners[:8]:
        if not isinstance(owner, dict):
            continue
        rows.append(
            '<div class="kv-row">'
            f'<span class="kv-key">{_h(str(owner.get("owner") or "unowned"))}</span>'
            f'<strong class="kv-val">{_safe_int(owner.get("reviewable"))}</strong>'
            "</div>"
        )
    return "".join(rows) if rows else '<p class="muted">No owner review rows yet.</p>'


def _app_reports_table(reports: list[Any], *, output_path: str | Path | None) -> str:
    if not reports:
        return '<div class="card" id="reports"><div class="card-head"><span class="card-title">Reports</span></div><div class="card-body"><p class="muted">No report JSON files found yet.</p></div></div>'
    rows = []
    for report in reports[:8]:
        if not isinstance(report, dict):
            continue
        summary = _app_dict(report.get("summary"))
        rows.append(
            '<div class="t-row">'
            f'<div class="t-info"><div class="t-name">{_h(str(report.get("name") or "-"))}</div><div class="t-sub">{_summary_pills(summary)}</div></div>'
            f'<div class="t-right">{_links([("HTML", str(report.get("html_path") or "")), ("JSON", str(report.get("path") or ""))], output_path=output_path)}</div>'
            "</div>"
        )
    return '<div class="card" id="reports"><div class="card-head"><span class="card-title">Reports</span></div><div class="card-body">' + "".join(rows) + "</div></div>"


def _app_history_rows(history: list[Any]) -> str:
    rows = []
    for item in history[:10]:
        if not isinstance(item, dict):
            continue
        summary = _app_dict(item.get("summary"))
        rows.append(
            '<div class="t-row">'
            f'<div class="t-info"><div class="t-name">{_h(str(item.get("label") or item.get("timestamp") or "-"))}</div><div class="t-sub">{_summary_pills(_summary_counts(summary))}</div></div>'
            f'<div class="t-right"><span class="muted">{_h(str(item.get("timestamp") or ""))}</span></div>'
            "</div>"
        )
    return "".join(rows) if rows else '<p class="muted">No history recorded yet.</p>'


def _app_alert(tone: str, title: str, message: str) -> str:
    return f'<div class="alert-bar alert-{_h(tone)}">{_app_icon("alert")}<div><b>{_h(title)}</b> {_h(message)}</div></div>'


def _app_breakdown_card(title: str, summary: dict[str, Any]) -> str:
    rows = [
        ("Regressions", _safe_int(summary.get("regression")), "red"),
        ("Missing", _safe_int(summary.get("missing")), "red"),
        ("Changed", _safe_int(summary.get("changed")), "amber"),
        ("Neutral", _safe_int(summary.get("neutral")), "green"),
    ]
    body = "".join(
        f'<div class="check-row"><div class="check-left"><span class="dot {tone}"></span>{_h(label)}</div><span class="kv-val {tone}">{value}</span></div>'
        for label, value, tone in rows
    )
    return f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("breakdown")} {_h(title)}</span></div><div class="card-body">{body}</div></div>'


def _app_fix_card(review_cases: list[Any]) -> str:
    first = next((item for item in review_cases if isinstance(item, dict)), {})
    case_id = str(first.get("case_id") or first.get("suite_case_id") or "case id")
    suite = str(first.get("suite") or "redline-suite.json")
    command = f"redline case {shell_quote(suite)} {shell_quote(case_id)}" if case_id != "case id" else "redline cases redline-suite.json"
    body = (
        '<div class="diff-block">'
        '<span class="diff-ctx">Recommended local loop</span>'
        f'<span class="diff-del">1. Inspect: {_h(command)}</span>'
        '<span class="diff-del">2. Fix prompt or runner output</span>'
        '<span class="diff-add">3. Mark expected only when the change is intentional</span>'
        '</div>'
    )
    return f'<div class="card"><div class="card-head"><span class="card-title">{_app_icon("fix")} Suggested fix</span></div><div class="card-body">{body}</div></div>'


def _app_report_chart(reports: list[Any]) -> str:
    points = []
    for index, report in enumerate(reversed([item for item in reports[:12] if isinstance(item, dict)])):
        summary = _app_dict(report.get("summary"))
        cases = max(_safe_int(summary.get("cases")), 1)
        blocking = _blocking_count(summary)
        pass_rate = max(0.0, min(1.0, (cases - blocking) / cases))
        x = 24 + index * 74
        y = 132 - int(pass_rate * 96)
        points.append((x, y))
    if not points:
        return '<p class="muted">No report chart yet. Run redline diff or eval to populate trend evidence.</p>'
    path = " ".join(f"{x},{y}" for x, y in points)
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="4"></circle>' for x, y in points)
    return (
        '<svg class="chart-svg" viewBox="0 0 900 150" role="img" aria-label="Pass rate trend">'
        '<line x1="20" y1="132" x2="880" y2="132"></line>'
        '<line x1="20" y1="36" x2="880" y2="36"></line>'
        f'<polyline points="{path}"></polyline>{dots}'
        "</svg>"
        '<div class="chart-legend"><span><i class="legend pass"></i> pass rate</span><span><i class="legend block"></i> blocking cases lower is better</span></div>'
    )


def _app_trust_strip(summary: dict[str, Any], suite_summary: dict[str, Any]) -> str:
    return (
        '<div class="trust-strip">'
        f'<div><span>Scope</span><strong>structural checks</strong></div>'
        f'<div><span>Cases</span><strong>{_safe_int(summary.get("cases"))}</strong></div>'
        f'<div><span>Coverage</span><strong>{_coverage_label(suite_summary)}</strong></div>'
        f'<div><span>Boundary</span><strong>review semantics separately</strong></div>'
        "</div>"
    )


def _app_integration_row(name: str, command: str, status: str) -> str:
    tone = "chip-pass" if status.lower() in {"ready", "available", "local"} else "chip-blue"
    return (
        '<div class="int-row">'
        f'<div class="int-logo">{_app_icon("plug")}</div>'
        f'<div class="t-info"><div class="t-name">{_h(name)}</div><div class="t-sub"><code>{_h(command)}</code></div></div>'
        f'<span class="chip {tone}">{_h(status)}</span>'
        "</div>"
    )


def _app_icon(name: str) -> str:
    paths = {
        "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
        "workflow": '<path d="M4 6h6"/><path d="M14 6h6"/><path d="M4 12h16"/><path d="M4 18h6"/><path d="M14 18h6"/><path d="m10 6 2 2 2-2"/><path d="m10 18 2-2 2 2"/>',
        "alert": '<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        "suite": '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="m3 6 1 1 2-2"/><path d="m3 12 1 1 2-2"/><path d="m3 18 1 1 2-2"/>',
        "logs": '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/><path d="M9 13h6"/><path d="M9 17h6"/>',
        "diff": '<path d="M7 7h10"/><path d="M7 12h6"/><path d="M7 17h10"/><path d="M3 7h.01"/><path d="M3 12h.01"/><path d="M3 17h.01"/>',
        "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/>',
        "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
        "plug": '<path d="M9 7V2"/><path d="M15 7V2"/><path d="M7 7h10v4a5 5 0 0 1-5 5h0a5 5 0 0 1-5-5z"/><path d="M12 16v6"/>',
        "settings": '<path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.1 3.6-.2-.1a1.7 1.7 0 0 0-2 .2 1.7 1.7 0 0 0-.8 1.7H9.3a1.7 1.7 0 0 0-.8-1.7 1.7 1.7 0 0 0-2-.2l-.2.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1.1v-3.8A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1 2.1-3.6.2.1a1.7 1.7 0 0 0 2-.2 1.7 1.7 0 0 0 .8-1.7h5.4a1.7 1.7 0 0 0 .8 1.7 1.7 1.7 0 0 0 2 .2l.2-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1.1v3.8a1.7 1.7 0 0 0-1.5 1.1Z"/>',
        "compare": '<path d="M7 7h10"/><path d="m14 4 3 3-3 3"/><path d="M17 17H7"/><path d="m10 14-3 3 3 3"/>',
        "health": '<path d="M20 7 9 18l-5-5"/>',
        "trend": '<path d="M3 19h18"/><path d="m5 15 4-4 4 3 6-8"/><path d="M18 6h1v1"/>',
        "owner": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
        "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-5"/>',
        "upload": '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 20h16"/>',
        "preset": '<path d="M4 5h16"/><path d="M4 12h16"/><path d="M4 19h16"/><path d="M8 3v4"/><path d="M16 10v4"/><path d="M11 17v4"/>',
        "report": '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/><path d="M9 12h6"/><path d="M9 16h6"/>',
        "warning": '<path d="M12 9v4"/><path d="M12 17h.01"/><circle cx="12" cy="12" r="10"/>',
        "breakdown": '<path d="M4 19V5"/><path d="M4 19h16"/><rect x="7" y="12" width="3" height="4"/><rect x="12" y="8" width="3" height="8"/><rect x="17" y="10" width="3" height="6"/>',
        "fix": '<path d="m14.7 6.3 3 3"/><path d="M4 20l4.5-1 9.2-9.2a2.1 2.1 0 0 0-3-3L5.5 16 4 20Z"/>',
    }
    path = paths.get(name, paths["dashboard"])
    return f'<svg class="svg-ico" aria-hidden="true" viewBox="0 0 24 24">{path}</svg>'


def _status_width(status: str) -> int:
    if status in {"regression", "missing"}:
        return 92
    if status == "changed":
        return 62
    return 35


def _chip_tone(tone: str) -> str:
    return {"red": "fail", "amber": "warn", "green": "pass", "blue": "blue"}.get(tone, "idle")


def _pass_rate_label(summary: dict[str, Any]) -> str:
    cases = _safe_int(summary.get("cases"))
    if not cases:
        return "-"
    blocking = _blocking_count(summary)
    return f"{max(0, int(round(((cases - blocking) / cases) * 100)))}%"


def _latest_blocking(reports: list[Any]) -> int:
    latest = next((report for report in reports if isinstance(report, dict)), {})
    return _blocking_count(_app_dict(latest.get("summary")))


def _coverage_label(summary: dict[str, Any]) -> str:
    coverage = summary.get("cluster_coverage")
    if isinstance(coverage, (int, float)):
        return f"{coverage * 100:.0f}%"
    return "-"


def _collect_reports(reports_dir: Path, *, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not reports_dir.exists():
        return [], []
    report_paths = sorted(
        (path for path in reports_dir.glob("*.json") if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in report_paths:
        if limit and len(reports) >= limit:
            break
        try:
            report = read_json(path)
        except ValueError as exc:
            errors.append({"path": str(path), "message": str(exc)})
            continue
        if _is_benchmark_report(report):
            continue
        summary = report.get("summary")
        if not isinstance(summary, dict):
            errors.append({"path": str(path), "message": "missing summary object"})
            continue
        prompt_evals = _report_prompt_evals(report.get("prompt_evals"))
        reports.append(
            {
                "path": str(path),
                "name": path.name,
                "kind": _report_kind(report, path),
                "suite": str(report.get("suite") or ""),
                "summary": _summary_counts(summary),
                "decision": report.get("decision") if isinstance(report.get("decision"), dict) else {},
                "methodology": report.get("methodology") if isinstance(report.get("methodology"), dict) else {},
                "suite_summary": report.get("suite_summary") if isinstance(report.get("suite_summary"), dict) else {},
                "owners": _report_owner_review(report.get("diffs"), suite_path=str(report.get("suite") or "")),
                "trust": _report_trust_summary(report.get("diffs")),
                "review": _report_review_summary(report.get("diffs")),
                "review_cases": _report_review_cases(report.get("diffs"), suite_path=str(report.get("suite") or "")),
                "prompt_evals": prompt_evals,
                "prompt_groups": _report_prompt_groups(prompt_evals),
                "html_path": _existing_sibling(path, ".html"),
                "markdown_path": _existing_sibling(path, ".md"),
            }
        )
    return reports, errors


def _collect_benchmarks(reports_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    if not reports_dir.exists():
        return []
    report_paths = sorted(
        (path for path in reports_dir.glob("*.json") if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    benchmarks: list[dict[str, Any]] = []
    for path in report_paths:
        if limit and len(benchmarks) >= limit:
            break
        try:
            report = read_json(path)
        except ValueError:
            continue
        if not _is_benchmark_report(report):
            continue
        benchmarks.append(_benchmark_row(report, path))
    return benchmarks


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


def _collect_checkpoint(checkpoint_path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not checkpoint_path.exists():
        return None, []
    try:
        checkpoint = read_json(checkpoint_path)
    except ValueError as exc:
        return None, [{"path": str(checkpoint_path), "message": str(exc)}]
    return {**checkpoint, "path": str(checkpoint_path)}, []


def _dashboard_notices(reports: list[dict[str, Any]], benchmarks: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not reports or benchmarks:
        return []
    return [
        {
            "kind": "benchmark_missing",
            "title": "Missing benchmark evidence",
            "message": (
                "Reports exist, but no benchmark artifact was found. Run a local benchmark "
                "before relying on the dashboard for runtime readiness."
            ),
            "command": (
                "redline budget redline-suite.json --measure-local "
                "--out-json .redline/reports/benchmark.json "
                "--out-md .redline/reports/benchmark.md"
            ),
        }
    ]


def _is_benchmark_report(report: dict[str, Any]) -> bool:
    return str(report.get("mode") or "") == "static_eval_budget_estimate"


def _benchmark_row(report: dict[str, Any], path: Path) -> dict[str, Any]:
    local = report.get("local_measurement")
    return {
        "path": str(path),
        "name": path.name,
        "suite": str(report.get("suite") or "-"),
        "cases": _safe_int(report.get("cases")),
        "workers": _safe_int(report.get("workers")),
        "timeout_seconds": _safe_float(report.get("timeout_seconds")),
        "worst_case_seconds": _safe_float(report.get("worst_case_seconds")),
        "sequential_worst_case_seconds": _safe_float(report.get("sequential_worst_case_seconds")),
        "max_seconds": _optional_float(report.get("max_seconds")),
        "within_budget": bool(report.get("within_budget")),
        "status": str(report.get("status") or ""),
        "is_prompt_manifest": bool(report.get("is_prompt_manifest")),
        "local_measurement": local if isinstance(local, dict) else {},
        "markdown_path": _existing_sibling(path, ".md"),
    }


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


def _report_owner_review(diffs: Any, *, suite_path: str = "") -> list[dict[str, int | str]]:
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
                "provenance": 0,
                "command": "",
                "total": 0,
            },
        )
        row["total"] = int(row["total"]) + 1
        if isinstance(item.get("owner_rule"), dict):
            row["provenance"] = int(row["provenance"]) + 1
        if not str(row.get("command") or ""):
            row["command"] = _dashboard_review_command(item, suite_path=suite_path)
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
            row = rows.setdefault(
                owner,
                {"owner": owner, "blocking": 0, "changed": 0, "provenance": 0, "command": "", "total": 0},
            )
            row["blocking"] = int(row["blocking"]) + int(owner_row.get("blocking") or 0)
            row["changed"] = int(row["changed"]) + int(owner_row.get("changed") or 0)
            row["provenance"] = int(row["provenance"]) + int(owner_row.get("provenance") or 0)
            if not str(row.get("command") or ""):
                row["command"] = str(owner_row.get("command") or "")
            row["total"] = int(row["total"]) + int(owner_row.get("total") or 0)
    return _sort_owner_rows(rows.values())


def _dashboard_review_command(item: dict[str, Any], *, suite_path: str = "") -> str:
    status = str(item.get("status") or "")
    if status not in {"regression", "missing", "changed"}:
        return ""
    suite = str(item.get("suite") or suite_path).strip()
    case_id = str(item.get("suite_case_id") or item.get("case_id") or "").strip()
    if not suite or not case_id:
        return ""
    return f'redline mark {shell_quote(suite)} {shell_quote(case_id)} --status expected --note "intentional change"'


def _report_trust_summary(diffs: Any) -> dict[str, Any]:
    confidence: dict[str, int] = {}
    signal: dict[str, int] = {}
    cases = 0
    if not isinstance(diffs, list):
        return {"cases": 0, "confidence": {}, "signal": {}}
    for item in diffs:
        if not isinstance(item, dict):
            continue
        cases += 1
        confidence_key = str(item.get("confidence") or "").strip()
        if confidence_key:
            confidence[confidence_key] = confidence.get(confidence_key, 0) + 1
        signal_key = str(item.get("signal") or "").strip()
        if signal_key:
            signal[signal_key] = signal.get(signal_key, 0) + 1
    return {
        "cases": cases,
        "confidence": dict(sorted(confidence.items())),
        "signal": dict(sorted(signal.items())),
    }


def _report_review_summary(diffs: Any) -> dict[str, int]:
    blocking = 0
    changed = 0
    if not isinstance(diffs, list):
        return {"reviewable": 0, "blocking": 0, "changed": 0}
    for item in diffs:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status in {"regression", "missing"}:
            blocking += 1
        elif status == "changed":
            changed += 1
    return {"reviewable": blocking + changed, "blocking": blocking, "changed": changed}


def _report_prompt_evals(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        decision = item.get("decision")
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "prompt": str(item.get("prompt") or ""),
                "suite": str(item.get("suite") or ""),
                "summary": _summary_counts(summary) if isinstance(summary, dict) else {},
                "decision": decision if isinstance(decision, dict) else {},
            }
        )
    return rows


def _report_prompt_groups(prompt_evals: Any) -> list[dict[str, Any]]:
    if not isinstance(prompt_evals, list):
        return []
    rows: dict[str, dict[str, Any]] = {}
    for item in prompt_evals:
        if not isinstance(item, dict):
            continue
        feature = _prompt_feature(item)
        row = rows.setdefault(
            feature,
            {
                "feature": feature,
                "prompt_count": 0,
                "summary": {},
                "action": "clean",
            },
        )
        row["prompt_count"] = int(row["prompt_count"]) + 1
        row_summary = row["summary"]
        summary = item.get("summary")
        if isinstance(row_summary, dict) and isinstance(summary, dict):
            for key, value in _summary_counts(summary).items():
                row_summary[key] = int(row_summary.get(key) or 0) + value

    groups = list(rows.values())
    for group in groups:
        summary = group.get("summary")
        group["action"] = _prompt_group_action(summary if isinstance(summary, dict) else {})
    return sorted(
        groups,
        key=lambda group: (
            -_blocking_count(group.get("summary")),
            -_changed_count(group.get("summary")),
            str(group.get("feature") or "").lower(),
        ),
    )


def _prompt_feature(item: dict[str, Any]) -> str:
    identifier = str(item.get("id") or "").strip().replace("\\", "/")
    if "/" in identifier:
        first = next((part for part in identifier.split("/") if part), "")
        if first:
            return first

    prompt = str(item.get("prompt") or "").strip().replace("\\", "/")
    parts = [part for part in prompt.split("/") if part and part not in {".", ".."}]
    if "prompts" in parts:
        index = parts.index("prompts")
        if index + 1 < len(parts):
            candidate = parts[index + 1]
            if index + 2 == len(parts):
                return Path(candidate).stem or "default"
            return candidate
    if len(parts) > 1:
        return parts[0]
    if parts:
        return Path(parts[0]).stem or "default"
    return "default"


def _prompt_group_action(summary: dict[str, Any]) -> str:
    if _blocking_count(summary):
        return "fix blocking cases before shipping"
    if _changed_count(summary):
        return "review changed cases before shipping"
    return "clean"


def _blocking_count(summary: Any) -> int:
    if not isinstance(summary, dict):
        return 0
    return int(summary.get("regression") or 0) + int(summary.get("missing") or 0)


def _changed_count(summary: Any) -> int:
    if not isinstance(summary, dict):
        return 0
    return int(summary.get("changed") or 0)


def _report_review_cases(diffs: Any, *, limit: int = 12, suite_path: str = "") -> list[dict[str, Any]]:
    if not isinstance(diffs, list):
        return []
    rows = []
    for item in diffs:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {"regression", "missing", "changed"}:
            continue
        reasons = item.get("reasons")
        first_reason = ""
        if isinstance(reasons, list) and reasons:
            first_reason = str(reasons[0])
        rows.append(
            {
                "case_id": str(item.get("case_id") or ""),
                "status": status,
                "owner": str(item.get("owner") or ""),
                "prompt": str(item.get("prompt") or ""),
                "reason": first_reason,
                "confidence": str(item.get("confidence") or ""),
                "signal": str(item.get("signal") or ""),
                "prompt_path": str(item.get("prompt_path") or ""),
                "suite": str(item.get("suite") or suite_path),
            }
        )
    return rows[:limit]


def _dashboard_trust_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    cases = 0
    confidence: dict[str, int] = {}
    signal: dict[str, int] = {}
    methodology: dict[str, int] = {}
    suite_coverage: dict[str, int] = {}
    for report in reports:
        trust = report.get("trust")
        if not isinstance(trust, dict):
            continue
        cases += int(trust.get("cases") or 0)
        _merge_counts(confidence, trust.get("confidence"))
        _merge_counts(signal, trust.get("signal"))
        method = report.get("methodology")
        if isinstance(method, dict):
            label = _methodology_label(method)
            if label:
                methodology[label] = methodology.get(label, 0) + 1
        suite_summary = report.get("suite_summary")
        if isinstance(suite_summary, dict):
            label = _suite_coverage_label(suite_summary)
            if label:
                suite_coverage[label] = suite_coverage.get(label, 0) + 1
    return {
        "cases": cases,
        "confidence": dict(sorted(confidence.items())),
        "signal": dict(sorted(signal.items())),
        "methodology": dict(sorted(methodology.items())),
        "suite_coverage": dict(sorted(suite_coverage.items())),
    }


def _merge_counts(target: dict[str, int], source: Any) -> None:
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        clean_key = str(key).strip()
        if clean_key:
            target[clean_key] = target.get(clean_key, 0) + count


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


def _overview(
    latest: dict[str, Any],
    report_count: int,
    benchmark_count: int,
    history_count: int,
) -> str:
    raw_summary = latest.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    cards = [
        ("Reports", report_count),
        ("Benchmarks", benchmark_count),
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


def _evidence_panel(
    latest: dict[str, Any],
    benchmarks: list[Any],
    history: list[Any],
    checkpoint: dict[str, Any],
    *,
    output_path: str | Path | None,
) -> str:
    if not latest and not benchmarks and not history and not checkpoint:
        return ""
    report_links = _links(
        [
            ("HTML", str(latest.get("html_path") or "")),
            ("Markdown", str(latest.get("markdown_path") or "")),
            ("JSON", str(latest.get("path") or "")),
        ],
        output_path=output_path,
    )
    first_benchmark = next((item for item in benchmarks if isinstance(item, dict)), {})
    benchmark_links = _links(
        [
            ("Markdown", str(first_benchmark.get("markdown_path") or "")),
            ("JSON", str(first_benchmark.get("path") or "")),
        ],
        output_path=output_path,
    )
    latest_history = next((item for item in history if isinstance(item, dict)), {})
    checkpoint_status = "Audit OK" if checkpoint.get("ok") else "No checkpoint"
    if checkpoint and not checkpoint.get("ok"):
        checkpoint_status = "Audit failed"
    cells = [
        _evidence_card(
            "Latest report",
            str(latest.get("name") or "none"),
            report_links,
        ),
        _evidence_card(
            "Runtime evidence",
            str(first_benchmark.get("name") or "none"),
            benchmark_links,
        ),
        _evidence_card(
            "History",
            f"{len(history)} entries",
            _h(str(latest_history.get("label") or "no trend yet")),
        ),
        _evidence_card(
            "Audit checkpoint",
            checkpoint_status,
            f"<code>{_h(str(checkpoint.get('path') or ''))}</code>" if checkpoint.get("path") else "",
        ),
    ]
    return (
        '<section class="panel evidence-trail">'
        "<h2>Evidence Trail</h2>"
        '<div class="cards compact">'
        f"{''.join(cells)}"
        "</div>"
        "</section>"
    )


def _evidence_card(label: str, value: str, detail: str) -> str:
    return (
        '<div class="card evidence-card">'
        f"<span>{_h(label)}</span>"
        f"<strong>{_h(value or '-')}</strong>"
        f"<p>{detail or '-'}</p>"
        "</div>"
    )


def _ship_panel(latest: dict[str, Any]) -> str:
    if not latest:
        return ""
    raw_summary = latest.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    cases = int(summary.get("cases") or 0)
    blocking = _blocking_count(summary)
    changed = _changed_count(summary)
    if cases <= 0:
        status = "No cases"
        tone = "neutral"
        guidance = "Generate a suite, then run eval to populate the dashboard."
    elif blocking:
        status = "Blocked"
        tone = "blocked"
        guidance = "Fix blocking cases or mark intentional changes before shipping."
    elif changed:
        status = "Review needed"
        tone = "review"
        guidance = "Review changed cases before accepting this prompt version."
    else:
        status = "Ready within checks"
        tone = "ready"
        guidance = "No blocking or changed cases were detected by configured checks."

    decision = latest.get("decision")
    decision_text = ""
    if isinstance(decision, dict):
        decision_text = str(decision.get("recommended_action") or "")
    review_command = _ship_review_command(latest)
    decision_html = f'<p class="decision">{_h(decision_text)}</p>' if decision_text else ""
    review_html = (
        '<p class="review-command"><span>Review command</span>'
        f"<code>{_h(review_command)}</code></p>"
        if review_command
        else ""
    )
    return (
        f'<section class="panel ship {tone}">'
        '<div class="section-title">'
        "<div>"
        "<h2>Ship Readiness</h2>"
        f"<p>{_h(guidance)}</p>"
        "</div>"
        f'<strong class="ship-status">{_h(status)}</strong>'
        "</div>"
        '<div class="cards compact">'
        f'<div class="card"><span>Blocking</span><strong>{blocking}</strong></div>'
        f'<div class="card"><span>Changed</span><strong>{changed}</strong></div>'
        f'<div class="card"><span>Total cases</span><strong>{cases}</strong></div>'
        "</div>"
        f"{decision_html}"
        f"{review_html}"
        "</section>"
    )


def _ship_review_command(latest: dict[str, Any]) -> str:
    review_cases = latest.get("review_cases")
    if not isinstance(review_cases, list):
        return ""
    for item in review_cases:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {"regression", "missing", "changed"}:
            continue
        suite = str(item.get("suite") or "").strip()
        case_id = str(item.get("case_id") or "").strip()
        if suite and case_id:
            return f'redline mark {suite} {case_id} --status expected --note "intentional change"'
    return ""


def _trust_panel(trust: dict[str, Any]) -> str:
    cases = int(trust.get("cases") or 0)
    confidence = trust.get("confidence")
    signal = trust.get("signal")
    methodology = trust.get("methodology")
    suite_coverage = trust.get("suite_coverage")
    if cases <= 0 or not isinstance(confidence, dict) or not isinstance(signal, dict):
        return ""
    confidence_pills = _count_pills(confidence)
    signal_pills = _count_pills(signal)
    methodology_pills = _count_pills(methodology) if isinstance(methodology, dict) else ""
    coverage_pills = _count_pills(suite_coverage) if isinstance(suite_coverage, dict) else ""
    if not confidence_pills and not signal_pills:
        return ""
    return (
        '<section class="panel trust-review">'
        "<h2>Trust Signals</h2>"
        '<div class="trust-grid">'
        f'<div><span>Confidence</span><p>{confidence_pills or "-"}</p></div>'
        f'<div><span>Signal</span><p>{signal_pills or "-"}</p></div>'
        f'<div><span>Methodology</span><p>{methodology_pills or "-"}</p></div>'
        f'<div><span>Suite coverage</span><p>{coverage_pills or "-"}</p></div>'
        "</div>"
        "</section>"
    )


def _checkpoint_panel(checkpoint: dict[str, Any]) -> str:
    if not checkpoint:
        return ""
    status = "OK" if checkpoint.get("ok") else "FAILED"
    entries = int(checkpoint.get("entries") or 0)
    signed = int(checkpoint.get("signed_entries") or 0)
    unsigned = int(checkpoint.get("unsigned_entries") or 0)
    last_hash = str(checkpoint.get("last_hash") or "")
    path = str(checkpoint.get("path") or "")
    events = checkpoint.get("events_by_type")
    event_pills = _count_pills(events) if isinstance(events, dict) else ""
    return (
        '<section class="panel trust-review">'
        "<h2>Audit Checkpoint</h2>"
        '<div class="trust-grid">'
        f"<div><span>Status</span><p>{_h(status)}</p></div>"
        f"<div><span>Entries</span><p>{entries} signed {signed} unsigned {unsigned}</p></div>"
        f"<div><span>Last hash</span><p><code>{_h(last_hash or '-')}</code></p></div>"
        f"<div><span>Path</span><p><code>{_h(path or '-')}</code></p></div>"
        f"<div><span>Events</span><p>{event_pills or '-'}</p></div>"
        "</div>"
        "</section>"
    )


def _count_pills(counts: dict[Any, Any]) -> str:
    rows = []
    for key, value in sorted(counts.items(), key=lambda item: str(item[0])):
        rows.append(
            f'<span class="pill">{_h(str(key).replace("_", " "))} {int(value or 0)}</span>'
        )
    return "".join(rows)


def _methodology_label(value: dict[str, Any]) -> str:
    name = str(value.get("name") or "").strip()
    version = str(value.get("version") or "").strip()
    if name and version:
        return f"{name} ({version})"
    return version or name


def _suite_coverage_label(value: dict[str, Any]) -> str:
    case_coverage = _percent_value(value.get("case_coverage"))
    cluster_coverage = _percent_value(value.get("cluster_coverage"))
    cases = value.get("cases")
    pairs = value.get("unique_prompt_response_pairs")
    clusters = value.get("clusters")
    parts = []
    if cases is not None and pairs is not None and case_coverage:
        parts.append(f"cases {cases}/{pairs} ({case_coverage})")
    if isinstance(clusters, int) and isinstance(value.get("cluster_coverage"), int | float) and cluster_coverage:
        covered_clusters = round(clusters * float(value["cluster_coverage"]))
        parts.append(f"groups {covered_clusters}/{clusters} ({cluster_coverage})")
    return "; ".join(parts)


def _percent_value(value: object) -> str:
    if not isinstance(value, int | float):
        return ""
    return f"{value * 100:.1f}%"


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
            f"<td>{int(item.get('provenance') or 0)}</td>"
            f"<td>{_owner_command_cell(str(item.get('command') or ''))}</td>"
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
        "<thead><tr><th>Owner</th><th>Blocking</th><th>Changed</th><th>Rule provenance</th><th>First review</th><th>Total</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _owner_command_cell(command: str) -> str:
    if not command:
        return "-"
    return f"<code>{_h(command)}</code>"


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
    cluster_html = _trend_cluster_diagnosis(trend.get("clusters"))
    return (
        f'<section class="notice trend {_trend_class(direction)}">'
        "<h2>Trend</h2>"
        f"<p><strong>{_h(direction)}</strong>: {_h(summary)}</p>"
        f"<p>{_h(recommendation)}</p>"
        f"{cluster_html}"
        "</section>"
    )


def _trend_cluster_diagnosis(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    rows = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        latest = item.get("latest")
        latest_counts = latest if isinstance(latest, dict) else {}
        label = str(item.get("label") or item.get("cluster") or "unclustered")
        blocking_delta = _safe_int(item.get("blocking_delta"))
        changed_delta = _safe_int(item.get("changed_delta"))
        latest_blocking = _safe_int(latest_counts.get("blocking"))
        rows.append(
            "<li>"
            f"<strong>{_h(label)}</strong>: "
            f"blocking {_h(_signed(blocking_delta))} "
            f"(latest {latest_blocking}), changed {_h(_signed(changed_delta))}"
            "</li>"
        )
    if not rows:
        return ""
    return "<h3>Behavior group diagnosis</h3><ul>" + "".join(rows) + "</ul>"


def _trend_class(direction: str) -> str:
    normalized = direction.lower().replace(" ", "-")
    if normalized in {"worse", "better", "flat", "baseline", "more-changed", "less-changed"}:
        return normalized
    return "unknown"


def _signed(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def _benchmark_panel(benchmarks: list[Any], *, output_path: str | Path | None) -> str:
    if not benchmarks:
        return ""
    rows = []
    for item in benchmarks:
        if not isinstance(item, dict):
            continue
        local = item.get("local_measurement")
        local_text = "-"
        if isinstance(local, dict) and local:
            local_text = (
                f"{_elapsed(local.get('seconds'))} for "
                f"{_safe_int(local.get('cases'))} cases "
                f"({_rate(local.get('cases_per_second'))} cases/sec)"
            )
        budget = "PASS" if item.get("within_budget") else "FAIL"
        links = _links(
            [
                ("Markdown", str(item.get("markdown_path") or "")),
                ("JSON", str(item.get("path") or "")),
            ],
            output_path=output_path,
        )
        rows.append(
            "<tr>"
            f"<td><strong>{_h(str(item.get('name') or '-'))}</strong><span>{_h(str(item.get('suite') or '-'))}</span></td>"
            f"<td>{_safe_int(item.get('cases'))}</td>"
            f"<td>{_safe_int(item.get('workers'))}</td>"
            f"<td>{_duration(item.get('worst_case_seconds'))}</td>"
            f"<td>{_h(local_text)}</td>"
            f"<td><span class=\"pill {'better' if item.get('within_budget') else 'worse'}\">{_h(budget)}</span></td>"
            f"<td>{links}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<section class="panel benchmark-evidence">'
        "<h2>Benchmark Evidence</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Benchmark</th><th>Cases</th><th>Workers</th><th>Worst Case</th><th>Local Check</th><th>Budget</th><th>Links</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


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


def _notices(notices: list[Any]) -> str:
    rows = []
    for notice in notices:
        if not isinstance(notice, dict):
            continue
        title = str(notice.get("title") or "Dashboard notice")
        message = str(notice.get("message") or "")
        command = str(notice.get("command") or "")
        command_html = f"<p><code>{_h(command)}</code></p>" if command else ""
        rows.append(
            '<section class="notice dashboard-notice">'
            f"<h2>{_h(title)}</h2>"
            f"<p>{_h(message)}</p>"
            f"{command_html}"
            "</section>"
        )
    return "".join(rows)


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
        raw_review = report.get("review")
        review = raw_review if isinstance(raw_review, dict) else {}
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
            f"<td>{_review_pills(review)}</td>"
            f"<td>{_h(str(decision.get('recommended_action') or '-'))}</td>"
            f"<td>{links}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        "<h2>Reports</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Report</th><th>Summary</th><th>Review</th><th>Decision</th><th>Links</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _prompt_groups_panel(prompt_groups: Any) -> str:
    if not isinstance(prompt_groups, list) or not prompt_groups:
        return ""
    rows = []
    for item in prompt_groups:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        rows.append(
            "<tr>"
            f"<td><strong>{_h(str(item.get('feature') or '-'))}</strong></td>"
            f"<td>{int(item.get('prompt_count') or 0)}</td>"
            f"<td>{_summary_pills(summary if isinstance(summary, dict) else {})}</td>"
            f"<td>{_h(str(item.get('action') or '-'))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<section class="panel prompt-groups">'
        "<h2>Feature Summary</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Feature</th><th>Prompts</th><th>Summary</th><th>Action</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _prompt_evals_panel(prompt_evals: Any) -> str:
    if not isinstance(prompt_evals, list) or not prompt_evals:
        return ""
    rows = []
    for item in prompt_evals:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        decision = item.get("decision")
        decision_text = ""
        if isinstance(decision, dict):
            decision_text = str(decision.get("recommended_action") or "")
        rows.append(
            "<tr>"
            f"<td><strong>{_h(str(item.get('id') or '-'))}</strong><span>{_h(str(item.get('prompt') or '-'))}</span></td>"
            f"<td><code>{_h(str(item.get('suite') or '-'))}</code></td>"
            f"<td>{_summary_pills(summary if isinstance(summary, dict) else {})}</td>"
            f"<td>{_h(decision_text or '-')}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<section class="panel prompt-evals">'
        "<h2>Prompt Evals</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Prompt</th><th>Suite</th><th>Summary</th><th>Decision</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _review_queue_panel(review_cases: Any) -> str:
    if not isinstance(review_cases, list) or not review_cases:
        return ""
    rows = []
    for item in review_cases:
        if not isinstance(item, dict):
            continue
        trust = " / ".join(
            value
            for value in (
                str(item.get("confidence") or ""),
                str(item.get("signal") or ""),
            )
            if value
        )
        context = " ".join(
            value
            for value in (
                str(item.get("prompt_path") or ""),
                str(item.get("suite") or ""),
            )
            if value
        )
        rows.append(
            "<tr>"
            f"<td><span class=\"pill { _h(str(item.get('status') or '')) }\">{_h(str(item.get('status') or '-'))}</span></td>"
            f"<td><strong>{_h(str(item.get('case_id') or '-'))}</strong><span>{_h(_preview(str(item.get('prompt') or '')))}</span></td>"
            f"<td>{_h(str(item.get('reason') or '-'))}</td>"
            f"<td>{_h(str(item.get('owner') or '-'))}</td>"
            f"<td>{_h(trust or '-')}<span>{_h(context)}</span></td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        '<section class="panel review-queue">'
        "<h2>Review Queue</h2>"
        '<div class="table-wrap">'
        "<table>"
        "<thead><tr><th>Status</th><th>Case</th><th>Reason</th><th>Owner</th><th>Signal</th></tr></thead>"
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


def _review_pills(review: dict[str, Any]) -> str:
    reviewable = int(review.get("reviewable") or 0)
    if reviewable <= 0:
        return "-"
    pills = []
    for key in ("blocking", "changed"):
        value = int(review.get(key) or 0)
        if value:
            pills.append(f'<span class="pill {key}">{_h(key)} {value}</span>')
    return "".join(pills) if pills else "-"


def _preview(text: str, limit: int = 96) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


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


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return _safe_float(value)


def _duration(value: Any) -> str:
    seconds = int(round(_safe_float(value)))
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def _elapsed(value: Any) -> str:
    seconds = _safe_float(value)
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    return _duration(seconds)


def _rate(value: Any) -> str:
    number = _safe_float(value)
    if number >= 100:
        return f"{number:.0f}"
    if number >= 10:
        return f"{number:.1f}"
    return f"{number:.2f}"


_APP_DASHBOARD_SCRIPT = """
<script>
(function () {
  const labels = {
    dashboard: "Dashboard",
    workflow: "Workflow",
    regressions: "Regressions",
    suites: "Eval suites",
    logs: "Log import",
    compare: "Prompt diff",
    history: "Run history",
    alerts: "Alerts",
    integrations: "Integrations",
    settings: "Settings"
  };
  const badges = {
    dashboard: ["Overview", "badge-blue"],
    workflow: ["Workflow", "badge-blue"],
    regressions: ["Review", "badge-crit"],
    suites: ["Suites", "badge-blue"],
    logs: ["Import", "badge-blue"],
    compare: ["Diff", "badge-warn"],
    history: ["History", "badge-blue"],
    alerts: ["Alerts", "badge-crit"],
    integrations: ["Ready", "badge-pass"],
    settings: ["Local", "badge-pass"]
  };
  document.querySelectorAll("[data-nav], [data-nav-link]").forEach((button) => {
    button.addEventListener("click", (event) => {
      const key = button.getAttribute("data-nav") || button.getAttribute("data-nav-link");
      if (!key) return;
      if (button.hasAttribute("data-nav-link")) event.preventDefault();
      document.querySelectorAll("[data-nav]").forEach((item) => item.classList.remove("active"));
      const navItem = document.querySelector('[data-nav="' + key + '"]');
      if (navItem) navItem.classList.add("active");
      document.querySelectorAll(".screen").forEach((screen) => screen.classList.remove("active"));
      const screen = document.getElementById("s-" + key);
      if (screen) screen.classList.add("active");
      const crumb = document.getElementById("crumb");
      if (crumb) crumb.innerHTML = "<b>" + (labels[key] || "Dashboard") + "</b>";
      const badge = document.getElementById("top-badge");
      if (badge && badges[key]) {
        badge.textContent = badges[key][0];
        badge.className = "top-badge " + badges[key][1];
      }
    });
  });
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy") || "";
      const previous = button.textContent || "Copy";
      const setCopied = () => {
        button.textContent = "Copied";
        button.classList.add("copied");
        window.setTimeout(() => {
          button.textContent = previous;
          button.classList.remove("copied");
        }, 1200);
      };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
          setCopied();
          return;
        }
      } catch (_error) {
        // Use a DOM fallback below for file:// dashboards and locked-down browsers.
      }
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "readonly");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); } catch (_error) {}
      document.body.removeChild(area);
      setCopied();
    });
  });
})();
</script>
"""


_APP_DASHBOARD_CSS = """
:root {
  color-scheme: dark;
  --bg0: #0e0f11;
  --bg1: #141519;
  --bg2: #1c1d22;
  --bg3: #23242b;
  --border: #2a2b33;
  --border2: #32333d;
  --text0: #f0f0f2;
  --text1: #b8b9c6;
  --text2: #6e6f82;
  --text3: #44455a;
  --green: #3ecf8e;
  --green-bg: #0d2a1f;
  --green-border: #1a4a32;
  --amber: #f5a623;
  --amber-bg: #2a1f08;
  --amber-border: #4a3510;
  --red: #f06060;
  --red-bg: #2a0e0e;
  --red-border: #4a1a1a;
  --blue: #60a5fa;
  --blue-bg: #0e1a2a;
  --blue-border: #1a3050;
  --accent: #e24b4a;
  --accent-bg: #2a0e0e;
  --accent-border: #5a1a1a;
  --radius: 6px;
  --radius-lg: 10px;
}
* { box-sizing: border-box; }
html, body { min-height: 100%; }
body {
  margin: 0;
  background: var(--bg0);
  color: var(--text0);
  font: 13px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
body::-webkit-scrollbar, .pane::-webkit-scrollbar, .sidebar::-webkit-scrollbar { width: 5px; height: 5px; }
body::-webkit-scrollbar-track, .pane::-webkit-scrollbar-track, .sidebar::-webkit-scrollbar-track { background: var(--bg1); }
body::-webkit-scrollbar-thumb, .pane::-webkit-scrollbar-thumb, .sidebar::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 10px; }
a { color: var(--blue); text-decoration: none; font-weight: 600; margin-right: 10px; }
code {
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  padding: 2px 5px;
  background: var(--bg3);
  color: var(--text0);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
.app {
  height: 100vh;
  overflow: hidden;
  display: grid;
  grid-template-columns: 176px minmax(0, 1fr);
}
.sidebar {
  background: var(--bg1);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.sb-logo {
  padding: 16px 16px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 9px;
}
.sb-logo-icon {
  width: 28px;
  height: 28px;
  background: var(--accent);
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
  font-size: 15px;
  font-weight: 700;
}
.sb-logo-name { font-size: 14px; font-weight: 650; color: var(--text0); letter-spacing: 0; }
.sb-logo-version { color: var(--text2); font-size: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.sb-section {
  padding: 14px 16px 4px;
  color: var(--text3);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
}
.sb-item {
  width: 100%;
  border: 0;
  border-left: 2px solid transparent;
  padding: 7px 14px 7px 12px;
  color: var(--text2);
  background: transparent;
  text-align: left;
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
  display: flex;
  align-items: center;
  gap: 9px;
  transition: all .12s;
}
.sb-item:hover, .sb-item.active {
  color: var(--text0);
  background: var(--bg2);
}
.sb-item.active {
  border-left-color: var(--accent);
  font-weight: 600;
}
.sb-spacer { flex: 1; }
.sb-bottom {
  padding: 10px 14px 14px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}
.sb-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.sb-user-name { font-size: 12px; font-weight: 600; color: var(--text1); }
.sb-user-role { font-size: 10px; color: var(--text2); }
.svg-ico {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  display: inline-block;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
  vertical-align: -2px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
}
.dot.red { background: var(--red); }
.dot.amber { background: var(--amber); }
.dot.green { background: var(--green); }
.main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.topbar {
  background: var(--bg1);
  border-bottom: 1px solid var(--border);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.crumb { font-size: 12px; color: var(--text2); }
.crumb b { color: var(--text0); font-weight: 600; }
.top-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
}
.badge-crit { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }
.badge-warn { background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-border); }
.badge-pass { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
.badge-blue { background: var(--blue-bg); color: var(--blue); border: 1px solid var(--blue-border); }
.btn {
  font-size: 12px;
  padding: 5px 13px;
  border-radius: var(--radius);
  border: 1px solid var(--border2);
  background: var(--bg2);
  color: var(--text1);
  cursor: pointer;
  transition: all .12s;
  display: flex;
  align-items: center;
  gap: 5px;
}
.btn:hover { color: var(--text0); background: var(--bg3); }
.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); font-weight: 600; }
.btn-primary:hover { opacity: .9; }
.pane {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: var(--bg0);
}
.screen { display: none; flex-direction: column; gap: 14px; }
.screen.active { display: flex; }
.metric-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.metric-card, .card, .alert {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.metric-card { padding: 12px 14px; }
.metric-label, .metric-sub, .muted, .t-sub, .kv-key { color: var(--text2); }
.metric-label {
  font-size: 10px;
  color: var(--text2);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: 5px;
}
.metric-val {
  font-size: 22px;
  font-weight: 650;
  color: var(--text0);
  line-height: 1;
}
.metric-val.green { color: var(--green); }
.metric-val.amber { color: var(--amber); }
.metric-val.red { color: var(--red); }
.metric-sub { font-size: 11px; margin-top: 4px; }
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.hero-grid { grid-template-columns: 1.2fr .8fr; }
.card { margin-bottom: 16px; overflow: hidden; }
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 10px;
  border-bottom: 1px solid var(--border);
}
.card-title {
  font-size: 12px;
  font-weight: 650;
  color: var(--text0);
  display: flex;
  align-items: center;
  gap: 7px;
}
.card-meta { font-size: 11px; color: var(--text2); display: flex; align-items: center; gap: 6px; }
.card-body { padding: 12px 14px; }
.decision { font-size: 16px; font-weight: 650; margin-bottom: 12px; }
.alert {
  padding: 13px 16px;
  margin: 16px 0;
}
.alert-bar {
  border-radius: var(--radius);
  padding: 10px 14px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 12px;
  line-height: 1.5;
}
.alert-red { background: var(--red-bg); border: 1px solid var(--red-border); color: var(--red); }
.alert-amber { background: var(--amber-bg); border: 1px solid var(--amber-border); color: var(--amber); }
.alert-green { background: var(--green-bg); border: 1px solid var(--green-border); color: var(--green); }
.alert-blue { background: var(--blue-bg); border: 1px solid var(--blue-border); color: var(--blue); }
.alert-bar b { font-weight: 650; }
.t-row, .kv-row, .log-row, .check-row, .setting-row, .int-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.t-row:last-child, .kv-row:last-child, .log-row:last-child, .check-row:last-child, .setting-row:last-child, .int-row:last-child { border-bottom: 0; }
.t-info { flex: 1; min-width: 0; }
.t-name { font-size: 12px; font-weight: 600; color: var(--text0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.t-sub { font-size: 11px; color: var(--text2); overflow-wrap: anywhere; }
.t-right { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.t-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius);
  background: var(--bg3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text2);
  flex-shrink: 0;
}
.t-icon.red, .reg-icon.red { background: var(--red-bg); color: var(--red); }
.t-icon.amber, .reg-icon.amber { background: var(--amber-bg); color: var(--amber); }
.t-icon.green, .reg-icon.green { background: var(--green-bg); color: var(--green); }
.t-icon.blue, .reg-icon.blue { background: var(--blue-bg); color: var(--blue); }
.reg-row {
  display: flex;
  align-items: flex-start;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  gap: 10px;
}
.reg-row:last-child { border-bottom: none; }
.reg-icon {
  width: 30px;
  height: 30px;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
  font-weight: 700;
}
.reg-info { flex: 1; min-width: 0; }
.reg-name { font-size: 12px; font-weight: 600; color: var(--text0); overflow-wrap: anywhere; }
.reg-sub { font-size: 11px; color: var(--text2); margin-top: 1px; overflow-wrap: anywhere; }
.prog-bar {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  margin-top: 6px;
  overflow: hidden;
}
.prog-fill { height: 100%; border-radius: 2px; background: var(--text3); }
.prog-fill.red { background: var(--red); }
.prog-fill.amber { background: var(--amber); }
.prog-fill.green { background: var(--green); }
.check-left {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text0);
}
.chip, .badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
}
.badge {
  margin-left: auto;
  padding: 1px 6px;
  font-size: 10px;
}
.red { color: var(--red); }
.amber { color: var(--amber); }
.green { color: var(--green); }
.blue { color: var(--blue); }
.chip-pass, .badge.green { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
.chip-warn, .badge.amber { background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber-border); }
.chip-fail, .badge.red { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }
.chip-blue { background: var(--blue-bg); color: var(--blue); border: 1px solid var(--blue-border); }
.chip-idle { background: var(--bg3); color: var(--text2); border: 1px solid var(--border); }
.kv-key { font-size: 12px; }
.kv-val { font-size: 12px; color: var(--text0); font-weight: 600; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.kv-val.red { color: var(--red); }
.kv-val.green { color: var(--green); }
.kv-val.amber { color: var(--amber); }
.upload-zone {
  border: 1.5px dashed var(--border2);
  border-radius: var(--radius-lg);
  padding: 28px 20px;
  margin-bottom: 12px;
  text-align: center;
}
.upload-zone p { color: var(--text2); margin-top: 8px; font-size: 12px; }
.log-row {
  align-items: flex-start;
  justify-content: flex-start;
}
.log-row span:first-child {
  width: 24px;
  height: 24px;
  border-radius: var(--radius);
  background: var(--bg3);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text2);
  flex-shrink: 0;
  font-weight: 700;
}
.log-row p { margin: 0; color: var(--text1); }
.diff-block {
  background: var(--bg1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.8;
}
.diff-del, .diff-add, .diff-ctx {
  display: block;
  padding: 1px 6px;
  border-radius: 3px;
  margin: 1px 0;
}
.diff-del { background: #2a0d0d; color: var(--red); }
.diff-add { background: #0d2a1a; color: var(--green); }
.diff-ctx { color: var(--text1); }
.command-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.command-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--blue);
  border-radius: var(--radius-lg);
  padding: 12px;
}
.command-card.featured {
  background: linear-gradient(180deg, rgba(96, 165, 250, .08), rgba(96, 165, 250, .02)), var(--bg2);
}
.command-green { border-left-color: var(--green); }
.command-amber { border-left-color: var(--amber); }
.command-red { border-left-color: var(--red); }
.command-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}
.command-stage {
  width: 24px;
  height: 24px;
  border-radius: var(--radius);
  background: var(--bg3);
  color: var(--text1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.command-title {
  color: var(--text0);
  font-size: 12px;
  font-weight: 650;
}
.command-body {
  color: var(--text2);
  font-size: 11px;
  margin-top: 2px;
}
.command-row {
  margin-top: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}
.command-row code {
  display: block;
  overflow-x: auto;
  white-space: nowrap;
}
.copy-btn {
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  background: var(--bg3);
  color: var(--text1);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 650;
  padding: 5px 9px;
}
.copy-btn:hover, .copy-btn.copied {
  border-color: var(--green-border);
  color: var(--green);
  background: var(--green-bg);
}
.chart-svg {
  width: 100%;
  height: 150px;
  display: block;
}
.chart-svg line {
  stroke: var(--border);
  stroke-width: 1;
}
.chart-svg polyline {
  fill: none;
  stroke: var(--green);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.chart-svg circle {
  fill: var(--green);
  stroke: var(--bg2);
  stroke-width: 2;
}
.chart-legend {
  display: flex;
  gap: 14px;
  padding-top: 8px;
  color: var(--text2);
  font-size: 10px;
}
.legend {
  width: 12px;
  height: 2px;
  display: inline-block;
  border-radius: 1px;
  margin-right: 5px;
  vertical-align: middle;
}
.legend.pass { background: var(--green); }
.legend.block { background: var(--red); }
.trust-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  border-top: 1px solid var(--border);
  margin-top: 12px;
  padding-top: 12px;
}
.trust-strip span {
  display: block;
  color: var(--text2);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.trust-strip strong {
  display: block;
  margin-top: 3px;
  color: var(--text0);
  font-size: 12px;
}
.pill {
  display: inline-block;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 8px;
  margin: 0 6px 6px 0;
  background: var(--bg3);
  font-size: 12px;
}
.regression, .missing, .worse { color: var(--red); border-color: var(--red-border); background: var(--red-bg); }
.changed { color: var(--amber); border-color: var(--amber-border); background: var(--amber-bg); }
.better, .resolved { color: var(--green); border-color: var(--green-border); background: var(--green-bg); }
.empty p { color: var(--text2); }
.row-note {
  margin: 10px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  font-size: 11px;
}
.int-logo {
  width: 32px;
  height: 32px;
  border-radius: var(--radius);
  background: var(--bg3);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--text2);
  flex-shrink: 0;
}
.setting-row { padding: 9px 0; }
.setting-label { font-size: 12px; color: var(--text0); font-weight: 600; }
.setting-sub { font-size: 11px; color: var(--text2); overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .metric-row { grid-template-columns: repeat(2, 1fr); }
  .two-col, .hero-grid, .trust-strip { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .app {
    display: block;
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }
  .sidebar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 4px;
    overflow-x: auto;
    overflow-y: hidden;
    border-right: 0;
    border-bottom: 1px solid var(--border);
    padding: 6px 8px;
  }
  .sb-logo {
    padding: 0 8px 0 0;
    border-bottom: 0;
    flex-shrink: 0;
  }
  .sb-logo-icon { width: 26px; height: 26px; }
  .sb-logo-version, .sb-section, .sb-bottom { display: none; }
  .sb-item {
    width: auto;
    flex: 0 0 auto;
    border-left: 0;
    border-bottom: 2px solid transparent;
    border-radius: var(--radius);
    padding: 7px 10px;
    white-space: nowrap;
  }
  .sb-item.active {
    border-left-color: transparent;
    border-bottom-color: var(--accent);
  }
  .main {
    display: block;
    overflow: visible;
  }
  .topbar { padding: 10px 12px; }
  .topbar-right .chip { display: none; }
  .pane {
    overflow: visible;
    padding: 12px;
  }
  .metric-row { grid-template-columns: 1fr; }
}
"""


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
.section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}
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
.cards.compact {
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
}
.trust-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
.trust-grid span { display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; }
.trust-grid p { margin-top: 8px; }
.trust-grid code { overflow-wrap: anywhere; }
.card {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: #fbfcfd;
}
.card span, td span { display: block; color: var(--muted); font-size: 12px; }
.card strong { display: block; font-size: 26px; margin-top: 4px; }
.evidence-card strong { font-size: 16px; overflow-wrap: anywhere; }
.evidence-card p { margin-top: 8px; color: var(--muted); overflow-wrap: anywhere; }
.ship {
  border-left: 4px solid var(--accent);
}
.ship.blocked { border-left-color: var(--danger); }
.ship.review { border-left-color: var(--warn); }
.ship.ready { border-left-color: var(--ok); }
.ship-status {
  border-radius: 999px;
  padding: 6px 12px;
  white-space: nowrap;
  color: #fff;
  background: var(--accent);
}
.ship.blocked .ship-status { background: var(--danger); }
.ship.review .ship-status { background: var(--warn); }
.ship.ready .ship-status { background: var(--ok); }
.decision {
  margin-top: 14px;
  color: var(--muted);
}
.review-command {
  margin-top: 14px;
  border-top: 1px solid var(--line);
  padding-top: 14px;
}
.review-command span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}
.review-command code {
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
}
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
  .section-title { display: block; }
  .ship-status { display: inline-block; margin-top: 12px; }
  th, td { padding: 10px 8px; }
}
"""
