import unittest

from redline.diff import compare_suite_to_candidate
from redline.io import LogRecord
from redline.requirements import add_case_requirement, clear_case_requirements, requirement_reasons
from redline.suite import build_suite


class RequirementTests(unittest.TestCase):
    def test_add_case_requirement_and_enforce_include_text(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "Refunds are available within 30 days.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        add_case_requirement(suite, case_id, include=["30 days"], note="policy invariant")

        result = compare_suite_to_candidate(
            suite,
            [LogRecord(1, "Refund policy", "Refunds are available.", {})],
        )

        self.assertEqual(result["summary"]["regression"], 1)
        self.assertIn("candidate missing required text: 30 days", result["diffs"][0]["reasons"])

    def test_requirement_reasons_pass_when_text_present(self) -> None:
        reasons = requirement_reasons({"include": ["30 days"]}, "Refunds take 30 days.")

        self.assertEqual(reasons, [])

    def test_clear_case_requirements(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "Refunds are available within 30 days.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        add_case_requirement(suite, case_id, include=["30 days"])

        self.assertTrue(clear_case_requirements(suite, case_id))
        self.assertFalse(clear_case_requirements(suite, case_id))


if __name__ == "__main__":
    unittest.main()
