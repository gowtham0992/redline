# redline Product Vision

redline is the local-first regression-test primitive for production AI prompts.
It turns prompt-response logs teams already have into an eval suite, then tells
the engineer whether a prompt change is better, worse, or dangerously different.

The north-star experience is deliberately small:

```text
I changed my system prompt.
Before I ship, I run redline.
It shows me the cases where the new version behaves differently:
some improved, some stayed neutral, and a few are regressions I would have missed.
I fix the regressions, accept intentional changes, and ship with confidence.
```

The product is not dashboard-first, SaaS-first, or model-benchmark-first. The
terminal diff is the core product. Reports, dashboards, GitHub summaries, and
team workflows exist to support that one loop.

## Primary User

redline is designed first for the AI engineer who owns a production prompt and
is about to change it.

They have a repo, a CI pipeline, a deadline, and logs of what the prompt returned
last week. They will not hand-write a full eval suite before every prompt change.
redline wins when it makes the first useful suite appear from evidence they
already have.

Secondary users include ML platform teams, founding engineers, AI library
maintainers, and enterprise AI leads who need a documented prompt-change review
process.

## Sharp Boundaries

redline is not an observability platform. Use trace and monitoring products for
post-ship analytics. redline is a pre-ship regression gate.

redline is not a general model benchmark. It compares your prompt v1 against
your prompt v2 on your cases.

redline is not a safety scanner. It can catch refusal and policy-behavior
regressions, but it is not a red-teaming or prompt-injection product.

redline is not a replacement for human judgment. It writes the first suite,
flags changes, records reasons, and makes review explicit. The engineer still
marks expected changes and accepts new baselines.

## End-State Layers

### 1. Watch: Passive Evidence Collection

The full watch layer should capture prompt-response evidence from real apps with
as little ceremony as possible: JSONL tailing, provider wrappers, framework
adapters, and eventually a Python decorator or middleware that can wrap existing
LLM calls.

World-class watch means:

- prompt, response, model, temperature, latency, token counts, and metadata can
  be captured locally;
- duplicate records are ignored by default;
- coverage gaps are visible before suite generation;
- the user knows when there is enough evidence to run `redline suite`;
- OpenAI, Anthropic, LangChain, LlamaIndex, HTTP APIs, LiteLLM, and raw JSONL all
  have a clear path.

### 2. Suite: Automatic Eval Generation

`redline suite` is the core product wedge. It takes raw prompt-response logs and
builds a representative suite weighted toward behavioral clusters, edge cases,
high-variance outputs, and failure-adjacent examples.

World-class suite generation means:

- clustering by behavior, not just topic;
- source provenance for every case;
- staleness warnings when the suite no longer matches recent behavior;
- manual pinning for important cases the algorithm missed;
- a stable, documented suite schema that other tools can generate.

### 3. Eval: The Regression Gate

`redline eval --prompt prompts/v2.txt` is the payoff. It replays the suite
against a changed prompt and emits a behavioral diff, not a score.

World-class eval means:

- deterministic structural checks run first;
- optional judges only review ambiguous changed cases;
- high-confidence regressions are obvious blockers;
- low-confidence changes are review items;
- reports include reasons that explain exactly what changed;
- run comparison shows whether a fix improved or worsened behavior.

### 4. CI: The Merge Gate

The CI layer should make redline boilerplate in AI repos. A prompt-touching pull
request should run the suite, attach the diff, upload reports, and block merge
on configured regression thresholds.

World-class CI means:

- a versioned GitHub Action;
- PR comments with compact behavioral diffs;
- JSON, Markdown, HTML, JUnit, and GitHub summary outputs;
- configurable fail thresholds;
- history artifacts that survive across runs.

### 5. History: Behavioral Drift Over Time

History turns redline from a one-shot diff into a long-term prompt quality
record. Teams should be able to see whether regressions are increasing, which
clusters degrade, and whether fixes actually improved behavior.

World-class history means:

- trend summaries across prompt changes;
- cluster-level drift detection;
- report comparison over time;
- review and acceptance audit trail.

## Trust Model

Trust comes from four guarantees:

- **Evidence:** every regression flag includes deterministic reasons when
  possible.
- **Calibration:** `neutral` means no configured high-signal blocker was found;
  it does not mean the output is factually correct, safe, or semantically
  equivalent.
- **Stability:** suite, report, and runner contracts are documented and versioned.
- **Privacy:** prompts and outputs stay on disk unless the user explicitly opts
  into a future sync or cloud workflow.

## Format as the Moat

The suite JSON format, report schema, and runner contract are the artifacts that
can become a standard. redline should make it easy for other tools to export
redline-compatible suites and consume redline-compatible reports.

The long-term goal is not just a useful CLI. The goal is for teams to say
“we use redline” the way they say “we use pytest”: no explanation needed.

## Current v0.1 Alpha State

Already built:

- suite generation from JSONL logs;
- deterministic diff and eval;
- optional judges and judge rubrics;
- runner adapters;
- mark, accept, and pinned requirements;
- JSON, Markdown, HTML, JUnit, GitHub summary, and dashboard outputs;
- history and compare commands;
- GitHub workflow generation;
- public demo, release gates, and launch site.

Highest-leverage remaining work:

- Python watch decorator and middleware capture;
- provider/framework capture helpers;
- deeper behavioral clustering and coverage readiness;
- versioned GitHub Action with PR comments;
- public PyPI release and first external dogfood loop;
- documented suite/report/runner compatibility specs.
