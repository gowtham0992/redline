from __future__ import annotations

from pathlib import Path
from typing import Any

from .dashboard import build_dashboard
from .diff import TRUST_SCOPE
from .doctor import doctor_report


def build_project_status(
    *,
    config_path: str,
    config: dict[str, Any],
    suite: dict[str, Any] | None,
    suite_error: str | None = None,
    suite_git_ignored: bool = False,
    reports_dir: str | Path = ".redline/reports",
    history_path: str | Path = ".redline/history.jsonl",
    checkpoint_path: str | Path = ".redline/audit-checkpoint.json",
    limit: int = 20,
) -> dict[str, Any]:
    doctor = doctor_report(
        config_path=config_path,
        config=config,
        suite=suite,
        suite_error=suite_error,
        suite_git_ignored=suite_git_ignored,
    )
    dashboard = build_dashboard(
        reports_dir=reports_dir,
        history_path=history_path,
        checkpoint_path=checkpoint_path,
        limit=limit,
    )
    latest = _first_dict(dashboard.get("reports"))
    summary = _dict(latest.get("summary"))
    review_cases = _list(latest.get("review_cases"))
    first_review_case = _first_dict(review_cases)
    blocking = _count(summary, "regression") + _count(summary, "missing")
    changed = _count(summary, "changed")
    suite_path = str(config.get("suite") or "redline-suite.json")
    state, message, next_command = _state_and_next(
        doctor=doctor,
        latest=latest,
        summary=summary,
        review_cases=review_cases,
        blocking=blocking,
        changed=changed,
        suite_path=suite_path,
        reports_dir=str(reports_dir),
        history_path=str(history_path),
    )
    return {
        "version": "0.1",
        "state": state,
        "message": message,
        "next_command": next_command,
        "app_command": _app_command(
            reports_dir=str(reports_dir),
            history_path=str(history_path),
            checkpoint_path=str(checkpoint_path),
        ),
        "config_path": config_path,
        "suite_path": suite_path,
        "reports_dir": str(reports_dir),
        "history_path": str(history_path),
        "checkpoint_path": str(checkpoint_path),
        "doctor": {
            "errors": int(doctor.get("errors") or 0),
            "warnings": int(doctor.get("warnings") or 0),
            "checks": doctor.get("checks") if isinstance(doctor.get("checks"), list) else [],
            "next_steps": doctor.get("next_steps") if isinstance(doctor.get("next_steps"), list) else [],
        },
        "reports": len(_list(dashboard.get("reports"))),
        "history": len(_list(dashboard.get("history"))),
        "benchmarks": len(_list(dashboard.get("benchmarks"))),
        "checkpoint": bool(dashboard.get("checkpoint")),
        "latest_report": latest,
        "first_review_case": _status_review_case(first_review_case, fallback_suite=suite_path),
        "summary": summary,
        "blocking": blocking,
        "changed": changed,
        "scope": TRUST_SCOPE,
    }


def format_project_status(status: dict[str, Any]) -> str:
    latest = _dict(status.get("latest_report"))
    summary = _dict(status.get("summary"))
    doctor = _dict(status.get("doctor"))
    checks = _list(doctor.get("checks"))
    first_review_case = _dict(status.get("first_review_case"))
    lines = [
        "redline status",
        "",
        f"State: {str(status.get('state') or '').upper()} - {status.get('message')}",
        f"Next:  {status.get('next_command')}",
        f"App:   {status.get('app_command')}",
        "",
        "Evidence",
        f"- Config: {_check_line(checks, 'config')}",
        f"- Suite: {_check_line(checks, 'suite')}",
        f"- Replay: {_check_line(checks, 'replay')}",
        f"- Reports: {status.get('reports')} in {status.get('reports_dir')}",
        f"- History: {status.get('history')} in {status.get('history_path')}",
        f"- Benchmarks: {status.get('benchmarks')}",
        f"- Audit checkpoint: {'yes' if status.get('checkpoint') else 'no'}",
        f"- Doctor: errors={doctor.get('errors', 0)} warnings={doctor.get('warnings', 0)}",
    ]
    if latest:
        lines.extend(
            [
                "",
                "Latest report",
                f"- File: {latest.get('path')}",
                f"- Summary: {_summary_line(summary)}",
                f"- Decision: {_decision_line(latest)}",
            ]
        )
        if first_review_case:
            lines.extend(
                [
                    "",
                    "First review case",
                    f"- Case: {first_review_case.get('case_id')} ({first_review_case.get('status')})",
                    f"- Reason: {first_review_case.get('reason') or 'review report details'}",
                    f"- Impact: {first_review_case.get('impact') or 'review the case before shipping'}",
                    f"- Command: {first_review_case.get('command')}",
                ]
            )
    else:
        lines.extend(["", "Latest report", "- No redline report found yet."])
    lines.extend(["", "Trust boundary", f"- {status.get('scope') or TRUST_SCOPE}"])
    next_steps = _list(doctor.get("next_steps"))
    if next_steps:
        lines.extend(["", "Doctor next steps"])
        lines.extend(f"- {step}" for step in next_steps)
    return "\n".join(str(line) for line in lines) + "\n"


def _state_and_next(
    *,
    doctor: dict[str, Any],
    latest: dict[str, Any],
    summary: dict[str, Any],
    review_cases: list[Any],
    blocking: int,
    changed: int,
    suite_path: str,
    reports_dir: str,
    history_path: str,
) -> tuple[str, str, str]:
    checks = {str(check.get("name") or ""): check for check in _list(doctor.get("checks")) if isinstance(check, dict)}
    doctor_steps = [str(step) for step in _list(doctor.get("next_steps")) if str(step).strip()]
    config = _dict(checks.get("config"))
    suite = _dict(checks.get("suite"))
    if config.get("status") == "warn":
        return "setup", "project is not initialized", _first_step(doctor_steps, "redline init --runner stdio --copy-runner")
    if suite.get("status") in {"warn", "error"}:
        return "setup", "no usable suite baseline yet", _first_step(
            doctor_steps,
            f"redline suite path/to/log.jsonl --out {suite_path}",
        )
    if not latest:
        return "ready", "suite exists; run the first eval or diff", "redline eval --compact"
    first_case = _first_dict(review_cases)
    case_command = _case_command(first_case, fallback_suite=suite_path)
    if blocking:
        return "blocked", f"latest report has {blocking} blocking case(s)", case_command
    if changed:
        return "review", f"latest report has {changed} changed case(s)", case_command
    if int(doctor.get("errors") or 0):
        return "setup", "doctor found setup errors", _first_step(doctor_steps, "redline doctor")
    if not Path(history_path).exists():
        report_path = str(latest.get("path") or f"{reports_dir}/eval.json")
        return "record", "latest report is clear; record it in history", (
            f"redline history {report_path} --label prompt-v2 --out {history_path}"
        )
    return "ready", "latest report has no blocking structural regressions", (
        f"redline app --reports-dir {reports_dir} --history {history_path}"
    )


def _case_command(case: dict[str, Any], *, fallback_suite: str) -> str:
    case_id = str(case.get("suite_case_id") or case.get("case_id") or "<case_id>")
    suite = str(case.get("suite") or fallback_suite)
    return f"redline case {suite} {case_id}"


def _app_command(*, reports_dir: str, history_path: str, checkpoint_path: str) -> str:
    return f"redline app --reports-dir {reports_dir} --history {history_path} --checkpoint {checkpoint_path}"


def _status_review_case(case: dict[str, Any], *, fallback_suite: str) -> dict[str, str]:
    if not case:
        return {}
    command = _case_command(case, fallback_suite=fallback_suite)
    return {
        "case_id": str(case.get("case_id") or case.get("suite_case_id") or ""),
        "status": str(case.get("status") or ""),
        "reason": str(case.get("reason") or ""),
        "impact": str(case.get("impact") or ""),
        "command": command,
    }


def _summary_line(summary: dict[str, Any]) -> str:
    if not summary:
        return "none"
    keys = ("cases", "regression", "missing", "changed", "neutral", "improved", "accepted", "ignored")
    return " ".join(f"{key}={_count(summary, key)}" for key in keys if key in summary)


def _decision_line(report: dict[str, Any]) -> str:
    decision = _dict(report.get("decision"))
    return str(decision.get("recommended_action") or "review report details")


def _check_line(checks: list[Any], name: str) -> str:
    for item in checks:
        if isinstance(item, dict) and item.get("name") == name:
            return f"{item.get('status')} - {item.get('message')}"
    return "not checked"


def _first_step(steps: list[str], fallback: str) -> str:
    if not steps:
        return fallback
    step = steps[0]
    if ": redline " in step:
        return "redline " + step.split(": redline ", 1)[1]
    return step


def _first_dict(value: Any) -> dict[str, Any]:
    items = _list(value)
    first = items[0] if items else {}
    return first if isinstance(first, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _count(summary: dict[str, Any], key: str) -> int:
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0
