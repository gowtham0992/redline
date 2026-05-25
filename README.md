# redline

<!-- mcp-name: io.github.gowtham0992/redline -->

[![CI](https://github.com/gowtham0992/redline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gowtham0992/redline/actions/workflows/ci.yml)
[![GitHub Pages](https://github.com/gowtham0992/redline/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/gowtham0992/redline/actions/workflows/pages.yml)
[![PyPI](https://img.shields.io/pypi/v/redline-ai.svg)](https://pypi.org/project/redline-ai/)
[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-io.github.gowtham0992%2Fredline-blue)](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Fredline)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/gowtham0992/redline?style=social)](https://github.com/gowtham0992/redline/stargazers)

[Website](https://gowtham0992.github.io/redline/) · [Docs](#project-docs) · [MCP](docs/mcp.md) · [MCP Registry](https://registry.modelcontextprotocol.io/?q=io.github.gowtham0992%2Fredline) · [Security](SECURITY.md) · [License](LICENSE)

**Automatic eval suites from the prompt logs you already have.**

redline turns real prompt-response logs into regression tests. It watches or
imports existing outputs, selects representative cases, replays your changed
prompt, and shows the behavioral diff before a bad prompt ships.

![redline product demo](https://gowtham0992.github.io/redline/assets/redline-product-demo.gif)

## Product Promise

In under five minutes, on a real prompt log, redline should catch one regression
you did not want to ship.

That promise is intentionally narrow. redline is not a hosted eval platform, a
generic score, or a replacement for human judgment. It is the local safety loop
between "I changed the prompt" and "this is safe enough to merge."

## Why It Exists

Most teams already have the raw material for evals: prompts, outputs, support
tickets, traces, model responses, and production logs. What they usually do not
have is time to hand-write a full regression suite before every prompt edit.

redline makes the first suite free:

1. Use the logs you already have.
2. Cluster behavior into representative cases.
3. Re-run the suite after a prompt change.
4. See exactly what broke: JSON keys, required numbers, URLs, tables, code
   blocks, refusals, empty answers, and other high-signal changes.
5. Mark intentional changes, accept reviewed outputs, and keep the suite moving
   with the product.

## Start Here

Install from PyPI:

```bash
python -m pip install redline-ai
```

Run the public proof:

```bash
redline demo --public --compact
```

The demo catches ten synthetic regressions without API keys, private logs, a
cloud account, or an LLM judge. It writes JSON, Markdown, and self-contained
HTML reports under `.redline/demo`.

Open the local demo report index:

```bash
redline dashboard --reports-dir .redline/demo/reports --open
```

## Real Workflow

Build a suite from baseline logs:

```bash
redline suite logs/baseline.jsonl --out redline-suite.json
```

Evaluate a changed prompt file through your configured runner:

```bash
redline eval --prompt prompts/v2.txt
```

Or compare candidate outputs you already generated:

```bash
redline diff redline-suite.json logs/candidate.jsonl
```

When redline finds a blocking change, it exits non-zero for CI and prints the
reason:

```text
REGRESSION case_004
- candidate missing JSON keys: owner, required_action
- candidate missing URL: https://example.com/policies/refunds

Confidence: HIGH | fix blocking cases before shipping
```

## What redline Catches

| Signal | Example regression |
| --- | --- |
| JSON validity and keys | Candidate stops returning valid JSON or drops `owner`. |
| Tables, lists, and code blocks | Markdown table becomes prose; code fence disappears. |
| Numbers, URLs, and entities | Refund window, ticket ID, policy URL, or owner is missing. |
| Empty outputs and refusals | Candidate newly refuses a safe task or returns nothing. |
| Content drift | Same-shape response changes substantially. |
| Explicit requirements | Pinned cases require or forbid exact strings. |

redline is deterministic and local-first by default. Optional judge commands are
available for ambiguous `changed` cases, but redline does not call a cloud model
unless you explicitly configure that command.

Suite generation groups logs by deterministic behavior signatures, not opaque
embedding clusters. It picks one representative per group first, then adds
high-variance edges and evenly spread prompt-diverse samples from large clusters
when the case budget allows.

## Trust Boundary

A green redline run means no configured high-signal structural blockers were
found. It does not prove factual correctness, tone, hallucination safety, policy
compliance, or subtle reasoning quality.

That boundary is visible in CLI output and reports because over-trusting eval
tools is dangerous. Each reported case includes a confidence and signal
(`structural`, `shallow_semantic`, `requirement`, `judge`, or `human_judgment`)
so reviewers can see why redline is making the call. Use requirements or an
optional judge for semantic risks that structural checks cannot prove.

## Product Surface

redline is built around the full prompt-regression loop:

- `redline watch`: collect prompt-response observations from logs, Python
  functions, OpenAI/Anthropic-compatible SDK calls, or ASGI apps, with common
  secrets and PII redacted before write by default.
- `RedlineMiddleware`: capture bounded JSON FastAPI or ASGI request/response pairs locally, with optional skip diagnostics.
- `redline redact --check`: scan logs for common secrets and PII, then write a scrubbed copy when needed.
- `redline cluster`: inspect behavior groups before suite generation.
- `redline suite`: generate a representative eval suite from baseline logs.
- `redline prompts`: scan many prompt files and write or check a versionable prompt-to-suite manifest.
  Add `--check-suites` in CI when every prompt should already have a built and valid suite.
- `redline suite add`: pin hand-picked edge cases the algorithm should never miss.
- `redline benchmark`: estimate suite runtime without executing replay commands,
  write budget artifacts, and optionally fail on a CI time budget.
- `redline eval`: replay each suite case through your local app or model runner.
- `redline diff`: compare candidate JSONL outputs against the suite baseline.
- `redline mark` and `redline accept`: review intentional changes and promote the
  new baseline.
- `redline require`: add deterministic must-include or must-not-include rules.
- `redline audit --verify`: inspect the local audit trail and verify the hash chain.
  Add `--expect-last-hash` or `--expect-entries` when you want to prove the
  local log tail still matches a checkpoint from CI or release evidence. Add
  `--out-checkpoint .redline/audit-checkpoint.json` to persist that evidence,
  then `--checkpoint .redline/audit-checkpoint.json` to verify against it later.
- `redline sbom`: write CycloneDX SBOM release evidence for security review.
- `redline history`, `redline compare`, and `redline dashboard`: track quality
  over time and inspect reports locally. The dashboard surfaces feature-level
  rollups, prompt-level eval rows, and a latest-report review queue when reports
  come from a prompt manifest.
- `redline-mcp`: let AI coding assistants run checks inside Claude, Codex,
  Cursor, Kiro, or any MCP client.

For repos with many prompt files, the manifest becomes the eval plan:

```bash
redline prompts prompts/ --suite-dir suites --out redline-prompts.json
redline prompts prompts/ --suite-dir suites --out redline-prompts.json --check --check-suites
redline eval redline-prompts.json
```

Manifest evals print prompt-level rollups before case details, so large repos
can see which prompt files or feature folders need attention first.

When mapped suites are valid, the check prints ready commands such as:

```bash
redline eval suites/support/triage.redline-suite.json --prompt prompts/support/triage.txt
```

## Connect Your App

Any command that reads a prompt from stdin and prints a response to stdout can
be a redline runner:

```bash
redline init --runner stdio --copy-runner --github-action
```

Built-in adapters cover provider-neutral stdio, OpenAI, Anthropic, LiteLLM,
HTTP APIs, Python chains, JSONL log imports, and OpenAI/Anthropic SDK capture:

```bash
redline runners
redline runners --copy all
```

Runner details live in [docs/runners.md](docs/runners.md). Log import and SDK
capture adapters are for building suites from real observations, not for
`redline eval` replay. The JSONL log adapter includes Langfuse and Helicone
presets for exported observability logs.

## AI Assistant Native

redline ships a local Model Context Protocol server:

```bash
redline-mcp
```

Use [docs/mcp.md](docs/mcp.md) to wire redline into an MCP client. The MCP
surface exposes safe capture-readiness, privacy, audit, scale, read,
case-inspection, eval, and report tools plus workflow prompts like
`setup_redline_project`, `check_prompt_change`, `build_suite_from_logs`, and
`review_candidate_outputs`.
It can also list or copy runner adapters and optional judge templates during setup.
It does not expose baseline mutation commands.

## CI And GitHub

Create config plus a GitHub Actions workflow:

```bash
redline init --runner stdio --copy-runner --github-action
```

Use redline as a composite GitHub Action from another repo:

```yaml
- uses: gowtham0992/redline@v0.1.0
  with:
    prompt-path: prompts/v2.txt
    benchmark-max-seconds: "300"
```

The action writes JSON, Markdown, HTML, JUnit, history, dashboard, and audit checkpoint artifacts
under `.redline/`, appends benchmark, report, and trend summaries to the
GitHub step summary, and exits with the eval gate status. Set
`benchmark-max-seconds` when a suite should fail CI if its worst-case runtime
budget grows too far.

## Reports

Every `diff` and `eval` run can write:

- JSON for machines and dashboards
- Markdown for PR comments and summaries, including prompt-manifest rollups
- self-contained HTML for side-by-side inspection, including feature and prompt eval tables
- JUnit XML for CI test reporting
- GitHub annotations for changed or blocking cases

Example:

```bash
redline diff redline-suite.json logs/candidate.jsonl \
  --out-json .redline/reports/diff.json \
  --out-md .redline/reports/diff.md \
  --out-html .redline/reports/diff.html \
  --out-junit .redline/reports/diff.xml
```

## Optional Judges

Use judges only where structural checks are not enough. redline sends only
ambiguous `changed` cases to the configured command as JSON on stdin:

```bash
redline judges
redline judges --copy openai
redline judges --copy support-rubric
redline diff logs/candidate.jsonl --judge "python examples/judge_changed.py"
```

Repo examples and installable templates:

- [examples/judge_changed.py](examples/judge_changed.py)
- [examples/openai_judge.sh](examples/openai_judge.sh)
- [examples/anthropic_judge.sh](examples/anthropic_judge.sh)
- [examples/litellm_judge.sh](examples/litellm_judge.sh)
- [examples/judges/support_rubric.md](examples/judges/support_rubric.md)
- [examples/judges/extraction_rubric.md](examples/judges/extraction_rubric.md)
- [examples/judges/safety_rubric.md](examples/judges/safety_rubric.md)

Calibration guidance lives in [docs/judges.md](docs/judges.md).

## Config

`redline init` writes `redline.json` with a `$schema` reference for editor
autocomplete. Important keys:

| Key | Purpose |
| --- | --- |
| `suite` | Suite baseline path, default `redline-suite.json`. |
| `input_field`, `output_field` | JSONL field paths for prompts and responses. |
| `max_cases` | Maximum representative cases selected for a suite. |
| `replay` | Command used by `eval`; prompts go to stdin by default. `{prompt}` is for small legacy argv runners; `{prompt_file}` passes a temporary rendered-prompt file path. |
| `workers` | Number of replay cases to run concurrently. |
| `owners` | Optional pattern-to-owner rules so regressions show the responsible team. |
| `approval` | Optional local guardrail; `require_approver` makes `accept` record an approver. |
| `fail_on` | Statuses that fail `diff` or `eval`; use `"none"` for report-only setup. |
| `reports` | JSON, Markdown, HTML, and JUnit output paths. |
| `logs` | Observed prompt-response log path and optional middleware skip diagnostics path. |
| `audit` | Append-only JSONL audit log path for evals, judgments, requirements, and accepted baselines. New entries include operator/approver context plus a local hash chain that `redline audit --verify` can check; use expected hash/count checkpoints or `--out-checkpoint` evidence files to detect tail truncation. |
| `judge` | Optional command for ambiguous `changed` cases. |

Check setup before relying on a suite:

```bash
redline doctor --strict
redline validate redline-suite.json --strict
redline summary redline-suite.json
```

`summary` reports cluster/case coverage, owner coverage, accepted baseline
history, and approver coverage so teams can review suite readiness before CI.
`dashboard` also shows audit checkpoint evidence when `.redline/audit-checkpoint.json`
is present.

## Dogfood Assets

The public fixture is synthetic, shaped after public instruction/chat dataset
patterns, and documented in
[examples/public_dogfood_sources.md](examples/public_dogfood_sources.md).

```bash
python -m redline suite examples/public_dogfood_baseline.jsonl --out /tmp/redline-public-suite.json --all-cases
python -m redline diff /tmp/redline-public-suite.json examples/public_dogfood_candidate.jsonl --compact --fail-on none
```

For AI-assistant session dogfood, use
[docs/ai-session-dogfood-prompts.jsonl](docs/ai-session-dogfood-prompts.jsonl)
and normalize raw exports with `scripts/normalize_ai_session_logs.py`.

From a repo checkout, record the public demo:

```bash
bash scripts/demo_terminal.sh
bash scripts/demo_gif.sh .redline/launch .redline/launch/redline-demo.gif
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m mypy redline tests scripts examples
```

Before cutting a release or asking someone else to try a branch:

```bash
bash scripts/release_check.sh
```

## Project Docs

- [docs/release.md](docs/release.md): package, tag, PyPI, and MCP Registry release flow
- [docs/launch.md](docs/launch.md): public alpha launch plan
- [docs/dogfood.md](docs/dogfood.md): first-user dogfood protocol
- [docs/runners.md](docs/runners.md): runner and log adapter setup
- [docs/mcp.md](docs/mcp.md): MCP server setup
- [docs/benchmarks.md](docs/benchmarks.md): performance contract and CI benchmark artifacts
- [docs/repository.md](docs/repository.md): GitHub repository controls
- [CONTRIBUTING.md](CONTRIBUTING.md): contributor validation
- [SECURITY.md](SECURITY.md): privacy and vulnerability reporting
- [LICENSE](LICENSE): MIT open source license

Website source for GitHub Pages lives in [site/](site/) and deploys from the
committed static assets on `main`.
