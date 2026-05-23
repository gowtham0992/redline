#!/usr/bin/env bash
set -euo pipefail

: "${LITELLM_API_KEY:?Set LITELLM_API_KEY before running this replay command.}"
: "${LITELLM_MODEL:?Set LITELLM_MODEL before running this replay command.}"
: "${LITELLM_BASE_URL:=http://localhost:4000}"

prompt="$(cat)"
payload="$(
  PROMPT="$prompt" MODEL="$LITELLM_MODEL" python - <<'PY'
import json
import os

print(json.dumps({
    "model": os.environ["MODEL"],
    "messages": [{"role": "user", "content": os.environ["PROMPT"]}],
}))
PY
)"

response="$(
  curl -sS "${LITELLM_BASE_URL%/}/v1/chat/completions" \
    -H "Authorization: Bearer ${LITELLM_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$payload"
)"

RESPONSE="$response" python - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["RESPONSE"])
if "error" in data:
    error = data["error"]
    if isinstance(error, dict):
        print(error.get("message", "LiteLLM API error"), file=sys.stderr)
    else:
        print(str(error), file=sys.stderr)
    raise SystemExit(1)

choices = data.get("choices", [])
if not choices:
    print("LiteLLM response missing choices", file=sys.stderr)
    raise SystemExit(1)

message = choices[0].get("message", {})
content = message.get("content", "")
print(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
PY
