import unittest

from redline.io import LogRecord
from redline.judgments import mark_suite_case
from redline.summary import format_suite_summary, suite_summary
from redline.suite import build_suite


class SummaryTests(unittest.TestCase):
    def test_suite_summary_counts_cases_clusters_and_judgments(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize", "- one\n- two", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        mark_suite_case(suite, suite["cases"][0]["id"], status="expected")

        summary = suite_summary(suite)

        self.assertEqual(summary["records_seen"], 2)
        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["judgments"], {"expected": 1})

    def test_format_suite_summary_is_readable(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        output = format_suite_summary(suite)

        self.assertIn("redline summary", output)
        self.assertIn("Records seen:", output)
        self.assertIn("Top clusters:", output)


if __name__ == "__main__":
    unittest.main()
