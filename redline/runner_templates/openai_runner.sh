#!/usr/bin/env bash
set -euo pipefail

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this replay command.}"
: "${OPENAI_MODEL:=gpt-4o-mini}"

prompt="$(cat)"
payload="$(
  PROMPT="$prompt" MODEL="$OPENAI_MODEL" python - <<'PY'
import json
import os

print(json.dumps({"model": os.environ["MODEL"], "input": os.environ["PROMPT"]}))
PY
)"

response="$(
  curl -sS https://api.openai.com/v1/responses \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$payload"
)"

RESPONSE="$response" python - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["RESPONSE"])
if "error" in data:
    print(data["error"].get("message", "OpenAI API error"), file=sys.stderr)
    raise SystemExit(1)

if data.get("output_text"):
    print(data["output_text"])
    raise SystemExit(0)

texts = []
for item in data.get("output", []):
    for content in item.get("content", []):
        if content.get("type") in {"output_text", "text"} and content.get("text"):
            texts.append(content["text"])

print("\n".join(texts))
PY
