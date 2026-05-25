from __future__ import annotations

from html import escape
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

    warnings = _result_warnings(result)
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    owner_rows = _owner_review_rows(result.get("diffs"))
    if owner_rows:
        lines.append("## Owner Review")
        lines.append("")
        lines.append("| Owner | Blocking | Changed | Accepted | Ignored | Other | Total |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in owner_rows:
            lines.append(
                f"| {_markdown_cell(str(row['owner']))} | {row['blocking']} | {row['changed']} | "
                f"{row['accepted']} | {row['ignored']} | {row['other']} | {row['total']} |"
            )
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


def format_html_report(result: dict[str, Any], *, title: str = "redline diff") -> str:
    summary = result.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    decision = result.get("decision")
    if not isinstance(decision, dict):
        decision = {}
    diffs = result.get("diffs", [])
    if not isinstance(diffs, list):
        diffs = []

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_h(title)}</title>",
            "<style>",
            _HTML_CSS,
            "</style>",
            "</head>",
            "<body>",
            '<main class="page">',
            "<header>",
            f"<h1>{_h(title)}</h1>",
            '<p class="lede">Prompt regression report with deterministic structural checks.</p>',
            "</header>",
            _html_summary(summary),
            _html_decision(decision),
            _html_warnings(result),
            _html_owner_review(diffs),
            _html_cases(diffs),
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


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
    fence = _code_fence(text)
    return f"{fence}\n{text}\n{fence}"


def _code_fence(text: str) -> str:
    longest = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(3, longest + 1)


def _metadata_lines(item: dict[str, Any]) -> list[str]:
    lines = []
    location = _source_location(item)
    if location:
        lines.append(f"Source: {_inline_code(location)}")
    cluster = str(item.get("cluster") or "")
    if cluster:
        lines.append(f"Cluster: {_inline_code(cluster)}")
    owner = str(item.get("owner") or "")
    if owner:
        lines.append(f"Owner: {_inline_code(owner)}")
    confidence = str(item.get("confidence") or "")
    if confidence:
        lines.append(f"Confidence: {_inline_code(confidence)}")
    signal = str(item.get("signal") or "")
    if signal:
        lines.append(f"Signal: {_inline_code(signal)}")
    return lines


def _result_warnings(result: dict[str, Any]) -> list[str]:
    warnings = result.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [str(warning) for warning in warnings if str(warning).strip()]


def _owner_review_rows(diffs: Any) -> list[dict[str, int | str]]:
    if not isinstance(diffs, list):
        return []
    rows: dict[str, dict[str, int | str]] = {}
    for item in diffs:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("owner") or "").strip()
        if not owner:
            continue
        status = str(item.get("status") or "")
        row = rows.setdefault(
            owner,
            {
                "owner": owner,
                "blocking": 0,
                "changed": 0,
                "accepted": 0,
                "ignored": 0,
                "other": 0,
                "total": 0,
            },
        )
        row["total"] = int(row["total"]) + 1
        if status in {"regression", "missing"}:
            row["blocking"] = int(row["blocking"]) + 1
        elif status == "changed":
            row["changed"] = int(row["changed"]) + 1
        elif status == "accepted":
            row["accepted"] = int(row["accepted"]) + 1
        elif status == "ignored":
            row["ignored"] = int(row["ignored"]) + 1
        else:
            row["other"] = int(row["other"]) + 1
    return sorted(
        rows.values(),
        key=lambda row: (
            -int(row["blocking"]),
            -int(row["changed"]),
            -int(row["total"]),
            str(row["owner"]).lower(),
        ),
    )


def _junit_properties(item: dict[str, Any]) -> dict[str, str]:
    properties = {}
    location = _source_location(item)
    if location:
        properties["source"] = location
    cluster = str(item.get("cluster") or "")
    if cluster:
        properties["cluster"] = cluster
    owner = str(item.get("owner") or "")
    if owner:
        properties["owner"] = owner
    confidence = str(item.get("confidence") or "")
    if confidence:
        properties["confidence"] = confidence
    signal = str(item.get("signal") or "")
    if signal:
        properties["signal"] = signal
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
    owner = str(item.get("owner") or "")
    confidence = str(item.get("confidence") or "")
    signal = str(item.get("signal") or "")
    reasons = item.get("reasons")
    reason = str(reasons[0]) if isinstance(reasons, list) and reasons else str(item.get("status") or "changed")
    owner_line = f"\nOwner: {owner}" if owner else ""
    trust_line = f"\nConfidence: {confidence} ({signal})" if confidence and signal else ""
    return f"{case_id}: {reason}{owner_line}{trust_line}\nPrompt: {prompt}"


_HTML_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2937;
  --muted: #5b6472;
  --line: #d8dde6;
  --regression: #b42318;
  --changed: #9a6700;
  --improved: #067647;
  --neutral: #4b5563;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.45;
}
.page { max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }
h1 { margin: 0 0 6px; font-size: 32px; letter-spacing: 0; }
h2 { margin: 28px 0 12px; font-size: 20px; letter-spacing: 0; }
h3 { margin: 0; font-size: 16px; letter-spacing: 0; }
.lede { margin: 0; color: var(--muted); }
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
  margin: 24px 0;
}
.metric {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
}
.metric strong { display: block; font-size: 24px; }
.metric span { color: var(--muted); font-size: 13px; text-transform: uppercase; }
.panel, .decision, .case {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
}
.decision p { margin: 8px 0 0; }
.scope { color: var(--muted); }
.case { margin: 14px 0; }
.panel { margin: 14px 0; }
.owner-review table {
  border-collapse: collapse;
  width: 100%;
}
.owner-review th, .owner-review td {
  border-top: 1px solid var(--line);
  padding: 9px 8px;
}
.owner-review th:first-child, .owner-review td:first-child { text-align: left; }
.owner-review th:not(:first-child), .owner-review td:not(:first-child) { text-align: right; }
.case-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.badge {
  border-radius: 999px;
  padding: 3px 9px;
  color: #ffffff;
  font-size: 12px;
  font-weight: 700;
}
.regression, .missing { background: var(--regression); }
.changed { background: var(--changed); }
.improved { background: var(--improved); }
.accepted, .ignored, .neutral { background: var(--neutral); }
.meta, .prompt { color: var(--muted); font-size: 13px; }
.reasons { margin: 10px 0 14px 20px; padding: 0; }
.responses {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.response {
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: #fbfcfe;
}
.response-title {
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  padding: 8px 10px;
  text-transform: uppercase;
}
pre {
  margin: 0;
  max-height: 520px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}
""".strip()


def _html_summary(summary: dict[str, Any]) -> str:
    rows = [
        ("Cases", "cases"),
        ("Regression", "regression"),
        ("Changed", "changed"),
        ("Improved", "improved"),
        ("Accepted", "accepted"),
        ("Ignored", "ignored"),
        ("Neutral", "neutral"),
        ("Missing", "missing"),
    ]
    cards = [
        (
            '<div class="metric">'
            f"<strong>{_h(_count_value(summary, key))}</strong>"
            f"<span>{_h(label)}</span>"
            "</div>"
        )
        for label, key in rows
    ]
    return '<section class="summary" aria-label="Summary">' + "".join(cards) + "</section>"


def _html_decision(decision: dict[str, Any]) -> str:
    confidence = str(decision.get("confidence") or "").upper()
    action = str(decision.get("recommended_action") or "")
    scope = str(decision.get("scope") or "")
    rationale = decision.get("rationale")
    lines = ['<section class="decision">', "<h2>Decision</h2>"]
    if confidence:
        lines.append(f"<p><strong>Confidence:</strong> {_h(confidence)}</p>")
    if action:
        lines.append(f"<p><strong>Recommended action:</strong> {_h(action)}</p>")
    if scope:
        lines.append(f'<p class="scope"><strong>Scope:</strong> {_h(scope)}</p>')
    if isinstance(rationale, list) and rationale:
        lines.append("<ul>")
        for item in rationale:
            lines.append(f"<li>{_h(str(item))}</li>")
        lines.append("</ul>")
    lines.append("</section>")
    return "".join(lines)


def _html_warnings(result: dict[str, Any]) -> str:
    warnings = _result_warnings(result)
    if not warnings:
        return ""
    lines = ['<section class="panel warning">', "<h2>Warnings</h2>", "<ul>"]
    for warning in warnings:
        lines.append(f"<li>{_h(warning)}</li>")
    lines.append("</ul></section>")
    return "".join(lines)


def _html_owner_review(diffs: list[Any]) -> str:
    rows = _owner_review_rows(diffs)
    if not rows:
        return ""
    lines = [
        '<section class="panel owner-review">',
        "<h2>Owner review</h2>",
        "<table>",
        "<thead><tr>",
        "<th>Owner</th>",
        "<th>Blocking</th>",
        "<th>Changed</th>",
        "<th>Accepted</th>",
        "<th>Ignored</th>",
        "<th>Other</th>",
        "<th>Total</th>",
        "</tr></thead>",
        "<tbody>",
    ]
    for row in rows:
        lines.append(
            "<tr>"
            f"<td>{_h(str(row['owner']))}</td>"
            f"<td>{row['blocking']}</td>"
            f"<td>{row['changed']}</td>"
            f"<td>{row['accepted']}</td>"
            f"<td>{row['ignored']}</td>"
            f"<td>{row['other']}</td>"
            f"<td>{row['total']}</td>"
            "</tr>"
        )
    lines.append("</tbody></table></section>")
    return "".join(lines)


def _html_cases(diffs: list[Any]) -> str:
    lines = ["<section>", "<h2>Cases</h2>"]
    if not diffs:
        lines.append('<p class="scope">No cases in this report.</p>')
        lines.append("</section>")
        return "".join(lines)
    for item in diffs:
        if isinstance(item, dict):
            lines.append(_html_case(item))
    lines.append("</section>")
    return "".join(lines)


def _html_case(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "unknown")
    case_id = str(item.get("case_id") or "unknown")
    location = _source_location(item)
    owner = str(item.get("owner") or "")
    confidence = str(item.get("confidence") or "")
    signal = str(item.get("signal") or "")
    prompt = str(item.get("prompt") or "")
    reasons = item.get("reasons")
    baseline = str(item.get("baseline_response") or "")
    candidate = item.get("candidate_response")
    lines = [
        '<article class="case">',
        '<div class="case-header">',
        f'<span class="badge {_h(status)}">{_h(status.upper())}</span>',
        f"<h3>{_h(case_id)}</h3>",
        "</div>",
    ]
    if location:
        lines.append(f'<div class="meta">{_h(location)}</div>')
    if owner:
        lines.append(f'<div class="meta">Owner: {_h(owner)}</div>')
    if confidence or signal:
        metadata = " | ".join(
            value
            for value in (
                f"Confidence: {confidence}" if confidence else "",
                f"Signal: {signal}" if signal else "",
            )
            if value
        )
        lines.append(f'<div class="meta">{_h(metadata)}</div>')
    if prompt:
        lines.append(f'<p class="prompt"><strong>Prompt:</strong> {_h(prompt)}</p>')
    if isinstance(reasons, list) and reasons:
        lines.append('<ul class="reasons">')
        for reason in reasons:
            lines.append(f"<li>{_h(str(reason))}</li>")
        lines.append("</ul>")
    lines.append('<div class="responses">')
    lines.append(_html_response("Baseline", baseline))
    if candidate is None:
        lines.append(_html_response("Candidate", "<missing>"))
    else:
        lines.append(_html_response("Candidate", str(candidate)))
    lines.append("</div>")
    lines.append("</article>")
    return "".join(lines)


def _html_response(title: str, value: str) -> str:
    return (
        '<div class="response">'
        f'<div class="response-title">{_h(title)}</div>'
        f"<pre>{_h(value)}</pre>"
        "</div>"
    )


def _count_value(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key, 0)
    return str(value if isinstance(value, int) else 0)


def _markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|")


def _h(value: str) -> str:
    return escape(value, quote=True)


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
