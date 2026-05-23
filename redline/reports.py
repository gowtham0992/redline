from __future__ import annotations

from typing import Any


def format_markdown_report(result: dict[str, Any], *, title: str = "redline diff") -> str:
    summary = result["summary"]
    lines = [
        f"# {title}",
        "",
        "| Status | Count |",
        "| --- | ---: |",
        f"| Regression | {summary['regression']} |",
        f"| Changed | {summary['changed']} |",
        f"| Improved | {summary['improved']} |",
        f"| Neutral | {summary['neutral']} |",
        f"| Missing | {summary['missing']} |",
        "",
    ]

    for status in ("regression", "changed", "improved", "missing", "neutral"):
        matching = [item for item in result["diffs"] if item["status"] == status]
        if not matching:
            continue
        lines.append(f"## {status.title()}")
        lines.append("")
        for item in matching:
            lines.append(f"### `{item['case_id']}`")
            lines.append("")
            lines.append(f"Prompt: {_inline_code(item['prompt'])}")
            lines.append("")
            for reason in item["reasons"]:
                lines.append(f"- {reason}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _inline_code(value: str) -> str:
    compact = " ".join(value.split())
    return f"`{compact.replace('`', '')}`"
