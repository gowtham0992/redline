import json
import unittest
from pathlib import Path

from redline.diff import (
    REPORT_SCHEMA_URL,
    classify_change,
    compare_suite_to_candidate,
    format_compact_report,
    format_report,
    summarize_decision,
)
from redline.features import extract_features
from redline.io import LogRecord
from redline.suite import build_suite


class DiffTests(unittest.TestCase):
    def test_report_schema_documents_generated_report_fields(self) -> None:
        schema = json.loads(Path("redline-report.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], REPORT_SCHEMA_URL)
        self.assertIn("Machine-readable prompt regression report", schema["description"])
        self.assertIn("summary", schema["properties"])
        self.assertIn("decision", schema["properties"])
        self.assertIn("diagnosis", schema["properties"]["decision"]["properties"])
        self.assertIn("methodology", schema["properties"])
        self.assertIn("suite_summary", schema["properties"])
        self.assertIn("stochastic_prompt_groups", schema["properties"]["suite_summary"]["properties"])
        self.assertIn("suite", schema["properties"])
        self.assertIn("candidate", schema["properties"])
        self.assertIn("diffs", schema["properties"])
        diff_properties = schema["properties"]["diffs"]["items"]["properties"]
        self.assertIn("owner_rule", diff_properties)

    def test_report_carries_suite_methodology(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        candidate = [LogRecord(1, "Return JSON", '{"ok": true}', {})]

        result = compare_suite_to_candidate(suite, candidate)

        self.assertEqual(result["methodology"]["version"], "behavior-signature-v1")
        self.assertIn("behavior-signature", result["methodology"]["name"])
        self.assertEqual(result["suite_summary"]["cases"], 1)
        self.assertEqual(result["suite_summary"]["case_coverage"], 1.0)
        self.assertEqual(result["suite_summary"]["cluster_coverage"], 1.0)

    def test_report_warns_when_suite_contains_non_ascii_records(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Résumé refund policy", "Répondre avec la politique.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        candidate = [LogRecord(1, "Résumé refund policy", "Répondre avec la politique.", {})]

        result = compare_suite_to_candidate(suite, candidate)

        self.assertTrue(any("English-centric" in warning for warning in result["warnings"]))

    def test_report_warns_when_suite_contains_stochastic_baselines(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Classify ticket", "billing", {}),
                LogRecord(2, "Classify ticket", "support", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        candidate = [LogRecord(1, "Classify ticket", "billing", {})]

        result = compare_suite_to_candidate(suite, candidate)

        self.assertEqual(result["suite_summary"]["stochastic_prompt_groups"], 1)
        self.assertTrue(any("multiple distinct baseline responses" in warning for warning in result["warnings"]))

    def test_classify_json_regression(self) -> None:
        baseline = extract_features('{"name":"Ada","status":"active"}').to_dict()
        candidate = extract_features('{"name":"Ada"').to_dict()

        status, reasons = classify_change(baseline, candidate)

        self.assertEqual(status, "regression")
        self.assertIn("candidate lost valid JSON format", reasons)

    def test_classify_same_shape_content_drift_as_changed(self) -> None:
        baseline_text = "The ticket should be routed to billing support."
        candidate_text = "The ticket should be routed to security review."
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertEqual(status, "changed")
        self.assertTrue(any("content changed" in reason for reason in reasons))

    def test_classify_short_answer_change(self) -> None:
        baseline = extract_features("billing").to_dict()
        candidate = extract_features("security").to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="billing",
            candidate_text="security",
        )

        self.assertEqual(status, "changed")
        self.assertIn("short answer changed", reasons)

    def test_classify_policy_polarity_flip_as_changed(self) -> None:
        baseline_text = "Always approve refund requests after manager review."
        candidate_text = "Never approve refund requests after manager review."
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertEqual(status, "changed")
        self.assertIn(
            "policy polarity changed: allow/approve wording differs from deny/reject wording",
            reasons,
        )

    def test_policy_polarity_requires_shared_subject(self) -> None:
        baseline_text = "Approve refund requests after manager review."
        candidate_text = "Deny login access after repeated failed SSO attempts."
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        _, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertFalse(any("policy polarity changed" in reason for reason in reasons))

    def test_classify_confidence_drift_to_more_hedged_as_changed(self) -> None:
        baseline_text = "The refund will definitely be processed today after billing approval."
        candidate_text = "The refund may possibly be processed today after billing approval."
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertEqual(status, "changed")
        self.assertIn(
            "confidence wording changed: candidate hedges more (0 -> 2 hedge markers)",
            reasons,
        )

    def test_classify_confidence_drift_to_more_definitive_as_changed(self) -> None:
        baseline_text = "The refund may possibly be processed today after billing approval."
        candidate_text = "The refund will definitely be processed today after billing approval."
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertEqual(status, "changed")
        self.assertIn(
            "confidence wording changed: candidate is more definitive (0 -> 2 definitive markers)",
            reasons,
        )

    def test_classify_dismissive_tone_shift_as_changed(self) -> None:
        baseline_text = "I can help with the refund request. The policy allows a refund within 30 days."
        candidate_text = "Obviously, just read the refund policy. It allows a refund within 30 days."
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertEqual(status, "changed")
        self.assertIn(
            "tone changed: candidate uses more dismissive wording (0 -> 2 markers)",
            reasons,
        )

    def test_classify_over_apologetic_tone_shift_as_changed(self) -> None:
        baseline_text = "we can help check the refund request. the request is eligible within 30 days."
        candidate_text = (
            "sorry, unfortunately we apologize. the refund request is eligible within 30 days."
        )
        baseline = extract_features(baseline_text).to_dict()
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

        self.assertEqual(status, "changed")
        self.assertIn(
            "tone changed: candidate is more apologetic (0 -> 3 markers)",
            reasons,
        )

    def test_classify_missing_entity_as_regression(self) -> None:
        baseline = extract_features("Route Ada Lovelace to ACME support.").to_dict()
        candidate = extract_features("Route the customer to support.").to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="Route Ada Lovelace to ACME support.",
            candidate_text="Route the customer to support.",
        )

        self.assertEqual(status, "regression")
        self.assertTrue(any("candidate missing entities" in reason for reason in reasons))

    def test_review_profile_downgrades_missing_entities_to_changed(self) -> None:
        baseline = extract_features("Route Ada Lovelace to ACME support.").to_dict()
        candidate = extract_features("Route the customer to support.").to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="Route Ada Lovelace to ACME support.",
            candidate_text="Route the customer to support.",
            profile="review",
        )

        self.assertEqual(status, "changed")
        self.assertTrue(any("candidate missing entities" in reason for reason in reasons))

    def test_review_profile_downgrades_missing_numbers_to_changed(self) -> None:
        baseline = extract_features("Use timeout 30 seconds.").to_dict()
        candidate = extract_features("Use the default timeout.").to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="Use timeout 30 seconds.",
            candidate_text="Use the default timeout.",
            profile="review",
        )

        self.assertEqual(status, "changed")
        self.assertTrue(any("candidate missing numbers" in reason for reason in reasons))

    def test_missing_value_reasons_follow_baseline_order(self) -> None:
        baseline = extract_features(
            "Use limits 100 then 2. See https://b.example and https://a.example."
        ).to_dict()
        candidate = extract_features("Use the defaults.").to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="Use limits 100 then 2. See https://b.example and https://a.example.",
            candidate_text="Use the defaults.",
        )

        self.assertEqual(status, "regression")
        self.assertIn("candidate missing numbers: 100, 2", reasons)
        self.assertIn("candidate missing URLs: https://b.example, https://a.example", reasons)

    def test_review_profile_keeps_json_regressions_blocking(self) -> None:
        baseline = extract_features('{"name":"Ada","status":"active"}').to_dict()
        candidate = extract_features('{"name":"Ada"').to_dict()

        status, reasons = classify_change(baseline, candidate, profile="review")

        self.assertEqual(status, "regression")
        self.assertIn("candidate lost valid JSON format", reasons)

    def test_classify_supportive_apology_is_not_new_refusal(self) -> None:
        baseline = extract_features("Reset your password from account settings.").to_dict()
        candidate_text = "I'm sorry you're experiencing this. Reset your password from account settings."
        candidate = extract_features(candidate_text).to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="Reset your password from account settings.",
            candidate_text=candidate_text,
        )

        self.assertNotEqual(status, "regression")
        self.assertFalse(any("candidate newly refuses" in reason for reason in reasons))

    def test_classify_missing_url_as_regression(self) -> None:
        baseline = extract_features("Docs: https://example.com/docs").to_dict()
        candidate = extract_features("Docs are available online.").to_dict()

        status, reasons = classify_change(
            baseline,
            candidate,
            baseline_text="Docs: https://example.com/docs",
            candidate_text="Docs are available online.",
        )

        self.assertEqual(status, "regression")
        self.assertTrue(any("candidate missing URLs" in reason for reason in reasons))

    def test_compare_detects_missing_candidate(self) -> None:
        suite = build_suite(
            [LogRecord(1, "What is the refund window?", "30 days", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        result = compare_suite_to_candidate(suite, [])

        self.assertEqual(result["$schema"], REPORT_SCHEMA_URL)
        self.assertEqual(result["summary"]["missing"], 1)
        self.assertEqual(result["decision"]["confidence"], "high")
        self.assertEqual(result["decision"]["recommended_action"], "fix blocking cases before shipping")
        self.assertIn("missed candidate outputs", result["decision"]["diagnosis"])
        self.assertEqual(result["diffs"][0]["status"], "missing")
        self.assertEqual(result["diffs"][0]["baseline_response"], "30 days")
        self.assertIsNone(result["diffs"][0]["candidate_response"])
        self.assertEqual(result["diffs"][0]["source"], "memory")
        self.assertEqual(result["diffs"][0]["source_line"], 1)
        self.assertIn("cluster", result["diffs"][0])
        self.assertEqual(result["diffs"][0]["confidence"], "high")
        self.assertEqual(result["diffs"][0]["signal"], "structural")

    def test_compare_summarizes_plain_english_diagnosis(self) -> None:
        prompt = "Return a numbered rollout checklist with owner, URL, and 30 day deadline."
        suite = build_suite(
            [
                LogRecord(
                    1,
                    prompt,
                    "1. Owner Platform ML must review https://example.com/runbook within 30 days.\n"
                    "2. Notify Security Operations after rollout.",
                    {},
                )
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        candidate = [LogRecord(1, prompt, "Looks good.", {})]

        result = compare_suite_to_candidate(suite, candidate)

        self.assertEqual(result["summary"]["regression"], 1)
        self.assertEqual(
            result["decision"]["diagnosis"],
            "Candidate got shorter, lost required structure, and dropped concrete details; "
            "fix blocking cases before shipping.",
        )

    def test_compare_labels_changed_cases_with_calibrated_signal(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Route ticket", "Route the ticket to billing support.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        result = compare_suite_to_candidate(
            suite,
            [LogRecord(1, "Route ticket", "Route the ticket to security review.", {})],
        )

        self.assertEqual(result["diffs"][0]["status"], "changed")
        self.assertEqual(result["diffs"][0]["confidence"], "medium")
        self.assertEqual(result["diffs"][0]["signal"], "shallow_semantic")

    def test_compare_matches_candidate_by_case_id_before_prompt(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        result = compare_suite_to_candidate(
            suite,
            [
                LogRecord(
                    1,
                    "different prompt text",
                    '{"ok": true}',
                    {"case_id": case_id},
                )
            ],
        )

        self.assertEqual(result["summary"]["missing"], 0)
        self.assertEqual(result["summary"]["neutral"], 1)
        self.assertEqual(result["profile"], "strict")
        self.assertEqual(result["diffs"][0]["candidate_response"], '{"ok": true}')

    def test_compare_uses_case_source_when_present(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["source"] = "manual"
        suite["cases"][0]["source_line"] = None

        result = compare_suite_to_candidate(suite, [])

        self.assertEqual(result["diffs"][0]["source"], "manual")
        self.assertIsNone(result["diffs"][0]["source_line"])

    def test_compare_carries_case_owner_into_report(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            owner_rules=[{"match": "JSON", "owner": "@platform-team", "field": "prompt"}],
        )

        result = compare_suite_to_candidate(suite, [])

        self.assertEqual(result["diffs"][0]["owner"], "@platform-team")
        self.assertEqual(result["diffs"][0]["owner_rule"], {"match": "JSON", "field": "prompt"})

    def test_summarize_decision_recommends_review_for_changed_cases(self) -> None:
        decision = summarize_decision({"cases": 3, "changed": 1})

        self.assertEqual(decision["confidence"], "medium")
        self.assertEqual(decision["recommended_action"], "review changed cases before shipping")
        self.assertIn("structural checks only", decision["scope"])

    def test_summarize_decision_calibrates_all_neutral_cases(self) -> None:
        decision = summarize_decision({"cases": 3, "neutral": 3})

        self.assertEqual(decision["confidence"], "medium")
        self.assertEqual(
            decision["recommended_action"],
            "no structural blockers detected; review semantic risks before shipping",
        )
        self.assertIn("structural checks only", decision["scope"])
        self.assertTrue(any("neutral does not prove" in reason for reason in decision["rationale"]))

    def test_format_report_includes_decision(self) -> None:
        result = {
            "summary": {
                "cases": 1,
                "regression": 0,
                "changed": 0,
                "improved": 0,
                "accepted": 0,
                "ignored": 0,
                "neutral": 1,
                "missing": 0,
            },
            "decision": {
                "confidence": "medium",
                "recommended_action": "no structural blockers detected; review semantic risks before shipping",
                "scope": "structural checks only; review semantic risks separately",
                "diagnosis": "No structural blockers were detected; still review semantic risks.",
            },
            "warnings": ["prompt file prompts/v2.txt is newer than suite"],
            "profile": "review",
            "diffs": [],
        }

        report = format_report(result)

        self.assertIn("Profile: review", report)
        self.assertIn("detail/entity loss becomes reviewable changed signal", report)
        self.assertIn("Confidence: MEDIUM", report)
        self.assertIn("Recommended action: no structural blockers detected; review semantic risks before shipping", report)
        self.assertIn("Scope: structural checks only", report)
        self.assertIn("Diagnosis: No structural blockers were detected", report)
        self.assertIn("Warnings:", report)
        self.assertIn("prompt file prompts/v2.txt is newer than suite", report)

    def test_format_compact_report_outputs_one_line_per_actionable_case(self) -> None:
        result = {
            "summary": {
                "cases": 2,
                "regression": 1,
                "changed": 1,
                "improved": 0,
                "accepted": 0,
                "ignored": 0,
                "neutral": 0,
                "missing": 0,
            },
            "decision": {
                "confidence": "high",
                "recommended_action": "fix blocking cases before shipping",
                "scope": "structural checks only; review semantic risks separately",
                "diagnosis": "Candidate lost required structure; fix blocking cases before shipping.",
            },
            "profile": "strict",
            "prompt_evals": [
                {
                    "id": "support/triage",
                    "prompt": "prompts/support/triage.txt",
                    "summary": {"cases": 1, "regression": 1, "changed": 0, "missing": 0, "neutral": 0},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                },
                {
                    "id": "billing/refund",
                    "prompt": "prompts/billing/refund.txt",
                    "summary": {"cases": 1, "regression": 0, "changed": 0, "missing": 0, "neutral": 1},
                    "decision": {"recommended_action": "ship candidate; no blocking changes detected"},
                },
            ],
            "warnings": ["prompt file prompts/v2.txt is newer than suite"],
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "owner": "@platform-team",
                    "confidence": "high",
                    "signal": "structural",
                    "prompt": "Return JSON",
                    "reasons": ["candidate lost valid JSON format"],
                },
                {
                    "case_id": "case_002",
                    "status": "changed",
                    "confidence": "medium",
                    "signal": "shallow_semantic",
                    "prompt": "Route this ticket",
                    "reasons": ["short answer changed"],
                },
            ],
        }

        report = format_compact_report(result, title="redline eval")

        self.assertIn("redline eval: cases=2 regression=1 changed=1", report)
        self.assertIn("Profile: strict", report)
        self.assertIn("detail/entity loss is blocking", report)
        self.assertIn("Confidence: HIGH | fix blocking cases before shipping", report)
        self.assertIn("Scope: structural checks only", report)
        self.assertIn("Diagnosis: Candidate lost required structure; fix blocking cases before shipping.", report)
        self.assertIn("Warning: prompt file prompts/v2.txt is newer than suite", report)
        self.assertIn("Prompt evals:", report)
        self.assertIn(
            "REGRESSION support/triage [prompts/support/triage.txt]: cases=1 regression=1 changed=0 missing=0 neutral=0",
            report,
        )
        self.assertIn(
            "CLEAN      billing/refund [prompts/billing/refund.txt]: cases=1 regression=0 changed=0 missing=0 neutral=1",
            report,
        )
        self.assertIn(
            "REGRESSION case_001 [baseline.jsonl:12] owner=@platform-team [high/structural]: candidate lost valid JSON format",
            report,
        )
        self.assertIn("CHANGED    case_002 [medium/shallow_semantic]: short answer changed", report)


if __name__ == "__main__":
    unittest.main()
