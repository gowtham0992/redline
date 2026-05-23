# Changelog

## 0.1.0

- Generate representative prompt eval suites from JSONL prompt-response logs.
- Package the CLI as `redline-ai` while exposing the `redline` command.
- Show first-run guidance when `redline` is run without a command.
- Replay suites through local commands with optional prompt templates and workers.
- Diff candidate outputs with deterministic regression signals and optional judges.
- Add a `review` diff profile for long-form assistant logs where missing numbers and entities should be reviewed instead of blocking by default.
- Emit JSON, Markdown, JUnit, GitHub summary, and GitHub annotation reports.
- Watch and follow prompt logs, validate suites, compare report runs, and append report history.
- Render Markdown history reports and publish trend history to GitHub step summaries.
- Run a realistic support-agent demo that catches concise-prompt regressions.
- Show actionable next steps after demo and suite generation commands.
- Ship larger dogfood prompt logs that exercise several regression classes.
- Normalize AI assistant session exports for private dogfood comparisons.
- Include all fixed prompt rows with `redline suite --all-cases`.
- Include optional OpenAI-, Anthropic-, and LiteLLM-backed judge command templates for ambiguous changes.
- Scaffold replay runners for OpenAI, Anthropic, HTTP APIs, Python chains, JSONL logs, and LiteLLM.
- Initialize projects with config schema, runner setup, and GitHub Actions workflow generation.
- Diagnose setup with actionable doctor checks and next-step commands.
- Protect the README quickstart path with an end-to-end integration test.
- Record the public terminal demo with `scripts/demo_terminal.sh`.
