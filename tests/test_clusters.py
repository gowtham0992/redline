import unittest

from redline.clusters import cluster_report, format_cluster_report
from redline.io import LogRecord
from redline.suite import build_suite


class ClusterReportTests(unittest.TestCase):
    def test_cluster_report_counts_behavioral_clusters(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON for Ada", '{"name":"Ada"}', {}),
                LogRecord(2, "Return JSON for Bob", '{"name":"Bob"}', {}),
                LogRecord(3, "Summarize", "- one\n- two", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = cluster_report(suite)

        self.assertEqual(report["records_seen"], 3)
        self.assertEqual(report["unique_prompt_response_pairs"], 3)
        self.assertEqual(report["duplicate_prompt_response_pairs"], 0)
        self.assertEqual(report["clusters"], 2)
        self.assertEqual(report["suggested_cases"], 2)
        self.assertEqual(report["high_variance_clusters"], 0)
        self.assertEqual(report["failure_pattern_clusters"], 0)
        self.assertEqual(report["high_risk_clusters"], 0)
        self.assertEqual(report["top_clusters"][0]["size"], 2)
        self.assertEqual(report["top_clusters"][0]["risk"], "low")

    def test_cluster_report_surfaces_failure_patterns(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", "not json", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = cluster_report(suite)

        self.assertEqual(report["failure_pattern_clusters"], 1)
        self.assertEqual(report["high_risk_clusters"], 1)
        self.assertEqual(report["top_clusters"][0]["risk"], "high")
        self.assertEqual(
            report["top_clusters"][0]["failure_patterns"],
            ["invalid_json_for_json_prompt"],
        )

    def test_format_cluster_report_is_readable(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        output = format_cluster_report(suite)

        self.assertIn("redline cluster", output)
        self.assertIn("Identified 1 behavioral clusters from 1 unique pairs", output)
        self.assertIn("Records seen: 1  Duplicate pairs: 0", output)
        self.assertIn("High-risk clusters: 0", output)
        self.assertIn("Failure-pattern clusters: 0", output)
        self.assertIn("Suggested eval suite: 1 representative cases.", output)
        self.assertIn("RISK", output)
        self.assertIn("FLAGS", output)
        self.assertIn("SIGNATURE", output)

    def test_cluster_report_marks_high_variance_as_medium_risk(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Summarize ticket A", "short", {}),
                LogRecord(2, "Summarize ticket B", "medium length response", {}),
                LogRecord(
                    3,
                    "Summarize ticket C",
                    "this response has enough extra words to create a much longer answer",
                    {},
                ),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = cluster_report(suite)

        self.assertEqual(report["high_variance_clusters"], 1)
        self.assertEqual(report["high_risk_clusters"], 0)
        self.assertEqual(report["top_clusters"][0]["risk"], "medium")


if __name__ == "__main__":
    unittest.main()
