# redline

Local-first prompt regression diffs from JSONL logs.

redline turns prompt-response logs you already have into a representative eval
suite, then compares new prompt runs against the baseline. It is built for the
fast local loop: change a prompt, run one command, see what got better, worse,
or dangerously different.

## Quick Start

Install from GitHub:

```bash
python -m pip install "git+https://github.com/gowtham0992/redline.git@develop"
```

Run the first-use demo:

```bash
redline demo
```

The demo writes a realistic support-agent suite under `.redline/demo` and
prints a behavioral diff where a shorter candidate prompt drops required
production details.

For a GIF-friendly terminal view:

```bash
redline demo --compact
```

To record the public demo from a repeatable script:

```bash
bash scripts/demo_terminal.sh
```

For a larger dogfood log that exercises JSON, refusal, table, code, numbered
list, empty-output, and entity-loss regressions:

```bash
python -m redline suite examples/dogfood_baseline.jsonl --out /tmp/redline-dogfood-suite.json --max-cases 20
python -m redline diff /tmp/redline-dogfood-suite.json examples/dogfood_candidate.jsonl --compact --fail-on none
```

For AI-assistant session dogfood, use the prompt set in
`docs/ai-session-dogfood-prompts.jsonl` and normalize raw exports with
`scripts/normalize_ai_session_logs.py`.

For local development on redline itself:

```bash
python -m pip install -e ".[dev]"
python -m unittest discover
```

Before cutting a release or asking someone else to try a branch, run the full
local gate:

```bash
bash scripts/release_check.sh
```

The full public-alpha checklist lives in [docs/release.md](docs/release.md), and
the first-user dogfood pass lives in [docs/dogfood.md](docs/dogfood.md).

Create a project config:

```bash
redline init
```

Create config plus a GitHub Actions workflow:

```bash
redline init --replay "python examples/replay_candidate.py" --github-action
```

Or choose a built-in runner adapter:

```bash
redline init --runner openai --copy-runner --github-action
```

The generated `redline.json` includes a `$schema` reference for editor help.
Regressions and missing outputs fail CI by default through `fail_on`; set
`fail_on` to `"none"` during setup if you want report-only runs.

Need to connect your app? See [runner adapters](docs/runners.md) for copy-paste
replay commands, starting with OpenAI direct.

Or list the available adapters from the CLI:

```bash
redline runners
```

Copy a runner into your project:

```bash
redline runners --copy openai
```

Or copy every built-in adapter:

```bash
redline runners --copy all
```

Store a default replay command in config:

```bash
python -m redline init --replay "python examples/replay_candidate.py" --force
```

Store a default judge command in config:

```bash
python -m redline init --judge "python examples/judge_changed.py" --force
```

Set a default per-case replay timeout in config:

```bash
python -m redline init --timeout 10 --force
```

## Config Reference

`redline.json` is intentionally small. These are the supported keys:

| Key | Purpose |
| --- | --- |
| `$schema` | JSON Schema URL for editor autocomplete. |
| `suite` | Committed suite baseline path, default `redline-suite.json`. |
| `input_field`, `output_field` | JSONL field paths for prompts and responses. Nested paths are supported. |
| `max_cases` | Maximum representative cases selected for a suite. Default `42` keeps early runs broad while still reviewable. |
| `timeout_seconds` | Per-case replay timeout for `redline eval`. |
| `workers` | Number of replay cases `redline eval` may run concurrently. Default `1`. |
| `diff_profile` | Diff signal profile. Use `strict` for CI blocking, or `review` to downgrade missing numbers/entities to changed signals in long-form assistant logs. |
| `fail_on` | Statuses that fail `diff` or `eval`; use `"none"` for report-only mode. |
| `reports` | JSON, Markdown, and JUnit output paths. `{command}` expands to `diff` or `eval`. |
| `logs.observed` | Local watch output JSONL path. |
| `runs.candidate`, `runs.metadata` | Candidate replay rows and eval metadata output paths. |
| `replay` | Command used by `eval`; prompts go to stdin unless the command contains `{prompt}`. |
| `judge` | Optional judge command for ambiguous `changed` cases only. Use a string or `{ "command": "...", "timeout_seconds": 10 }`. |

Check local setup health:

```bash
python -m redline doctor
```

Doctor checks config, suite presence, report paths, and whether the configured
replay command points at files that exist locally. When setup is incomplete, it
prints the next command to run.

Use strict mode in CI to fail on missing setup pieces:

```bash
python -m redline doctor --strict
```

Collect prompt-response pairs from an existing log:

```bash
python -m redline watch --log examples/baseline.jsonl
```

Repeated `watch` runs skip source lines that were already collected. Pass
`--allow-duplicates` only when you intentionally want duplicate observations.

Keep polling a log during local development:

```bash
python -m redline watch --log logs/prompts.jsonl --follow
```

In human output mode, follow prints each collected prompt-response pair as it
arrives. Use `--json` when another process needs machine-readable output.

Summarize collected evidence:

```bash
python -m redline watch --stats
```

Inspect behavioral clusters before generating a suite:

```bash
python -m redline cluster
```

Cluster reports include risk levels, high-variance markers, and failure-pattern
flags so risky coverage is visible before eval runs. When `--max-cases` is
tight, risky clusters are selected before larger low-risk clusters.

Generate a suite from baseline logs:

```bash
python -m redline suite examples/baseline.jsonl
```

The suite command prints next steps for inspecting cases, comparing a candidate
log, and wiring a replay runner.

Or generate it from the locally collected watch log:

```bash
python -m redline suite
```

List the generated cases and IDs:

```bash
python -m redline cases redline-suite.json
```

Inspect a single case:

```bash
python -m redline case case_002_1612556e83
```

Summarize suite coverage:

```bash
python -m redline summary
```

Validate a generated or hand-edited suite before relying on it:

```bash
python -m redline validate
```

Compare candidate outputs against that suite:

```bash
python -m redline diff examples/candidate.jsonl
```

Write reports for CI or PR comments:

```bash
python -m redline diff redline-suite.json examples/candidate.jsonl \
  --out-json .redline/reports/diff.json \
  --out-md .redline/reports/diff.md \
  --out-junit .redline/reports/diff.xml
```

The default config writes JSON, Markdown, and JUnit XML reports under
`.redline/reports/` for `diff` and `eval` runs.

Compare two redline JSON reports to see whether a prompt fix made the run
better or worse:

```bash
python -m redline compare .redline/reports/eval-before.json .redline/reports/eval.json
```

`compare` fails on `worse` cases by default. Use `--fail-on none` for
report-only history checks, or include other directions such as `new`:

```bash
python -m redline compare before.json after.json --fail-on worse,new
```

Archive report summaries for trend history:

```bash
python -m redline history .redline/reports/eval.json \
  --label prompt-v2 \
  --out .redline/history.jsonl \
  --out-md .redline/history.md \
  --github-summary
python -m redline history --out .redline/history.jsonl --out-md .redline/history.md
```

The generated GitHub Actions workflow also runs this comparison when
`.redline/reports/eval-before.json` exists, records `.redline/history.jsonl`,
renders `.redline/history.md`, appends the trend table to the job summary, then
uploads the history and report artifacts.

In GitHub Actions, append the Markdown report to the job summary:

```bash
python -m redline eval --compact --github-summary --github-annotations
```

`--github-annotations` emits PR-check annotations for regressions, missing
outputs, and ambiguous changed cases.

Use `--compact` in CI logs when you want one line per blocking or reviewable
case while still writing full JSON, Markdown, and JUnit reports.

Mark a known change as expected so future runs do not fail on that case:

```bash
python -m redline mark redline-suite.json case_002_1612556e83 \
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

Add a deterministic requirement for a case:

```bash
python -m redline require case_003_b13b74def7 --include "30 days"
```

Forbid text that should never appear in a case response:

```bash
python -m redline require case_003_b13b74def7 --exclude "final sale"
```

Tune CI strictness with `--fail-on`. By default redline exits `1` for
`regression` and `missing` cases. Use `none` for report-only runs:

```bash
python -m redline diff redline-suite.json examples/candidate.jsonl --fail-on none
```

For long-form assistant logs, use the review profile so missing incidental
numbers and entities are treated as reviewable changes instead of blocking
regressions:

```bash
python -m redline diff redline-suite.json candidate.jsonl --profile review --fail-on none
```

Or let redline replay each suite case with a local command. The command receives
the prompt on stdin and should print the candidate response to stdout:

```bash
python -m redline eval redline-suite.json --replay "python examples/replay_candidate.py"
```

Run replay cases concurrently when your runner can handle it:

```bash
python -m redline eval redline-suite.json --workers 4
```

Evaluate a changed prompt template with your configured replay command:

```bash
python -m redline eval --prompt prompts/v2.txt
```

Prompt templates support `{prompt}`, `{case_id}`, `{source_line}`, `{cluster}`,
and `{baseline_response}`.

Diff and eval output includes a decision line so the run answers the shipping
question directly:

```text
Confidence: HIGH  |  Recommended action: fix blocking cases before shipping
```

Add an optional judge command for ambiguous `changed` cases. Redline still runs
deterministic checks first and only sends changed cases to the judge command as
JSON on stdin:

```bash
python -m redline diff examples/candidate.jsonl --judge "python examples/judge_changed.py"
```

The judge command should print JSON with `status`, `confidence`, and `reason`.
Accepted statuses are `regression`, `changed`, `improved`, and `neutral`.
See [examples/judge_changed.py](examples/judge_changed.py) for a small local
judge that demonstrates the stdin/stdout contract. For an optional model-backed
judge template:

```bash
OPENAI_API_KEY="..." python -m redline diff examples/candidate.jsonl --judge "./examples/openai_judge.sh"
ANTHROPIC_API_KEY="..." python -m redline diff examples/candidate.jsonl --judge "./examples/anthropic_judge.sh"
LITELLM_API_KEY="..." LITELLM_JUDGE_MODEL="..." python -m redline diff examples/candidate.jsonl --judge "./examples/litellm_judge.sh"
```

Save replayed candidate outputs for debugging or a later `diff` run:

```bash
python -m redline eval redline-suite.json \
  --replay "python examples/replay_candidate.py" \
  --candidate-out .redline/runs/candidate.jsonl
```

When `runs.metadata` is configured, `eval` also writes replay metadata with the
suite path, candidate artifact path, replay command, and diff summary:

```bash
python -m redline eval redline-suite.json \
  --replay "python examples/replay_candidate.py" \
  --run-metadata .redline/runs/replay.json
```

If your command takes the prompt as an argument, use `{prompt}`:

```bash
python -m redline eval redline-suite.json --replay "my-prompt-runner {prompt}"
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

This v0 is local-first and deterministic by default. It clusters outputs by
observable behavior such as response shape, JSON validity, list/code/table
structure, refusal behavior, and length bucket. Cluster reports flag failure
patterns such as empty outputs, refusals, invalid JSON for JSON requests, missing
tables for table requests, and high length variance. Diff reports format
regressions, newly empty answers, new refusals, missing JSON keys, lost numbers,
and other high-signal behavioral changes.

Optional judge commands are supported for ambiguous `changed` cases, but redline
does not call any cloud model unless you explicitly configure that command. A
`neutral` result means no high-signal change was detected by the configured
checks; it should not be read as a proof that the text is identical.
Entity and refusal checks are deliberately conservative so sentence starters,
supportive apologies, and ordinary support-ticket words do not become noisy
regression signals.

The next iterations should focus on external dogfood feedback, richer judge
templates, and the public demo/PyPI release path.

See [examples/github-action.yml](examples/github-action.yml) for a GitHub
Actions starting point.
