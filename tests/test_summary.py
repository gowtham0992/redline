import unittest
from tempfile import TemporaryDirectory

from redline.io import LogRecord, write_json
from redline.judgments import mark_suite_case
from redline.requirements import add_case_requirement
from redline.summary import (
    format_prompt_manifest_summary,
    format_suite_summary,
    prompt_manifest_summary,
    suite_summary,
)
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
        self.assertEqual(summary["methodology_version"], "behavior-signature-v1")
        self.assertEqual(summary["methodology_name"], "deterministic behavior-signature grouping")
        self.assertEqual(summary["records_seen"], 2)
        self.assertEqual(summary["unique_prompt_response_pairs"], 2)
        self.assertEqual(summary["duplicate_prompt_response_pairs"], 0)
        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["covered_clusters"], 2)
        self.assertEqual(summary["case_coverage"], 1.0)
        self.assertEqual(summary["cluster_coverage"], 1.0)
        self.assertEqual(summary["pinned_cases"], 0)
        self.assertEqual(summary["owned_cases"], 0)
        self.assertEqual(summary["unowned_cases"], 2)
        self.assertEqual(summary["owner_rule_cases"], 0)
        self.assertEqual(summary["unexplained_owner_cases"], 0)
        self.assertIsNone(summary["owner_rule_coverage"])
        self.assertEqual(summary["owners"], {})
        self.assertEqual(summary["accepted_baselines"], 0)
        self.assertEqual(summary["approved_baselines"], 0)
        self.assertEqual(summary["unapproved_baselines"], 0)
        self.assertEqual(summary["requirement_cases"], 1)
        self.assertEqual(summary["judgment_cases"], 1)
        self.assertEqual(summary["explicit_guard_cases"], 1)
        self.assertEqual(summary["explicit_guard_coverage"], 0.5)
        self.assertEqual(summary["suite_readiness"]["score"], 80)
        self.assertEqual(summary["suite_readiness"]["label"], "strong")
        self.assertIn(
            "many cases have requirements or recorded judgments",
            summary["suite_readiness"]["reasons"],
        )
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
        self.assertIn("Methodology:", output)
        self.assertIn("behavior-signature-v1", output)
        self.assertIn("Records seen:", output)
        self.assertIn("Unique pairs:", output)
        self.assertIn("Duplicate pairs:", output)
        self.assertIn("Group coverage:", output)
        self.assertIn("Case coverage:", output)
        self.assertIn("Suite readiness:", output)
        self.assertIn("Readiness scope:        suite health, not model quality or candidate safety", output)
        self.assertIn("Pinned cases:", output)
        self.assertIn("Owned cases:", output)
        self.assertIn("Owner rule coverage:", output)
        self.assertIn("Accepted baselines:", output)
        self.assertIn("Approved baselines:", output)
        self.assertIn("Explicit guard coverage:", output)
        self.assertIn("High-risk groups:", output)
        self.assertIn("Failure-pattern groups:", output)
        self.assertIn("Top groups:", output)
        self.assertIn("Readiness signals:", output)
        self.assertIn("structured JSON prompt -> JSON response", output)

    def test_suite_summary_surfaces_non_ascii_calibration(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Responde en español", "Incluye política de reembolso", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        summary = suite_summary(suite)
        output = format_suite_summary(suite)

        self.assertEqual(summary["non_ascii_records"], 1)
        self.assertIn("Non-ASCII records:      1", output)
        self.assertIn("entity/refusal heuristics are English-oriented", "\n".join(summary["next_steps"]))

    def test_suite_summary_counts_owners(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return billing JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize support ticket", "- one\n- two", {}),
            ],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            owner_rules=[
                {"match": "billing", "owner": "@billing-team"},
                {"match": "support", "owner": "@support-team"},
            ],
        )

        summary = suite_summary(suite)
        output = format_suite_summary(suite)

        self.assertEqual(summary["owned_cases"], 2)
        self.assertEqual(summary["unowned_cases"], 0)
        self.assertEqual(summary["owner_rule_cases"], 2)
        self.assertEqual(summary["unexplained_owner_cases"], 0)
        self.assertEqual(summary["owner_rule_coverage"], 1.0)
        self.assertEqual(summary["owners"], {"@billing-team": 1, "@support-team": 1})
        self.assertEqual(
            summary["top_owners"],
            [
                {"owner": "@billing-team", "cases": 1},
                {"owner": "@support-team", "cases": 1},
            ],
        )
        self.assertIn("Owned cases:            2/2", output)
        self.assertIn("Owner rule coverage:    2/2 (100.0%)", output)
        self.assertIn("Owners:", output)
        self.assertIn("@billing-team", output)
        self.assertIn("@support-team", output)

    def test_suite_summary_counts_approved_baseline_promotions(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return billing JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize support ticket", "- one\n- two", {}),
            ],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["accepted_baselines"] = [
            {"case_id": suite["cases"][0]["id"], "approver": "lead@example.com"},
            {"case_id": suite["cases"][1]["id"], "note": "accepted locally"},
        ]

        summary = suite_summary(suite)
        output = format_suite_summary(suite)

        self.assertEqual(summary["accepted_baselines"], 2)
        self.assertEqual(summary["approved_baselines"], 1)
        self.assertEqual(summary["unapproved_baselines"], 1)
        self.assertIn("Accepted baselines:     2", output)
        self.assertIn("Approved baselines:     1/2", output)
        self.assertIn("Record approvers for accepted baselines before team rollout.", summary["next_steps"])

    def test_prompt_manifest_summary_rolls_up_mapped_suites(self) -> None:
        with TemporaryDirectory() as temp_dir:
            first_suite_path = f"{temp_dir}/triage.redline-suite.json"
            second_suite_path = f"{temp_dir}/refunds.redline-suite.json"
            missing_suite_path = f"{temp_dir}/missing.redline-suite.json"
            first_suite = build_suite(
                [
                    LogRecord(1, "Return billing JSON", '{"ok": true}', {}),
                    LogRecord(2, "Summarize support ticket", "- one\n- two", {}),
                ],
                source="logs/triage.jsonl",
                input_field="prompt",
                output_field="response",
                max_cases=10,
                owner="@support-team",
            )
            add_case_requirement(first_suite, first_suite["cases"][0]["id"], include=["ok"])
            second_suite = build_suite(
                [LogRecord(1, "Route refund for José", "Envíalo a Billing Ops", {})],
                source="logs/refunds.jsonl",
                input_field="prompt",
                output_field="response",
                max_cases=10,
            )
            write_json(first_suite_path, first_suite)
            write_json(second_suite_path, second_suite)
            manifest = {
                "schema": "redline-prompt-manifest-v1",
                "root": "prompts",
                "suite_dir": "suites",
                "prompts": [
                    {"id": "support/triage", "path": "prompts/support/triage.txt", "suite": first_suite_path},
                    {"id": "billing/refunds", "path": "prompts/billing/refunds.txt", "suite": second_suite_path},
                    {"id": "missing", "path": "prompts/missing.txt", "suite": missing_suite_path},
                ],
            }

            summary = prompt_manifest_summary(manifest, manifest_path="redline-prompts.json")
            output = format_prompt_manifest_summary(summary)

        self.assertEqual(summary["status"], "missing_suites")
        self.assertEqual(summary["prompt_count"], 3)
        self.assertEqual(summary["suite_count"], 2)
        self.assertEqual(summary["missing_suite_count"], 1)
        self.assertEqual(summary["cases"], 3)
        self.assertEqual(summary["owned_cases"], 2)
        self.assertEqual(summary["unowned_cases"], 1)
        self.assertEqual(summary["owner_rule_cases"], 0)
        self.assertEqual(summary["unexplained_owner_cases"], 2)
        self.assertEqual(summary["requirements"], 1)
        self.assertEqual(summary["non_ascii_records"], 1)
        self.assertEqual(summary["explicit_guard_cases"], 1)
        self.assertAlmostEqual(summary["explicit_guard_coverage"], 1 / 3)
        self.assertEqual(summary["owners"], {"@support-team": 2})
        self.assertIn("Prompt manifest:", output)
        self.assertIn("Suites ready:           2/3", output)
        self.assertIn("Explicit guard coverage: 1/3 (33.3%)", output)
        self.assertIn("Non-ASCII records:      1", output)
        self.assertIn("Owner rule coverage:    0/2 (0.0%)", output)
        self.assertIn("Prompt suites:", output)
        self.assertIn("READY   support/triage", output)
        self.assertIn("guards=1", output)
        self.assertIn("MISSING missing", output)
        self.assertIn("Build missing suite:", output)
        self.assertIn("Review non-English cases manually", output)

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
        output = format_suite_summary(suite, suite_path="redline-suite.json")

        self.assertEqual(summary["cases"], 1)
        self.assertEqual(summary["covered_clusters"], 1)
        self.assertEqual(summary["clusters"], 2)
        self.assertEqual(summary["case_coverage"], 0.5)
        self.assertEqual(summary["cluster_coverage"], 0.5)
        self.assertEqual(summary["suite_readiness"]["label"], "needs_work")
        self.assertIn("Increase --max-cases", summary["next_steps"][0])
        self.assertIn("redline suite add redline-suite.json --prompt-file", output)
        self.assertIn("Group coverage:         1/2 (50.0%)", output)
        self.assertIn("Next:", output)


if __name__ == "__main__":
    unittest.main()
