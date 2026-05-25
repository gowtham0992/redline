from __future__ import annotations

from html import escape
from shlex import quote
from typing import Any
from xml.etree import ElementTree

from .labels import behavior_label


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

    prompt_rows = _prompt_eval_rows(result.get("prompt_evals"))
    prompt_groups = _prompt_group_rows(prompt_rows)
    if prompt_groups:
        lines.append("## Feature Summary")
        lines.append("")
        lines.append("| Feature | Prompts | Cases | Regression | Changed | Missing | Neutral | Action |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
        for row in prompt_groups:
            summary = row["summary"]
            lines.append(
                f"| {_markdown_cell(str(row['feature']))} | {row['prompt_count']} | "
                f"{_summary_count(summary, 'cases')} | {_summary_count(summary, 'regression')} | "
                f"{_summary_count(summary, 'changed')} | {_summary_count(summary, 'missing')} | "
                f"{_summary_count(summary, 'neutral')} | {_markdown_cell(str(row['action']))} |"
            )
        lines.append("")

    if prompt_rows:
        lines.append("## Prompt Evals")
        lines.append("")
        lines.append("| Prompt | Suite | Cases | Regression | Changed | Missing | Neutral | Action |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
        for row in prompt_rows:
            summary = row["summary"]
            lines.append(
                f"| {_markdown_cell(str(row['id']))}<br>{_markdown_cell(str(row['prompt']))} | "
                f"{_markdown_cell(str(row['suite']))} | {_summary_count(summary, 'cases')} | "
                f"{_summary_count(summary, 'regression')} | {_summary_count(summary, 'changed')} | "
                f"{_summary_count(summary, 'missing')} | {_summary_count(summary, 'neutral')} | "
                f"{_markdown_cell(str(row['action'] or '-'))} |"
            )
        lines.append("")

    review_commands = _review_command_lines(result)
    if review_commands:
        lines.append("## Review Commands")
        lines.append("")
        lines.append("Use these only for intentional changes after human review; fix real regressions instead.")
        lines.append("")
        for command in review_commands:
            lines.append(f"- `{command}`")
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
            _html_prompt_groups(result),
            _html_prompt_evals(result),
            _html_review_commands(result),
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
        lines.append(f"Behavior: {_inline_code(behavior_label(cluster))}")
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


def _review_command_lines(result: dict[str, Any]) -> list[str]:
    suite_path = str(result.get("suite") or "").strip()
    if not suite_path:
        return []
    suite = quote(suite_path)
    diffs = result.get("diffs")
    if not isinstance(diffs, list):
        return []
    reviewable = [
        str(item.get("case_id") or "").strip()
        for item in diffs
        if isinstance(item, dict) and item.get("status") in {"regression", "changed", "missing"}
    ]
    reviewable = [case_id for case_id in reviewable if case_id]
    if not reviewable:
        return []
    commands = [
        f'redline mark {suite} {case_id} --status expected --note "intentional change"'
        for case_id in reviewable[:5]
    ]
    candidate_path = str(result.get("candidate") or "").strip()
    if candidate_path:
        candidate = quote(candidate_path)
        commands.append(
            f'redline accept {suite} --all-expected --candidate {candidate} --note "accepted reviewed changes"'
        )
    if len(reviewable) > 5:
        commands.append(f"redline cases {suite}")
    return commands


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


def _prompt_eval_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        decision = item.get("decision")
        action = ""
        if isinstance(decision, dict):
            action = str(decision.get("recommended_action") or "")
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "prompt": str(item.get("prompt") or ""),
                "suite": str(item.get("suite") or ""),
                "summary": _summary_counts(summary if isinstance(summary, dict) else {}),
                "action": action,
            }
        )
    return rows


def _prompt_group_rows(prompt_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in prompt_rows:
        feature = _prompt_feature(row)
        group = groups.setdefault(
            feature,
            {
                "feature": feature,
                "prompt_count": 0,
                "summary": {},
                "action": "clean",
            },
        )
        group["prompt_count"] = int(group["prompt_count"]) + 1
        group_summary = group["summary"]
        row_summary = row.get("summary")
        if isinstance(group_summary, dict) and isinstance(row_summary, dict):
            for key, value in row_summary.items():
                group_summary[key] = int(group_summary.get(key) or 0) + int(value or 0)
    rows = list(groups.values())
    for row in rows:
        summary = row.get("summary")
        row["action"] = _prompt_group_action(summary if isinstance(summary, dict) else {})
    return sorted(
        rows,
        key=lambda row: (
            -_blocking_count(row.get("summary")),
            -_summary_count(row.get("summary"), "changed"),
            str(row.get("feature") or "").lower(),
        ),
    )


def _prompt_feature(row: dict[str, Any]) -> str:
    identifier = str(row.get("id") or "").strip().replace("\\", "/")
    if "/" in identifier:
        first = next((part for part in identifier.split("/") if part), "")
        if first:
            return first
    prompt = str(row.get("prompt") or "").strip().replace("\\", "/")
    parts = [part for part in prompt.split("/") if part and part not in {".", ".."}]
    if "prompts" in parts:
        index = parts.index("prompts")
        if index + 1 < len(parts):
            candidate = parts[index + 1]
            if index + 2 == len(parts):
                return candidate.rsplit(".", 1)[0] or "default"
            return candidate
    if len(parts) > 1:
        return parts[0]
    if parts:
        return parts[0].rsplit(".", 1)[0] or "default"
    return "default"


def _prompt_group_action(summary: dict[str, Any]) -> str:
    if _blocking_count(summary):
        return "fix blocking cases before shipping"
    if _summary_count(summary, "changed"):
        return "review changed cases before shipping"
    return "clean"


def _blocking_count(summary: Any) -> int:
    return _summary_count(summary, "regression") + _summary_count(summary, "missing")


def _summary_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {}
    for key, value in summary.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return counts


def _summary_count(summary: Any, key: str) -> int:
    if not isinstance(summary, dict):
        return 0
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0


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
.prompt-groups th:last-child, .prompt-groups td:last-child,
.prompt-evals th:nth-child(2), .prompt-evals td:nth-child(2),
.prompt-evals th:last-child, .prompt-evals td:last-child { text-align: left; }
.prompt-evals td span { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
.review-commands p { color: var(--muted); margin: 0 0 12px; }
.review-commands ul { margin: 0; padding-left: 20px; }
.review-commands li { margin: 8px 0; }
.review-commands code {
  background: #f0f3f8;
  border: 1px solid var(--line);
  border-radius: 6px;
  display: inline-block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  padding: 4px 6px;
}
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


def _html_prompt_groups(result: dict[str, Any]) -> str:
    prompt_rows = _prompt_eval_rows(result.get("prompt_evals"))
    rows = _prompt_group_rows(prompt_rows)
    if not rows:
        return ""
    lines = [
        '<section class="panel owner-review prompt-groups">',
        "<h2>Feature summary</h2>",
        "<table>",
        "<thead><tr>",
        "<th>Feature</th>",
        "<th>Prompts</th>",
        "<th>Cases</th>",
        "<th>Regression</th>",
        "<th>Changed</th>",
        "<th>Missing</th>",
        "<th>Neutral</th>",
        "<th>Action</th>",
        "</tr></thead>",
        "<tbody>",
    ]
    for row in rows:
        summary = row["summary"]
        lines.append(
            "<tr>"
            f"<td>{_h(str(row['feature']))}</td>"
            f"<td>{row['prompt_count']}</td>"
            f"<td>{_summary_count(summary, 'cases')}</td>"
            f"<td>{_summary_count(summary, 'regression')}</td>"
            f"<td>{_summary_count(summary, 'changed')}</td>"
            f"<td>{_summary_count(summary, 'missing')}</td>"
            f"<td>{_summary_count(summary, 'neutral')}</td>"
            f"<td>{_h(str(row['action']))}</td>"
            "</tr>"
        )
    lines.append("</tbody></table></section>")
    return "".join(lines)


def _html_prompt_evals(result: dict[str, Any]) -> str:
    rows = _prompt_eval_rows(result.get("prompt_evals"))
    if not rows:
        return ""
    lines = [
        '<section class="panel owner-review prompt-evals">',
        "<h2>Prompt evals</h2>",
        "<table>",
        "<thead><tr>",
        "<th>Prompt</th>",
        "<th>Suite</th>",
        "<th>Cases</th>",
        "<th>Regression</th>",
        "<th>Changed</th>",
        "<th>Missing</th>",
        "<th>Neutral</th>",
        "<th>Action</th>",
        "</tr></thead>",
        "<tbody>",
    ]
    for row in rows:
        summary = row["summary"]
        lines.append(
            "<tr>"
            f"<td>{_h(str(row['id'] or '-'))}<span>{_h(str(row['prompt'] or '-'))}</span></td>"
            f"<td>{_h(str(row['suite'] or '-'))}</td>"
            f"<td>{_summary_count(summary, 'cases')}</td>"
            f"<td>{_summary_count(summary, 'regression')}</td>"
            f"<td>{_summary_count(summary, 'changed')}</td>"
            f"<td>{_summary_count(summary, 'missing')}</td>"
            f"<td>{_summary_count(summary, 'neutral')}</td>"
            f"<td>{_h(str(row['action'] or '-'))}</td>"
            "</tr>"
        )
    lines.append("</tbody></table></section>")
    return "".join(lines)


def _html_review_commands(result: dict[str, Any]) -> str:
    commands = _review_command_lines(result)
    if not commands:
        return ""
    lines = [
        '<section class="panel review-commands">',
        "<h2>Review commands</h2>",
        "<p>Use these only for intentional changes after human review; fix real regressions instead.</p>",
        "<ul>",
    ]
    for command in commands:
        lines.append(f"<li><code>{_h(command)}</code></li>")
    lines.append("</ul></section>")
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
    cluster = str(item.get("cluster") or "")
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
    if cluster:
        lines.append(f'<div class="meta">Behavior: {_h(behavior_label(cluster))}</div>')
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
