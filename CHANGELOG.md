# Changelog

## 0.1.0

- Generate representative prompt eval suites from JSONL prompt-response logs.
- Replay suites through local commands with optional prompt templates and workers.
- Diff candidate outputs with deterministic regression signals and optional judges.
- Emit JSON, Markdown, JUnit, GitHub summary, and GitHub annotation reports.
- Watch and follow prompt logs, validate suites, compare report runs, and append report history.
- Run a realistic support-agent demo that catches concise-prompt regressions.
- Scaffold replay runners for OpenAI, Anthropic, HTTP APIs, Python chains, JSONL logs, and LiteLLM.
- Initialize projects with config schema, runner setup, and GitHub Actions workflow generation.
- Diagnose setup with actionable doctor checks and next-step commands.
- Protect the README quickstart path with an end-to-end integration test.
- Record the public terminal demo with `scripts/demo_terminal.sh`.
