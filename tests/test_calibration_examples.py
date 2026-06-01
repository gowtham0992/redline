import unittest

from redline.diff import compare_suite_to_candidate
from redline.io import read_jsonl_records
from redline.suite import build_suite


class CalibrationExampleTests(unittest.TestCase):
    def test_calibration_fixture_shows_regression_changed_and_neutral(self) -> None:
        baseline = read_jsonl_records("examples/calibration_baseline.jsonl", "prompt", "response")
        candidate = read_jsonl_records("examples/calibration_candidate.jsonl", "prompt", "response")
        suite = build_suite(
            baseline,
            source="examples/calibration_baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            all_cases=True,
        )

        result = compare_suite_to_candidate(suite, candidate)
        statuses = [item["status"] for item in result["diffs"]]
        reasons = "\n".join(reason for item in result["diffs"] for reason in item["reasons"])

        self.assertEqual(result["summary"]["regression"], 2)
        self.assertEqual(result["summary"]["changed"], 1)
        self.assertEqual(result["summary"]["neutral"], 1)
        self.assertEqual(statuses, ["regression", "regression", "changed", "neutral"])
        self.assertIn("candidate lost valid JSON format", reasons)
        self.assertIn("candidate missing URLs", reasons)
        self.assertIn("tone changed", reasons)
