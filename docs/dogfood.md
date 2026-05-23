# Dogfood Protocol

Use this before a public alpha push. The goal is to find the first five-minute
failure a stranger would hit.

## Rules

- Start from a fresh temp directory, not this repo checkout.
- Use only the README and copied terminal output as guidance.
- Do not inspect source code while running the pass.
- Time the run. Stop at the first confusing moment and write it down.
- Treat unclear output as a product bug, even if the command technically works.

## Pass 1: First-Run Demo

```bash
python -m pip install "git+https://github.com/gowtham0992/redline.git@develop"
redline demo
redline cases .redline/demo/suite.json
redline runners
redline doctor
```

Expected result: the demo catches realistic support-agent regressions, the next
steps are obvious, and the first warning explains exactly what to run next.

## Pass 2: Real Replay Setup

```bash
redline init --runner openai --copy-runner --github-action
redline doctor
```

Expected result: redline writes config, copies a runnable adapter, and explains
that the missing suite is solved by `redline suite path/to/log.jsonl`.

## Pass 3: Core Loop

```bash
redline suite .redline/demo/baseline.jsonl --out redline-suite.json
redline diff redline-suite.json .redline/demo/candidate.jsonl --compact --fail-on none
redline eval redline-suite.json --replay "python path/to/replay.py" --fail-on none
```

If replay is not available, mark the exact point where the workflow stops and
what command or example would have unblocked it.

## Pass 4: Larger Sample

Use the bigger checked-in sample to confirm redline catches more than one demo
pattern:

```bash
redline suite examples/dogfood_baseline.jsonl --out /tmp/redline-dogfood-suite.json --max-cases 20
redline diff /tmp/redline-dogfood-suite.json examples/dogfood_candidate.jsonl --compact --fail-on none
```

Expected result: the diff includes regressions for missing JSON keys, refusals,
lost Markdown tables, lost code blocks, lost numbered lists, and empty output.

## Pass 5: AI Assistant Session Logs

Use the same prompts in [ai-session-dogfood-prompts.jsonl](ai-session-dogfood-prompts.jsonl)
across Claude, Kiro, Antigravity, or another assistant. Ask each tool to export
its session as JSONL with `prompt`, `response`, and optional `metadata`.

Save raw exports under `.redline/private/` so they stay out of git:

```bash
python scripts/normalize_ai_session_logs.py \
  --prompts docs/ai-session-dogfood-prompts.jsonl \
  --out .redline/private/normalized \
  claude=.redline/private/claude.jsonl \
  kiro=.redline/private/kiro.jsonl \
  antigravity=.redline/private/antigravity.jsonl

redline suite .redline/private/normalized/claude.jsonl \
  --out .redline/private/normalized/claude-suite.json \
  --max-cases 10

redline diff .redline/private/normalized/claude-suite.json \
  .redline/private/normalized/kiro.jsonl \
  --profile review \
  --compact \
  --fail-on none
```

Expected result: long-form assistant differences show as `changed` review items
instead of blocking regressions unless the candidate loses stronger signals such
as JSON validity, required structure, URLs, refusals, or empty output.

## Friction Log

Record every issue in this format:

```text
time:
command:
expected:
actual:
fix:
severity: blocker | confusing | polish
```

Fix blockers before tagging. Fix confusing issues before posting publicly unless
there is a clear workaround in the README.
