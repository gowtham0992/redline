# Real Log Dogfood

Use this protocol when testing redline on real prompt/output logs from a team,
agent, support workflow, extraction job, or public dataset. The goal is to learn
whether redline catches useful regressions without leaking private data.

## Rule Zero

Do not send raw customer logs, secrets, API keys, or private prompts to another
person. Keep the raw export local. Share only sanitized reports or short
hand-redacted examples.

## 1. Inspect the Export

Open a few rows before importing:

```bash
python -m json.tool < first-row.json
```

Find the field that contains the user prompt or instruction, and the field that
contains the model or agent response. Common examples:

| Source shape | Input field | Output field |
| --- | --- | --- |
| redline JSONL | `prompt` | `response` |
| Dolly-style public data | `instruction` | `response` |
| OpenAI wrapper log | `request.messages` | `response.output_text` |
| Langfuse/Helicone-style export | `input` | `output` |
| Support traces | `ticket.text` | `assistant.reply` |

## 2. Import With Redaction On

`redline import` redacts common secrets and PII by default before writing the
normalized baseline file.

```bash
redline import raw-export.jsonl \
  --input-field instruction \
  --output-field response \
  --metadata-field category \
  --out .redline/dogfood/baseline.jsonl
```

The command prints how many values were redacted. If the count is non-zero,
inspect the normalized output before generating a suite.

Use `--no-redact` only for local-only test fixtures that have already been
reviewed.

## 3. Generate a Suite

```bash
redline suite .redline/dogfood/baseline.jsonl \
  --out .redline/dogfood/suite.json
```

Then inspect the selected cases:

```bash
redline cases .redline/dogfood/suite.json
redline summary .redline/dogfood/suite.json
```

## 4. Compare a Candidate

If you already have candidate outputs:

```bash
redline diff .redline/dogfood/suite.json .redline/dogfood/candidate.jsonl \
  --compact \
  --out-json .redline/dogfood/diff.json \
  --out-html .redline/dogfood/diff.html \
  --fail-on none
```

If you have a runner configured:

```bash
redline eval .redline/dogfood/suite.json \
  --prompt prompts/v2.txt \
  --compact \
  --fail-on none
```

## 5. Report Back

For early dogfood, collect this information:

- Source type: public dataset, app logs, trace export, SDK capture, or manual JSONL.
- Rows imported and redaction count.
- Suite cases generated and behavior groups covered.
- Blocking regressions found, if any.
- False positives that felt noisy.
- First command or error message that caused confusion.
- Whether the result would have changed a shipping decision.

Do not share raw logs. Share the redline report only after reviewing it for
private content.

## What Good Looks Like

A useful dogfood run does not need to prove semantic correctness. It should show
whether redline caught concrete structural drift:

- JSON keys disappeared.
- A table became prose.
- A safe task became a refusal.
- Required numbers, URLs, owners, or action items were dropped.
- A pinned requirement failed.

Those are the regressions redline is designed to catch quickly and locally.
