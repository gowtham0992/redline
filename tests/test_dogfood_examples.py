import unittest

from redline.diff import compare_suite_to_candidate
from redline.io import read_jsonl_records
from redline.suite import build_suite


class DogfoodExampleTests(unittest.TestCase):
    def test_dogfood_logs_cover_multiple_regression_types(self) -> None:
        baseline = read_jsonl_records("examples/dogfood_baseline.jsonl", "prompt", "response")
        candidate = read_jsonl_records("examples/dogfood_candidate.jsonl", "prompt", "response")
        suite = build_suite(
            baseline,
            source="examples/dogfood_baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=20,
        )

        result = compare_suite_to_candidate(suite, candidate)
        reasons = "\n".join(reason for item in result["diffs"] for reason in item["reasons"])

        self.assertEqual(result["summary"]["cases"], 10)
        self.assertGreaterEqual(result["summary"]["regression"], 8)
        self.assertEqual(result["summary"]["neutral"], 1)
        self.assertIn("candidate missing JSON keys", reasons)
        self.assertIn("candidate newly refuses", reasons)
        self.assertIn("candidate lost markdown table structure", reasons)
        self.assertIn("candidate lost code block structure", reasons)
        self.assertIn("candidate lost numbered list structure", reasons)
        self.assertIn("candidate became empty", reasons)

    def test_public_dogfood_fixture_catches_visible_regressions(self) -> None:
        baseline = read_jsonl_records("examples/public_dogfood_baseline.jsonl", "prompt", "response")
        candidate = read_jsonl_records("examples/public_dogfood_candidate.jsonl", "prompt", "response")
        suite = build_suite(
            baseline,
            source="examples/public_dogfood_baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=20,
            all_cases=True,
        )

        result = compare_suite_to_candidate(suite, candidate)
        reasons = "\n".join(reason for item in result["diffs"] for reason in item["reasons"])

        self.assertEqual(result["summary"]["cases"], 10)
        self.assertGreaterEqual(result["summary"]["regression"], 9)
        self.assertIn("candidate missing JSON keys", reasons)
        self.assertIn("candidate lost valid JSON format", reasons)
        self.assertIn("candidate lost markdown table structure", reasons)
        self.assertIn("candidate lost code block structure", reasons)
        self.assertIn("candidate lost numbered list structure", reasons)
        self.assertIn("candidate missing URLs", reasons)
        self.assertIn("candidate newly refuses", reasons)
        self.assertIn("candidate became empty", reasons)
        self.assertIn("candidate missing entities", reasons)


if __name__ == "__main__":
    unittest.main()
