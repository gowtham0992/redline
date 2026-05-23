import unittest

from redline.diff import classify_change, compare_suite_to_candidate
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
        self.assertEqual(result["diffs"][0]["status"], "missing")
        self.assertEqual(result["diffs"][0]["baseline_response"], "30 days")
        self.assertIsNone(result["diffs"][0]["candidate_response"])

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
        self.assertEqual(result["diffs"][0]["candidate_response"], '{"ok": true}')


if __name__ == "__main__":
    unittest.main()
