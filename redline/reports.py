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
    decision = result.get("decision")
    if isinstance(decision, dict):
        confidence = str(decision.get("confidence") or "").upper()
        action = str(decision.get("recommended_action") or "")
        if confidence and action:
            lines.append(f"**Confidence:** {confidence}")
            lines.append("")
            lines.append(f"**Recommended action:** {action}")
            lines.append("")
            scope = str(decision.get("scope") or "")
            if scope:
                lines.append(f"**Scope:** {scope}")
                lines.append("")

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
            metadata = _metadata_lines(item)
            if metadata:
                lines.extend(metadata)
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
        properties = _junit_properties(item)
        if properties:
            element = ElementTree.SubElement(testcase, "properties")
            for name, value in properties.items():
                ElementTree.SubElement(element, "property", {"name": name, "value": value})

        if status in {"regression", "missing"}:
            failure = ElementTree.SubElement(testcase, "failure", {"message": status})
            failure.text = "\n".join(str(reason) for reason in item.get("reasons", []))
        elif status in {"accepted", "ignored"}:
            skipped = ElementTree.SubElement(testcase, "skipped", {"message": status})
            skipped.text = "\n".join(str(reason) for reason in item.get("reasons", []))

    return ElementTree.tostring(testsuite, encoding="unicode") + "\n"


def format_github_annotations(result: dict[str, Any], *, title: str = "redline diff") -> str:
    lines = []
    for item in result.get("diffs", []):
        if not isinstance(item, dict):
            continue
        level = _annotation_level(str(item.get("status", "")))
        if level is None:
            continue
        props = _annotation_properties(item, title=title)
        prop_text = ",".join(
            f"{key}={_escape_annotation_property(value)}"
            for key, value in props.items()
        )
        lines.append(
            f"::{level} {prop_text}::{_escape_annotation_message(_annotation_message(item))}"
        )
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def _inline_code(value: str) -> str:
    compact = " ".join(value.split())
    fence = "`"
    while fence in compact:
        fence += "`"
    return f"{fence}{compact}{fence}"


def _code_block(value: str, limit: int = 1200) -> str:
    text = value if len(value) <= limit else value[: limit - 1] + "..."
    fence = "````" if "```" in text else "```"
    return f"{fence}\n{text}\n{fence}"


def _metadata_lines(item: dict[str, Any]) -> list[str]:
    lines = []
    location = _source_location(item)
    if location:
        lines.append(f"Source: {_inline_code(location)}")
    cluster = str(item.get("cluster") or "")
    if cluster:
        lines.append(f"Cluster: {_inline_code(cluster)}")
    return lines


def _junit_properties(item: dict[str, Any]) -> dict[str, str]:
    properties = {}
    location = _source_location(item)
    if location:
        properties["source"] = location
    cluster = str(item.get("cluster") or "")
    if cluster:
        properties["cluster"] = cluster
    return properties


def _source_location(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "")
    source_line = item.get("source_line")
    if source and source_line is not None:
        return f"{source}:{source_line}"
    if source_line is not None:
        return f"line {source_line}"
    if source:
        return source
    return ""


def _annotation_level(status: str) -> str | None:
    if status in {"regression", "missing"}:
        return "error"
    if status == "changed":
        return "warning"
    return None


def _annotation_properties(item: dict[str, Any], *, title: str) -> dict[str, str]:
    case_id = str(item.get("case_id") or "unknown")
    status = str(item.get("status") or "unknown")
    props = {"title": f"{title}: {status} {case_id}"}
    source = str(item.get("source") or "")
    if source:
        props["file"] = source
    source_line = item.get("source_line")
    if isinstance(source_line, int) and source_line >= 1:
        props["line"] = str(source_line)
    return props


def _annotation_message(item: dict[str, Any]) -> str:
    case_id = str(item.get("case_id") or "unknown")
    prompt = _preview(str(item.get("prompt") or ""))
    reasons = item.get("reasons")
    reason = str(reasons[0]) if isinstance(reasons, list) and reasons else str(item.get("status") or "changed")
    return f"{case_id}: {reason}\nPrompt: {prompt}"


def _escape_annotation_property(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def _escape_annotation_message(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."
