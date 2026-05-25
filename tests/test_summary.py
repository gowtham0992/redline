import unittest

from redline.io import LogRecord
from redline.judgments import mark_suite_case
from redline.requirements import add_case_requirement
from redline.summary import format_suite_summary, suite_summary
from redline.suite import build_suite


class SummaryTests(unittest.TestCase):
    def test_suite_summary_counts_cases_clusters_and_judgments(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize", "- one\n- two", {}),
            ],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        mark_suite_case(suite, case_id, status="expected")
        add_case_requirement(suite, case_id, include=["ok"])

        summary = suite_summary(suite)

        self.assertEqual(summary["source"], "logs/baseline.jsonl")
        self.assertEqual(summary["selection"], "representative")
        self.assertEqual(summary["records_seen"], 2)
        self.assertEqual(summary["unique_prompt_response_pairs"], 2)
        self.assertEqual(summary["duplicate_prompt_response_pairs"], 0)
        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["covered_clusters"], 2)
        self.assertEqual(summary["case_coverage"], 1.0)
        self.assertEqual(summary["cluster_coverage"], 1.0)
        self.assertEqual(summary["pinned_cases"], 0)
        self.assertEqual(summary["judgments"], {"expected": 1})
        self.assertEqual(summary["requirements"], 1)
        self.assertEqual(summary["failure_pattern_clusters"], 0)
        self.assertEqual(
            summary["top_clusters"][0]["behavior"],
            "structured JSON prompt -> JSON response (short; JSON dict keys: ok)",
        )

    def test_suite_summary_counts_failure_pattern_clusters(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", "not json", {})],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        summary = suite_summary(suite)

        self.assertEqual(summary["failure_pattern_clusters"], 1)

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
        self.assertIn("Source:", output)
        self.assertIn("Selection:", output)
        self.assertIn("Records seen:", output)
        self.assertIn("Unique pairs:", output)
        self.assertIn("Duplicate pairs:", output)
        self.assertIn("Cluster coverage:", output)
        self.assertIn("Case coverage:", output)
        self.assertIn("Pinned cases:", output)
        self.assertIn("High-risk clusters:", output)
        self.assertIn("Failure-pattern clusters:", output)
        self.assertIn("Top clusters:", output)
        self.assertIn("structured JSON prompt -> JSON response", output)

    def test_suite_summary_recommends_more_coverage_when_budget_is_tight(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize", "- one\n- two", {}),
            ],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=1,
        )

        summary = suite_summary(suite)
        output = format_suite_summary(suite)

        self.assertEqual(summary["cases"], 1)
        self.assertEqual(summary["covered_clusters"], 1)
        self.assertEqual(summary["clusters"], 2)
        self.assertEqual(summary["case_coverage"], 0.5)
        self.assertEqual(summary["cluster_coverage"], 0.5)
        self.assertIn("Increase --max-cases", summary["next_steps"][0])
        self.assertIn("Cluster coverage:       1/2 (50.0%)", output)
        self.assertIn("Next:", output)


if __name__ == "__main__":
    unittest.main()
