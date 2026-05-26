# Contributing to redline

redline is a local-first eval tool, so every change should keep the first-user
loop clear: bring existing prompt-response logs, generate a suite, compare a
candidate run, and understand the trust boundary.

## Before you open a PR

Install the development tools from a clean checkout:

```bash
python -m pip install -e ".[dev]"
```

Run the same core checks as CI:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy redline tests scripts examples
git diff --check
```

For product-surface, packaging, report, or GitHub Action changes, also run the
external smoke paths:

```bash
bash scripts/action_smoke.sh /tmp/redline-action-smoke
bash scripts/build_release.sh /tmp/redline-dist
```

For release preparation, run the complete certification wrapper:

```bash
bash scripts/certify_release.sh /tmp/redline-certify
```

You can install the same checks as local git hooks:

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Code layout

```text
redline/          CLI, diff engine, suite generation, reports, MCP, audit
redline/runner_templates/  copyable runner and watch templates
redline/judge_template_files/  copyable judge scripts and rubrics
examples/         checked-in dogfood fixtures and GitHub Action example
docs/             user guides, release process, command reference
site/             static GitHub Pages website
scripts/          release, smoke, demo, and certification helpers
tests/            unit and integration tests for every product surface
```

Good first issues are usually docs, runner examples, importer presets, report
polish, or small false-positive reductions with a focused fixture. Start with
`docs/troubleshooting.md`, `docs/commands.md`, and tests around the behavior you
want to improve.

## Dogfood evidence

User-facing changes need at least one dogfood note in the PR. Keep it short and
concrete:

```text
Command: redline demo --public --compact
Result: caught 10 regressions, wrote HTML report, next step was clear
Friction: none / one specific issue
```

Prefer sanitized or synthetic logs. Do not commit private prompts, customer
data, API keys, model outputs that contain secrets, or product vision drafts.
The ignored local product docs stay local by design.

## Trust calibration

redline catches structural regressions first: invalid JSON, lost tables, new
refusals, missing keys, missing required numbers/entities, empty outputs, and
large content drift. A neutral result means no configured high-signal change was
detected. It is not proof that a response is factual, safe, on-tone, or
semantically equivalent.

If your change affects classification, summary text, reports, CI, or docs,
preserve that boundary in the output. When a workflow needs semantic judgment,
use pinned requirements or an optional judge rubric instead of making the
deterministic result sound stronger than it is.

## Good PR shape

- Keep slices small enough to validate and review independently.
- Add or update tests for every behavioral change.
- Prefer the existing CLI, JSONL, schema, and report patterns over new
  abstractions.
- Include the exact commands you ran and the user-visible result.
- If a change makes first run slower or noisier, call that out explicitly.
