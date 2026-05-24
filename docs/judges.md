# Judge Templates

redline is deterministic by default. Use a judge only for `changed` cases where
the structural checks found a meaningful difference but cannot know whether the
difference is good, bad, or acceptable.

## Contract

A judge command reads one JSON object from stdin and prints one JSON object:

```json
{"status":"regression","confidence":"high","reason":"candidate drops the refund policy URL"}
```

Allowed `status` values are `regression`, `changed`, `improved`, and `neutral`.
Allowed `confidence` values are `low`, `medium`, and `high`.

## Model-backed judges

The provider templates include a strict default rubric and accept an optional
domain rubric file through `REDLINE_JUDGE_RUBRIC`.

```bash
REDLINE_JUDGE_RUBRIC=examples/judges/support_rubric.md \
  OPENAI_API_KEY="..." \
  redline diff redline-suite.json candidate.jsonl \
  --judge "./examples/openai_judge.sh"

REDLINE_JUDGE_RUBRIC=examples/judges/extraction_rubric.md \
  ANTHROPIC_API_KEY="..." \
  redline diff redline-suite.json candidate.jsonl \
  --judge "./examples/anthropic_judge.sh"

REDLINE_JUDGE_RUBRIC=examples/judges/safety_rubric.md \
  LITELLM_API_KEY="..." LITELLM_JUDGE_MODEL="..." \
  redline diff redline-suite.json candidate.jsonl \
  --judge "./examples/litellm_judge.sh"
```

Use the same commands with `redline eval` after replay is configured.

## Included rubrics

- `examples/judges/support_rubric.md`: support-agent regressions such as lost
  owners, policy URLs, SLAs, IDs, routing targets, and escalation paths.
- `examples/judges/extraction_rubric.md`: structured-output regressions such as
  invalid JSON, missing keys, table/list/code loss, and weaker extracted values.
- `examples/judges/safety_rubric.md`: safety/compliance regressions such as
  weaker caveats, secret requests, unsafe policy flips, and changed approval
  criteria.

## Calibration

Keep the judge narrow. The judge should decide whether a changed case is worse
for your product contract, not whether it personally prefers the candidate.
Use deterministic `require` rules for must-have strings and formats; use a judge
for semantic risks that are hard to encode as exact text.
