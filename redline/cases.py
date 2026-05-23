from __future__ import annotations

from typing import Any


def suite_case_rows(suite: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in suite.get("cases", []):
        rows.append(
            {
                "id": str(case["id"]),
                "source_line": case.get("source_line"),
                "cluster": str(case.get("cluster", "")),
                "prompt": str(case.get("prompt", "")),
                "prompt_preview": _preview(str(case.get("prompt", ""))),
                "baseline_preview": _preview(str(case.get("baseline_response", ""))),
            }
        )
    return rows


def format_suite_cases(suite: dict[str, Any]) -> str:
    rows = suite_case_rows(suite)
    lines = ["redline cases", ""]
    if not rows:
        return "redline cases\n\nNo cases found.\n"

    lines.append(f"{'CASE':<24} {'LINE':>5}  PROMPT")
    lines.append(f"{'-' * 24} {'-' * 5}  {'-' * 60}")
    for row in rows:
        source_line = "" if row["source_line"] is None else str(row["source_line"])
        lines.append(f"{row['id']:<24} {source_line:>5}  {row['prompt_preview']}")
    return "\n".join(lines) + "\n"


def _preview(text: str, limit: int = 76) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."
