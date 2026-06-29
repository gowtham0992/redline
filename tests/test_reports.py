import json
import tempfile
import unittest
from pathlib import Path

from redline.io import write_json, write_text
from redline.reports import (
    format_github_annotations,
    format_html_report,
    format_junit_report,
    format_markdown_report,
    format_pr_comment,
    format_slack_report,
)


class ReportTests(unittest.TestCase):
    def test_markdown_report_includes_summary_and_reasons(self) -> None:
        result = {
            "summary": {
                "cases": 1,
                "regression": 1,
                "changed": 0,
                "improved": 0,
                "neutral": 0,
                "missing": 0,
            },
            "decision": {
                "confidence": "high",
                "recommended_action": "fix blocking cases before shipping",
                "scope": "structural checks only; review semantic risks separately",
                "diagnosis": "Candidate lost required structure; fix blocking cases before shipping.",
            },
            "warnings": ["prompt file prompts/v2.txt is newer than suite"],
            "suite": "redline-suite.json",
            "methodology": {
                "name": "deterministic behavior-signature grouping",
                "version": "behavior-signature-v1",
            },
            "suite_summary": {
                "cases": 1,
                "unique_prompt_response_pairs": 2,
                "clusters": 1,
                "case_coverage": 0.5,
                "cluster_coverage": 1.0,
            },
            "candidate": ".redline/runs/candidate.jsonl",
            "artifacts": {
                "json": ".redline/reports/eval.json",
                "markdown": ".redline/reports/eval.md",
                "html": ".redline/reports/eval.html",
                "junit": ".redline/reports/eval.xml",
            },
            "prompt_evals": [
                {
                    "id": "support/triage",
                    "prompt": "prompts/support/triage.txt",
                    "suite": "suites/support/triage.redline-suite.json",
                    "summary": {"cases": 1, "regression": 1, "changed": 0, "missing": 0, "neutral": 0},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                },
                {
                    "id": "billing/refund",
                    "prompt": "prompts/billing/refund.txt",
                    "suite": "suites/billing/refund.redline-suite.json",
                    "summary": {"cases": 2, "regression": 0, "changed": 0, "missing": 0, "neutral": 2},
                    "decision": {"recommended_action": "ship candidate; no blocking changes detected"},
                },
            ],
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "cluster": "structured_json|json|short",
                    "owner": "@platform-team",
                    "owner_rule": {"match": "platform", "field": "prompt"},
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return JSON",
                    "baseline_response": '{"ok": true}',
                    "candidate_response": "ok",
                    "reasons": ["candidate lost valid JSON format"],
                }
            ],
        }

        report = format_markdown_report(result, title="redline eval")

        self.assertIn("# redline eval", report)
        self.assertIn("| Regression | 1 |", report)
        self.assertIn("**Confidence:** HIGH", report)
        self.assertIn("**Recommended action:** fix blocking cases before shipping", report)
        self.assertIn("**Scope:** structural checks only", report)
        self.assertIn("**Diagnosis:** Candidate lost required structure; fix blocking cases before shipping.", report)
        self.assertIn("**Methodology:** deterministic behavior-signature grouping (behavior-signature-v1)", report)
        self.assertIn("**Suite coverage:** cases 1/2 (50.0%); behavior groups 1/1 (100.0%)", report)
        self.assertIn("## Warnings", report)
        self.assertIn("prompt file prompts/v2.txt is newer than suite", report)
        self.assertIn("## Artifacts", report)
        self.assertIn("| HTML | `.redline/reports/eval.html` |", report)
        self.assertIn("| JUnit | `.redline/reports/eval.xml` |", report)
        self.assertIn("## Owner Review", report)
        self.assertIn("| @platform-team | 1 | 0 | 0 | 0 | 0 | 1 | 1 |", report)
        self.assertIn("## Feature Summary", report)
        self.assertIn("| support | 1 | 1 | 1 | 0 | 0 | 0 | fix blocking cases before shipping |", report)
        self.assertIn("| billing | 1 | 2 | 0 | 0 | 0 | 2 | clean |", report)
        self.assertIn("## Prompt Evals", report)
        self.assertIn("support/triage<br>prompts/support/triage.txt", report)
        self.assertIn("suites/support/triage.redline-suite.json", report)
        self.assertIn("## Review Commands", report)
        self.assertIn(
            '`redline mark redline-suite.json case_001 --status expected --note "intentional change"`',
            report,
        )
        self.assertIn(
            '`redline accept redline-suite.json --all-expected --candidate .redline/runs/candidate.jsonl --note "accepted reviewed changes"`',
            report,
        )
        self.assertIn("candidate lost valid JSON format", report)
        self.assertIn("Source: `baseline.jsonl:12`", report)
        self.assertIn("Cluster: `structured_json|json|short`", report)
        self.assertIn("Behavior: `structured JSON prompt -> JSON response (short)`", report)
        self.assertIn("Owner: `@platform-team`", report)
        self.assertIn("Confidence: `high`", report)
        self.assertIn("Signal: `structural`", report)
        self.assertIn(
            "Why this matters: Downstream code may fail if consumers expect parseable JSON or required fields.",
            report,
        )
        self.assertIn("Baseline:", report)
        self.assertIn('{"ok": true}', report)
        self.assertIn("Candidate:", report)

    def test_markdown_inline_code_preserves_backticks(self) -> None:
        result = {
            "summary": {"regression": 0, "changed": 1, "improved": 0, "neutral": 0, "missing": 0},
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "changed",
                    "prompt": "Use `json` output",
                    "baseline_response": "ok",
                    "candidate_response": "sure",
                    "reasons": ["short answer changed"],
                }
            ],
        }

        report = format_markdown_report(result)

        self.assertIn("Prompt: ``Use `json` output``", report)

    def test_markdown_report_prefers_explicit_case_impact(self) -> None:
        result = {
            "summary": {"regression": 1, "changed": 0, "improved": 0, "neutral": 0, "missing": 0},
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "prompt": "Return JSON",
                    "baseline_response": '{"owner":"billing"}',
                    "candidate_response": "billing",
                    "reasons": ["candidate lost valid JSON format"],
                    "impact": "Billing routing automation may fail because the owner field disappeared.",
                }
            ],
        }

        report = format_markdown_report(result)

        self.assertIn(
            "Why this matters: Billing routing automation may fail because the owner field disappeared.",
            report,
        )
        self.assertNotIn(
            "Why this matters: Downstream code may fail if consumers expect parseable JSON or required fields.",
            report,
        )

    def test_markdown_code_blocks_use_fence_longer_than_output_backticks(self) -> None:
        result = {
            "summary": {"regression": 0, "changed": 1, "improved": 0, "neutral": 0, "missing": 0},
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "changed",
                    "prompt": "Show a Markdown fence",
                    "baseline_response": "````\ninner\n````",
                    "candidate_response": "`````\ninner\n`````",
                    "reasons": ["content changed substantially: similarity 0.50"],
                }
            ],
        }

        report = format_markdown_report(result)

        self.assertIn("`````\n````\ninner\n````\n`````", report)
        self.assertIn("``````\n`````\ninner\n`````\n``````", report)

    def test_html_report_includes_side_by_side_case_detail(self) -> None:
        result = {
            "summary": {
                "cases": 1,
                "regression": 1,
                "changed": 0,
                "improved": 0,
                "accepted": 0,
                "ignored": 0,
                "neutral": 0,
                "missing": 0,
            },
            "decision": {
                "confidence": "high",
                "recommended_action": "fix blocking cases before shipping",
                "scope": "structural checks only; review semantic risks separately",
                "diagnosis": "Candidate lost required structure; fix blocking cases before shipping.",
                "rationale": ["1 regression case(s)"],
            },
            "warnings": ["prompt file prompts/v2.txt is newer than suite"],
            "suite": "redline-suite.json",
            "methodology": {
                "name": "deterministic behavior-signature grouping",
                "version": "behavior-signature-v1",
            },
            "suite_summary": {
                "cases": 1,
                "unique_prompt_response_pairs": 2,
                "clusters": 1,
                "case_coverage": 0.5,
                "cluster_coverage": 1.0,
            },
            "candidate": ".redline/runs/candidate.jsonl",
            "artifacts": {
                "json": ".redline/reports/eval.json",
                "markdown": ".redline/reports/eval.md",
                "html": ".redline/reports/eval.html",
                "junit": ".redline/reports/eval.xml",
            },
            "prompt_evals": [
                {
                    "id": "support/triage",
                    "prompt": "prompts/support/triage.txt",
                    "suite": "suites/support/triage.redline-suite.json",
                    "summary": {"cases": 1, "regression": 1, "changed": 0, "missing": 0, "neutral": 0},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                },
                {
                    "id": "billing/refund",
                    "prompt": "prompts/billing/refund.txt",
                    "suite": "suites/billing/refund.redline-suite.json",
                    "summary": {"cases": 2, "regression": 0, "changed": 0, "missing": 0, "neutral": 2},
                    "decision": {"recommended_action": "ship candidate; no blocking changes detected"},
                },
            ],
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "cluster": "structured_json|json|short",
                    "owner": "@platform-team",
                    "owner_rule": {"match": "platform", "field": "prompt"},
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return <JSON>",
                    "baseline_response": '{"ok": true}',
                    "candidate_response": "<script>alert(1)</script>",
                    "reasons": ["candidate lost valid JSON format"],
                }
            ],
        }

        report = format_html_report(result, title="redline eval")

        self.assertIn("<!doctype html>", report)
        self.assertIn("<title>redline eval</title>", report)
        self.assertIn('<section class="summary"', report)
        self.assertIn("Owner: @platform-team", report)
        self.assertIn("Behavior: structured JSON prompt -&gt; JSON response (short)", report)
        self.assertIn("Confidence: high | Signal: structural", report)
        self.assertIn("Why this matters:", report)
        self.assertIn("Downstream code may fail if consumers expect parseable JSON or required fields.", report)
        self.assertIn("fix blocking cases before shipping", report)
        self.assertIn("structural checks only", report)
        self.assertIn("Candidate lost required structure; fix blocking cases before shipping.", report)
        self.assertIn("<h2>Methodology</h2>", report)
        self.assertIn("deterministic behavior-signature grouping (behavior-signature-v1)", report)
        self.assertIn("<h2>Suite coverage</h2>", report)
        self.assertIn("cases 1/2 (50.0%); behavior groups 1/1 (100.0%)", report)
        self.assertIn("<h2>Warnings</h2>", report)
        self.assertIn("<h2>Artifacts</h2>", report)
        self.assertIn("<td>HTML</td><td>.redline/reports/eval.html</td>", report)
        self.assertIn("<td>JUnit</td><td>.redline/reports/eval.xml</td>", report)
        self.assertIn("<h2>Owner review</h2>", report)
        self.assertIn("<th>Rule provenance</th>", report)
        self.assertIn("<td>@platform-team</td><td>1</td><td>0</td>", report)
        self.assertIn("<td>0</td><td>1</td><td>1</td>", report)
        self.assertIn("<h2>Feature summary</h2>", report)
        self.assertIn("<td>support</td><td>1</td><td>1</td><td>1</td>", report)
        self.assertIn("<td>billing</td><td>1</td><td>2</td><td>0</td>", report)
        self.assertIn("<h2>Prompt evals</h2>", report)
        self.assertIn("support/triage", report)
        self.assertIn("prompts/support/triage.txt", report)
        self.assertIn("suites/support/triage.redline-suite.json", report)
        self.assertIn("<h2>Review commands</h2>", report)
        self.assertIn(
            'redline mark redline-suite.json case_001 --status expected --note &quot;intentional change&quot;',
            report,
        )
        self.assertIn(
            'redline accept redline-suite.json --all-expected --candidate .redline/runs/candidate.jsonl --note &quot;accepted reviewed changes&quot;',
            report,
        )
        self.assertIn("prompt file prompts/v2.txt is newer than suite", report)
        self.assertIn("case_001", report)
        self.assertIn("Baseline", report)
        self.assertIn("Candidate", report)
        self.assertIn("Return &lt;JSON&gt;", report)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", report)
        self.assertNotIn("<script>alert(1)</script>", report)

    def test_report_files_create_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "nested" / "report.json", {"ok": True})
            write_text(root / "nested" / "report.md", "# ok\n")

            self.assertEqual(json.loads((root / "nested" / "report.json").read_text()), {"ok": True})
            self.assertEqual((root / "nested" / "report.md").read_text(), "# ok\n")

    def test_junit_report_marks_regressions_as_failures(self) -> None:
        result = {
            "summary": {
                "cases": 1,
                "regression": 1,
                "changed": 0,
                "improved": 0,
                "accepted": 0,
                "ignored": 0,
                "neutral": 0,
                "missing": 0,
            },
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "cluster": "structured_json|json|short",
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return JSON",
                    "reasons": ["candidate lost valid JSON format"],
                }
            ],
        }

        report = format_junit_report(result, suite_name="redline.diff")

        self.assertIn('tests="1"', report)
        self.assertIn('failures="1"', report)
        self.assertIn("<failure", report)
        self.assertIn('name="source" value="baseline.jsonl:12"', report)
        self.assertIn('name="cluster" value="structured_json|json|short"', report)
        self.assertIn('name="confidence" value="high"', report)
        self.assertIn('name="signal" value="structural"', report)
        self.assertIn("candidate lost valid JSON format", report)

    def test_github_annotations_mark_regressions_and_changed_cases(self) -> None:
        result = {
            "summary": {},
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "logs/baseline.jsonl",
                    "source_line": 7,
                    "owner": "@platform-team",
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return JSON",
                    "reasons": ["candidate lost valid JSON format"],
                },
                {
                    "case_id": "case_002",
                    "status": "changed",
                    "source": "logs/baseline.jsonl",
                    "source_line": 8,
                    "prompt": "Route to billing, not security",
                    "reasons": ["short answer changed"],
                },
                {
                    "case_id": "case_003",
                    "status": "neutral",
                    "prompt": "hello",
                    "reasons": ["no high-signal behavioral change detected"],
                },
            ],
        }

        annotations = format_github_annotations(result, title="redline eval")

        self.assertIn("::error", annotations)
        self.assertIn("::warning", annotations)
        self.assertIn("title=redline eval%3A regression case_001", annotations)
        self.assertIn("file=logs/baseline.jsonl,line=7", annotations)
        self.assertIn("candidate lost valid JSON format", annotations)
        self.assertIn("Owner: @platform-team", annotations)
        self.assertIn("Confidence: high (structural)", annotations)
        self.assertIn("Prompt: Route to billing, not security", annotations)
        self.assertNotIn("case_003", annotations)

    def test_github_annotations_escape_newlines_and_percent_signs(self) -> None:
        result = {
            "summary": {},
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "missing",
                    "source": "logs/baseline.jsonl",
                    "source_line": 1,
                    "prompt": "Discount 50%",
                    "reasons": ["first line\nsecond 50%"],
                }
            ],
        }

        annotations = format_github_annotations(result)

        self.assertIn("first line%0Asecond 50%25", annotations)
        self.assertIn("Prompt: Discount 50%25", annotations)

    def test_pr_comment_report_is_concise_and_actionable(self) -> None:
        result = {
            "suite": "redline-prompts.json",
            "summary": {
                "cases": 3,
                "regression": 1,
                "changed": 1,
                "improved": 0,
                "accepted": 0,
                "ignored": 0,
                "neutral": 1,
                "missing": 0,
            },
            "decision": {
                "confidence": "high",
                "recommended_action": "fix blocking cases before shipping",
                "scope": "structural checks only",
                "diagnosis": "Candidate lost required structure; fix blocking cases before shipping.",
            },
            "artifacts": {
                "html": ".redline/reports/eval.html",
                "comment": ".redline/reports/eval-comment.md",
            },
            "diffs": [
                {
                    "case_id": "support/case_001",
                    "suite_case_id": "case_001",
                    "suite": "suites/support.redline-suite.json",
                    "status": "regression",
                    "owner": "@support-team",
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return JSON with owner and priority.",
                    "reasons": ["candidate lost valid JSON format"],
                },
                {
                    "case_id": "billing/case_002",
                    "suite_case_id": "case_002",
                    "suite": "suites/billing.redline-suite.json",
                    "status": "changed",
                    "owner": "@billing-team",
                    "prompt": "Write a refund reply.",
                    "reasons": ["content changed substantially"],
                },
                {
                    "case_id": "case_003",
                    "status": "neutral",
                    "prompt": "Hello",
                    "reasons": ["no high-signal behavioral change detected"],
                },
            ],
        }

        comment = format_pr_comment(result, title="redline eval")

        self.assertIn("## redline eval", comment)
        self.assertIn("**Regression:** 1", comment)
        self.assertIn("**Changed:** 1", comment)
        self.assertIn("**Action:** fix blocking cases before shipping", comment)
        self.assertIn("**Diagnosis:** Candidate lost required structure; fix blocking cases before shipping.", comment)
        self.assertIn("### Owners", comment)
        self.assertIn(
            '- @support-team: 1 blocking case (1 owned case) · first review: `redline mark suites/support.redline-suite.json case_001 --status expected --note "intentional change"`',
            comment,
        )
        self.assertIn(
            '- @billing-team: 1 changed case (1 owned case) · first review: `redline mark suites/billing.redline-suite.json case_002 --status expected --note "intentional change"`',
            comment,
        )
        self.assertIn("**REGRESSION** `support/case_001` owner @support-team [high/structural]", comment)
        self.assertIn("**CHANGED** `billing/case_002` owner @billing-team", comment)
        self.assertIn("redline mark suites/support.redline-suite.json case_001", comment)
        self.assertIn("PR comment: `.redline/reports/eval-comment.md`", comment)
        self.assertNotIn("case_003", comment)

    def test_slack_report_is_block_kit_json_for_review_channels(self) -> None:
        result = {
            "suite": "redline-prompts.json",
            "summary": {
                "cases": 3,
                "regression": 1,
                "changed": 1,
                "improved": 0,
                "accepted": 0,
                "ignored": 0,
                "neutral": 1,
                "missing": 0,
            },
            "decision": {
                "confidence": "high",
                "recommended_action": "fix blocking cases before shipping",
                "scope": "structural checks only",
                "diagnosis": "Candidate lost required structure; fix blocking cases before shipping.",
            },
            "artifacts": {
                "html": ".redline/reports/eval.html",
                "slack": ".redline/reports/eval.slack.json",
            },
            "diffs": [
                {
                    "case_id": "support/case_001",
                    "suite_case_id": "case_001",
                    "suite": "suites/support.redline-suite.json",
                    "status": "regression",
                    "owner": "@support-team",
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return JSON with owner and priority.",
                    "reasons": ["candidate lost valid JSON format"],
                },
                {
                    "case_id": "billing/case_002",
                    "status": "changed",
                    "owner": "@billing-team",
                    "prompt": "Write a refund reply.",
                    "reasons": ["content changed substantially"],
                },
                {
                    "case_id": "case_003",
                    "status": "neutral",
                    "prompt": "Hello",
                    "reasons": ["no high-signal behavioral change detected"],
                },
            ],
        }

        payload = format_slack_report(result, title="redline eval", max_cases=1)
        body = json.dumps(payload)

        self.assertEqual(payload["text"], "redline eval: Regression: 1 | Changed: 1 | Neutral: 1")
        self.assertEqual(payload["blocks"][0]["type"], "header")
        self.assertIn("fix blocking cases before shipping", body)
        self.assertIn("structural checks only", body)
        self.assertIn("Candidate lost required structure", body)
        self.assertIn("candidate lost valid JSON format", body)
        self.assertIn("@support-team", body)
        self.assertIn("1 more changed or blocking case", body)
        self.assertIn(".redline/reports/eval.html", body)
        self.assertNotIn("case_003", body)


if __name__ == "__main__":
    unittest.main()
