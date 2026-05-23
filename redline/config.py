from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .policy import DEFAULT_FAIL_ON


DEFAULT_CONFIG_PATH = "redline.json"


def default_config(
    *,
    input_field: str = "prompt",
    output_field: str = "response",
    max_cases: int = 42,
) -> dict[str, Any]:
    return {
        "version": "0.1",
        "suite": ".redline/suite.json",
        "input_field": input_field,
        "output_field": output_field,
        "max_cases": max_cases,
        "fail_on": list(DEFAULT_FAIL_ON),
        "reports": {
            "json": ".redline/reports/{command}.json",
            "markdown": ".redline/reports/{command}.md",
        },
        "runs": {
            "candidate": ".redline/runs/candidate.jsonl",
        },
    }


def create_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    input_field: str = "prompt",
    output_field: str = "response",
    max_cases: int = 42,
    force: bool = False,
) -> dict[str, Any]:
    target = Path(path)
    if target.exists() and not force:
        raise ValueError(f"{target} already exists; pass --force to overwrite")
    if max_cases < 1:
        raise ValueError("max_cases must be at least 1")
    return default_config(
        input_field=input_field,
        output_field=output_field,
        max_cases=max_cases,
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
