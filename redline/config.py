from __future__ import annotations

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
            "json": ".redline/reports/redline.json",
            "markdown": ".redline/reports/redline.md",
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
