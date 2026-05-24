from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path
from typing import Any

from .runners import runner_adapters
from .validate import validate_suite


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
        validation = validate_suite(suite, suite_path=suite_path)
        validation_message = (
            f"{validation['errors']} error(s), {validation['warnings']} warning(s)"
        )
        if validation["errors"]:
            checks.append({"status": "error", "name": "suite-validation", "message": validation_message})
        elif validation["warnings"]:
            checks.append({"status": "warn", "name": "suite-validation", "message": validation_message})
        else:
            checks.append({"status": "ok", "name": "suite-validation", "message": "valid"})
    elif suite_error:
        checks.append({"status": "error", "name": "suite", "message": suite_error})
    else:
        checks.append({"status": "warn", "name": "suite", "message": _missing_suite_message(suite_path)})
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
        replay_check = _replay_adapter_misuse_check(replay) or _command_check("replay", replay)
        checks.append(replay_check)
        if replay_check["status"] == "ok":
            replay_env_check = _replay_env_check(replay)
            if replay_env_check:
                checks.append(replay_env_check)
    else:
        checks.append({"status": "warn", "name": "replay", "message": "not configured"})

    if "judge" in config:
        checks.append(_judge_check(config.get("judge")))

    checks.append(_coverage_check(config=config, suite=suite))

    report_paths = _configured_paths(config.get("reports"), ("json", "markdown", "html", "junit"))
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
        "next_steps": _next_steps(checks, suite_path=suite_path),
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


def _missing_suite_message(suite_path: str) -> str:
    message = f"{suite_path} not found"
    demo_suite = Path(".redline/demo/suite.json")
    if suite_path != str(demo_suite) and demo_suite.exists():
        message += f"; demo suite exists at {demo_suite}, but project CI needs its own suite"
    return message


def _coverage_check(*, config: dict[str, Any], suite: dict[str, Any] | None) -> dict[str, str]:
    message = (
        "structural checks only; use requirements or an optional judge "
        "for factual, tone, hallucination, or reasoning risks"
    )
    if suite is None:
        return {"status": "ok", "name": "coverage", "message": message}

    summary = suite.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    requirements = suite.get("requirements")
    requirements_count = len(requirements) if isinstance(requirements, dict) else 0
    high_risk_clusters = _high_risk_cluster_count(suite, summary)
    judge_configured = "judge" in config
    message += (
        f"; high-risk clusters={high_risk_clusters}; "
        f"requirements={requirements_count}; judge={'yes' if judge_configured else 'no'}"
    )
    if high_risk_clusters and not requirements_count and not judge_configured:
        message += "; add requirements or a judge before trusting semantic quality"
    return {"status": "ok", "name": "coverage", "message": message}


def _high_risk_cluster_count(suite: dict[str, Any], summary: dict[str, Any]) -> int:
    value = summary.get("high_risk_clusters")
    if isinstance(value, int):
        return value
    clusters = suite.get("clusters")
    if not isinstance(clusters, list):
        return 0
    return sum(
        1
        for cluster in clusters
        if isinstance(cluster, dict) and str(cluster.get("risk") or "") == "high"
    )


def _next_steps(checks: list[dict[str, str]], *, suite_path: str) -> list[str]:
    steps: list[str] = []
    by_name = {check["name"]: check for check in checks}

    config_missing = _check_has(by_name, "config", "warn")
    replay_missing = (
        _check_has(by_name, "replay", "warn")
        and by_name["replay"]["message"] == "not configured"
    )
    if config_missing:
        steps.append("Create config: redline init --runner stdio --copy-runner")
    elif replay_missing:
        steps.append(
            "Configure replay: redline init --runner stdio --copy-runner --force"
        )

    suite = by_name.get("suite")
    if suite and suite["status"] == "warn":
        steps.append(
            "Generate suite: redline suite path/to/log.jsonl --out redline-suite.json"
        )
    elif suite and suite["status"] == "error":
        steps.append("Fix suite JSON, then rerun: redline doctor")

    suite_validation = by_name.get("suite-validation")
    if suite_validation and suite_validation["status"] in {"error", "warn"}:
        steps.append(f"Review suite health: redline validate {suite_path}")

    replay = by_name.get("replay")
    if replay and replay["status"] == "error":
        steps.append(_replay_next_step(replay["message"]))

    replay_env = by_name.get("replay-env")
    if replay_env and replay_env["status"] == "warn":
        steps.append(f"Set runner environment: {replay_env['message']}")

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
    if "converts logs" in message or "jsonl_log_adapter.py" in message:
        return (
            "Convert exported logs first: redline runners --copy jsonl-logs, "
            "then redline suite .redline/logs/prompts.jsonl --out redline-suite.json"
        )
    if "stdio_runner.py" in message:
        return "Copy missing runner: redline runners --copy stdio"
    if "openai_runner.sh" in message:
        return "Copy missing runner: redline runners --copy openai"
    if "anthropic_runner.sh" in message:
        return "Copy missing runner: redline runners --copy anthropic"
    if "python_chain_runner.py" in message:
        return "Copy missing runner: redline runners --copy python-chain"
    if "http_runner.py" in message:
        return "Copy missing runner: redline runners --copy http"
    if "litellm_runner.sh" in message:
        return "Copy missing runner: redline runners --copy litellm"
    return "Fix replay command in redline.json, then rerun: redline doctor"


def _replay_adapter_misuse_check(command_line: str) -> dict[str, str] | None:
    try:
        argv = shlex.split(command_line)
    except ValueError:
        return None
    command_text = " ".join(argv)
    for adapter in runner_adapters():
        if adapter.get("kind") != "log":
            continue
        markers = {adapter["template"], Path(adapter["file"]).name}
        if any(marker in command_text for marker in markers):
            return {
                "status": "error",
                "name": "replay",
                "message": (
                    f"{adapter['id']} ({adapter['template']}) converts logs and "
                    "cannot be used as eval replay"
                ),
            }
    return None


def _replay_env_check(command_line: str) -> dict[str, str] | None:
    try:
        argv = shlex.split(command_line)
    except ValueError:
        return None
    command_text = " ".join(argv)
    requirements = {
        "stdio_runner.py": ("REDLINE_STDIO_COMMAND",),
        "openai_runner.sh": ("OPENAI_API_KEY",),
        "anthropic_runner.sh": ("ANTHROPIC_API_KEY",),
        "python_chain_runner.py": ("REDLINE_PYTHON_RUNNER",),
        "http_runner.py": ("REDLINE_HTTP_URL",),
        "litellm_runner.sh": ("LITELLM_BASE_URL", "LITELLM_API_KEY", "LITELLM_MODEL"),
    }
    for marker, env_names in requirements.items():
        if marker not in command_text:
            continue
        missing = [name for name in env_names if not os.environ.get(name)]
        if not missing:
            return None
        return {
            "status": "warn",
            "name": "replay-env",
            "message": f"missing {', '.join(missing)} for {marker}",
        }
    return None


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
