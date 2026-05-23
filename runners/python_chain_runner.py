#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import sys
from typing import Any, Callable


def main() -> int:
    target = os.environ.get("REDLINE_PYTHON_RUNNER", "").strip()
    if not target or ":" not in target:
        print(
            "Set REDLINE_PYTHON_RUNNER to 'module:function' before running this replay command.",
            file=sys.stderr,
        )
        return 2

    prompt = sys.stdin.read()
    try:
        runner = _load_runner(target)
        result = runner(prompt)
    except Exception as exc:
        print(f"Python chain runner failed: {exc}", file=sys.stderr)
        return 1

    print(_stringify_result(result))
    return 0


def _load_runner(target: str) -> Callable[[str], Any]:
    module_name, function_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    runner = getattr(module, function_name)
    if not callable(runner):
        raise TypeError(f"{target} is not callable")
    return runner


def _stringify_result(result: Any) -> str:
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, sort_keys=True)
    return str(result)


if __name__ == "__main__":
    raise SystemExit(main())
