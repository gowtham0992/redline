from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from redline.import_logs import import_jsonl_log
from redline.io import read_jsonl_records


class ImportLogTests(unittest.TestCase):
    def test_import_jsonl_log_maps_external_fields_and_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            output = root / "baseline.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "row_id": "dolly_001",
                        "instruction": "Answer the question.",
                        "context": "Use the refund policy.",
                        "response": "Refunds are available within 30 days.",
                        "category": "closed_qa",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = import_jsonl_log(
                source,
                output=output,
                input_field="instruction",
                output_field="response",
                context_field="context",
                id_field="row_id",
                metadata_fields=["category"],
            )

            self.assertEqual(report["records"], 1)
            records = read_jsonl_records(output, "prompt", "response")
            self.assertEqual(records[0].raw["id"], "dolly_001")
            self.assertEqual(records[0].prompt, "Answer the question.\n\nContext:\nUse the refund policy.")
            self.assertEqual(records[0].response, "Refunds are available within 30 days.")
            self.assertEqual(records[0].raw["metadata"], {"category": "closed_qa"})

    def test_import_jsonl_log_limits_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            output = root / "baseline.jsonl"
            source.write_text(
                '{"instruction": "one", "response": "1"}\n'
                '{"instruction": "two", "response": "2"}\n',
                encoding="utf-8",
            )

            report = import_jsonl_log(
                source,
                output=output,
                input_field="instruction",
                output_field="response",
                limit=1,
            )

            self.assertEqual(report["records"], 1)
            self.assertEqual(len(read_jsonl_records(output, "prompt", "response")), 1)

    def test_import_jsonl_log_redacts_common_secrets_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            output = root / "baseline.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "instruction": "Email ada@example.com with the result.",
                        "response": "Used key sk-ant-" + ("a" * 24),
                        "metadata": {"api_key": "secret-value"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = import_jsonl_log(
                source,
                output=output,
                input_field="instruction",
                output_field="response",
                metadata_fields=["metadata"],
            )

            self.assertTrue(report["redacted"])
            self.assertEqual(report["redactions"], 3)
            records = read_jsonl_records(output, "prompt", "response")
            self.assertNotIn("ada@example.com", records[0].prompt)
            self.assertNotIn("sk-ant-", records[0].response)
            self.assertEqual(records[0].raw["metadata"]["metadata"]["api_key"], "[REDACTED]")

    def test_import_jsonl_log_can_disable_redaction_for_local_only_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            output = root / "baseline.jsonl"
            source.write_text(
                '{"instruction": "Email ada@example.com", "response": "ok"}\n',
                encoding="utf-8",
            )

            report = import_jsonl_log(
                source,
                output=output,
                input_field="instruction",
                output_field="response",
                redact=False,
            )

            self.assertFalse(report["redacted"])
            self.assertEqual(report["redactions"], 0)
            records = read_jsonl_records(output, "prompt", "response")
            self.assertIn("ada@example.com", records[0].prompt)

    def test_import_jsonl_log_reports_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            source.write_text('{"instruction": "missing response"}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing output field: response"):
                import_jsonl_log(source, output=root / "baseline.jsonl", input_field="instruction")
