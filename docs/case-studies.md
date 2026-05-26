# Case Studies

These are repo-local dogfood runs that anyone can reproduce from a fresh
checkout. They are not customer case studies yet. They are the proof fixtures we
use until external users share anonymized logs.

The important property is that the data is checked in, deterministic, and
launch-safe. If a future redline change stops catching these regressions, the
product promise has weakened.

## Case Study 1: Public-Pattern Prompt Logs

Scenario: a candidate prompt or model update keeps answers short, but drops the
production details the baseline preserved.

Data:

- Baseline: `examples/public_dogfood_baseline.jsonl`
- Candidate: `examples/public_dogfood_candidate.jsonl`
- Source notes: `examples/public_dogfood_sources.md`

Run:

```bash
redline suite examples/public_dogfood_baseline.jsonl \
  --out /tmp/redline-public-suite.json \
  --all-cases

redline diff /tmp/redline-public-suite.json \
  examples/public_dogfood_candidate.jsonl \
  --compact \
  --fail-on none
```

Current result:

```text
redline diff: cases=10 regression=10 changed=0 improved=0 accepted=0 ignored=0 missing=0 neutral=0
```

What redline catches:

- JSON validity and required-key loss.
- Markdown table, code block, numbered list, and bullet list loss.
- Missing URL, numbers, dates, owners, and entities.
- New refusal on a safe compliance-prep prompt.
- Empty output.

Why this matters: this is the first-run proof. It shows the product can catch
the kind of obvious prompt regression teams actually ship when they make a
response "cleaner" or shorter.

## Case Study 2: Support-Agent Dogfood

Scenario: a support-agent prompt iteration sounds more concise, but removes
operational detail from support responses.

Data:

- Baseline: `examples/dogfood_baseline.jsonl`
- Candidate: `examples/dogfood_candidate.jsonl`

Run:

```bash
redline suite examples/dogfood_baseline.jsonl \
  --out /tmp/redline-dogfood-suite.json \
  --max-cases 20

redline diff /tmp/redline-dogfood-suite.json \
  examples/dogfood_candidate.jsonl \
  --compact \
  --fail-on none
```

Current result:

```text
redline diff: cases=10 regression=9 changed=0 improved=0 accepted=0 ignored=0 missing=0 neutral=1
```

What redline catches:

- A billing classifier that drops required JSON keys.
- A safe audit-log support reply that becomes a refusal.
- Markdown table, code block, numbered list, and bullet list loss.
- Empty escalation output.
- Missing refund windows, seat limits, ARR, and dates.

Why this matters: this is closer to the product's intended daily workflow. A
team changes a support prompt, runs one diff, and sees concrete blocking cases
before the bad prompt reaches customers.

## Case Study 3: AI Assistant Session Dogfood

Scenario: compare outputs from different AI coding assistants on the same
redline product prompts. This is the route for private, realistic dogfood
without committing private assistant logs.

Prompt set:

- `docs/ai-session-dogfood-prompts.jsonl`

Save raw exports under `.redline/private/` so they stay out of git, then
normalize them:

```bash
python scripts/normalize_ai_session_logs.py \
  --prompts docs/ai-session-dogfood-prompts.jsonl \
  --out .redline/private/normalized \
  claude=.redline/private/claude.jsonl \
  kiro=.redline/private/kiro.jsonl \
  antigravity=.redline/private/antigravity.jsonl
```

Use one assistant as the baseline and compare another:

```bash
redline suite .redline/private/normalized/claude.jsonl \
  --out .redline/private/normalized/claude-suite.json \
  --all-cases

redline diff .redline/private/normalized/claude-suite.json \
  .redline/private/normalized/kiro.jsonl \
  --profile review \
  --compact \
  --fail-on none
```

Expected result: long-form assistant differences appear as `changed` review
items unless a candidate loses stronger deterministic signals such as required
structure, URLs, refusals, or empty output.

## External Case Studies Still Needed

The repo fixtures prove the loop and protect regressions in redline itself. The
world-class proof is still external:

- Five to ten users run redline on their own prompt-response logs.
- They report one regression redline caught or one regression it missed.
- We anonymize the command, the signal, and the fix.
- We add the sanitized story here only after confirming no private prompts,
  outputs, customer data, or API keys are included.

For public internet dogfood, start with the ranked dataset shortlist in
[internet-dogfood-sources.md](internet-dogfood-sources.md), keep raw samples
under `.redline/private/`, and publish only sanitized or synthetic examples
with source attribution.
