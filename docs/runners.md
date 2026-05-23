# Runner Adapters

redline replay commands read the rendered prompt from `stdin` and print only the
candidate response to `stdout`. Logs and debugging output belong on `stderr`.

## OpenAI Direct

What you need: an OpenAI API key and a prompt file.

Your replay command:

```bash
./runners/openai_runner.sh
```

What it does: reads input from `stdin`, calls the OpenAI Responses API, prints
the response text to `stdout`.

Wire it in:

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-4o-mini"
redline eval --prompt prompts/v2.txt --replay "./runners/openai_runner.sh"
```

That's it.

## LiteLLM Or Model Proxy

What you need: a LiteLLM-compatible `/v1/chat/completions` endpoint.

Your replay command:

```bash
./runners/litellm_runner.sh
```

What it does: reads input from `stdin`, calls your OpenAI-compatible proxy,
prints the first chat completion message to `stdout`.

Wire it in:

```bash
export LITELLM_BASE_URL="http://localhost:4000"
export LITELLM_API_KEY="..."
export LITELLM_MODEL="gpt-4o-mini"
redline eval --prompt prompts/v2.txt --replay "./runners/litellm_runner.sh"
```

That's it.

## App Logs To JSONL

What you need: exported production logs as JSONL.

Your adapter command:

```bash
python runners/jsonl_log_adapter.py logs/export.jsonl \
  --input-field request.prompt \
  --output-field response.text \
  --out .redline/logs/prompts.jsonl
```

What it does: reads your exported log rows, copies the configured prompt and
response fields into redline's JSONL shape, writes `prompt` and `response`.

Wire it in:

```bash
redline suite .redline/logs/prompts.jsonl
```

Common field mappings:

```bash
# Langfuse-style exports
--input-field input --output-field output

# Helicone-style request/response rows
--input-field request.prompt --output-field response.text

# Your app's own JSONL logs
--input-field messages.user --output-field result.answer
```

That's it.

## HTTP API

What you need: a POST endpoint that accepts a prompt and returns JSON.

Your replay command:

```bash
python runners/http_runner.py
```

What it does: reads input from `stdin`, POSTs `{"prompt": "..."}` to your app,
prints the configured response field to `stdout`.

Wire it in:

```bash
export REDLINE_HTTP_URL="https://your-app.example.com/eval"
export REDLINE_HTTP_RESPONSE_FIELD="response"
redline eval --prompt prompts/v2.txt --replay "python runners/http_runner.py"
```

For bearer auth:

```bash
export REDLINE_HTTP_BEARER_TOKEN="..."
```

That's it.

## Anthropic Direct

What you need: an Anthropic API key and a prompt file.

Your replay command:

```bash
./runners/anthropic_runner.sh
```

What it does: reads input from `stdin`, calls the Anthropic Messages API, prints
the response text to `stdout`.

Wire it in:

```bash
export ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL="claude-3-5-sonnet-latest"
redline eval --prompt prompts/v2.txt --replay "./runners/anthropic_runner.sh"
```

That's it.
