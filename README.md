# redline

Local-first prompt regression diffs from JSONL logs.

redline turns prompt-response logs you already have into a representative eval
suite, then compares new prompt runs against the baseline. It is built for the
fast local loop: change a prompt, run one command, see what got better, worse,
or dangerously different.

The product promise is intentionally narrow and useful: in under five minutes,
on a real prompt log, redline should catch one regression you did not want to
ship. It starts with deterministic structural checks, then lets you add pinned
requirements or optional judges where semantic judgment matters.

Website source for GitHub Pages lives in [site/](site/) and deploys from the
committed static assets on `main` and `develop`.

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
production details. It also prints the review loop: inspect the report, mark an
intentional change, accept reviewed outputs into the baseline, and keep the
suite moving with your prompt.

For a GIF-friendly terminal view:

```bash
redline demo --public --compact
```

Write a local dashboard from reports and history:

```bash
redline dashboard --open
```

The public-pattern proof is the launch-safe demo path: it catches ten synthetic
regressions without needing API keys, private logs, or a cloud account.

```bash
redline demo --public --compact
```

From a repo checkout, record the public demo from a repeatable script:

```bash
bash scripts/demo_terminal.sh
bash scripts/demo_gif.sh .redline/launch .redline/launch/redline-demo.gif
```

From a repo checkout, the raw dogfood fixtures are also available as JSONL:

```bash
python -m redline suite examples/dogfood_baseline.jsonl --out /tmp/redline-dogfood-suite.json --max-cases 20
python -m redline diff /tmp/redline-dogfood-suite.json examples/dogfood_candidate.jsonl --compact --fail-on none
python -m redline suite examples/public_dogfood_baseline.jsonl --out /tmp/redline-public-suite.json --all-cases
python -m redline diff /tmp/redline-public-suite.json examples/public_dogfood_candidate.jsonl --compact --fail-on none
```

The public fixture is synthetic, shaped after public instruction/chat dataset
patterns, and documented in
[examples/public_dogfood_sources.md](examples/public_dogfood_sources.md).

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

The full public-alpha checklist lives in [docs/release.md](docs/release.md), the
launch playbook lives in [docs/launch.md](docs/launch.md), and the first-user
dogfood pass lives in [docs/dogfood.md](docs/dogfood.md).

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
redline init --runner stdio --copy-runner --github-action
```

The generated `redline.json` includes a `$schema` reference for editor help.
Regressions and missing outputs fail CI by default through `fail_on`; set
`fail_on` to `"none"` during setup if you want report-only runs.
Redline is deterministic and structural by default: it catches lost formats,
keys, URLs, numbers, entities, refusals, empty outputs, code blocks, tables, and
lists. It also flags obvious allow/deny policy wording flips as `changed` so
they get reviewed instead of disappearing as neutral text drift. It does not
prove factual correctness, tone, hallucination safety, or subtle reasoning
quality; add case requirements or an optional judge for those risks.

Need to connect your app? See [runner adapters](docs/runners.md) for
provider-neutral replay commands first, then optional OpenAI, Anthropic,
LiteLLM, HTTP, and framework examples.

Or list the available adapters from the CLI:

```bash
redline runners
```

Copy a provider-neutral runner into your project:

```bash
redline runners --copy stdio
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
| `reports` | JSON, Markdown, HTML, and JUnit output paths. `{command}` expands to `diff` or `eval`. |
| `logs.observed` | Local watch output JSONL path. |
| `runs.candidate`, `runs.metadata` | Candidate replay rows and eval metadata output paths. |
| `replay` | Command used by `eval`; prompts go to stdin unless the command contains `{prompt}`. |
| `judge` | Optional judge command for ambiguous `changed` cases only. Use a string or `{ "command": "...", "timeout_seconds": 10 }`. |

Check local setup health:

```bash
python -m redline doctor
```

Doctor checks config, suite presence, suite validation health, report paths,
and whether the configured replay command points at files that exist locally.
When setup is incomplete, it prints the next command to run.

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

Capture prompt-response pairs directly from Python code:

```python
from redline import watch

@watch(log=".redline/logs/prompts.jsonl")
def generate_response(prompt: str) -> str:
    return call_llm(prompt)
```

The decorator appends local JSONL with `prompt`, `response`, a stable
`content_hash`, source function, source line, timestamp, and metadata. It works
with sync and async functions. Exact duplicate prompt-response pairs are skipped
by default; pass `dedupe=False` when you intentionally want repeated identical
observations. Use `prompt_arg="question"` when your function does not name the
prompt argument `prompt`.

Or record one observation manually when your app already has the prompt and
response in hand:

```python
from redline import record

response = call_llm(prompt)
record(prompt, response, metadata={"model": "gpt-4o"})
```

`record()` returns the normalized row plus `recorded: true` when it wrote to
disk or `recorded: false` when the exact prompt-response pair was already in
the log.

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

Stats include unique prompt-response pairs, duplicate pairs, and a basic
readiness hint. When enough unique pairs and behavior patterns are present,
redline points you to `redline suite`; otherwise it tells you to collect more
evidence.

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

The suite command skips exact duplicate prompt-response pairs, stores a stable
`content_hash` on each case, then prints next steps for inspecting cases,
comparing a candidate log, and wiring a replay runner.

Use `--all-cases` when dogfooding small fixed prompt sets where every unique
row should be compared instead of sampling representative clusters.

Pin an important edge case the clustering did not select:

```bash
python -m redline suite add redline-suite.json \
  --prompt "Answer refund questions with the policy URL" \
  --response "Refund policy: https://example.com/policy/refunds" \
  --include "https://example.com/policy/refunds"
```

`suite add` refuses exact duplicate prompt-response pairs and prints the
existing case ID. Pass `--allow-duplicate` only when you intentionally want a
second pinned case for the same prompt and baseline response.

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

Validation catches duplicate case IDs, stale stored features, missing or stale
case hashes, broken requirements, and redundant duplicate prompt-response cases.
When validation finds a problem, it prints a repair-oriented next step.

Compare candidate outputs against that suite:

```bash
python -m redline diff examples/candidate.jsonl
```

Write reports for CI or PR comments:

```bash
python -m redline diff redline-suite.json examples/candidate.jsonl \
  --out-json .redline/reports/diff.json \
  --out-md .redline/reports/diff.md \
  --out-html .redline/reports/diff.html \
  --out-junit .redline/reports/diff.xml
```

The default config writes JSON, Markdown, self-contained HTML, and JUnit XML reports under
`.redline/reports/` for `diff` and `eval` runs.

Compare two redline JSON reports to see whether a prompt fix made the run
better or worse:

```bash
python -m redline compare .redline/reports/eval-before.json .redline/reports/eval.json
python -m redline compare before.json after.json --out-html .redline/reports/compare.html
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

Render a self-contained local dashboard that links latest JSON, Markdown, and
HTML reports plus recent trend entries:

```bash
python -m redline dashboard --out .redline/dashboard.html
```

The generated GitHub Actions workflow also runs this comparison when
`.redline/reports/eval-before.json` exists, records `.redline/history.jsonl`,
renders `.redline/history.md` and `.redline/dashboard.html`, appends the trend
table to the job summary, then uploads the history, dashboard, and report
artifacts.

In GitHub Actions, append the Markdown report to the job summary:

```bash
python -m redline eval --compact --github-summary --github-annotations
```

`--github-annotations` emits PR-check annotations for regressions, missing
outputs, and ambiguous changed cases.

Use `--compact` in CI logs when you want one line per blocking or reviewable
case while still writing full JSON, Markdown, HTML, and JUnit reports.

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

That mark-and-accept loop is how redline learns from your decisions without an
LLM judge. Catch regressions, mark intentional changes, promote the reviewed
candidate output, then the next run compares against the new baseline.

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
`{baseline_response}`, and `{content_hash}`.

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

For product-specific rubrics, set `REDLINE_JUDGE_RUBRIC` to one of the included
templates such as `examples/judges/support_rubric.md`,
`examples/judges/extraction_rubric.md`, or `examples/judges/safety_rubric.md`.
See [judge templates](docs/judges.md) for calibration guidance.

Save replayed candidate outputs for debugging or a later `diff` run:

```bash
python -m redline eval redline-suite.json \
  --replay "python examples/replay_candidate.py" \
  --candidate-out .redline/runs/candidate.jsonl
```

Candidate rows include `content_hash` for the replayed response and
`baseline_content_hash` for the suite case they were compared against.

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
obvious allow/deny policy wording flips, and other high-signal behavioral
changes.

Optional judge commands are supported for ambiguous `changed` cases, but redline
does not call any cloud model unless you explicitly configure that command. A
`neutral` result means no high-signal change was detected by the configured
checks; it should not be read as a proof that the text is identical, factual,
safe, or semantically equivalent. Diff and eval reports include this scope note
so green structural checks do not get mistaken for full semantic approval.
Entity and refusal checks are deliberately conservative so sentence starters,
supportive apologies, and ordinary support-ticket words do not become noisy
regression signals.

The next iterations should focus on external dogfood feedback, PyPI/tagged
release mechanics, and learning where real users need stronger adapters,
requirements, or judge rubrics.

See [examples/github-action.yml](examples/github-action.yml) for a GitHub
Actions starting point.
