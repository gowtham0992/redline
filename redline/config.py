from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .policy import DEFAULT_FAIL_ON


DEFAULT_CONFIG_PATH = "redline.json"
DEFAULT_SCHEMA_URL = "https://raw.githubusercontent.com/gowtham0992/redline/develop/redline.schema.json"


def default_config(
    *,
    input_field: str = "prompt",
    output_field: str = "response",
    max_cases: int = 42,
    timeout_seconds: float = 30.0,
    replay: str | None = None,
    judge: str | None = None,
    judge_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "$schema": DEFAULT_SCHEMA_URL,
        "version": "0.1",
        "suite": "redline-suite.json",
        "input_field": input_field,
        "output_field": output_field,
        "max_cases": max_cases,
        "timeout_seconds": timeout_seconds,
        "workers": 1,
        "fail_on": list(DEFAULT_FAIL_ON),
        "reports": {
            "json": ".redline/reports/{command}.json",
            "markdown": ".redline/reports/{command}.md",
            "junit": ".redline/reports/{command}.xml",
        },
        "logs": {
            "observed": ".redline/logs/prompts.jsonl",
        },
        "runs": {
            "candidate": ".redline/runs/candidate.jsonl",
            "metadata": ".redline/runs/replay.json",
        },
    }
    if replay:
        config["replay"] = replay
    if judge:
        if judge_timeout_seconds is None:
            config["judge"] = judge
        else:
            config["judge"] = {
                "command": judge,
                "timeout_seconds": judge_timeout_seconds,
            }
    return config


def create_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    input_field: str = "prompt",
    output_field: str = "response",
    max_cases: int = 42,
    timeout_seconds: float = 30.0,
    replay: str | None = None,
    judge: str | None = None,
    judge_timeout_seconds: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    target = Path(path)
    if target.exists() and not force:
        raise ValueError(f"{target} already exists; pass --force to overwrite")
    if max_cases < 1:
        raise ValueError("max_cases must be at least 1")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")
    if judge_timeout_seconds is not None and judge_timeout_seconds <= 0:
        raise ValueError("judge_timeout_seconds must be greater than 0")
    return default_config(
        input_field=input_field,
        output_field=output_field,
        max_cases=max_cases,
        timeout_seconds=timeout_seconds,
        replay=replay,
        judge=judge,
        judge_timeout_seconds=judge_timeout_seconds,
    )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{target} invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{target} expected a JSON object")
    return data
