from __future__ import annotations

import shlex
import subprocess
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import LogRecord


_TEMPLATE_FIELD_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ReplayResult:
    records: list[LogRecord]
    command: str
    timeout_seconds: float
    prompt_path: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        metadata = {
            "command": self.command,
            "timeout_seconds": self.timeout_seconds,
            "records": len(self.records),
        }
        if self.prompt_path:
            metadata["prompt"] = self.prompt_path
        return metadata


def replay_suite(
    suite: dict[str, Any],
    command: str,
    *,
    timeout_seconds: float = 30.0,
    prompt_template: str | None = None,
    prompt_path: str | None = None,
) -> ReplayResult:
    argv_template = _parse_command(command)
    records: list[LogRecord] = []

    for line_number, case in enumerate(suite.get("cases", []), 1):
        case_id = str(case["id"])
        case_prompt = str(case["prompt"])
        rendered_prompt = render_prompt_template(prompt_template, case) if prompt_template is not None else case_prompt
        extra_env = {
            "REDLINE_CASE_ID": case_id,
            "REDLINE_SOURCE_LINE": str(case.get("source_line", "")),
            "REDLINE_CLUSTER": str(case.get("cluster", "")),
            "REDLINE_PROMPT_PATH": prompt_path or "",
        }
        try:
            output = _run_replay(argv_template, rendered_prompt, timeout_seconds, extra_env)
        except ValueError as exc:
            raise ValueError(f"{case_id}: {exc}") from exc
        records.append(
            LogRecord(
                line_number=line_number,
                prompt=case_prompt,
                response=output,
                raw={
                    "case_id": case_id,
                    "prompt": case_prompt,
                    "rendered_prompt": rendered_prompt,
                    "response": output,
                },
            )
        )

    return ReplayResult(
        records=records,
        command=command,
        timeout_seconds=timeout_seconds,
        prompt_path=prompt_path,
    )


def read_prompt_template(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"{path} not found") from exc


def render_prompt_template(template: str | None, case: dict[str, Any]) -> str:
    case_prompt = str(case.get("prompt", ""))
    if template is None:
        return case_prompt
    values = {
        "prompt": case_prompt,
        "case_id": str(case.get("id", "")),
        "source_line": str(case.get("source_line", "")),
        "cluster": str(case.get("cluster", "")),
        "baseline_response": str(case.get("baseline_response", "")),
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)

    unknown = [
        name
        for name in _TEMPLATE_FIELD_RE.findall(rendered)
        if name not in values
    ]
    if unknown:
        raise ValueError(f"unknown prompt template field: {unknown[0]}")
    return rendered


def _parse_command(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"invalid replay command: {exc}") from exc
    if not argv:
        raise ValueError("replay command cannot be empty")
    return argv


def _run_replay(
    argv_template: list[str],
    prompt: str,
    timeout_seconds: float,
    extra_env: dict[str, str],
) -> str:
    uses_placeholder = any("{prompt}" in arg for arg in argv_template)
    argv = [arg.replace("{prompt}", prompt) for arg in argv_template]
    stdin = None if uses_placeholder else prompt
    env = os.environ.copy()
    env.update(extra_env)

    try:
        completed = subprocess.run(
            argv,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
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
