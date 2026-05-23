import json
import tempfile
import unittest
from pathlib import Path

from redline.io import write_json, write_text
from redline.reports import format_junit_report, format_markdown_report


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
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "cluster": "structured_json|json|short",
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
        self.assertIn("candidate lost valid JSON format", report)
        self.assertIn("Source: `baseline.jsonl:12`", report)
        self.assertIn("Cluster: `structured_json|json|short`", report)
        self.assertIn("Baseline:", report)
        self.assertIn('{"ok": true}', report)
        self.assertIn("Candidate:", report)

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
        self.assertIn("candidate lost valid JSON format", report)


if __name__ == "__main__":
    unittest.main()
