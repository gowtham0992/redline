from __future__ import annotations

import shlex
from importlib import resources
from pathlib import Path
from typing import Any


JUDGE_TEMPLATES: list[dict[str, str]] = [
    {
        "name": "Local changed-case judge",
        "id": "local",
        "need": "no API key; useful as a copyable contract example",
        "file": "judges/judge_changed.py",
        "template": "judge_changed.py",
        "command": "python judges/judge_changed.py",
        "setup": "Customize the route/product rules for your domain.",
        "kind": "judge",
    },
    {
        "name": "OpenAI judge",
        "id": "openai",
        "need": "OPENAI_API_KEY and optional REDLINE_JUDGE_RUBRIC",
        "file": "judges/openai_judge.sh",
        "template": "openai_judge.sh",
        "command": "./judges/openai_judge.sh",
        "setup": "Set OPENAI_API_KEY and optionally OPENAI_JUDGE_MODEL.",
        "kind": "judge",
    },
    {
        "name": "Anthropic judge",
        "id": "anthropic",
        "need": "ANTHROPIC_API_KEY and optional REDLINE_JUDGE_RUBRIC",
        "file": "judges/anthropic_judge.sh",
        "template": "anthropic_judge.sh",
        "command": "./judges/anthropic_judge.sh",
        "setup": "Set ANTHROPIC_API_KEY and optionally ANTHROPIC_JUDGE_MODEL.",
        "kind": "judge",
    },
    {
        "name": "LiteLLM or proxy judge",
        "id": "litellm",
        "need": "LITELLM_BASE_URL, LITELLM_API_KEY, and LITELLM_JUDGE_MODEL",
        "file": "judges/litellm_judge.sh",
        "template": "litellm_judge.sh",
        "command": "./judges/litellm_judge.sh",
        "setup": "Set LITELLM_BASE_URL, LITELLM_API_KEY, and LITELLM_JUDGE_MODEL.",
        "kind": "judge",
    },
    {
        "name": "Support-agent rubric",
        "id": "support-rubric",
        "need": "support workflows with SLAs, owners, policies, and escalation paths",
        "file": "judges/support_rubric.md",
        "template": "support_rubric.md",
        "command": "",
        "setup": "Use through REDLINE_JUDGE_RUBRIC with a model-backed judge.",
        "kind": "rubric",
    },
    {
        "name": "Extraction rubric",
        "id": "extraction-rubric",
        "need": "structured extraction workflows with JSON, tables, lists, and code",
        "file": "judges/extraction_rubric.md",
        "template": "extraction_rubric.md",
        "command": "",
        "setup": "Use through REDLINE_JUDGE_RUBRIC with a model-backed judge.",
        "kind": "rubric",
    },
    {
        "name": "Safety rubric",
        "id": "safety-rubric",
        "need": "safety, compliance, caveat, and policy-boundary workflows",
        "file": "judges/safety_rubric.md",
        "template": "safety_rubric.md",
        "command": "",
        "setup": "Use through REDLINE_JUDGE_RUBRIC with a model-backed judge.",
        "kind": "rubric",
    },
]


def judge_templates() -> list[dict[str, str]]:
    return [dict(template) for template in JUDGE_TEMPLATES]


def format_judge_templates(templates: list[dict[str, Any]] | None = None) -> str:
    items = templates if templates is not None else JUDGE_TEMPLATES
    lines = [
        "redline judges",
        "",
        "Judges are optional: use them only for semantic risks structural checks cannot prove.",
        "",
    ]
    for template in items:
        lines.extend(
            [
                str(template["name"]),
                f"  Need:   {template['need']}",
                f"  Setup:  {template['setup']}",
                f"  File:   {template['file']}",
            ]
        )
        if template.get("kind") == "rubric":
            lines.append(f"  Rubric: REDLINE_JUDGE_RUBRIC={template['file']}")
        else:
            lines.append(f"  Judge:  {template['command']}")
        lines.append("")
    lines.append("Docs: docs/judges.md")
    return "\n".join(lines).rstrip() + "\n"


def copy_judge_template(
    template_id: str,
    *,
    output: str | None = None,
    force: bool = False,
) -> dict[str, str]:
    template = _judge_template(template_id)
    target = Path(output or template["file"])
    if target.exists() and not force:
        raise ValueError(f"{target} already exists; pass --force to overwrite")

    resource = resources.files("redline.judge_template_files").joinpath(template["template"])
    text = resource.read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if target.suffix in {".sh", ".py"}:
        current_mode = target.stat().st_mode
        target.chmod(current_mode | 0o755)

    command = _judge_command_for_target(template, target)
    result = {
        "id": template["id"],
        "name": template["name"],
        "path": str(target),
        "command": command,
        "setup": template["setup"],
        "kind": template["kind"],
        "next": _next_step_for_template(template, target, command),
    }
    return result


def copy_all_judge_templates(*, force: bool = False) -> list[dict[str, str]]:
    existing = [
        Path(template["file"])
        for template in JUDGE_TEMPLATES
        if Path(template["file"]).exists()
    ]
    if existing and not force:
        first = existing[0]
        raise ValueError(f"{first} already exists; pass --force to overwrite")
    return [
        copy_judge_template(template["id"], force=force)
        for template in JUDGE_TEMPLATES
    ]


def _judge_template(template_id: str) -> dict[str, str]:
    for template in JUDGE_TEMPLATES:
        if template["id"] == template_id:
            return template
    raise ValueError(f"unknown judge template: {template_id}")


def _judge_command_for_target(template: dict[str, str], target: Path) -> str:
    if template.get("kind") == "rubric":
        return ""
    command = template["command"]
    if str(target) == template["file"]:
        return command
    if target.suffix == ".py":
        return f"python {target}"
    if target.is_absolute():
        return str(target)
    return f"./{target}"


def _next_step_for_template(template: dict[str, str], target: Path, command: str) -> str:
    if template.get("kind") == "rubric":
        return (
            "Use with a model judge: "
            f"REDLINE_JUDGE_RUBRIC={shlex.quote(str(target))} "
            "redline diff redline-suite.json candidate.jsonl --judge ./judges/openai_judge.sh"
        )
    return f"Configure judge: redline init --judge {shlex.quote(command)} --force"
