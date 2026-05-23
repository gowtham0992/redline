import unittest

from redline.cases import format_suite_case_detail, suite_case_detail
from redline.io import LogRecord
from redline.requirements import add_case_requirement
from redline.suite import build_suite


class CaseDetailTests(unittest.TestCase):
    def test_suite_case_detail_returns_case_metadata(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        detail = suite_case_detail(suite, case_id)

        self.assertEqual(detail["id"], case_id)
        self.assertEqual(detail["prompt"], "Return JSON")
        self.assertIn("features", detail)

    def test_suite_case_detail_includes_requirements(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "Refunds are available within 30 days.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        add_case_requirement(suite, case_id, include=["30 days"])

        detail = suite_case_detail(suite, case_id)

        self.assertEqual(detail["requirements"]["include"], ["30 days"])

    def test_format_suite_case_detail_is_readable(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        output = format_suite_case_detail(suite, case_id)

        self.assertIn(f"redline case {case_id}", output)
        self.assertIn("Baseline response:", output)


if __name__ == "__main__":
    unittest.main()
