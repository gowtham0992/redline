import unittest

from redline.cases import format_suite_case_detail, format_suite_cases, suite_case_detail, suite_case_rows
from redline.io import LogRecord
from redline.judgments import mark_suite_case
from redline.requirements import add_case_requirement
from redline.suite import build_suite


class CasesTests(unittest.TestCase):
    def test_suite_case_rows_include_ids_and_previews(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        rows = suite_case_rows(suite)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["id"].startswith("case_"))
        self.assertEqual(rows[0]["content_hash"], suite["cases"][0]["content_hash"])
        self.assertEqual(rows[0]["prompt_preview"], "Return JSON for Ada")
        self.assertEqual(rows[0]["requirements"], 0)
        self.assertEqual(rows[0]["judgment"], "")
        self.assertFalse(rows[0]["pinned"])
        self.assertEqual(rows[0]["cluster_risk"], "low")
        self.assertEqual(rows[0]["selection_reason"], "cluster_representative")

    def test_suite_case_detail_includes_content_hash(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        detail = suite_case_detail(suite, case_id)
        text = format_suite_case_detail(suite, case_id)

        self.assertEqual(detail["content_hash"], suite["cases"][0]["content_hash"])
        self.assertFalse(detail["pinned"])
        self.assertEqual(detail["cluster_risk"], "low")
        self.assertEqual(detail["selection_reason"], "cluster_representative")
        self.assertIn("Pinned:     no", text)
        self.assertEqual(detail["source"], "logs/baseline.jsonl")
        self.assertIn("Source:      logs/baseline.jsonl:1", text)
        self.assertIn("Risk:        low", text)
        self.assertIn("Selected:    representative", text)
        self.assertIn("Content hash:", text)

    def test_suite_case_detail_marks_pinned_case(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["pinned"] = True
        case_id = suite["cases"][0]["id"]

        detail = suite_case_detail(suite, case_id)
        text = format_suite_case_detail(suite, case_id)

        self.assertTrue(detail["pinned"])
        self.assertIn("Pinned:     yes", text)

    def test_suite_case_rows_count_requirements(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "Refunds are available within 30 days.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        add_case_requirement(suite, case_id, include=["30 days"], exclude=["final sale"])

        rows = suite_case_rows(suite)

        self.assertEqual(rows[0]["requirements"], 2)

    def test_suite_case_rows_count_empty_requirements_as_zero(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "Refunds are available within 30 days.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        suite["requirements"] = {case_id: {}}

        rows = suite_case_rows(suite)

        self.assertEqual(rows[0]["requirements"], 0)

    def test_suite_case_rows_include_judgment_status(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        mark_suite_case(suite, case_id, status="expected")

        rows = suite_case_rows(suite)

        self.assertEqual(rows[0]["judgment"], "expected")

    def test_suite_case_rows_include_pinned_status(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["pinned"] = True

        rows = suite_case_rows(suite)

        self.assertTrue(rows[0]["pinned"])

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
        self.assertIn("PIN", output)
        self.assertIn("RISK", output)
        self.assertIn("WHY", output)
        self.assertIn("RULES", output)
        self.assertIn("JUDGMENT", output)
        self.assertIn("representative", output)
        self.assertIn("Return JSON for Ada", output)

    def test_format_suite_cases_marks_pinned_cases(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON for Ada", '{"name": "Ada"}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["pinned"] = True

        output = format_suite_cases(suite)

        self.assertIn(" yes ", output)


if __name__ == "__main__":
    unittest.main()
