import json
import tempfile
import unittest
from pathlib import Path

from redline.redact import (
    format_redaction_report,
    redact_jsonl,
    redact_object,
    redact_text,
    scan_jsonl_redactions,
)


class RedactTests(unittest.TestCase):
    def test_redact_text_replaces_common_secret_and_pii_patterns(self) -> None:
        counts: dict[str, int] = {}
        text = (
            "Contact ada@example.com with "
            "sk-ant-abcdefghijklmnopqrstuvwxyz123456 "
            "and ghp_abcdefghijklmnopqrstuvwxyz123456."
        )

        redacted = redact_text(text, counts=counts)

        self.assertNotIn("ada@example.com", redacted)
        self.assertNotIn("sk-ant-", redacted)
        self.assertNotIn("ghp_", redacted)
        self.assertEqual(counts["email"], 1)
        self.assertEqual(counts["anthropic_key"], 1)
        self.assertEqual(counts["github_token"], 1)

    def test_redact_object_redacts_sensitive_field_values(self) -> None:
        counts: dict[str, int] = {}

        redacted = redact_object(
            {
                "prompt": "hello",
                "metadata": {
                    "api_key": "plain-secret-value",
                    "nested": [{"password": "hunter2"}],
                },
            },
            counts=counts,
        )

        self.assertEqual(redacted["prompt"], "hello")
        self.assertEqual(redacted["metadata"]["api_key"], "[REDACTED]")
        self.assertEqual(redacted["metadata"]["nested"][0]["password"], "[REDACTED]")
        self.assertEqual(counts["sensitive_field"], 2)

    def test_redact_jsonl_writes_sanitized_log_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.jsonl"
            output = Path(directory) / "redacted.jsonl"
            source.write_text(
                '{"prompt": "Email ada@example.com", "response": "ok", "token": "secret"}\n',
                encoding="utf-8",
            )

            report = redact_jsonl(str(source), str(output))

            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["token"], "[REDACTED]")
            self.assertNotIn("ada@example.com", row["prompt"])
            self.assertEqual(report["records"], 1)
            self.assertEqual(report["redactions"], 2)
            self.assertEqual(report["patterns"], {"email": 1, "sensitive_field": 1})

    def test_scan_jsonl_redactions_counts_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.jsonl"
            source.write_text(
                '{"prompt": "Email ada@example.com", "response": "ok", "token": "secret"}\n',
                encoding="utf-8",
            )

            report = scan_jsonl_redactions(str(source))

            self.assertIsNone(report["output"])
            self.assertTrue(report["check"])
            self.assertEqual(report["records"], 1)
            self.assertEqual(report["redactions"], 2)
            self.assertFalse((Path(directory) / "redacted.jsonl").exists())

    def test_format_redaction_report_points_to_next_suite_step(self) -> None:
        output = format_redaction_report(
            {
                "source": "raw.jsonl",
                "output": "clean.jsonl",
                "records": 2,
                "redactions": 1,
                "patterns": {"email": 1},
            }
        )

        self.assertIn("redline redact", output)
        self.assertIn("best-effort common secret/PII patterns", output)
        self.assertIn("redline suite clean.jsonl --out redline-suite.json", output)

    def test_format_redaction_check_report_points_to_write_step(self) -> None:
        output = format_redaction_report(
            {
                "source": "raw.jsonl",
                "output": None,
                "records": 2,
                "redactions": 1,
                "patterns": {"email": 1},
                "check": True,
            }
        )

        self.assertIn("Mode:       check only", output)
        self.assertIn("redline redact raw.jsonl --out redacted.jsonl", output)
        self.assertNotIn("redline suite None", output)


if __name__ == "__main__":
    unittest.main()
