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
                "summary": _summary_counts(summary),
                "decision": report.get("decision") if isinstance(report.get("decision"), dict) else {},
                "owners": _report_owner_review(report.get("diffs"), suite_path=str(report.get("suite") or "")),
                "trust": _report_trust_summary(report.get("diffs")),
                "review": _report_review_summary(report.get("diffs")),
                "review_cases": _report_review_cases(report.get("diffs")),
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
                "redline benchmark redline-suite.json --measure-local "
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


def _report_review_cases(diffs: Any, *, limit: int = 12) -> list[dict[str, Any]]:
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
                "suite": str(item.get("suite") or ""),
            }
        )
    return rows[:limit]


def _dashboard_trust_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    cases = 0
    confidence: dict[str, int] = {}
    signal: dict[str, int] = {}
    for report in reports:
        trust = report.get("trust")
        if not isinstance(trust, dict):
            continue
        cases += int(trust.get("cases") or 0)
        _merge_counts(confidence, trust.get("confidence"))
        _merge_counts(signal, trust.get("signal"))
    return {
        "cases": cases,
        "confidence": dict(sorted(confidence.items())),
        "signal": dict(sorted(signal.items())),
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
    if cases <= 0 or not isinstance(confidence, dict) or not isinstance(signal, dict):
        return ""
    confidence_pills = _count_pills(confidence)
    signal_pills = _count_pills(signal)
    if not confidence_pills and not signal_pills:
        return ""
    return (
        '<section class="panel trust-review">'
        "<h2>Trust Signals</h2>"
        '<div class="trust-grid">'
        f'<div><span>Confidence</span><p>{confidence_pills or "-"}</p></div>'
        f'<div><span>Signal</span><p>{signal_pills or "-"}</p></div>'
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
    return "<h3>Cluster diagnosis</h3><ul>" + "".join(rows) + "</ul>"


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
