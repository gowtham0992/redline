# Command Reference

This is the compact map. Run `redline <command> --help` for exact argparse
output and examples after installing.

| Command | Purpose | Common flags |
| --- | --- | --- |
| `redline` | Show first-run help. | `--version` |
| `redline demo` | Generate and diff the bundled demo logs. | `--public`, `--compact` |
| `redline init` | Write `redline.json`, runner files, and optional CI workflow. | `--runner`, `--copy-runner`, `--github-action`, `--force` |
| `redline doctor` | Check config, suite, replay, reports, audit, and team workflow. | `--strict`, `--json` |
| `redline watch` | Collect prompt-response observations or print snippets. | `--log`, `--stats`, `--snippet`, `--follow` |
| `redline import` | Normalize exported JSONL fields into redline `prompt`/`response` logs, with best-effort redaction on by default. | `--list-presets`, `--preset`, `--input-field`, `--output-field`, `--context-field`, `--metadata-field`, `--limit`, `--out`, `--no-redact` |
| `redline redact` | Check or write best-effort redacted logs. | `--check`, `--out`, `--json` |
| `redline cluster` | Inspect deterministic behavior-signature groups before suite generation. | `--max-cases`, `--json` |
| `redline suite` | Generate a suite from baseline JSONL logs. | `--out`, `--max-cases`, `--all-cases`, `--owner` |
| `redline suite add` | Pin a hand-picked edge case. | `--prompt`, `--response`, `--include`, `--exclude`, `--owner` |
| `redline cases` | List generated suite case IDs and coverage. | `--json` |
| `redline case` | Show one full suite case. | `--json` |
| `redline require` | Add deterministic include/exclude requirements. | `--include`, `--exclude`, `--owner` |
| `redline prompts` | Build or check a prompt-to-suite manifest. | `--suite-dir`, `--out`, `--check`, `--check-suites` |
| `redline summary` | Summarize suite or manifest readiness, including suite score and coverage gaps. | `--json` |
| `redline validate` | Validate suite or manifest structure and freshness. | `--strict`, `--json` |
| `redline budget` | Estimate CI runtime without replaying prompts. | `--workers`, `--timeout`, `--max-seconds`, `--measure-local` |
| `redline benchmark` | Compatibility alias for `redline budget`. | Same as `budget` |
| `redline eval` | Replay suite cases through a configured runner. | `--prompt`, `--replay`, `--workers`, `--judge`, `--fail-on`, `--compact` |
| `redline diff` | Compare candidate JSONL against a suite baseline. | `--profile`, `--fail-on`, `--compact`, `--out-json`, `--out-html` |
| `redline mark` | Record human judgment on a case. | `--status`, `--note`, `--owner` |
| `redline accept` | Promote reviewed candidate outputs into the suite baseline. | `--candidate`, `--all-expected`, `--approver`, `--note` |
| `redline history` | Append and summarize trend history. | `--label`, `--out`, `--out-md`, `--fail-on` |
| `redline compare` | Compare two redline reports. | `--fail-on`, `--out-json`, `--out-html` |
| `redline dashboard` | Render a self-contained local HTML dashboard. | `--reports-dir`, `--history`, `--checkpoint`, `--out`, `--open` |
| `redline runners` | List or copy runner and log adapter templates. | `--copy`, `--out`, `--force` |
| `redline judges` | List or copy judge templates. | `--copy`, `--out`, `--force` |
| `redline audit` | Show and verify local audit events. | `--verify`, `--checkpoint`, `--out-checkpoint`, `--expect-last-hash` |
| `redline sbom` | Write CycloneDX SBOM release evidence. | `--out`, `--json` |
| `redline-mcp` | Start the local MCP stdio server. | `--help` |

## Defaults to know

- Config path: `redline.json`.
- Default suite: `redline-suite.json`.
- Default fail-on statuses: `regression,missing`.
- Default eval timeout: `30` seconds per case.
- Default workers: `1`, unless configured in `redline.json`.
- Reports default to `.redline/reports/{command}.*` when configured by
  `redline init`.

## Trust boundary

Structural checks are deterministic and local. Green or neutral does not prove
semantic equivalence. Use `redline require`, `redline mark`, and optional judge
templates for factual, tone, hallucination, policy, or reasoning risks.

## Diff profiles

- `--profile strict` is the default CI-oriented mode. Missing concrete details
  such as numbers and likely entities are blocking regressions.
- `--profile review` is a softer calibration mode for noisy exploratory logs.
  Missing numbers and likely entities become reviewable `changed` cases while
  hard structural losses, such as invalid JSON, missing JSON keys, empty
  outputs, refusals, tables, lists, code blocks, and URLs, stay blocking.
