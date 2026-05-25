# Runner Adapters

redline is model- and provider-agnostic. It only needs prompt text in and
candidate response text out; use the provider-specific runners only when they
save you setup time.

Replay contract: redline sends the rendered prompt to `stdin`; your runner
prints only the candidate response to `stdout`. Logs belong on `stderr`.

redline also sets `REDLINE_CASE_ID`, `REDLINE_SOURCE_LINE`, `REDLINE_CLUSTER`,
and `REDLINE_PROMPT_PATH` for each replay.

To set replay config and copy a built-in runner in one step:

```bash
redline init --runner stdio --copy-runner
```

To copy every built-in adapter for exploration:

```bash
redline runners --copy all
```

Replay runners are for `redline eval`. Log adapters, such as `jsonl-logs`, are
for converting exported app logs into redline JSONL before `redline suite`.

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
)
```

What it does: records each JSON request/response pair to
`.redline/logs/prompts.jsonl`. Nothing leaves disk.

Wire it in:

```bash
redline watch --stats
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
