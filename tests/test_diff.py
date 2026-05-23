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


if __name__ == "__main__":
    unittest.main()
