import unittest
from unittest.mock import patch

from redline.features import extract_features
from redline.io import LogRecord
from redline.suite import add_suite_case, build_suite


class SuiteTests(unittest.TestCase):
    def test_build_suite_groups_behavioral_clusters(self) -> None:
        records = [
            LogRecord(1, "Return JSON for Ada", '{"name":"Ada"}', {}),
            LogRecord(2, "Return JSON for Bob", '{"name":"Bob"}', {}),
            LogRecord(3, "Summarize in bullets", "- one\n- two", {}),
        ]

        suite = build_suite(
            records,
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        self.assertEqual(suite["summary"]["records_seen"], 3)
        self.assertEqual(suite["summary"]["cases"], 2)
        self.assertEqual(suite["summary"]["clusters"], 2)
        self.assertTrue(all("baseline_response" in case for case in suite["cases"]))

    def test_suite_features_include_entities(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return support owner", "Ada owns ACME support", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        self.assertIn("Ada", suite["cases"][0]["features"]["entities"])
        self.assertIn("ACME", suite["cases"][0]["features"]["entities"])

    def test_clusters_include_failure_patterns(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON for Ada", "not json", {}),
                LogRecord(2, "Show CSV table", "name,status\nAda,active", {}),
                LogRecord(3, "Answer the support question", "", {}),
                LogRecord(4, "Answer the policy question", "Sorry, I can't provide that.", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        patterns = {
            pattern
            for cluster in suite["clusters"]
            for pattern in cluster["failure_patterns"]
        }

        self.assertIn("invalid_json_for_json_prompt", patterns)
        self.assertIn("missing_table_for_table_prompt", patterns)
        self.assertIn("empty_response", patterns)
        self.assertIn("refusal_response", patterns)

    def test_suite_prioritizes_high_risk_clusters_when_budget_is_tight(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "General prompt A", "ok", {}),
                LogRecord(2, "General prompt B", "ok", {}),
                LogRecord(3, "General prompt C", "ok", {}),
                LogRecord(4, "Return JSON for Ada", "not json", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=1,
        )

        self.assertEqual(suite["cases"][0]["prompt"], "Return JSON for Ada")
        self.assertEqual(suite["clusters"][0]["risk"], "high")

    def test_build_suite_extracts_features_once_per_record(self) -> None:
        records = [
            LogRecord(1, "Return JSON for Ada", '{"name":"Ada"}', {}),
            LogRecord(2, "Summarize in bullets", "- one\n- two", {}),
            LogRecord(3, "Answer", "plain text", {}),
        ]

        with patch("redline.suite.extract_features", wraps=extract_features) as wrapped:
            build_suite(records, source="memory", input_field="prompt", output_field="response")

        self.assertEqual(wrapped.call_count, len(records))

    def test_build_suite_can_include_all_records(self) -> None:
        records = [
            LogRecord(1, "Return JSON for Ada", '{"name":"Ada"}', {}),
            LogRecord(2, "Return JSON for Bob", '{"name":"Bob"}', {}),
            LogRecord(3, "Return JSON for Cy", '{"name":"Cy"}', {}),
        ]

        suite = build_suite(
            records,
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=1,
            all_cases=True,
        )

        self.assertEqual(suite["summary"]["cases"], 3)
        self.assertEqual(suite["summary"]["max_cases"], 3)
        self.assertEqual(suite["summary"]["selection"], "all")
        self.assertEqual([case["source_line"] for case in suite["cases"]], [1, 2, 3])

    def test_add_suite_case_pins_manual_case(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        case = add_suite_case(
            suite,
            prompt="Always mention the refund URL",
            baseline_response="Refund policy: https://example.com/refunds",
            note="critical policy edge case",
        )

        self.assertEqual(suite["summary"]["cases"], 2)
        self.assertEqual(suite["summary"]["pinned_cases"], 1)
        self.assertEqual(case["source"], "manual")
        self.assertTrue(case["pinned"])
        self.assertEqual(case["note"], "critical policy edge case")
        self.assertIn("https://example.com/refunds", case["features"]["urls"])

    def test_add_suite_case_refuses_duplicate_case_id(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        with self.assertRaisesRegex(ValueError, "case id already exists"):
            add_suite_case(
                suite,
                prompt="Another edge",
                baseline_response="expected",
                case_id=case_id,
            )


if __name__ == "__main__":
    unittest.main()
