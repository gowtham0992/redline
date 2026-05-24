#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    endpoint = os.environ.get("REDLINE_HTTP_URL", "").strip()
    if not endpoint:
        print("Set REDLINE_HTTP_URL before running this replay command.", file=sys.stderr)
        return 2

    prompt = sys.stdin.read()
    request_field = os.environ.get("REDLINE_HTTP_PROMPT_FIELD", "prompt")
    response_field = os.environ.get("REDLINE_HTTP_RESPONSE_FIELD", "response")
    timeout = float(os.environ.get("REDLINE_HTTP_TIMEOUT", "30"))
    payload = json.dumps({request_field: prompt}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    token = os.environ.get("REDLINE_HTTP_BEARER_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP runner received {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"HTTP runner failed: {exc.reason}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0

    value = _get_field(data, response_field)
    if value is None:
        print(f"Response JSON missing field: {response_field}", file=sys.stderr)
        return 1
    print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
    return 0


def _get_field(data: object, path: str) -> object | None:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


if __name__ == "__main__":
    raise SystemExit(main())
