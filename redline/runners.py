from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any


RUNNER_ADAPTERS: list[dict[str, str]] = [
    {
        "name": "Custom stdio command",
        "id": "stdio",
        "need": "any command that reads stdin and prints stdout",
        "file": "runners/stdio_runner.py",
        "template": "stdio_runner.py",
        "replay": "python runners/stdio_runner.py",
    },
    {
        "name": "OpenAI direct",
        "id": "openai",
        "need": "OPENAI_API_KEY and a prompt file",
        "file": "runners/openai_runner.sh",
        "template": "openai_runner.sh",
        "replay": "./runners/openai_runner.sh",
    },
    {
        "name": "Anthropic direct",
        "id": "anthropic",
        "need": "ANTHROPIC_API_KEY and a prompt file",
        "file": "runners/anthropic_runner.sh",
        "template": "anthropic_runner.sh",
        "replay": "./runners/anthropic_runner.sh",
    },
    {
        "name": "LangChain or LlamaIndex",
        "id": "python-chain",
        "need": "REDLINE_PYTHON_RUNNER=module:function",
        "file": "runners/python_chain_runner.py",
        "template": "python_chain_runner.py",
        "replay": "python runners/python_chain_runner.py",
    },
    {
        "name": "HTTP API",
        "id": "http",
        "need": "REDLINE_HTTP_URL for your app endpoint",
        "file": "runners/http_runner.py",
        "template": "http_runner.py",
        "replay": "python runners/http_runner.py",
    },
    {
        "name": "App logs to JSONL",
        "id": "jsonl-logs",
        "need": "exported production logs as JSONL",
        "file": "runners/jsonl_log_adapter.py",
        "template": "jsonl_log_adapter.py",
        "replay": "python runners/jsonl_log_adapter.py logs/export.jsonl --input-field request.prompt --output-field response.text --out .redline/logs/prompts.jsonl",
    },
    {
        "name": "LiteLLM or model proxy",
        "id": "litellm",
        "need": "LITELLM_BASE_URL, LITELLM_API_KEY, and LITELLM_MODEL",
        "file": "runners/litellm_runner.sh",
        "template": "litellm_runner.sh",
        "replay": "./runners/litellm_runner.sh",
    },
]


def runner_adapters() -> list[dict[str, str]]:
    return [dict(adapter) for adapter in RUNNER_ADAPTERS]


def format_runner_adapters(adapters: list[dict[str, Any]] | None = None) -> str:
    items = adapters if adapters is not None else RUNNER_ADAPTERS
    lines = ["redline runners", ""]
    for adapter in items:
        lines.extend(
            [
                str(adapter["name"]),
                f"  Need:   {adapter['need']}",
                f"  File:   {adapter['file']}",
                f"  Replay: {adapter['replay']}",
                "",
            ]
        )
    lines.append("Docs: docs/runners.md")
    return "\n".join(lines).rstrip() + "\n"


def copy_runner_adapter(
    runner_id: str,
    *,
    output: str | None = None,
    force: bool = False,
) -> dict[str, str]:
    adapter = _runner_adapter(runner_id)
    target = Path(output or adapter["file"])
    if target.exists() and not force:
        raise ValueError(f"{target} already exists; pass --force to overwrite")

    template = resources.files("redline.runner_templates").joinpath(adapter["template"])
    text = template.read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if target.suffix in {".sh", ".py"}:
        current_mode = target.stat().st_mode
        target.chmod(current_mode | 0o755)

    return {
        "id": adapter["id"],
        "name": adapter["name"],
        "path": str(target),
        "replay": _replay_for_target(adapter, target),
    }


def copy_all_runner_adapters(*, force: bool = False) -> list[dict[str, str]]:
    existing = [
        Path(adapter["file"])
        for adapter in RUNNER_ADAPTERS
        if Path(adapter["file"]).exists()
    ]
    if existing and not force:
        first = existing[0]
        raise ValueError(f"{first} already exists; pass --force to overwrite")
    return [
        copy_runner_adapter(adapter["id"], force=force)
        for adapter in RUNNER_ADAPTERS
    ]


def _runner_adapter(runner_id: str) -> dict[str, str]:
    for adapter in RUNNER_ADAPTERS:
        if adapter["id"] == runner_id:
            return adapter
    raise ValueError(f"unknown runner adapter: {runner_id}")


def _replay_for_target(adapter: dict[str, str], target: Path) -> str:
    replay = adapter["replay"]
    if str(target) == adapter["file"]:
        return replay
    if target.suffix == ".py":
        return f"python {target}"
    if target.is_absolute():
        return str(target)
    return f"./{target}"
