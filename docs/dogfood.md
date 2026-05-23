# Dogfood Protocol

Use this before a public alpha push. The goal is to find the first five-minute
failure a stranger would hit.

## Rules

- Start from a fresh temp directory, not this repo checkout.
- Use only the README and copied terminal output as guidance.
- Do not inspect source code while running the pass.
- Time the run. Stop at the first confusing moment and write it down.
- Treat unclear output as a product bug, even if the command technically works.

## Pass 1: First-Run Demo

```bash
python -m pip install "git+https://github.com/gowtham0992/redline.git@develop"
redline demo
redline cases .redline/demo/suite.json
redline runners
redline doctor
```

Expected result: the demo catches realistic support-agent regressions, the next
steps are obvious, and the first warning explains exactly what to run next.

## Pass 2: Real Replay Setup

```bash
redline init --runner openai --copy-runner --github-action
redline doctor
```

Expected result: redline writes config, copies a runnable adapter, and explains
that the missing suite is solved by `redline suite path/to/log.jsonl`.

## Pass 3: Core Loop

```bash
redline suite .redline/demo/baseline.jsonl --out redline-suite.json
redline diff redline-suite.json .redline/demo/candidate.jsonl --compact --fail-on none
redline eval redline-suite.json --replay "python path/to/replay.py" --fail-on none
```

If replay is not available, mark the exact point where the workflow stops and
what command or example would have unblocked it.

## Friction Log

Record every issue in this format:

```text
time:
command:
expected:
actual:
fix:
severity: blocker | confusing | polish
```

Fix blockers before tagging. Fix confusing issues before posting publicly unless
there is a clear workaround in the README.
