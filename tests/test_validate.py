import tempfile
import unittest
from pathlib import Path

from redline.io import LogRecord, write_json
from redline.suite import build_suite
from redline.validate import format_validation_report, validate_prompt_manifest, validate_suite


class ValidateTests(unittest.TestCase):
    def test_validate_suite_accepts_generated_suite(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = validate_suite(suite, suite_path="redline-suite.json")

        self.assertTrue(report["valid"])
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["warnings"], 0)
        self.assertEqual(report["next_steps"], [])

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
            source="logs/baseline.jsonl",
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
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["content_hash"] = "stale"

        report = validate_suite(suite, suite_path="redline-suite.json")

        self.assertFalse(report["valid"])
        self.assertTrue(any(item["path"].endswith(".content_hash") for item in report["items"]))
        self.assertIn(
            "Refresh stale content hashes: redline suite logs/baseline.jsonl --out redline-suite.json",
            report["next_steps"],
        )

    def test_validate_suite_warns_for_missing_content_hash(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="logs/baseline.jsonl",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        del suite["cases"][0]["content_hash"]

        report = validate_suite(suite, suite_path="redline-suite.json")

        self.assertTrue(report["valid"])
        self.assertEqual(report["warnings"], 1)
        self.assertTrue(any("missing stable prompt-response hash" in item["message"] for item in report["items"]))
        self.assertIn(
            "Regenerate suite metadata from trusted logs: redline suite logs/baseline.jsonl --out redline-suite.json",
            report["next_steps"],
        )

    def test_validate_suite_warns_when_source_log_is_newer_than_suite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "baseline.jsonl"
            source.write_text('{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n', encoding="utf-8")
            suite = build_suite(
                [LogRecord(1, "Return JSON", '{"ok": true}', {})],
                source=source,
                input_field="prompt",
                output_field="response",
                max_cases=10,
            )
            suite["created_at"] = "2000-01-01T00:00:00+00:00"

            report = validate_suite(suite, suite_path="redline-suite.json")

        self.assertTrue(report["valid"])
        self.assertEqual(report["warnings"], 1)
        self.assertTrue(any(item["path"] == "source" for item in report["items"]))
        self.assertIn(
            f"Regenerate suite from newer source log: redline suite {source} --out redline-suite.json",
            report["next_steps"],
        )

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

    def test_validate_suite_warns_for_judgments_without_review_metadata(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "30 days", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        suite["judgments"] = {
            case_id: {
                "status": "expected",
                "note": "",
            }
        }

        report = validate_suite(suite, suite_path="redline-suite.json")
        text = format_validation_report(report)

        self.assertTrue(report["valid"])
        self.assertEqual(report["warnings"], 2)
        self.assertTrue(any(item["path"] == f"judgments.{case_id}.note" for item in report["items"]))
        self.assertTrue(any(item["path"] == f"judgments.{case_id}.updated_at" for item in report["items"]))
        self.assertIn("expected or ignored judgments should include a reason", text)
        self.assertIn(
            "Add judgment notes before team rollout, then rerun: redline validate redline-suite.json",
            report["next_steps"],
        )

    def test_validate_suite_rejects_unknown_judgment_status(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Refund policy", "30 days", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        suite["judgments"] = {
            case_id: {
                "status": "accepted",
                "note": "approved elsewhere",
                "updated_at": "2026-05-25T00:00:00+00:00",
            }
        }

        report = validate_suite(suite, suite_path="redline-suite.json")

        self.assertFalse(report["valid"])
        self.assertTrue(any("unknown status accepted" in item["message"] for item in report["items"]))
        self.assertIn(
            "Use a supported judgment status, then rerun: redline validate redline-suite.json",
            report["next_steps"],
        )

    def test_validate_prompt_manifest_checks_mapped_suites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompts" / "support.txt"
            prompt.parent.mkdir()
            prompt.write_text("Support prompt", encoding="utf-8")
            suite_path = root / "suites" / "support.redline-suite.json"
            suite_path.parent.mkdir()
            write_json(
                suite_path,
                build_suite(
                    [LogRecord(1, "Return JSON", '{"ok": true}', {})],
                    source="memory",
                    input_field="prompt",
                    output_field="response",
                    max_cases=10,
                ),
            )
            manifest = {
                "schema": "redline-prompt-manifest-v1",
                "prompts": [
                    {"id": "support", "path": str(prompt), "suite": str(suite_path)},
                    {
                        "id": "billing",
                        "path": str(root / "prompts" / "billing.txt"),
                        "suite": str(root / "suites" / "billing.redline-suite.json"),
                    },
                ],
            }

            report = validate_prompt_manifest(manifest, manifest_path="redline-prompts.json")
            text = format_validation_report(report)

        self.assertFalse(report["valid"])
        self.assertEqual(report["prompt_count"], 2)
        self.assertEqual(report["suite_count"], 1)
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["warnings"], 1)
        self.assertTrue(any("mapped suite not found" in item["message"] for item in report["items"]))
        self.assertTrue(any("prompt file not found" in item["message"] for item in report["items"]))
        self.assertIn("Prompt manifest: redline-prompts.json", text)
        self.assertIn("Suites:   1/2", text)
        self.assertIn("Build missing suite:", text)

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
            "next_steps": [
                "Refresh stale stored features: redline suite logs/baseline.jsonl --out redline-suite.json"
            ],
        }

        text = format_validation_report(report)

        self.assertIn("redline validate", text)
        self.assertIn("Status:   invalid", text)
        self.assertIn("ERROR cases[0].features.shape", text)
        self.assertIn("Next:", text)
        self.assertIn("Refresh stale stored features", text)


if __name__ == "__main__":
    unittest.main()
