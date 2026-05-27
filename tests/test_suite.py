import json
import unittest
from pathlib import Path
from unittest.mock import patch

from redline.features import extract_features
from redline.io import LogRecord
from redline.suite import SUITE_SCHEMA_URL, add_suite_case, build_suite


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
        self.assertEqual(suite["$schema"], SUITE_SCHEMA_URL)
        self.assertEqual(suite["summary"]["unique_prompt_response_pairs"], 3)
        self.assertEqual(suite["summary"]["duplicate_prompt_response_pairs"], 0)
        self.assertEqual(suite["summary"]["cases"], 2)
        self.assertEqual(suite["summary"]["clusters"], 2)
        self.assertEqual(suite["summary"]["high_risk_clusters"], 0)
        self.assertEqual(suite["summary"]["medium_risk_clusters"], 0)
        self.assertEqual(suite["summary"]["prompt_diversity_cases"], 0)
        self.assertTrue(all("baseline_response" in case for case in suite["cases"]))
        self.assertTrue(all(len(case["content_hash"]) == 64 for case in suite["cases"]))
        self.assertTrue(all(case["selection_reason"] == "cluster_representative" for case in suite["cases"]))
        self.assertTrue(all(case["cluster_risk"] == "low" for case in suite["cases"]))

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

    def test_suite_schema_documents_generated_suite_fields(self) -> None:
        schema = json.loads(Path("redline-suite.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], SUITE_SCHEMA_URL)
        self.assertIn("Portable prompt-response regression suite", schema["description"])
        for key in ("summary", "clusters", "cases"):
            self.assertIn(key, schema["properties"])
        case_properties = schema["properties"]["cases"]["items"]["properties"]
        self.assertIn("selection_reason", case_properties)
        self.assertIn("cluster_risk", case_properties)
        self.assertIn("owner", case_properties)
        self.assertIn("owner_rule", case_properties)
        self.assertIn("owned_cases", schema["properties"]["summary"]["properties"])
        self.assertIn("prompt_diversity_cases", schema["properties"]["summary"]["properties"])
        self.assertIn("non_ascii_records", schema["properties"]["summary"]["properties"])

    def test_build_suite_assigns_case_owners_from_rules(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Route billing refund", "Billing Ops handles refunds.", {}),
                LogRecord(2, "Route security alert", "Security Ops handles alerts.", {}),
            ],
            source="logs/support.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            all_cases=True,
            owner_rules=[
                {"match": "billing", "owner": "@billing-team", "field": "prompt"},
                {"match": "security", "owner": "@security-team"},
            ],
        )

        owners = {case["prompt"]: case.get("owner") for case in suite["cases"]}
        owner_rules = {case["prompt"]: case.get("owner_rule") for case in suite["cases"]}
        self.assertEqual(owners["Route billing refund"], "@billing-team")
        self.assertEqual(owners["Route security alert"], "@security-team")
        self.assertEqual(owner_rules["Route billing refund"], {"match": "billing", "field": "prompt"})
        self.assertEqual(owner_rules["Route security alert"], {"match": "security", "field": "any"})
        self.assertEqual(suite["summary"]["owned_cases"], 2)

    def test_build_suite_owner_flag_overrides_owner_rules(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Route billing refund", "Billing Ops handles refunds.", {})],
            source="logs/support.jsonl",
            input_field="prompt",
            output_field="response",
            owner="@ai-platform",
            owner_rules={"billing": "@billing-team"},
        )

        self.assertEqual(suite["cases"][0]["owner"], "@ai-platform")
        self.assertNotIn("owner_rule", suite["cases"][0])
        self.assertEqual(suite["summary"]["owned_cases"], 1)

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
        self.assertEqual(suite["cases"][0]["cluster_risk"], "high")
        self.assertEqual(suite["cases"][0]["selection_reason"], "cluster_representative")
        self.assertEqual(suite["clusters"][0]["risk"], "high")
        self.assertEqual(suite["summary"]["high_risk_clusters"], 1)

    def test_build_suite_selects_high_variance_edge_cases_when_budget_allows(self) -> None:
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

        reasons = {case["selection_reason"] for case in suite["cases"]}
        self.assertIn("cluster_representative", reasons)
        self.assertIn("high_variance_short_edge", reasons)
        self.assertIn("high_variance_long_edge", reasons)
        self.assertEqual(suite["summary"]["medium_risk_clusters"], 1)

    def test_build_suite_selects_prompt_diversity_edges_for_large_clusters(self) -> None:
        records = [
            LogRecord(index, f"Summarize support ticket {index} for account {index}", "same shape answer", {})
            for index in range(1, 7)
        ]

        suite = build_suite(
            records,
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=3,
        )

        reasons = [case["selection_reason"] for case in suite["cases"]]
        self.assertEqual(suite["summary"]["clusters"], 1)
        self.assertEqual(suite["summary"]["cases"], 3)
        self.assertEqual(reasons.count("cluster_representative"), 1)
        self.assertEqual(reasons.count("prompt_diversity_edge"), 2)
        self.assertEqual(suite["summary"]["prompt_diversity_cases"], 2)

    def test_build_suite_spreads_prompt_diversity_budget_across_large_clusters(self) -> None:
        records = [
            LogRecord(
                index,
                f"Summarize account {index} " + ("detail " * index),
                "same shape answer",
                {},
            )
            for index in range(1, 21)
        ]

        suite = build_suite(
            records,
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=7,
        )

        diversity_lines = [
            case["source_line"]
            for case in suite["cases"]
            if case["selection_reason"] == "prompt_diversity_edge"
        ]
        self.assertEqual(suite["summary"]["clusters"], 1)
        self.assertEqual(suite["summary"]["cases"], 7)
        self.assertEqual(suite["summary"]["prompt_diversity_cases"], 6)
        self.assertEqual(len(set(diversity_lines)), 6)
        self.assertTrue(any(1 < line < 20 for line in diversity_lines))

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
        self.assertEqual({case["selection_reason"] for case in suite["cases"]}, {"all_cases"})

    def test_build_suite_skips_exact_duplicate_prompt_response_pairs(self) -> None:
        records = [
            LogRecord(1, "Return JSON for Ada", '{"name":"Ada"}', {}),
            LogRecord(2, "Return JSON for Ada", '{"name":"Ada"}', {}),
            LogRecord(3, "Summarize in bullets", "- one\n- two", {}),
        ]

        suite = build_suite(
            records,
            source="memory",
            input_field="prompt",
            output_field="response",
            all_cases=True,
        )

        self.assertEqual(suite["summary"]["records_seen"], 3)
        self.assertEqual(suite["summary"]["unique_prompt_response_pairs"], 2)
        self.assertEqual(suite["summary"]["duplicate_prompt_response_pairs"], 1)
        self.assertEqual(suite["summary"]["cases"], 2)
        self.assertEqual(suite["summary"]["max_cases"], 2)
        self.assertEqual([case["source_line"] for case in suite["cases"]], [1, 3])

    def test_build_suite_counts_non_ascii_records(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Responde en español", "Incluye política de reembolso", {}),
                LogRecord(2, "Return JSON", '{"ok": true}', {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            all_cases=True,
        )

        self.assertEqual(suite["summary"]["non_ascii_records"], 1)

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
        self.assertEqual(case["selection_reason"], "manual_pin")
        self.assertEqual(case["cluster_risk"], "low")
        self.assertEqual(case["note"], "critical policy edge case")
        self.assertEqual(len(case["content_hash"]), 64)
        self.assertIn("https://example.com/refunds", case["features"]["urls"])

    def test_add_suite_case_can_assign_owner(self) -> None:
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
            owner="@billing-team",
        )

        self.assertEqual(case["owner"], "@billing-team")
        self.assertEqual(suite["summary"]["owned_cases"], 1)

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

    def test_add_suite_case_refuses_duplicate_prompt_response_pair(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        existing_id = suite["cases"][0]["id"]

        with self.assertRaisesRegex(ValueError, f"already covered by {existing_id}"):
            add_suite_case(
                suite,
                prompt="Return JSON",
                baseline_response='{"ok": true}',
            )

    def test_add_suite_case_can_allow_duplicate_prompt_response_pair(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        case = add_suite_case(
            suite,
            prompt="Return JSON",
            baseline_response='{"ok": true}',
            allow_duplicate=True,
        )

        self.assertEqual(suite["summary"]["cases"], 2)
        self.assertNotEqual(case["id"], suite["cases"][0]["id"])


if __name__ == "__main__":
    unittest.main()
