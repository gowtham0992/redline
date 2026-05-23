import unittest

from redline.compare import compare_reports, format_report_comparison


class CompareTests(unittest.TestCase):
    def test_compare_reports_marks_worse_and_resolved_cases(self) -> None:
        previous = {
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "changed",
                    "prompt": "Return JSON",
                    "reasons": ["content changed"],
                },
                {
                    "case_id": "case_002",
                    "status": "regression",
                    "prompt": "Refund policy",
                    "reasons": ["candidate missing numbers: 30"],
                },
            ]
        }
        current = {
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "prompt": "Return JSON",
                    "reasons": ["candidate lost valid JSON format"],
                },
                {
                    "case_id": "case_002",
                    "status": "neutral",
                    "prompt": "Refund policy",
                    "reasons": ["no high-signal behavioral change detected"],
                },
            ]
        }

        result = compare_reports(previous, current)

        self.assertEqual(result["summary"]["worse"], 1)
        self.assertEqual(result["summary"]["resolved"], 1)
        self.assertEqual(result["changes"][0]["direction"], "worse")
        self.assertEqual(result["changes"][1]["direction"], "resolved")

    def test_format_report_comparison_prints_notable_changes(self) -> None:
        result = {
            "previous": "before.json",
            "current": "after.json",
            "summary": {
                "cases": 1,
                "worse": 1,
                "better": 0,
                "new": 0,
                "resolved": 0,
                "removed": 0,
                "unchanged": 0,
                "changed": 0,
            },
            "changes": [
                {
                    "case_id": "case_001",
                    "direction": "worse",
                    "previous_status": "changed",
                    "current_status": "regression",
                    "prompt": "Return JSON",
                    "reason": "candidate lost valid JSON format",
                }
            ],
        }

        text = format_report_comparison(result)

        self.assertIn("redline compare", text)
        self.assertIn("Previous: before.json", text)
        self.assertIn("Worse:     1", text)
        self.assertIn("WORSE    case_001: changed -> regression", text)


if __name__ == "__main__":
    unittest.main()
