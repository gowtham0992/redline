import unittest

from redline.diff import (
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

        self.assertEqual(result["summary"]["missing"], 1)
        self.assertEqual(result["decision"]["confidence"], "high")
        self.assertEqual(result["decision"]["recommended_action"], "fix blocking cases before shipping")
        self.assertEqual(result["diffs"][0]["status"], "missing")
        self.assertEqual(result["diffs"][0]["baseline_response"], "30 days")
        self.assertIsNone(result["diffs"][0]["candidate_response"])
        self.assertEqual(result["diffs"][0]["source"], "memory")
        self.assertEqual(result["diffs"][0]["source_line"], 1)
        self.assertIn("cluster", result["diffs"][0])

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
            },
            "diffs": [],
        }

        report = format_report(result)

        self.assertIn("Confidence: MEDIUM", report)
        self.assertIn("Recommended action: no structural blockers detected; review semantic risks before shipping", report)
        self.assertIn("Scope: structural checks only", report)

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
            },
            "diffs": [
                {
                    "case_id": "case_001",
                    "status": "regression",
                    "source": "baseline.jsonl",
                    "source_line": 12,
                    "prompt": "Return JSON",
                    "reasons": ["candidate lost valid JSON format"],
                },
                {
                    "case_id": "case_002",
                    "status": "changed",
                    "prompt": "Route this ticket",
                    "reasons": ["short answer changed"],
                },
            ],
        }

        report = format_compact_report(result, title="redline eval")

        self.assertIn("redline eval: cases=2 regression=1 changed=1", report)
        self.assertIn("Confidence: HIGH | fix blocking cases before shipping", report)
        self.assertIn("Scope: structural checks only", report)
        self.assertIn("REGRESSION case_001 [baseline.jsonl:12]: candidate lost valid JSON format", report)
        self.assertIn("CHANGED    case_002: short answer changed", report)


if __name__ == "__main__":
    unittest.main()
