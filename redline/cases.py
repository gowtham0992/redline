from __future__ import annotations

from typing import Any


def suite_case_rows(suite: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    requirements = suite.get("requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}
    judgments = suite.get("judgments", {})
    if not isinstance(judgments, dict):
        judgments = {}
    for case in suite.get("cases", []):
        case_id = str(case["id"])
        judgment = judgments.get(case_id)
        rows.append(
            {
                "id": case_id,
                "content_hash": str(case.get("content_hash", "")),
                "source_line": case.get("source_line"),
                "cluster": str(case.get("cluster", "")),
                "prompt": str(case.get("prompt", "")),
                "prompt_preview": _preview(str(case.get("prompt", ""))),
                "baseline_preview": _preview(str(case.get("baseline_response", ""))),
                "requirements": _requirement_count(requirements.get(case_id)),
                "judgment": _judgment_status(judgment),
            }
        )
    return rows


def format_suite_cases(suite: dict[str, Any]) -> str:
    rows = suite_case_rows(suite)
    lines = ["redline cases", ""]
    if not rows:
        return "redline cases\n\nNo cases found.\n"

    lines.append(f"{'CASE':<24} {'LINE':>5} {'RULES':>5} {'JUDGMENT':<10} PROMPT")
    lines.append(f"{'-' * 24} {'-' * 5} {'-' * 5} {'-' * 10} {'-' * 60}")
    for row in rows:
        source_line = "" if row["source_line"] is None else str(row["source_line"])
        lines.append(
            f"{row['id']:<24} {source_line:>5} {row['requirements']:>5} "
            f"{row['judgment']:<10} {row['prompt_preview']}"
        )
    return "\n".join(lines) + "\n"


def suite_case_detail(suite: dict[str, Any], case_id: str) -> dict[str, Any]:
    case = _find_case(suite, case_id)
    judgments = suite.get("judgments", {})
    if not isinstance(judgments, dict):
        judgments = {}
    judgment = judgments.get(case_id)
    requirements = suite.get("requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}
    requirement = requirements.get(case_id)
    return {
        "id": str(case["id"]),
        "source_line": case.get("source_line"),
        "cluster": str(case.get("cluster", "")),
        "prompt": str(case.get("prompt", "")),
        "baseline_response": str(case.get("baseline_response", "")),
        "content_hash": str(case.get("content_hash", "")),
        "features": case.get("features", {}),
        "judgment": judgment if isinstance(judgment, dict) else None,
        "requirements": requirement if isinstance(requirement, dict) else None,
    }


def format_suite_case_detail(suite: dict[str, Any], case_id: str) -> str:
    detail = suite_case_detail(suite, case_id)
    lines = [
        f"redline case {detail['id']}",
        "",
        f"Source line: {detail['source_line']}",
        f"Cluster:     {detail['cluster']}",
        f"Content hash: {detail['content_hash']}",
        "",
        "Prompt:",
        detail["prompt"],
        "",
        "Baseline response:",
        detail["baseline_response"],
        "",
        "Features:",
    ]
    features = detail["features"]
    if isinstance(features, dict):
        for key in sorted(features):
            lines.append(f"  {key}: {features[key]}")
    else:
        lines.append("  <missing>")

    if detail["judgment"]:
        lines.extend(["", "Judgment:"])
        for key, value in detail["judgment"].items():
            lines.append(f"  {key}: {value}")

    if detail["requirements"]:
        lines.extend(["", "Requirements:"])
        for key, value in detail["requirements"].items():
            lines.append(f"  {key}: {value}")

    return "\n".join(lines).rstrip() + "\n"


def _preview(text: str, limit: int = 76) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _requirement_count(requirement: object) -> int:
    if not isinstance(requirement, dict):
        return 0
    count = 0
    for key in ("include", "exclude"):
        values = requirement.get(key)
        if isinstance(values, list):
            count += len([value for value in values if str(value).strip()])
    return count


def _judgment_status(judgment: object) -> str:
    if not isinstance(judgment, dict):
        return ""
    status = judgment.get("status")
    return str(status) if status else ""


def _find_case(suite: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in suite.get("cases", []):
        if isinstance(case, dict) and str(case.get("id")) == case_id:
            return case
    raise ValueError(f"case not found in suite: {case_id}")
