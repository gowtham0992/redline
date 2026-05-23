from __future__ import annotations

from typing import Any
from xml.etree import ElementTree


def format_markdown_report(result: dict[str, Any], *, title: str = "redline diff") -> str:
    summary = result["summary"]
    lines = [
        f"# {title}",
        "",
        "| Status | Count |",
        "| --- | ---: |",
        f"| Regression | {summary.get('regression', 0)} |",
        f"| Changed | {summary.get('changed', 0)} |",
        f"| Improved | {summary.get('improved', 0)} |",
        f"| Accepted | {summary.get('accepted', 0)} |",
        f"| Ignored | {summary.get('ignored', 0)} |",
        f"| Neutral | {summary.get('neutral', 0)} |",
        f"| Missing | {summary.get('missing', 0)} |",
        "",
    ]

    for status in ("regression", "changed", "improved", "accepted", "ignored", "missing", "neutral"):
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
            lines.append("Baseline:")
            lines.append("")
            lines.append(_code_block(str(item.get("baseline_response", ""))))
            lines.append("")
            if item.get("candidate_response") is not None:
                lines.append("Candidate:")
                lines.append("")
                lines.append(_code_block(str(item.get("candidate_response", ""))))
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_junit_report(result: dict[str, Any], *, suite_name: str = "redline") -> str:
    diffs = result.get("diffs", [])
    if not isinstance(diffs, list):
        diffs = []

    failures = [
        item
        for item in diffs
        if isinstance(item, dict) and item.get("status") in {"regression", "missing"}
    ]
    testsuite = ElementTree.Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(diffs)),
            "failures": str(len(failures)),
            "errors": "0",
        },
    )

    for item in diffs:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "unknown"))
        status = str(item.get("status", "unknown"))
        testcase = ElementTree.SubElement(
            testsuite,
            "testcase",
            {
                "classname": suite_name,
                "name": case_id,
            },
        )
        if status in {"regression", "missing"}:
            failure = ElementTree.SubElement(testcase, "failure", {"message": status})
            failure.text = "\n".join(str(reason) for reason in item.get("reasons", []))
        elif status in {"accepted", "ignored"}:
            skipped = ElementTree.SubElement(testcase, "skipped", {"message": status})
            skipped.text = "\n".join(str(reason) for reason in item.get("reasons", []))

    return ElementTree.tostring(testsuite, encoding="unicode") + "\n"


def _inline_code(value: str) -> str:
    compact = " ".join(value.split())
    return f"`{compact.replace('`', '')}`"


def _code_block(value: str, limit: int = 1200) -> str:
    text = value if len(value) <= limit else value[: limit - 1] + "..."
    fence = "````" if "```" in text else "```"
    return f"{fence}\n{text}\n{fence}"
