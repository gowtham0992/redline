# Command Reference

This is the compact map. Run `redline <command> --help` for exact argparse
output and examples after installing.

| Command | Purpose | Common flags |
| --- | --- | --- |
| `redline` | Show first-run help. | `--version` |
| `redline demo` | Generate and diff the bundled demo logs. | `--public`, `--compact` |
| `redline status` | Show project readiness, latest local evidence, app command, first review case, and the next command to run. | `--reports-dir`, `--history`, `--checkpoint`, `--limit`, `--json` |
| `redline app` | Open the guided local product app for import, suite, eval, review, history, and integration commands. | `--demo`, `--reports-dir`, `--history`, `--checkpoint`, `--out`, `--no-open`, `--json` |
| `redline init` | Write `redline.json`, runner files, and optional CI workflow. | `--runner`, `--copy-runner`, `--github-action`, `--force` |
| `redline doctor` | Check config, suite, replay, reports, audit, and team workflow. | `--strict`, `--json` |
| `redline watch` | Collect prompt-response observations or print snippets. | `--log`, `--stats`, `--snippet`, `--follow` |
| `redline import` | Normalize exported JSONL fields into redline `prompt`/`response` logs, with best-effort redaction on by default. | `--list-presets`, `--detect`, `--auto-map`, `--preview`, `--preset`, `--input-field`, `--output-field`, `--context-field`, `--metadata-field`, `--limit`, `--out`, `--no-redact` |
| `redline redact` | Check or write best-effort redacted logs. | `--check`, `--out`, `--json` |
| `redline cluster` | Inspect deterministic behavior-signature groups before suite generation. | `--max-cases`, `--json` |
| `redline suite` | Generate a suite from baseline JSONL logs, with excluded-case previews when representative sampling omits unique pairs. | `--out`, `--max-cases`, `--all-cases`, `--owner` |
| `redline suite add` | Pin a hand-picked edge case. | `--prompt`, `--response`, `--include`, `--exclude`, `--owner` |
| `redline cases` | List generated suite case IDs and coverage. | `--json` |
| `redline case` | Show one full suite case. | `--json` |
| `redline require` | Add deterministic include/exclude requirements. | `--include`, `--exclude`, `--owner` |
| `redline prompts` | Build or check a prompt-to-suite manifest. | `--suite-dir`, `--out`, `--check`, `--check-suites` |
| `redline summary` | Summarize suite or manifest readiness, including suite score and coverage gaps. | `--json` |
| `redline validate` | Validate suite or manifest structure and freshness. | `--strict`, `--json` |
| `redline quick-check` | Generate a temporary suite from baseline JSONL, diff candidate JSONL, and write reports plus a guided local app in one first-run command. Small logs are exhaustive by default; larger sampled logs print excluded-case previews. | `--input-field`, `--output-field`, `--out-dir`, `--max-cases`, `--all-cases`, `--profile`, `--fail-on`, `--open`, `--open-app` |
| `redline budget` | Estimate CI runtime without replaying prompts. | `--workers`, `--timeout`, `--max-seconds`, `--measure-local` |
| `redline benchmark` | Compatibility alias for `redline budget`. | Same as `budget` |
| `redline eval` | Replay suite cases through a configured runner. | `--prompt`, `--replay`, `--workers`, `--judge`, `--fail-on`, `--compact` |
| `redline diff` | Compare candidate JSONL against a suite baseline. | `--profile`, `--fail-on`, `--compact`, `--out-json`, `--out-html` |
| `redline mark` | Record human judgment on a case. | `--status`, `--note`, `--owner` |
| `redline accept` | Promote reviewed candidate outputs into the suite baseline. | `--candidate`, `--all-expected`, `--approver`, `--note` |
| `redline history` | Append and summarize trend history. | `--label`, `--out`, `--out-md`, `--fail-on` |
| `redline compare` | Compare two redline reports. | `--fail-on`, `--out-json`, `--out-html` |
| `redline dashboard` | Render a self-contained local HTML dashboard artifact. | `--reports-dir`, `--history`, `--checkpoint`, `--out`, `--style classic\|app`, `--open` |
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
- `redline quick-check` includes all unique prompt-response pairs when the log
  fits within `--max-cases`; use `--all-cases` to force exhaustive coverage on
  larger logs.

## Trust boundary

Structural checks are deterministic and local. Green or neutral does not prove
semantic equivalence. Use `redline require`, `redline mark`, and optional judge
templates for factual, tone, hallucination, policy, or reasoning risks.

## Import Help

Use `redline import --detect` when you do not know an export's field names.
Use `--auto-map --preview 3` when you want redline to try the best detected
mapping before writing normalized logs. Source-specific recipes live in
[docs/import-guides.md](import-guides.md).

## Diff profiles

- `--profile strict` is the default CI-oriented mode. Missing concrete details
  such as numbers and likely entities are blocking regressions.
- `--profile review` is a softer calibration mode for noisy exploratory logs.
  Missing numbers and likely entities become reviewable `changed` cases while
  hard structural losses, such as invalid JSON, missing JSON keys, empty
  outputs, refusals, tables, lists, code blocks, and URLs, stay blocking.
