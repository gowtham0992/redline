# Calibration Examples

Use this fixture when you want to see redline's trust boundary in a tiny,
inspectable dataset. It is not a benchmark. It is a calibration exercise that
shows what deterministic checks catch, what they mark for review, and what a
green case means.

```bash
redline suite examples/calibration_baseline.jsonl \
  --out /tmp/redline-calibration-suite.json \
  --all-cases

redline diff /tmp/redline-calibration-suite.json \
  examples/calibration_candidate.jsonl \
  --fail-on none
```

Expected result:

- Two regressions: lost JSON structure, and dropped refund details.
- One changed case: the reply added apologetic tone.
- One neutral case: the response is unchanged.

The neutral case is deliberately boring. It means redline found no configured
behavioral change in that case. It does not prove factual correctness,
hallucination safety, policy compliance, or subtle reasoning quality.

## Why This Matters

The fixture demonstrates the intended operating model:

- structural losses should block a prompt release;
- tone or wording shifts should be reviewed before acceptance;
- unchanged or neutral cases still inherit the global trust boundary;
- must-cover product requirements should be pinned with `redline suite add` or
  `redline require`.

For semantic risks, add requirements or configure an optional judge. Keep the
default deterministic checks as the fast local gate, and use judges where the
product risk is not visible from structure or concrete detail loss.
