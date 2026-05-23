import json
import tempfile
import unittest
from pathlib import Path

from redline.io import write_json, write_text
from redline.reports import format_markdown_report


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
                    "prompt": "Return JSON",
                    "reasons": ["candidate lost valid JSON format"],
                }
            ],
        }

        report = format_markdown_report(result, title="redline eval")

        self.assertIn("# redline eval", report)
        self.assertIn("| Regression | 1 |", report)
        self.assertIn("candidate lost valid JSON format", report)

    def test_report_files_create_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "nested" / "report.json", {"ok": True})
            write_text(root / "nested" / "report.md", "# ok\n")

            self.assertEqual(json.loads((root / "nested" / "report.json").read_text()), {"ok": True})
            self.assertEqual((root / "nested" / "report.md").read_text(), "# ok\n")


if __name__ == "__main__":
    unittest.main()
