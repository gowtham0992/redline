## What changed

-

## User-facing behavior

-

## Dogfood evidence

Command:

```bash

```

Result:

-

Friction noticed:

-

## Trust boundary

- [ ] This PR does not make neutral or green results sound stronger than redline's configured checks.
- [ ] Structural checks, requirements, and optional judge behavior are described accurately where relevant.
- [ ] Private prompts, outputs, customer data, API keys, and product vision drafts are not included.

## Validation

- [ ] `python -m pytest -q`
- [ ] `python -m ruff check .`
- [ ] `python -m mypy redline tests scripts examples`
- [ ] `git diff --check`
- [ ] `bash scripts/action_smoke.sh /tmp/redline-action-smoke` if product surface, reports, packaging, or action behavior changed
- [ ] `bash scripts/build_release.sh /tmp/redline-dist` if packaging or release behavior changed
