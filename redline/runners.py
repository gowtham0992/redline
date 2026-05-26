from __future__ import annotations

import shlex
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
        "setup": "Set REDLINE_STDIO_COMMAND to the command that runs your app.",
        "kind": "replay",
    },
    {
        "name": "OpenAI direct",
        "id": "openai",
        "need": "OPENAI_API_KEY and a prompt file",
        "file": "runners/openai_runner.sh",
        "template": "openai_runner.sh",
        "replay": "./runners/openai_runner.sh",
        "setup": "Set OPENAI_API_KEY and optionally OPENAI_MODEL.",
        "kind": "replay",
    },
    {
        "name": "Anthropic direct",
        "id": "anthropic",
        "need": "ANTHROPIC_API_KEY and a prompt file",
        "file": "runners/anthropic_runner.sh",
        "template": "anthropic_runner.sh",
        "replay": "./runners/anthropic_runner.sh",
        "setup": "Set ANTHROPIC_API_KEY and optionally ANTHROPIC_MODEL.",
        "kind": "replay",
    },
    {
        "name": "LangChain or LlamaIndex",
        "id": "python-chain",
        "need": "REDLINE_PYTHON_RUNNER=module:function",
        "file": "runners/python_chain_runner.py",
        "template": "python_chain_runner.py",
        "replay": "python runners/python_chain_runner.py",
        "setup": "Set REDLINE_PYTHON_RUNNER to module:function.",
        "kind": "replay",
    },
    {
        "name": "HTTP API",
        "id": "http",
        "need": "REDLINE_HTTP_URL for your app endpoint",
        "file": "runners/http_runner.py",
        "template": "http_runner.py",
        "replay": "python runners/http_runner.py",
        "setup": "Set REDLINE_HTTP_URL and optionally REDLINE_HTTP_RESPONSE_FIELD.",
        "kind": "replay",
    },
    {
        "name": "App logs to JSONL",
        "id": "jsonl-logs",
        "need": "exported production logs as JSONL",
        "file": "runners/jsonl_log_adapter.py",
        "template": "jsonl_log_adapter.py",
        "replay": "python runners/jsonl_log_adapter.py logs/export.jsonl --preset langfuse --out .redline/logs/prompts.jsonl",
        "discover": "python runners/jsonl_log_adapter.py --list-presets",
        "setup": "Export app logs as JSONL, then use a preset or map prompt and response fields.",
        "kind": "log",
    },
    {
        "name": "OpenAI SDK capture",
        "id": "openai-sdk",
        "need": "an app that already calls an OpenAI-compatible Python client",
        "file": "runners/openai_watch_patch.py",
        "template": "openai_watch_patch.py",
        "replay": "python runners/openai_watch_patch.py",
        "setup": "Patch your OpenAI client with redline.patch_openai during app startup.",
        "kind": "capture",
    },
    {
        "name": "Anthropic SDK capture",
        "id": "anthropic-sdk",
        "need": "an app that already calls an Anthropic-compatible Python client",
        "file": "runners/anthropic_watch_patch.py",
        "template": "anthropic_watch_patch.py",
        "replay": "python runners/anthropic_watch_patch.py",
        "setup": "Patch your Anthropic client with redline.patch_anthropic during app startup.",
        "kind": "capture",
    },
    {
        "name": "LiteLLM or model proxy",
        "id": "litellm",
        "need": "LITELLM_BASE_URL, LITELLM_API_KEY, and LITELLM_MODEL",
        "file": "runners/litellm_runner.sh",
        "template": "litellm_runner.sh",
        "replay": "./runners/litellm_runner.sh",
        "setup": "Set LITELLM_BASE_URL, LITELLM_API_KEY, and LITELLM_MODEL.",
        "kind": "replay",
    },
]


def runner_adapters() -> list[dict[str, str]]:
    return [dict(adapter) for adapter in RUNNER_ADAPTERS]


def replay_runner_adapters() -> list[dict[str, str]]:
    return [dict(adapter) for adapter in RUNNER_ADAPTERS if adapter["kind"] == "replay"]


def format_runner_adapters(adapters: list[dict[str, Any]] | None = None) -> str:
    items = adapters if adapters is not None else RUNNER_ADAPTERS
    lines = [
        "redline runners",
        "",
        "Model- and provider-agnostic: any command that reads stdin and writes stdout can be a runner.",
        "",
    ]
    for adapter in items:
        discovery_command = adapter.get("discover")
        lines.extend(
            [
                str(adapter["name"]),
                f"  Need:   {adapter['need']}",
                f"  Setup:  {adapter['setup']}",
                f"  File:   {adapter['file']}",
                f"  {_command_label(adapter)}: {adapter['replay']}",
            ]
        )
        if discovery_command:
            lines.append(f"  Presets: {discovery_command}")
        lines.append("")
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

    command = _replay_for_target(adapter, target)
    return {
        "id": adapter["id"],
        "name": adapter["name"],
        "path": str(target),
        "replay": command,
        "setup": adapter["setup"],
        "kind": adapter["kind"],
        "next": _next_step_for_adapter(adapter, command),
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


def _command_label(adapter: dict[str, Any]) -> str:
    if adapter.get("kind") == "replay":
        return "Replay"
    if adapter.get("kind") == "capture":
        return "Capture"
    return "Command"


def _next_step_for_adapter(adapter: dict[str, str], command: str) -> str:
    if adapter.get("kind") == "log":
        return (
            "Run adapter command, then build a suite: "
            "redline suite .redline/logs/prompts.jsonl --out redline-suite.json"
        )
    if adapter.get("kind") == "capture":
        return (
            "Patch your app client, run real traffic, then build a suite: "
            "redline suite .redline/logs/prompts.jsonl --out redline-suite.json"
        )
    return f"Configure replay: redline init --replay {shlex.quote(command)} --force"
