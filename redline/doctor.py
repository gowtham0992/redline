from __future__ import annotations

from pathlib import Path
from typing import Any


def doctor_report(
    *,
    config_path: str,
    config: dict[str, Any],
    suite: dict[str, Any] | None,
    suite_error: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    config_exists = Path(config_path).exists()
    if config_exists:
        checks.append({"status": "ok", "name": "config", "message": f"found {config_path}"})
    else:
        checks.append({"status": "warn", "name": "config", "message": f"{config_path} not found"})

    suite_path = str(config.get("suite") or ".redline/suite.json")
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

    replay = config.get("replay")
    if isinstance(replay, str) and replay:
        checks.append({"status": "ok", "name": "replay", "message": "configured"})
    else:
        checks.append({"status": "warn", "name": "replay", "message": "not configured"})

    errors = sum(1 for check in checks if check["status"] == "error")
    warnings = sum(1 for check in checks if check["status"] == "warn")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def format_doctor_report(report: dict[str, Any]) -> str:
    lines = ["redline doctor", ""]
    for check in report["checks"]:
        label = check["status"].upper()
        lines.append(f"{label:<5} {check['name']}: {check['message']}")
    lines.append("")
    lines.append(f"Errors: {report['errors']}")
    lines.append(f"Warnings: {report['warnings']}")
    return "\n".join(lines) + "\n"
