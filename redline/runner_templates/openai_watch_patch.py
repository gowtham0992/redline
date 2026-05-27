#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY before running this capture command.", file=sys.stderr)
        return 2

    try:
        openai_module = import_module("openai")
    except ImportError:
        print("Install the OpenAI SDK first: python -m pip install openai", file=sys.stderr)
        return 2
    OpenAI = getattr(openai_module, "OpenAI")

    prompt = sys.stdin.read().strip()
    if not prompt:
        print("Pass prompt text on stdin.", file=sys.stderr)
        return 2

    log_path = Path(os.environ.get("REDLINE_OBSERVED_LOG", ".redline/logs/prompts.jsonl"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI()
    from redline import patch_openai

    patch_openai(client, log=log_path)

    response = client.responses.create(model=model, input=prompt)
    output = getattr(response, "output_text", "")
    if not output:
        output = str(response)
    print(output)
    print(f"redline captured observation in {log_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
