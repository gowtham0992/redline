from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections import Counter
from typing import Any

from .diff import summarize_result_decision


JUDGE_STATUSES = {"regression", "changed", "improved", "neutral"}
JUDGE_CONFIDENCES = {"low", "medium", "high"}


def apply_judge(
    result: dict[str, Any],
    command: str,
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    argv = _parse_command(command)
    judged = 0
    for item in result.get("diffs", []):
        if not isinstance(item, dict) or item.get("status") != "changed":
            continue
        if item.get("candidate_response") is None:
            continue
        judgment = _run_judge(argv, _judge_payload(item), timeout_seconds)
        judged += 1
        item["judge"] = judgment
        item["status"] = judgment["status"]
        item["reasons"] = _judged_reasons(item.get("reasons", []), judgment)
        item["confidence"] = judgment["confidence"]
        item["signal"] = "judge"

    result["summary"] = _summary_from_diffs(result.get("diffs", []))
    result["decision"] = summarize_result_decision(result["summary"], result.get("diffs", []))
    result["judge"] = {
        "command": command,
        "timeout_seconds": timeout_seconds,
        "cases": judged,
    }
    return result


def _run_judge(argv: list[str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            input=json.dumps(payload, sort_keys=True),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=os.environ.copy(),
        )
    except FileNotFoundError as exc:
        raise ValueError(f"judge command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"judge command timed out after {timeout_seconds:g}s") from exc

    if completed.returncode != 0:
        detail = _command_output_detail(completed.stdout, completed.stderr)
        raise ValueError(f"judge command exited {completed.returncode}{detail}")

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge command must print a JSON object: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("judge command must print a JSON object")

    status = str(data.get("status", "")).lower()
    if status not in JUDGE_STATUSES:
        allowed = ", ".join(sorted(JUDGE_STATUSES))
        raise ValueError(f"judge status must be one of: {allowed}")
    confidence = str(data.get("confidence", "medium")).lower()
    if confidence not in JUDGE_CONFIDENCES:
        allowed = ", ".join(sorted(JUDGE_CONFIDENCES))
        raise ValueError(f"judge confidence must be one of: {allowed}")
    reason = str(data.get("reason", "")).strip() or "judge returned no reason"
    return {
        "status": status,
        "confidence": confidence,
        "reason": reason,
    }


def _judge_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": item.get("case_id"),
        "prompt": item.get("prompt"),
        "baseline_response": item.get("baseline_response"),
        "candidate_response": item.get("candidate_response"),
        "deterministic_status": item.get("status"),
        "deterministic_reasons": item.get("reasons", []),
        "cluster": item.get("cluster"),
        "source": item.get("source"),
        "source_line": item.get("source_line"),
    }


def _judged_reasons(reasons: Any, judgment: dict[str, Any]) -> list[str]:
    existing = [str(reason) for reason in reasons] if isinstance(reasons, list) else []
    prefix = (
        f"judge {judgment['status']} ({judgment['confidence']} confidence): "
        f"{judgment['reason']}"
    )
    return [prefix] + existing


def _summary_from_diffs(diffs: Any) -> dict[str, int]:
    items = [item for item in diffs if isinstance(item, dict)]
    counts = Counter(str(item.get("status", "")) for item in items)
    return {
        "cases": len(items),
        "regression": counts["regression"],
        "changed": counts["changed"],
        "improved": counts["improved"],
        "accepted": counts["accepted"],
        "ignored": counts["ignored"],
        "neutral": counts["neutral"],
        "missing": counts["missing"],
    }


def _parse_command(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"invalid judge command: {exc}") from exc
    if not argv:
        raise ValueError("judge command cannot be empty")
    return argv


def _command_output_detail(stdout: str, stderr: str) -> str:
    parts = []
    if stderr.strip():
        parts.append(f"stderr: {stderr.strip()}")
    if stdout.strip():
        parts.append(f"stdout: {stdout.strip()}")
    return f": {'; '.join(parts)}" if parts else ""
