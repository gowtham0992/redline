# Changelog

## 0.2.0

redline 0.2.0 makes the public alpha easier to adopt from real team logs and
easier to evaluate from the README, GitHub Pages, MCP clients, and CI.

Highlights:

- Normalize arbitrary JSONL exports into redline's `prompt`/`response` shape
  with `redline import`.
- Expose the same import workflow through MCP as `redline_import`.
- Add product proof screenshots from real generated dashboard and HTML report
  artifacts.
- Harden public-release readiness with troubleshooting docs, a command
  reference, Python 3.10-3.13 CI coverage, pre-commit guidance, and isolated
  release builds.

### Added

- Add `redline import` for converting public datasets, team logs, and exported
  traces into redline JSONL using configurable input, output, context, id, and
  metadata fields.
- Add MCP `redline_import` so AI coding assistants can normalize exported logs
  before generating suites.
- Add dashboard and HTML report proof screenshots to the README and GitHub
  Pages site.
- Add `docs/troubleshooting.md` for first-run, dashboard, validation, Action,
  and trust-boundary recovery paths.
- Add `docs/commands.md` as a compact command reference.
- Add `scripts/README.md` as a maintainer script index.
- Add `.pre-commit-config.yaml` and contributor docs for local validation.
- Add a contributor architecture map.
- Add Python 3.10, 3.11, 3.12, and 3.13 CI matrix coverage.
- Add pytest coverage output to CI.
- Add direct tests for stable prompt-response content hashing.

### Changed

- Move README installation and first-run commands above the product narrative.
- Call out zero runtime dependencies as a product and supply-chain advantage.
- Add Docs navigation, project badges, and product proof imagery to GitHub
  Pages.
- Rewrite the changelog into grouped release sections.
- Run release builds with isolated build dependencies instead of relying on the
  ambient environment.
- Document SemVer expectations before 1.0.
- Document ASGI middleware and SDK watch snippet privacy boundaries.
- Document `action.yml` `extra-args` spacing limitations.

### Fixed

- Fix Python 3.10 mypy compatibility for TOML parsing in packaging tests.
- Remove public docs/tests that depended on ignored local `ROADMAP.md`.
- Fix stale onboarding and release references surfaced during public-release
  review.
- Keep product proof assets small enough for README and Pages use.

## 0.1.0

redline's first public release turns existing prompt-response logs into local
regression suites, compares changed prompts or candidate runs, and produces
reviewable reports without runtime dependencies or cloud services.

Highlights:

- First value in under a minute with `python -m pip install redline-ai` and
  `redline demo --public --compact`.
- Local deterministic checks for structural regressions, with optional judges
  for ambiguous or domain-specific changes.
- Complete loop from logs to suite, diff/eval, review, accept, history,
  dashboard, CI, MCP, and release evidence.

### Added

**Core eval loop**

- Generate representative prompt eval suites from JSONL prompt-response logs.
- Show actionable next steps after demo and suite generation commands.
- Replay suites through local commands with optional prompt templates and
  workers.
- Diff candidate outputs with deterministic regression signals and optional
  judges.
- Add the `review` diff profile for long-form assistant logs where missing
  numbers and entities should be reviewed instead of blocking by default.
- Support `redline suite --all-cases` for exhaustive fixed-row suites.
- Pin hand-picked edge cases with `redline suite add`.
- Run prompt manifests with `redline eval redline-prompts.json`.
- Print ready `redline eval <suite> --prompt <file>` commands from prompt
  manifest suite checks.

**Reports and dashboards**

- Emit JSON, Markdown, JUnit, GitHub summary, and GitHub annotation reports.
- Write self-contained HTML diff/eval reports for side-by-side inspection.
- Write Slack Block Kit JSON reports for CI bots or webhook integrations.
- Add `redline dashboard` for a self-contained local HTML index of reports,
  benchmark artifacts, trend history, audit checkpoints, prompt rollups, and
  review queues.
- Show blocking and changed review counts in the dashboard reports table.
- Show prompt-level eval rows and a latest-report review queue in the local
  dashboard.
- Add HTML output for `redline compare`.
- Add human-readable behavior labels in cluster output and diff/eval reports.

**History, trends, and review**

- Render Markdown history reports and publish trend history to GitHub step
  summaries.
- Diagnose history trends as better, worse, or flat based on blocking
  regressions across recent runs.
- Diagnose top cluster-level trend deltas in `redline history`.
- Add review command guidance to Markdown, HTML, PR-comment, and dashboard
  outputs.
- Write concise PR-comment Markdown reports with owners, top blocking cases,
  artifacts, and review commands.
- Show the mark/accept review loop in the first-run demo.

**Prompt manifests and team ownership**

- Summarize prompt manifests with readiness, owners, requirements, and missing
  suite rollups.
- Validate prompt manifests and mapped suites with
  `redline validate redline-prompts.json`.
- Support prompt manifests in the composite GitHub Action and generated
  workflow.
- Aggregate prompt manifest runtime budgets in `redline benchmark` and GitHub
  Action reports.
- Show owner coverage, top owners, owner-rule provenance, approver coverage,
  and explicit guard coverage in summaries, doctor checks, reports, and the
  dashboard.

**CI, release, and trust evidence**

- Add a composite GitHub Action entrypoint for external repositories.
- Render and upload `.redline/dashboard.html` from generated GitHub workflows.
- Append concise eval-comment Markdown directly to GitHub step summaries in
  generated workflows and the composite action.
- Add audit checkpoint files from `redline audit --verify --out-checkpoint`.
- Verify audit logs against saved checkpoint files with
  `redline audit --verify --checkpoint`.
- Return non-zero from `redline audit --verify` when the audit hash chain fails.
- Add `redline sbom` and release-build SBOM output for CycloneDX security
  evidence.
- Include default data-egress and judge data-flow guarantees in SBOM evidence.
- Add release certification scripts, action smoke tests, and public release
  documentation.

**MCP and AI-editor workflow**

- Add `redline-mcp`, a local MCP stdio server for running redline checks inside
  AI coding assistants without mutating baselines by default.
- Add MCP Registry metadata for publishing the PyPI-backed server.
- Expose suite generation, validation, eval, diff, summary, history, dashboard,
  budget, runner discovery, judge discovery, and guarded mark flows through MCP.
- Add a first-time MCP setup prompt for runner selection, prompt/log discovery,
  suite validation, CI scale checks, and optional judge setup.
- Expose parsed JSON stdout in MCP structured content when tools are called with
  `json: true`.

**Adapters, watch capture, and runners**

- Add copyable runner templates for OpenAI, Anthropic, HTTP APIs, Python
  chains, JSONL logs, LiteLLM, and stdio.
- Add Langfuse, Helicone, LangSmith, and Braintrust presets to the JSONL log
  adapter.
- Add a Braintrust suite-export adapter for turning redline suites into dataset
  JSONL.
- Add `redline watch --snippet` for copy-paste decorator, SDK patch, and
  FastAPI capture setup.
- Capture prompt-response pairs from Python functions with the local `@watch`
  decorator and `record()` helper.
- Bound ASGI middleware capture by JSON content type, content length, byte
  count, and non-streaming responses by default.
- Include middleware skip reason counts in `redline watch --stats`.

**Docs, launch, and product surface**

- Add a product-focused README, demo GIF, public alpha launch playbook, static
  GitHub Pages site, logo assets, troubleshooting guide, command reference,
  runner guide, judge guide, MCP guide, release guide, repository guide, and
  scripts index.
- Add richer judge rubrics for support, structured extraction, and
  safety/compliance review.
- Add `redline judges` to list and copy packaged judge commands and domain
  rubrics from any install.
- Record reproducible public dogfood case studies and internet dogfood source
  notes.

### Changed

- Calibrate diff and eval decisions so neutral runs say "no structural
  blockers" instead of implying full semantic approval.
- Replace raw JSON parser failures with actionable JSONL-vs-suite guidance for
  suite and prompt-manifest commands.
- Spread suite budget across more prompt-diverse samples inside very large
  same-shape clusters.
- Reduce noisy entity-loss signals from pronouns and bullet-leading adjectives
  found during Dolly dogfood.
- Lead `redline runners` output with the provider-agnostic stdin/stdout
  contract.
- Keep top-level `redline --help` on the curated first-run path and include the
  review loop.
- Preserve baseline order when reporting missing numbers, URLs, and entities.
- Keep comma-formatted numbers, percentages, and times readable in regression
  reasons.
- Strip trailing sentence punctuation from extracted URLs.
- Warn when suite validation finds redundant duplicate prompt-response cases,
  missing stable content hashes, or source logs newer than suite generation
  timestamps.

### Fixed

- Guard generated config keys against schema documentation drift.
- Prevent log import adapters from being configured as eval replay runners.
- Warn from `redline doctor` when copied runner adapters are missing required
  environment variables.
- Explain from `redline doctor` when a log adapter is manually configured as
  replay.
- Detect common Spanish, French, Portuguese, German, Chinese, and Japanese AI
  refusal phrasing.
- Validate judgment statuses, timestamps, and missing reasons before team
  rollout.
- Skip exact duplicate prompt-response pairs when generating suites from noisy
  logs.
- Store stable prompt-response content hashes on suite cases and refresh them
  when accepting new baselines.
