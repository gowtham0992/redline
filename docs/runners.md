# Runner Adapters

redline is model- and provider-agnostic. It only needs prompt text in and
candidate response text out; use the provider-specific runners only when they
save you setup time.

Replay contract: redline sends the rendered prompt to `stdin`; your runner
prints only the candidate response to `stdout`. Logs belong on `stderr`. Prefer
stdin for large prompts; `{prompt}` is supported for small legacy runners, and
`{prompt_file}` passes a temporary file path when a runner needs file input.

redline also sets `REDLINE_CASE_ID`, `REDLINE_SOURCE_LINE`, `REDLINE_CLUSTER`,
and `REDLINE_PROMPT_PATH` for each replay. When `{prompt_file}` is used, it also
sets `REDLINE_RENDERED_PROMPT_PATH`.

To set replay config and copy a built-in runner in one step:

```bash
redline init --runner stdio --copy-runner
```

To copy every built-in adapter for exploration:

```bash
redline runners --copy all
```

To copy one SDK capture starter:

```bash
redline runners --copy openai-sdk
```

Replay runners are for `redline eval`. Log adapters, such as `jsonl-logs`, are
for converting exported app logs into redline JSONL before `redline suite`.
SDK capture adapters, such as `openai-sdk` and `anthropic-sdk`, are for
recording real app calls into `.redline/logs/prompts.jsonl`.

## Custom Stdio Command

What you need: any command that reads prompt text from `stdin` and prints only
the model or app response to `stdout`.

Your replay command:

```bash
python runners/stdio_runner.py
```

What it does: passes redline's prompt input to `REDLINE_STDIO_COMMAND`, forwards
the command's `stdout` as the candidate response, and forwards logs from
`stderr`.

Wire it in:

```bash
export REDLINE_STDIO_COMMAND="python my_app/run_prompt.py"
redline eval --prompt prompts/v2.txt --replay "python runners/stdio_runner.py"
```

That's it.

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

## LangChain Or LlamaIndex

What you need: a Python function that loads your chain/index and accepts a
prompt string.

Your replay command:

```bash
python runners/python_chain_runner.py
```

What it does: imports `module:function` from `REDLINE_PYTHON_RUNNER`, passes the
rendered prompt string, prints the returned text to `stdout`.

Create a small wrapper in your app:

```python
# my_app/redline_runner.py
from my_app.chain import chain


def run(prompt: str) -> str:
    result = chain.invoke(prompt)
    return result.content if hasattr(result, "content") else str(result)
```

Wire it in:

```bash
export REDLINE_PYTHON_RUNNER="my_app.redline_runner:run"
redline eval --prompt prompts/v2.txt --replay "python runners/python_chain_runner.py"
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

## App Logs To JSONL

What you need: exported production logs as JSONL.

Your adapter command:

```bash
python runners/jsonl_log_adapter.py logs/export.jsonl \
  --preset langfuse \
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
# Langfuse enriched observations / trace or observation JSONL exports
--preset langfuse

# Helicone exports with request/response bodies included
--preset helicone

# LangSmith dataset, run, or trace exports with input/output objects
--preset langsmith

# Braintrust experiment or dataset rows with input/output fields
--preset braintrust

# Your app's own JSONL logs
--input-field request.prompt --output-field response.text

--input-field messages.user --output-field result.answer
```

Presets try several common field paths and record the matched paths in row
metadata. Preset fields can still be overridden with `--input-field` or
`--output-field` if your export shape differs.

That's it.

## OpenAI Or Anthropic SDK Patch

What you need: Python code that already calls an OpenAI-compatible or
Anthropic-compatible client.

Copy runnable starters:

```bash
redline runners --copy openai-sdk
redline runners --copy anthropic-sdk
```

Patch the client once during app startup:

```python
from openai import OpenAI
from anthropic import Anthropic
from redline import patch_anthropic, patch_openai

openai_client = OpenAI()
patch_openai(openai_client)

anthropic_client = Anthropic()
patch_anthropic(anthropic_client)
```

Calls like `client.chat.completions.create(...)` and
`client.responses.create(...)`, or `client.messages.create(...)` for Anthropic,
now append prompt-response observations to `.redline/logs/prompts.jsonl`.
redline infers prompts from `system`, `messages`, `input`, or `prompt`,
extracts common provider response text and token metadata, and redacts common
secrets and PII before write by default.

For `stream=True` calls, redline passes chunks through unchanged and records the
assembled text after your app consumes the stream. If a stream is never consumed,
no observation is written.

Wire it in:

```bash
redline watch --stats
redline suite .redline/logs/prompts.jsonl --out redline-suite.json
```

That's it.

## FastAPI Or ASGI Middleware

What you need: a Python ASGI app that receives JSON and returns JSON.

Add middleware:

```python
from redline import RedlineMiddleware

app.add_middleware(
    RedlineMiddleware,
    prompt_field="prompt",
    response_field="answer",
)
```

For nested chat-style payloads:

```python
app.add_middleware(
    RedlineMiddleware,
    prompt_field="messages.0.content",
    response_field="choices.0.message.content",
    skip_log=".redline/logs/middleware-skips.jsonl",
)
```

What it does: records each JSON request/response pair to
`.redline/logs/prompts.jsonl`, redacting common secrets and PII before write by
default. Nothing leaves disk. By default, the middleware only captures
JSON-compatible content types and skips request or response bodies larger than
1 MB; pass `max_body_bytes=` if your prompt payloads need a different cap. It
also skips streaming responses by default so long-lived streams or binary
downloads are never buffered; pass `capture_streaming_responses=True` only for
bounded JSON responses that are intentionally sent in chunks. To debug why a
request was not recorded, pass `skip_log=`. Skip rows include reason codes and
metadata such as route, status, content type, content length, and bytes seen;
they never include request or response body text.

Wire it in:

```bash
redline watch --stats
redline watch --stats --skip-log .redline/logs/middleware-skips.jsonl
redline suite .redline/logs/prompts.jsonl --out redline-suite.json
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
