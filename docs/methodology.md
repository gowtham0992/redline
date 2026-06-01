# Methodology

redline is a deterministic regression detector for prompt-response systems. It
does not claim that a green run proves semantic safety. It turns logs into a
reviewable suite, checks high-signal behavioral changes, and leaves factual,
tone, policy, hallucination, and subtle reasoning judgment to explicit
requirements, optional judges, or humans.

## Input Model

redline expects prompt-response observations as JSONL. The canonical fields are
`prompt` and `response`, but `redline import` can normalize nested exports from
application logs, observability tools, or model gateways.

Import is redaction-first by default. The importer redacts common secrets and
PII before extracting fields so copied metadata is treated with the same local
privacy boundary as prompt and response text. Use `--no-redact` only for local
fixtures you have already inspected.

## Behavior Grouping

redline does not run statistical, embedding, or semantic clustering by default.
It groups observations by deterministic behavior signatures:

- prompt intent, such as classify, summarize, transform, generate, or answer
- response shape, such as JSON, table, code block, bullet list, numbered list,
  refusal, empty output, or prose
- response length bucket
- JSON schema shape when the response is valid JSON

The CLI command is named `redline cluster` for compatibility, but the public
model is behavior-signature grouping. These groups are explainable and stable;
they are not a claim that two prompts are semantically equivalent.

## Case Selection

Suite generation chooses cases in this order:

1. One representative from each behavior group.
2. High-risk groups with obvious failure patterns, such as invalid JSON,
   malformed tables, empty outputs, or refusals.
3. High-variance edges where same-shape outputs vary substantially in length.
4. Prompt-diverse samples from large groups when the case budget allows.
5. User-pinned cases from `redline suite add`.

This strategy optimizes for useful regression coverage from existing logs, not
perfect coverage of every product risk. If a scenario matters, pin it.

## Regression Signals

The deterministic diff engine checks for high-signal changes:

- lost JSON validity or missing JSON keys
- lost table, list, or code-block structure
- missing numbers, URLs, ticket IDs, and likely entities
- empty outputs
- newly refused safe-looking tasks
- allow/deny polarity flips
- large same-shape content drift
- explicit include/exclude requirements

These checks are intentionally conservative. They catch common prompt
regressions quickly in CI, but they do not replace domain review.

## Suite Readiness Score

`redline summary` reports a suite readiness score from 0 to 100. The score is a
suite-health signal, not a model-quality score. It combines:

- behavior-group coverage
- unique prompt-response pair coverage
- explicit requirements or recorded judgments
- owner coverage
- high-risk group calibration
- non-English calibration warnings

Use the score to decide what to improve before CI gating. A high score means the
suite is better prepared for review and automation. It does not mean the
candidate prompt is safe to ship.

## Judges

Optional judges are for ambiguous `changed` cases and semantic risks that
deterministic checks cannot prove. A judge can be a local script, a local model,
or a cloud LLM command you control. redline routes only the configured review
surface and records judge output as evidence.

Default redline behavior is local and deterministic. No cloud judge is called
unless you configure one.

## Calibration

Use redline as a safety loop:

1. Import or watch real logs.
2. Generate a suite.
3. Inspect `redline summary` and `redline cases`.
4. Pin must-cover edge cases.
5. Add requirements for details that must not disappear.
6. Run `redline eval` or `redline diff` before prompt changes ship.
7. Mark expected changes and accept new baselines after review.

The strongest evidence for redline is not a score. It is a concrete report that
says which production behavior changed and why it matters.

For a tiny runnable boundary check, see [docs/calibration.md](calibration.md).
