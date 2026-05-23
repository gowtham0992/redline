# redline Roadmap

## Iteration 0: Deterministic Local Diff

Status: started.

- Generate a representative suite from existing JSONL prompt-response logs.
- Compare candidate JSONL outputs against the saved baseline suite.
- Detect high-signal behavioral regressions without calling an LLM judge.
- Return a non-zero exit code when regressions or missing candidate outputs are found.

## Iteration 1: Replay

- Add `redline eval --replay "<command>"` so redline can run candidate outputs itself.
- Support prompt templates, raw rendered prompts, and structured input variables.
- Persist run artifacts under `.redline/runs/`.

## Iteration 2: Human Judgment Capture

- Let engineers mark a diff as `expected`, `regression`, or `ignore`.
- Save those judgments into the suite so future runs become sharper.
- Add suite versioning and case provenance.

## Iteration 3: LLM Judge For Ambiguous Cases

- Keep deterministic checks first.
- Call an LLM judge only when structural checks are inconclusive.
- Require judge prompts to emit reasons, confidence, and machine-readable labels.

## Iteration 4: CI Integration

- Add JSON and Markdown report outputs.
- Add GitHub Actions examples.
- Fail PRs only on configured severity thresholds.

## Iteration 5: Team Workflow

- Add suite review, sharing, and collaboration workflows.
- Keep the core CLI local-first and open.
