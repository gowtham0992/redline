# Public Alpha Launch Playbook

Use this after `docs/release.md` passes. The goal is a small, credible launch:
one demo GIF, one install command, one clear product promise, and a tight
feedback loop.

## Launch Positioning

One sentence:

> redline turns prompt-response logs you already have into a local eval suite
> that catches prompt regressions before you ship.

What to show:

- A prompt change makes answers shorter.
- redline catches lost JSON keys, URLs, numbers, refusals, tables, lists, or
  other high-signal behavior changes.
- The user can mark intentional changes and accept reviewed outputs into the
  baseline.
- No cloud account or judge is required for the default path.

What not to claim:

- Do not claim full semantic correctness.
- Do not claim hallucination detection without a configured judge or explicit
  requirements.
- Do not describe neutral as safe to ship without review.

## Asset Checklist

Generate launch artifacts from a clean `develop` checkout:

```bash
bash scripts/release_check.sh
bash scripts/demo_gif.sh .redline/launch .redline/launch/redline-demo.gif
bash scripts/build_release.sh /tmp/redline-dist-v0.1.0
```

Required artifacts:

- `.redline/launch/redline-demo.gif` or `.redline/launch/redline-demo-transcript.txt`
- `.redline/dashboard.html` from the demo path
- `/tmp/redline-dist-v0.1.0/redline_ai-0.1.0-py3-none-any.whl`
- `/tmp/redline-dist-v0.1.0/redline_ai-0.1.0.tar.gz`

## Publish Sequence

1. Confirm `develop` is clean and pushed.
2. Tag the exact commit:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. Upload the release distribution:

   ```bash
   python -m twine upload /tmp/redline-dist-v0.1.0/*
   ```

4. Create the GitHub release from `v0.1.0`.
5. Attach the demo GIF or link it from the README once the asset location is
   stable.

## Launch Post

Short post:

```text
I built redline, a local-first tool that turns prompt-response logs into eval
suites automatically.

You point it at existing JSONL logs, it clusters behavior, picks representative
cases, and catches regressions when a prompt change drops structure, numbers,
URLs, entities, refusals, tables, code blocks, or required fields.

No cloud account required. Optional judges are supported only for ambiguous
changed cases.

Install:
python -m pip install redline-ai

First run:
redline demo

Repo: https://github.com/gowtham0992/redline
```

Longer post:

```text
Most eval tools start with "write test cases." redline starts from the logs you
already have.

It watches or imports prompt-response JSONL, clusters observed behavior, builds
a representative suite, and compares new prompt runs against the accepted
baseline. The default checks are deterministic and local: JSON validity, missing
keys, empty outputs, refusals, URLs, numbers, entities, code blocks, tables,
lists, output shape, and obvious allow/deny polarity flips.

The point is not to replace semantic review. The point is to catch the boring,
expensive regressions that slip through prompt iteration and CI.

Try:
python -m pip install redline-ai
redline demo
redline init --runner stdio --copy-runner
```

## First 10 Feedback Loops

Track every early user report as one of:

- `blocked`: they could not install, run `redline demo`, or load their logs.
- `confused`: they understood the value but did not know the next command.
- `false-positive`: redline flagged a case that felt noisy or unactionable.
- `false-negative`: redline missed a regression they expected it to catch.
- `adapter-gap`: their app did not fit an existing runner/log adapter.
- `docs-gap`: the command existed but the documentation did not make it obvious.

For the first ten users, fix in this order:

1. Anything blocking `redline demo`.
2. Any private-log import issue.
3. Any runner setup issue affecting OpenAI, Anthropic, LiteLLM, HTTP, LangChain,
   or app logs.
4. Any trust-calibration issue that makes users over-trust neutral results.
5. Any false positive that appears in more than one user workflow.

Do not add a desktop app during this phase. Improve the CLI, generated reports,
dashboard, runner adapters, and docs until the first-use loop is obviously
valuable.
