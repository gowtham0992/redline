import unittest

from redline.accept import accept_candidate_baseline, expected_case_ids
from redline.io import LogRecord
from redline.judgments import mark_suite_case
from redline.suite import build_suite


class AcceptTests(unittest.TestCase):
    def test_accept_candidate_updates_baseline_and_features(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        mark_suite_case(suite, case_id, status="expected")

        result = accept_candidate_baseline(
            suite,
            [LogRecord(4, "Return JSON", '{"ok": false}', {"case_id": case_id})],
            case_id,
            note="new contract",
        )

        self.assertEqual(result["accepted_response"], '{"ok": false}')
        self.assertEqual(suite["cases"][0]["baseline_response"], '{"ok": false}')
        self.assertEqual(suite["cases"][0]["cluster"], "structured_json|json|short|json:dict:ok")
        self.assertNotIn(case_id, suite.get("judgments", {}))
        self.assertEqual(suite["accepted_baselines"][0]["note"], "new contract")

    def test_accept_candidate_falls_back_to_prompt_match(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        accept_candidate_baseline(
            suite,
            [LogRecord(2, "Return JSON", '{"ok": false}', {})],
            case_id,
        )

        self.assertEqual(suite["cases"][0]["baseline_response"], '{"ok": false}')

    def test_accept_missing_candidate_fails(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        with self.assertRaisesRegex(ValueError, "candidate output not found"):
            accept_candidate_baseline(suite, [], suite["cases"][0]["id"])

    def test_expected_case_ids_returns_only_expected_judgments(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON", '{"ok": true}', {}),
                LogRecord(2, "Classify", "billing", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        expected_id = suite["cases"][0]["id"]
        ignored_id = suite["cases"][1]["id"]
        mark_suite_case(suite, expected_id, status="expected")
        mark_suite_case(suite, ignored_id, status="ignored")

        self.assertEqual(expected_case_ids(suite), [expected_id])


if __name__ == "__main__":
    unittest.main()
