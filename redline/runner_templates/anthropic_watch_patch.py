#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY before running this capture command.", file=sys.stderr)
        return 2

    try:
        anthropic_module = import_module("anthropic")
    except ImportError:
        print("Install the Anthropic SDK first: python -m pip install anthropic", file=sys.stderr)
        return 2
    Anthropic = getattr(anthropic_module, "Anthropic")

    prompt = sys.stdin.read().strip()
    if not prompt:
        print("Pass prompt text on stdin.", file=sys.stderr)
        return 2

    log_path = Path(os.environ.get("REDLINE_OBSERVED_LOG", ".redline/logs/prompts.jsonl"))
    model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    client = Anthropic()
    from redline import patch_anthropic

    patch_anthropic(client, log=log_path)

    response = client.messages.create(
        model=model,
        max_tokens=int(os.environ.get("ANTHROPIC_MAX_TOKENS", "1024")),
        messages=[{"role": "user", "content": prompt}],
    )
    output = "\n".join(
        str(getattr(block, "text", ""))
        for block in getattr(response, "content", [])
        if getattr(block, "type", "text") == "text"
    ).strip()
    print(output or str(response))
    print(f"redline captured observation in {log_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
