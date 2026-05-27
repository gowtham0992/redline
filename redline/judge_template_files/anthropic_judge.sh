#!/usr/bin/env bash
set -euo pipefail

: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY before running this judge command.}"
: "${ANTHROPIC_JUDGE_MODEL:=claude-3-5-sonnet-latest}"
: "${ANTHROPIC_VERSION:=2023-06-01}"

judge_payload="$(cat)"
judge_rubric=""
if [[ -n "${REDLINE_JUDGE_RUBRIC:-}" ]]; then
  judge_rubric="$(cat "$REDLINE_JUDGE_RUBRIC")"
fi
request="$(
  JUDGE_PAYLOAD="$judge_payload" MODEL="$ANTHROPIC_JUDGE_MODEL" RUBRIC="$judge_rubric" python - <<'PY'
import json
import os

DEFAULT_RUBRIC = """Default redline judge rubric:
- Preserve explicit prompt requirements, required fields, output format, ordering constraints, numbers, dates, URLs, names, owners, policies, and safety/compliance caveats.
- Treat lost JSON validity, missing required keys, lost table/code/list structure, new refusals, empty answers, and allow/deny policy reversals as regressions unless the prompt made that change intentional.
- Treat factual contradictions, hallucinated unsupported facts, weaker escalation/safety posture, or dropped operational details as regressions.
- Treat pure wording, tone, or brevity changes as neutral when the candidate keeps the same meaning and required facts.
- Use changed when the behavior differs but the product impact is not clearly better or worse.
- Use improved only when the candidate fixes a baseline issue without dropping any prompt requirement.
- Do not overrule deterministic regressions unless the candidate clearly satisfies the prompt and baseline intent.
"""

payload = json.loads(os.environ["JUDGE_PAYLOAD"])
rubric = os.environ.get("RUBRIC", "").strip() or DEFAULT_RUBRIC
prompt = f"""You are a strict redline regression judge.

You receive one prompt-regression case as JSON. Judge whether the candidate
response preserves the baseline behavior for the original prompt.

Return exactly one JSON object with:
- status: one of regression, changed, improved, neutral
- confidence: one of low, medium, high
- reason: one short sentence grounded in the prompt or response evidence

Rubric:
{rubric}

Status definitions:
- regression: candidate is worse for the original prompt or product contract.
- improved: candidate is clearly better and preserves all requirements.
- neutral: candidate preserves the same behavior and required facts.
- changed: behavior changed but impact is uncertain and needs human review.

Case JSON:
{json.dumps(payload, sort_keys=True)}
"""

print(json.dumps({
    "model": os.environ["MODEL"],
    "max_tokens": 512,
    "messages": [{"role": "user", "content": prompt}],
}))
PY
)"

response="$(
  curl -sS https://api.anthropic.com/v1/messages \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: ${ANTHROPIC_VERSION}" \
    -H "content-type: application/json" \
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
        error = data["error"]
        print(error.get("message", "Anthropic API error"), file=sys.stderr)
        return 1

    text = _response_text(data)
    if not text:
        print("Anthropic judge returned no text", file=sys.stderr)
        return 1

    try:
        judgment = _parse_judgment(text)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Anthropic judge returned invalid JSON: {exc}", file=sys.stderr)
        return 1
    status = str(judgment.get("status", "")).strip().lower()
    confidence = str(judgment.get("confidence", "")).strip().lower()
    reason = str(judgment.get("reason", "")).strip() or "judge returned no reason"

    if status not in ALLOWED_STATUSES:
        print(f"Anthropic judge returned invalid status: {status}", file=sys.stderr)
        return 1
    if confidence not in ALLOWED_CONFIDENCE:
        print(f"Anthropic judge returned invalid confidence: {confidence}", file=sys.stderr)
        return 1

    print(json.dumps({"status": status, "confidence": confidence, "reason": reason}, sort_keys=True))
    return 0


def _response_text(data):
    texts = []
    for item in data.get("content", []):
        if item.get("type") == "text" and item.get("text"):
            texts.append(str(item["text"]))
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
