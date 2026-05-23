# redline

Local-first prompt regression diffs from JSONL logs.

This is the first implementation slice from the product vision: take prompt-response
logs you already have, generate a representative eval suite, then compare a new
run against the baseline.

## Quick Start

Create a project config:

```bash
python -m redline init
```

Store a default replay command in config:

```bash
python -m redline init --replay "python examples/replay_candidate.py" --force
```

Check local setup health:

```bash
python -m redline doctor
```

Generate a suite from baseline logs:

```bash
python -m redline suite examples/baseline.jsonl
```

List the generated cases and IDs:

```bash
python -m redline cases .redline/suite.json
```

Inspect a single case:

```bash
python -m redline case case_002_1612556e83
```

Summarize suite coverage:

```bash
python -m redline summary
```

Compare candidate outputs against that suite:

```bash
python -m redline diff examples/candidate.jsonl
```

Write reports for CI or PR comments:

```bash
python -m redline diff .redline/suite.json examples/candidate.jsonl \
  --out-json .redline/reports/diff.json \
  --out-md .redline/reports/diff.md \
  --out-junit .redline/reports/diff.xml
```

Mark a known change as expected so future runs do not fail on that case:

```bash
python -m redline mark .redline/suite.json case_002_1612556e83 \
  --status expected \
  --note "intentional response format change"
```

Promote a reviewed candidate output into the suite baseline:

```bash
python -m redline accept case_002_1612556e83 \
  --candidate .redline/runs/candidate.jsonl \
  --note "new expected response"
```

Accept all cases previously marked `expected`:

```bash
python -m redline accept --all-expected --candidate .redline/runs/candidate.jsonl
```

Tune CI strictness with `--fail-on`. By default redline exits `1` for
`regression` and `missing` cases. Use `none` for report-only runs:

```bash
python -m redline diff .redline/suite.json examples/candidate.jsonl --fail-on none
```

Or let redline replay each suite case with a local command. The command receives
the prompt on stdin and should print the candidate response to stdout:

```bash
python -m redline eval .redline/suite.json --replay "python examples/replay_candidate.py"
```

Save replayed candidate outputs for debugging or a later `diff` run:

```bash
python -m redline eval .redline/suite.json \
  --replay "python examples/replay_candidate.py" \
  --candidate-out .redline/runs/candidate.jsonl
```

If your command takes the prompt as an argument, use `{prompt}`:

```bash
python -m redline eval .redline/suite.json --replay "my-prompt-runner {prompt}"
```

Replay commands also receive `REDLINE_CASE_ID`, `REDLINE_SOURCE_LINE`, and
`REDLINE_CLUSTER` as environment variables.

The default JSONL fields are `prompt` and `response`. Override them when your
logs use different names. Nested field paths are supported:

```bash
python -m redline suite logs.jsonl --input-field input --output-field output
python -m redline suite logs.jsonl --input-field request.prompt --output-field result.text
```

## Current Scope

This v0 is deliberately local and deterministic. It does not call an LLM judge.
It clusters outputs by observable behavior such as response shape, JSON validity,
list/code/table structure, refusal behavior, and length bucket. The diff reports
format regressions, newly empty answers, new refusals, missing JSON keys, lost
numbers, and other high-signal behavioral changes.

The next iterations should add rubric capture, LLM judging for ambiguous cases,
and CI output.

See [examples/github-action.yml](examples/github-action.yml) for a GitHub
Actions starting point.
