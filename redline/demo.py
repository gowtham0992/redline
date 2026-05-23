from __future__ import annotations

from pathlib import Path
from typing import Any

from .diff import compare_suite_to_candidate, format_report
from .io import read_jsonl_records, write_json, write_jsonl, write_text
from .reports import format_markdown_report
from .suite import build_suite


DEMO_BASELINE = [
    {
        "prompt": "Return JSON with name and status for customer Ada.",
        "response": '{"name":"Ada","status":"active"}',
    },
    {
        "prompt": "Summarize the release note in three bullets.",
        "response": "- Added CSV export\n- Fixed invoice retries\n- Improved admin search",
    },
    {
        "prompt": "What is the refund window? Include the number of days.",
        "response": "Customers can request a refund within 30 days of purchase.",
    },
    {
        "prompt": "Write a Python function that adds two numbers.",
        "response": "```python\ndef add(a, b):\n    return a + b\n```",
    },
    {
        "prompt": "Classify this ticket: Cannot log in after password reset.",
        "response": "authentication",
    },
]

DEMO_CANDIDATE = [
    {
        "prompt": "Return JSON with name and status for customer Ada.",
        "response": '{"name":"Ada"',
    },
    {
        "prompt": "Summarize the release note in three bullets.",
        "response": "The release adds CSV export, fixes invoice retries, and improves admin search.",
    },
    {
        "prompt": "What is the refund window? Include the number of days.",
        "response": "Customers can request a refund after purchase.",
    },
    {
        "prompt": "Write a Python function that adds two numbers.",
        "response": "def add(a, b):\n    return a + b",
    },
    {
        "prompt": "Classify this ticket: Cannot log in after password reset.",
        "response": "authentication",
    },
]

DEMO_PROMPT = """You are testing a candidate prompt with redline.

Answer the user request exactly and preserve any required format.

User request:
{prompt}
"""


def run_demo(output_dir: str | Path = ".redline/demo") -> dict[str, Any]:
    root = Path(output_dir)
    baseline_path = root / "baseline.jsonl"
    candidate_path = root / "candidate.jsonl"
    prompt_path = root / "prompts" / "v2.txt"
    suite_path = root / "suite.json"
    report_json_path = root / "reports" / "diff.json"
    report_md_path = root / "reports" / "diff.md"

    write_jsonl(baseline_path, DEMO_BASELINE)
    write_jsonl(candidate_path, DEMO_CANDIDATE)
    write_text(prompt_path, DEMO_PROMPT)

    baseline = read_jsonl_records(baseline_path, "prompt", "response")
    suite = build_suite(
        baseline,
        source=baseline_path,
        input_field="prompt",
        output_field="response",
        max_cases=42,
    )
    write_json(suite_path, suite)

    candidate = read_jsonl_records(candidate_path, "prompt", "response")
    result = compare_suite_to_candidate(suite, candidate)
    write_json(report_json_path, result)
    write_text(report_md_path, format_markdown_report(result, title="redline demo"))

    return {
        "output_dir": str(root),
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "prompt": str(prompt_path),
        "suite": str(suite_path),
        "report_json": str(report_json_path),
        "report_markdown": str(report_md_path),
        "summary": result["summary"],
        "decision": result["decision"],
        "diff": result,
    }


def format_demo(result: dict[str, Any]) -> str:
    lines = [
        "redline demo",
        "",
        "Generated a local prompt-regression demo with an intentional candidate regression.",
        f"Baseline log: {result['baseline']}",
        f"Candidate log: {result['candidate']}",
        f"Prompt file:   {result['prompt']}",
        f"Suite:         {result['suite']}",
        f"Reports:       {result['report_json']}, {result['report_markdown']}",
        "",
        format_report(result["diff"], title="redline demo").rstrip(),
    ]
    return "\n".join(lines).rstrip() + "\n"
