# MCP Server

redline ships a local Model Context Protocol server so AI coding assistants can
run prompt regression checks instead of guessing whether a prompt change is
safe.

The MCP server is a thin stdio wrapper around the existing redline CLI. It does
not start a cloud service, does not add telemetry, and does not call model
providers unless the project already configured a replay or judge command that
does so.

## Install

```bash
python -m pip install redline-ai
```

From a repo checkout:

```bash
python -m pip install -e ".[dev]"
```

## Server Command

Configure your MCP client to run:

```bash
redline-mcp
```

Run it from the project root, or pass `cwd` in tool arguments so redline runs in
the intended repository.

## Tools

The first MCP surface is intentionally safe. It can generate suites, inspect
coverage, run diffs/evals, and write reports. It does not expose baseline mutation commands
such as `redline accept`, `redline mark`, or `redline require`.

Available tools:

- `redline_doctor`
- `redline_suite`
- `redline_validate`
- `redline_summary`
- `redline_cases`
- `redline_diff`
- `redline_eval`
- `redline_history`
- `redline_dashboard`

`redline_diff` and `redline_eval` return the underlying redline exit code as
structured data. Exit code `1` means redline found blocking regressions or
missing outputs; the MCP tool still returns successfully because that is a
product finding, not a protocol failure. Exit code `2` and above indicates a
setup or command error.

## Prompts

The server also exposes MCP prompt templates for the workflows agents should
reach for most often:

- `check_prompt_change`: run doctor, then eval a changed prompt file.
- `build_suite_from_logs`: generate a suite, validate it, and summarize coverage.
- `review_candidate_outputs`: diff candidate JSONL outputs and lead with blocking findings.

These prompts are intentionally conservative. They tell the assistant to treat
redline exit code `1` as a product finding, avoid baseline mutation, and avoid
claiming a prompt is semantically safe when redline only found neutral output.

## Example Prompts

Ask your assistant:

```text
Run redline doctor in this repo and tell me the next setup step.
```

```text
Generate a redline suite from logs/baseline.jsonl, then diff it against
logs/candidate.jsonl. Summarize only regressions I should review.
```

```text
Run redline eval with prompts/v2.txt and tell me whether this prompt change is
safe to ship. Do not accept or modify the baseline.
```

## Trust Boundary

The MCP server inherits redline's trust model:

- local-first by default
- deterministic structural checks first
- optional judges only when explicitly configured
- neutral does not mean semantically safe
- human review closes the loop before baselines are changed

Keep private prompt logs under ignored local paths such as `.redline/private/`.
