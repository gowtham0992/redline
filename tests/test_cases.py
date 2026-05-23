import unittest

from redline.cases import format_suite_cases, suite_case_rows
from redline.io import LogRecord
from redline.suite import build_suite


class CasesTests(unittest.TestCase):
    def test_suite_case_rows_include_ids_and_previews(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        rows = suite_case_rows(suite)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["id"].startswith("case_"))
        self.assertEqual(rows[0]["prompt_preview"], "Return JSON for Ada")

    def test_format_suite_cases_prints_reviewable_table(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        output = format_suite_cases(suite)

        self.assertIn("redline cases", output)
        self.assertIn("Return JSON for Ada", output)


if __name__ == "__main__":
    unittest.main()
