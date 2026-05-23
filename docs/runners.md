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
