from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from .io import LogRecord


@dataclass(frozen=True)
class ReplayResult:
    records: list[LogRecord]
    command: str
    timeout_seconds: float

    def to_metadata(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "timeout_seconds": self.timeout_seconds,
            "records": len(self.records),
        }


def replay_suite(
    suite: dict[str, Any],
    command: str,
    *,
    timeout_seconds: float = 30.0,
) -> ReplayResult:
    argv_template = _parse_command(command)
    records: list[LogRecord] = []

    for line_number, case in enumerate(suite.get("cases", []), 1):
        prompt = str(case["prompt"])
        output = _run_replay(argv_template, prompt, timeout_seconds)
        records.append(
            LogRecord(
                line_number=line_number,
                prompt=prompt,
                response=output,
                raw={
                    "case_id": str(case["id"]),
                    "prompt": prompt,
                    "response": output,
                },
            )
        )

    return ReplayResult(records=records, command=command, timeout_seconds=timeout_seconds)


def _parse_command(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"invalid replay command: {exc}") from exc
    if not argv:
        raise ValueError("replay command cannot be empty")
    return argv


def _run_replay(argv_template: list[str], prompt: str, timeout_seconds: float) -> str:
    uses_placeholder = any("{prompt}" in arg for arg in argv_template)
    argv = [arg.replace("{prompt}", prompt) for arg in argv_template]
    stdin = None if uses_placeholder else prompt

    try:
        completed = subprocess.run(
            argv,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"replay command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"replay command timed out after {timeout_seconds:g}s") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise ValueError(f"replay command exited {completed.returncode}{detail}")

    return completed.stdout.rstrip("\n")
