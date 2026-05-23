from __future__ import annotations

import shlex
import shutil
from pathlib import Path
from typing import Any


def doctor_report(
    *,
    config_path: str,
    config: dict[str, Any],
    suite: dict[str, Any] | None,
    suite_error: str | None = None,
    suite_git_ignored: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    config_exists = Path(config_path).exists()
    if config_exists:
        checks.append({"status": "ok", "name": "config", "message": f"found {config_path}"})
    else:
        checks.append({"status": "warn", "name": "config", "message": f"{config_path} not found"})

    suite_path = str(config.get("suite") or "redline-suite.json")
    if suite is not None:
        cases = suite.get("cases", [])
        case_count = len(cases) if isinstance(cases, list) else 0
        checks.append(
            {
                "status": "ok",
                "name": "suite",
                "message": f"found {suite_path} with {case_count} cases",
            }
        )
    elif suite_error:
        checks.append({"status": "error", "name": "suite", "message": suite_error})
    else:
        checks.append({"status": "warn", "name": "suite", "message": f"{suite_path} not found"})
    if suite_git_ignored:
        checks.append(
            {
                "status": "warn",
                "name": "suite-git",
                "message": f"{suite_path} is ignored by git; CI needs a committed suite baseline",
            }
        )

    replay = config.get("replay")
    if isinstance(replay, str) and replay:
        checks.append(_command_check("replay", replay))
    else:
        checks.append({"status": "warn", "name": "replay", "message": "not configured"})

    if "judge" in config:
        checks.append(_judge_check(config.get("judge")))

    report_paths = _configured_paths(config.get("reports"), ("json", "markdown", "junit"))
    if report_paths:
        checks.append({"status": "ok", "name": "reports", "message": ", ".join(report_paths)})
    elif "reports" in config:
        checks.append({"status": "warn", "name": "reports", "message": "not configured"})

    run_paths = _configured_paths(config.get("runs"), ("candidate", "metadata"))
    if run_paths:
        checks.append({"status": "ok", "name": "runs", "message": ", ".join(run_paths)})
    elif "runs" in config:
        checks.append({"status": "warn", "name": "runs", "message": "not configured"})

    errors = sum(1 for check in checks if check["status"] == "error")
    warnings = sum(1 for check in checks if check["status"] == "warn")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "next_steps": _next_steps(checks),
    }


def format_doctor_report(report: dict[str, Any]) -> str:
    lines = ["redline doctor", ""]
    for check in report["checks"]:
        label = check["status"].upper()
        lines.append(f"{label:<5} {check['name']}: {check['message']}")
    lines.append("")
    lines.append(f"Errors: {report['errors']}")
    lines.append(f"Warnings: {report['warnings']}")
    next_steps = report.get("next_steps") or []
    if next_steps:
        lines.append("")
        lines.append("Next:")
        for step in next_steps:
            lines.append(f"- {step}")
    return "\n".join(lines) + "\n"


def _configured_paths(value: object, keys: tuple[str, ...]) -> list[str]:
    if not isinstance(value, dict):
        return []
    paths = []
    for key in keys:
        path = value.get(key)
        if isinstance(path, str) and path:
            paths.append(f"{key}={path}")
    return paths


def _next_steps(checks: list[dict[str, str]]) -> list[str]:
    steps: list[str] = []
    by_name = {check["name"]: check for check in checks}

    config_missing = _check_has(by_name, "config", "warn")
    replay_missing = (
        _check_has(by_name, "replay", "warn")
        and by_name["replay"]["message"] == "not configured"
    )
    if config_missing:
        steps.append("Create config: redline init --runner openai --copy-runner")
    elif replay_missing:
        steps.append(
            "Configure replay: redline init --runner openai --copy-runner --force"
        )

    suite = by_name.get("suite")
    if suite and suite["status"] == "warn":
        steps.append(
            "Generate suite: redline suite path/to/log.jsonl --out redline-suite.json"
        )
    elif suite and suite["status"] == "error":
        steps.append("Fix suite JSON, then rerun: redline doctor")

    replay = by_name.get("replay")
    if replay and replay["status"] == "error":
        steps.append(_replay_next_step(replay["message"]))

    judge = by_name.get("judge")
    if judge and judge["status"] in {"error", "warn"}:
        steps.append("Fix judge command in redline.json, then rerun: redline doctor")

    if _check_has(by_name, "suite-git", "warn"):
        steps.append("Commit the suite baseline, or move it out of ignored paths")

    return steps


def _check_has(
    checks: dict[str, dict[str, str]],
    name: str,
    status: str,
) -> bool:
    check = checks.get(name)
    return bool(check and check["status"] == status)


def _replay_next_step(message: str) -> str:
    if "openai_runner.sh" in message:
        return "Copy missing runner: redline runners --copy openai"
    if "anthropic_runner.sh" in message:
        return "Copy missing runner: redline runners --copy anthropic"
    if "python_chain_runner.py" in message:
        return "Copy missing runner: redline runners --copy python-chain"
    if "http_runner.py" in message:
        return "Copy missing runner: redline runners --copy http"
    if "jsonl_log_adapter.py" in message:
        return "Copy missing runner: redline runners --copy jsonl-logs"
    if "litellm_runner.sh" in message:
        return "Copy missing runner: redline runners --copy litellm"
    return "Fix replay command in redline.json, then rerun: redline doctor"


def _judge_check(value: object) -> dict[str, str]:
    if isinstance(value, str) and value:
        return _command_check("judge", value)
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str) and command:
            return _command_check("judge", command)
    return {"status": "error", "name": "judge", "message": "not configured"}


def _command_check(name: str, command_line: str) -> dict[str, str]:
    try:
        argv = shlex.split(command_line)
    except ValueError as exc:
        return {
            "status": "error",
            "name": name,
            "message": f"invalid {name} command: {exc}",
        }
    if not argv:
        return {"status": "warn", "name": name, "message": "not configured"}

    command = argv[0]
    if _looks_like_path(command):
        command_path = Path(command)
        if not command_path.exists():
            return {
                "status": "error",
                "name": name,
                "message": f"command path not found: {command}",
            }
        if not _is_executable(command_path):
            return {
                "status": "warn",
                "name": name,
                "message": f"command path is not executable: {command}",
            }
    elif shutil.which(command) is None:
        return {
            "status": "error",
            "name": name,
            "message": f"command not found on PATH: {command}",
        }

    for arg in argv[1:]:
        if _should_check_arg_path(arg) and not Path(arg).exists():
            return {
                "status": "error",
                "name": name,
                "message": f"referenced file not found: {arg}",
            }

    return {"status": "ok", "name": name, "message": "configured"}


def _should_check_arg_path(value: str) -> bool:
    if value.startswith("-") or "://" in value or "{" in value:
        return False
    if Path(value).suffix in {".py", ".sh", ".js", ".mjs", ".ts"}:
        return True
    return _looks_like_path(value)


def _looks_like_path(value: str) -> bool:
    return value.startswith(".") or "/" in value or "\\" in value


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)
