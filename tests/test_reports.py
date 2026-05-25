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
            },
            "warnings": ["prompt file prompts/v2.txt is newer than suite"],
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "cluster": "structured_json|json|short",
                    "owner": "@platform-team",
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
        self.assertIn("## Warnings", report)
        self.assertIn("prompt file prompts/v2.txt is newer than suite", report)
        self.assertIn("candidate lost valid JSON format", report)
        self.assertIn("Source: `baseline.jsonl:12`", report)
        self.assertIn("Cluster: `structured_json|json|short`", report)
        self.assertIn("Owner: `@platform-team`", report)
        self.assertIn("Confidence: `high`", report)
        self.assertIn("Signal: `structural`", report)
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
                "rationale": ["1 regression case(s)"],
            },
            "warnings": ["prompt file prompts/v2.txt is newer than suite"],
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "cluster": "structured_json|json|short",
                    "owner": "@platform-team",
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
        self.assertIn("Confidence: high | Signal: structural", report)
        self.assertIn("fix blocking cases before shipping", report)
        self.assertIn("structural checks only", report)
        self.assertIn("<h2>Warnings</h2>", report)
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


if __name__ == "__main__":
    unittest.main()
