import unittest

from redline.io import LogRecord
from redline.suite import build_suite
from redline.validate import format_validation_report, validate_suite


class ValidateTests(unittest.TestCase):
    def test_validate_suite_accepts_generated_suite(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = validate_suite(suite, suite_path="redline-suite.json")

        self.assertTrue(report["valid"])
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["warnings"], 0)

    def test_validate_suite_rejects_duplicate_case_ids(self) -> None:
        suite = build_suite(
            [
                LogRecord(1, "Return JSON", '{"ok": true}', {}),
                LogRecord(2, "Summarize", "- one\n- two", {}),
            ],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][1]["id"] = suite["cases"][0]["id"]

        report = validate_suite(suite)

        self.assertFalse(report["valid"])
        self.assertTrue(any("duplicate case id" in item["message"] for item in report["items"]))

    def test_validate_suite_warns_for_duplicate_prompt_response_pairs(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        duplicate = dict(suite["cases"][0])
        duplicate["id"] = "case_duplicate"
        duplicate["source_line"] = 2
        suite["cases"].append(duplicate)
        suite["summary"]["cases"] = 2

        report = validate_suite(suite)

        self.assertTrue(report["valid"])
        self.assertEqual(report["warnings"], 1)
        self.assertTrue(
            any("duplicate prompt-response pair" in item["message"] for item in report["items"])
        )

    def test_validate_suite_rejects_stale_features(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["features"]["valid_json"] = False

        report = validate_suite(suite)

        self.assertFalse(report["valid"])
        self.assertTrue(
            any(item["path"].endswith(".features.valid_json") for item in report["items"])
        )

    def test_validate_suite_rejects_stale_content_hash(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["content_hash"] = "stale"

        report = validate_suite(suite)

        self.assertFalse(report["valid"])
        self.assertTrue(any(item["path"].endswith(".content_hash") for item in report["items"]))

    def test_validate_suite_rejects_unknown_requirement_case_ids(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "30 days", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["requirements"] = {"missing_case": {"include": ["30 days"]}}

        report = validate_suite(suite)

        self.assertFalse(report["valid"])
        self.assertTrue(any("references unknown case id" in item["message"] for item in report["items"]))

    def test_format_validation_report_includes_findings(self) -> None:
        report = {
            "suite": "redline-suite.json",
            "valid": False,
            "errors": 1,
            "warnings": 0,
            "items": [
                {
                    "level": "error",
                    "path": "cases[0].features.shape",
                    "message": "does not match baseline_response",
                }
            ],
        }

        text = format_validation_report(report)

        self.assertIn("redline validate", text)
        self.assertIn("Status:   invalid", text)
        self.assertIn("ERROR cases[0].features.shape", text)


if __name__ == "__main__":
    unittest.main()
