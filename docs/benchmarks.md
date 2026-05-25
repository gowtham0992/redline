# redline benchmarks

redline is meant to stay fast enough for normal prompt work, not just nightly CI.
Use `redline benchmark` before making an eval suite a required gate.

## Performance contract

These are the working targets for local structural checks:

| Operation | Target |
| --- | --- |
| 50-case eval, structural only | under 1 second of redline diff work, excluding your runner latency |
| 50-case eval with a user-supplied judge | under 30 seconds with parallel workers |
| Suite generation from 1,000 log pairs | under 5 seconds |
| Watch ingestion from 10,000 JSONL records | under 10 seconds |
| Diff report generation | under 500ms for normal CI reports |
| MCP tool response | under 2 seconds before external runner or judge latency |

The benchmark command is a static budget estimate from suite size, timeout, and
worker count. It does not run replay commands, call models, or pretend to know
your model latency. Treat it as a CI capacity preflight.

For multi-prompt repos, pass the prompt manifest. redline aggregates the budget
for every mapped suite because manifest evals replay each prompt suite in turn.

## Local preflight

```bash
redline benchmark redline-suite.json --workers 8 --timeout 30
```

```bash
redline benchmark redline-prompts.json --workers 8 --timeout 30
```

To make the preflight enforce a budget:

```bash
redline benchmark redline-suite.json \
  --workers 8 \
  --timeout 30 \
  --max-seconds 300
```

Exit code `1` means the suite exceeds the requested budget.
When a budget fails, the report prints the minimum worker count that would fit
the requested timeout and max-seconds budget when such a worker count is
possible.

## Publish benchmark artifacts

```bash
redline benchmark redline-suite.json \
  --workers 8 \
  --timeout 30 \
  --out-json .redline/reports/benchmark.json \
  --out-md .redline/reports/benchmark.md
```

The GitHub Action writes those benchmark artifacts automatically under
`.redline/reports/` and appends the same summary to the GitHub step summary.

## What to do when the suite grows

- Raise `workers` before raising `timeout`.
- Split large suites by product area or prompt family.
- Add deterministic requirements to high-value cases so scale does not dilute
  trust.
- Keep `--max-seconds` strict enough that engineers still run redline before
  merging prompt changes.
