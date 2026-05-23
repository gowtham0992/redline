from __future__ import annotations

from pathlib import Path
from typing import Any

from .diff import compare_suite_to_candidate, format_report
from .io import read_jsonl_records, write_json, write_jsonl, write_text
from .reports import format_markdown_report
from .suite import build_suite


DEMO_BASELINE = [
    {
        "prompt": "Classify this support ticket for Maya Chen: double charged invoice INV-1042 after upgrading to Pro. Return JSON with category, priority, owner, and required_action.",
        "response": '{"category": "billing", "priority": "high", "owner": "Billing Ops", "required_action": "open refund review for invoice INV-1042"}',
    },
    {
        "prompt": "Answer the customer asking whether Enterprise annual plans can be refunded. Include the refund window and the policy URL.",
        "response": "Enterprise annual plans can be refunded within 30 days of purchase when the workspace has fewer than 5 active seats. Policy: https://docs.redline.ai/policies/refunds",
    },
    {
        "prompt": "Draft a support reply for ticket SEC-441 about a failed SOC 2 evidence export. Include escalation owner and response ETA.",
        "response": "Thanks for reporting ticket SEC-441. I escalated this to Security Operations and we will send an update within 4 hours. You can retry the SOC 2 export from Compliance > Evidence while we investigate.",
    },
    {
        "prompt": "Summarize this incident update as a Markdown table with columns Impact, Status, Owner, and Next update: EU search indexing delayed for 12 minutes; mitigated; Search Platform owns follow-up; next update 09:30 UTC.",
        "response": "| Impact | Status | Owner | Next update |\n| --- | --- | --- | --- |\n| EU search indexing delayed for 12 minutes | Mitigated | Search Platform | 09:30 UTC |",
    },
    {
        "prompt": "Classify this login ticket: user cannot sign in after SSO migration.",
        "response": "authentication",
    },
]

DEMO_CANDIDATE = [
    {
        "prompt": "Classify this support ticket for Maya Chen: double charged invoice INV-1042 after upgrading to Pro. Return JSON with category, priority, owner, and required_action.",
        "response": '{"category": "billing", "priority": "normal"}',
    },
    {
        "prompt": "Answer the customer asking whether Enterprise annual plans can be refunded. Include the refund window and the policy URL.",
        "response": "Enterprise annual plans may be eligible for a refund depending on account usage. Ask the customer success team to review the request.",
    },
    {
        "prompt": "Draft a support reply for ticket SEC-441 about a failed SOC 2 evidence export. Include escalation owner and response ETA.",
        "response": "Sorry, I can't access internal security escalations. Please ask your admin to contact support.",
    },
    {
        "prompt": "Summarize this incident update as a Markdown table with columns Impact, Status, Owner, and Next update: EU search indexing delayed for 12 minutes; mitigated; Search Platform owns follow-up; next update 09:30 UTC.",
        "response": "EU search indexing was delayed briefly, but the issue is now mitigated. The search team owns follow-up and will post another update soon.",
    },
    {
        "prompt": "Classify this login ticket: user cannot sign in after SSO migration.",
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
        "Generated a local support-agent regression demo.",
        "Scenario: a shorter candidate prompt sounds cleaner but drops required production details.",
        f"Baseline log: {result['baseline']}",
        f"Candidate log: {result['candidate']}",
        f"Prompt file:   {result['prompt']}",
        f"Suite:         {result['suite']}",
        f"Reports:       {result['report_json']}, {result['report_markdown']}",
        "",
        format_report(result["diff"], title="redline demo").rstrip(),
        "",
        "Next steps",
        f"- Inspect the Markdown report: {result['report_markdown']}",
        f"- List demo cases: redline cases {result['suite']}",
        '- Initialize your project: redline init --replay "python your_runner.py" --github-action',
        "- Build a real suite: redline suite path/to/baseline.jsonl",
        "- Check setup before CI: redline doctor --strict",
    ]
    return "\n".join(lines).rstrip() + "\n"
