import unittest

from redline.diff import compare_suite_to_candidate
from redline.io import LogRecord
from redline.judgments import clear_suite_case_judgment, mark_suite_case
from redline.suite import build_suite


class JudgmentTests(unittest.TestCase):
    def test_expected_judgment_accepts_regression(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        mark_suite_case(suite, case_id, status="expected", note="intentional format change")

        result = compare_suite_to_candidate(
            suite,
            [LogRecord(1, "Return JSON", "ok", {})],
        )

        self.assertEqual(result["summary"]["regression"], 0)
        self.assertEqual(result["summary"]["accepted"], 1)
        self.assertEqual(result["diffs"][0]["status"], "accepted")
        self.assertIn("accepted by suite judgment", result["diffs"][0]["reasons"][0])

    def test_ignored_judgment_suppresses_missing_candidate(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        mark_suite_case(suite, case_id, status="ignored")

        result = compare_suite_to_candidate(suite, [])

        self.assertEqual(result["summary"]["missing"], 0)
        self.assertEqual(result["summary"]["ignored"], 1)

    def test_clear_judgment_removes_case_metadata(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        mark_suite_case(suite, case_id, status="ignored")

        self.assertTrue(clear_suite_case_judgment(suite, case_id))
        self.assertFalse(clear_suite_case_judgment(suite, case_id))

    def test_mark_unknown_case_fails(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        with self.assertRaises(ValueError):
            mark_suite_case(suite, "missing", status="expected")


if __name__ == "__main__":
    unittest.main()
