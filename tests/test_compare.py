import unittest

from redline.compare import (
    compare_reports,
    format_html_comparison,
    format_markdown_comparison,
    format_report_comparison,
    parse_compare_fail_on,
    should_fail_comparison,
)


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

    def test_format_markdown_comparison_prints_summary_and_changes(self) -> None:
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
                    "prompt": "Return `JSON`",
                    "reason": "candidate lost valid JSON format",
                }
            ],
        }

        text = format_markdown_comparison(result)

        self.assertIn("# redline compare", text)
        self.assertIn("| Worse | 1 |", text)
        self.assertIn("Previous: `before.json`", text)
        self.assertIn("Direction: **Worse**", text)
        self.assertIn("Status: `changed` -> `regression`", text)
        self.assertIn("Prompt: ``Return `JSON```", text)

    def test_format_html_comparison_prints_summary_and_escapes_changes(self) -> None:
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
                    "prompt": "<script>alert(1)</script>",
                    "reason": "candidate lost valid JSON format",
                }
            ],
        }

        text = format_html_comparison(result)

        self.assertIn("<title>redline compare</title>", text)
        self.assertIn("Worse", text)
        self.assertIn("case_001", text)
        self.assertIn("changed", text)
        self.assertIn("regression", text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertNotIn("<script>alert(1)</script>", text)

    def test_parse_compare_fail_on_accepts_directions_and_none(self) -> None:
        self.assertEqual(parse_compare_fail_on("worse,new"), {"worse", "new"})
        self.assertEqual(parse_compare_fail_on("none"), set())

    def test_parse_compare_fail_on_rejects_unknown_direction(self) -> None:
        with self.assertRaisesRegex(ValueError, "compare --fail-on"):
            parse_compare_fail_on("regression")

    def test_should_fail_comparison_uses_selected_directions(self) -> None:
        result = {
            "summary": {
                "cases": 2,
                "worse": 0,
                "new": 1,
            }
        }

        self.assertTrue(should_fail_comparison(result, {"new"}))
        self.assertFalse(should_fail_comparison(result, {"worse"}))


if __name__ == "__main__":
    unittest.main()
