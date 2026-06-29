# Import Guides

redline only needs prompt-response JSONL. Your production system probably calls
those fields something else. Start with detection, preview the mapping, then
write the normalized baseline.

```bash
redline import raw-export.jsonl --detect
redline import raw-export.jsonl --auto-map --preview 3
redline import raw-export.jsonl --auto-map --out logs/baseline.jsonl
redline import raw-export.jsonl --input-field request.prompt --output-field response.text --preview 3
redline import raw-export.jsonl --input-field request.prompt --output-field response.text --out logs/baseline.jsonl
```

Redaction is enabled by default during import. It is best-effort pattern
matching, not a privacy boundary; review normalized files before sharing or
committing them.

## Langfuse-Style Exports

Use the built-in preset when your export has `input` and `output` fields.

```bash
redline import langfuse-export.jsonl --preset langfuse --preview 3
redline import langfuse-export.jsonl --preset langfuse --out logs/baseline.jsonl
```

If your export nests generations under a trace object, detect first:

```bash
redline import langfuse-export.jsonl --detect
```

Then rerun import with the suggested field paths.

## Helicone-Style Exports

The preset expects `request.prompt` and `response.text`.

```bash
redline import helicone-export.jsonl --preset helicone --preview 3
redline import helicone-export.jsonl --preset helicone --out logs/baseline.jsonl
```

For chat payloads, the prompt may be an array of messages. That is acceptable;
redline stringifies structured prompts deterministically.

## OpenAI Chat Traces

The `openai-chat` preset maps chat messages to the prompt and the first choice
message to the response.

```bash
redline import openai-chat.jsonl --preset openai-chat --preview 3
redline import openai-chat.jsonl --preset openai-chat --out logs/baseline.jsonl
```

If your app stores `response.output_text`, override the response path:

```bash
redline import openai-chat.jsonl \
  --input-field request.messages \
  --output-field response.output_text \
  --preview 3
```

## Datadog Or App Logs

The `datadog` preset expects `attributes.input` and `attributes.output`.

```bash
redline import datadog.jsonl --preset datadog --preview 3
redline import datadog.jsonl --preset datadog --out logs/baseline.jsonl
```

For custom app logs, common mappings look like:

```bash
redline import app.jsonl --input-field ticket.text --output-field assistant.reply --preview 3
redline import app.jsonl --input-field prompt --output-field completion --preview 3
redline import app.jsonl --input-field payload.user_question --output-field result.assistant_answer --preview 3
```

## Database Exports

Export the rows you want as JSONL, one object per line:

```json
{"prompt":"Classify ticket INV-1042","response":"{\"owner\":\"billing\"}","created_at":"2026-06-14T10:00:00Z"}
```

Then import:

```bash
redline import db-export.jsonl \
  --input-field prompt \
  --output-field response \
  --metadata-field created_at \
  --preview 3

redline import db-export.jsonl \
  --input-field prompt \
  --output-field response \
  --metadata-field created_at \
  --out logs/baseline.jsonl
```

## After Import

```bash
redline suite logs/baseline.jsonl --out redline-suite.json
redline summary redline-suite.json
redline cases redline-suite.json
```

If the suite looks thin, add pinned cases:

```bash
redline suite add redline-suite.json --prompt "..." --response "..."
```
