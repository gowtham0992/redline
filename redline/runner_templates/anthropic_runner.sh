#!/usr/bin/env bash
set -euo pipefail

: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY before running this replay command.}"
: "${ANTHROPIC_MODEL:=claude-3-5-sonnet-latest}"
: "${ANTHROPIC_VERSION:=2023-06-01}"

prompt="$(cat)"
payload="$(
  PROMPT="$prompt" MODEL="$ANTHROPIC_MODEL" python - <<'PY'
import json
import os

print(json.dumps({
    "model": os.environ["MODEL"],
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": os.environ["PROMPT"]}],
}))
PY
)"

response="$(
  curl -sS https://api.anthropic.com/v1/messages \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: ${ANTHROPIC_VERSION}" \
    -H "content-type: application/json" \
    -d "$payload"
)"

RESPONSE="$response" python - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["RESPONSE"])
if "error" in data:
    error = data["error"]
    print(error.get("message", "Anthropic API error"), file=sys.stderr)
    raise SystemExit(1)

texts = []
for item in data.get("content", []):
    if item.get("type") == "text" and item.get("text"):
        texts.append(item["text"])

print("\n".join(texts))
PY
