#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    command = os.environ.get("REDLINE_STDIO_COMMAND", "").strip()
    if not command:
        print(
            "Set REDLINE_STDIO_COMMAND to a command that reads prompt text on stdin and prints the response on stdout.",
            file=sys.stderr,
        )
        return 2

    prompt = sys.stdin.read()
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        shell=True,
        capture_output=True,
        check=False,
    )
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        print(f"stdio runner command exited {completed.returncode}", file=sys.stderr)
        return completed.returncode

    print(completed.stdout, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
