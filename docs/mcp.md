# MCP Server

redline ships a local Model Context Protocol server so AI coding assistants can
run prompt regression checks instead of guessing whether a prompt change is
safe.

The MCP server is a thin stdio wrapper around the existing redline CLI. It does
not start a cloud service, does not add telemetry, and does not call model
providers unless the project already configured a replay or judge command that
does so.

For command execution safety, MCP tools do not accept ad hoc replay or judge
command strings from the assistant. Configure those commands in `redline.json`
with `redline init --runner ...` or `redline init --judge ...`, review them as
repo-local code, then let MCP invoke the configured project setup.

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

For clients that prefer an explicit package runner, use `uvx`:

```json
{
  "mcpServers": {
    "redline": {
      "command": "uvx",
      "args": ["--from", "redline-ai", "redline-mcp"]
    }
  }
}
```

## Tools

The MCP surface is conservative. Most tools are read-only or write new reports,
but `redline_mark` can mutate a suite judgment and therefore requires
`allow_write: true` plus a human-readable `note`. Baseline promotion commands
such as `redline accept` stay out of the MCP server. The server can inspect
capture readiness, scan/redact logs, generate suites, inspect coverage, estimate
CI runtime, run diffs/evals, mark intentional findings after approval, read the
local audit trail, generate SBOM evidence, check prompt manifests, and write
reports.

Available tools:

- `redline_doctor`
- `redline_suite`
- `redline_redact`
- `redline_import`
- `redline_import_presets`
- `redline_watch_stats`
- `redline_watch_snippets`
- `redline_prompts`
- `redline_runners`
- `redline_judges`
- `redline_validate`
- `redline_summary`
- `redline_budget`
- `redline_benchmark` compatibility alias
- `redline_cases`
- `redline_case`
- `redline_mark` (guarded write: requires `allow_write: true` and `note`)
- `redline_diff`
- `redline_eval`
- `redline_history`
- `redline_dashboard`
- `redline_audit` (including `verify` and checkpoint output for the local audit hash chain)
- `redline_sbom`

`redline_diff` and `redline_eval` return the underlying redline exit code as
structured data. Exit code `1` means redline found blocking regressions or
missing outputs; the MCP tool still returns successfully because that is a
product finding, not a protocol failure. Exit code `2` and above indicates a
setup or command error.

When a tool is called with `json: true` and stdout is valid JSON, the MCP
response also includes the parsed payload under `structuredContent.json` so
assistants can reason over reports without scraping terminal text.

## Prompts

The server also exposes MCP prompt templates for the workflows agents should
reach for most often:

- `check_prompt_change`: run doctor, then eval a changed prompt file.
- `build_suite_from_logs`: generate a suite, validate it, and summarize coverage.
- `review_candidate_outputs`: diff candidate JSONL outputs and lead with blocking findings.
- `setup_redline_project`: guide first-time setup through runner selection,
  prompt/log discovery, suite validation, CI scale checks, and optional judge setup.

These prompts are intentionally conservative. They tell the assistant to treat
redline exit code `1` as a product finding, avoid baseline mutation unless the
user explicitly approves a guarded write, and avoid claiming a prompt is
semantically safe when redline only found neutral output.

## Example Prompts

Ask your assistant:

```text
Run redline doctor in this repo and tell me the next setup step.
```

```text
Set up redline for this project. Use my existing logs if available, choose the
right runner adapter, and do not mutate the baseline.
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
- replay and judge commands must come from reviewed project configuration, not
  ad hoc MCP tool arguments
- neutral does not mean semantically safe
- human review closes the loop before baselines are changed

Keep private prompt logs under ignored local paths such as `.redline/private/`.

## Registry

The root [server.json](../server.json) is the MCP Registry manifest for
`io.github.gowtham0992/redline`. It points at the PyPI package `redline-ai`,
uses stdio transport, and declares the `uvx --from redline-ai==<version>
redline-mcp` startup path.

The package README includes the hidden `mcp-name: io.github.gowtham0992/redline`
verification marker required for PyPI-backed MCP registry entries. Keep
`server.json`, `pyproject.toml`, and `redline/__init__.py` versions aligned
before publishing.
