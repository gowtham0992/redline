#!/usr/bin/env bash
set -euo pipefail

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this judge command.}"
: "${OPENAI_JUDGE_MODEL:=gpt-4o-mini}"

judge_payload="$(cat)"
request="$(
  JUDGE_PAYLOAD="$judge_payload" MODEL="$OPENAI_JUDGE_MODEL" python - <<'PY'
import json
import os

payload = json.loads(os.environ["JUDGE_PAYLOAD"])
prompt = f"""You are a strict redline regression judge.

You receive one prompt-regression case as JSON. Judge whether the candidate
response preserves the baseline behavior for the original prompt.

Return exactly one JSON object with:
- status: one of regression, changed, improved, neutral
- confidence: one of low, medium, high
- reason: one short sentence

Rules:
- regression: candidate drops a requirement, contradicts the baseline, refuses
  when the baseline answered, removes important structured data, or weakens
  safety/compliance behavior.
- improved: candidate clearly fixes a baseline problem without dropping prompt
  requirements.
- neutral: candidate preserves the same behavior and required facts.
- changed: behavior changed but the impact is not clearly better or worse.

Case JSON:
{json.dumps(payload, sort_keys=True)}
"""

print(json.dumps({"model": os.environ["MODEL"], "input": prompt}))
PY
)"

response="$(
  curl -sS https://api.openai.com/v1/responses \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$request"
)"

RESPONSE="$response" python - <<'PY'
import json
import os
import sys

ALLOWED_STATUSES = {"regression", "changed", "improved", "neutral"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


def main() -> int:
    data = json.loads(os.environ["RESPONSE"])
    if "error" in data:
        print(data["error"].get("message", "OpenAI API error"), file=sys.stderr)
        return 1

    text = _response_text(data)
    if not text:
        print("OpenAI judge returned no text", file=sys.stderr)
        return 1

    try:
        judgment = _parse_judgment(text)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"OpenAI judge returned invalid JSON: {exc}", file=sys.stderr)
        return 1
    status = str(judgment.get("status", "")).strip().lower()
    confidence = str(judgment.get("confidence", "")).strip().lower()
    reason = str(judgment.get("reason", "")).strip() or "judge returned no reason"

    if status not in ALLOWED_STATUSES:
        print(f"OpenAI judge returned invalid status: {status}", file=sys.stderr)
        return 1
    if confidence not in ALLOWED_CONFIDENCE:
        print(f"OpenAI judge returned invalid confidence: {confidence}", file=sys.stderr)
        return 1

    print(json.dumps({"status": status, "confidence": confidence, "reason": reason}, sort_keys=True))
    return 0


def _response_text(data):
    if data.get("output_text"):
        return str(data["output_text"]).strip()
    texts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                texts.append(str(content["text"]))
    return "\n".join(texts).strip()


def _parse_judgment(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("judge output must be a JSON object")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
PY
