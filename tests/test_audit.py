import json
import tempfile
import unittest
from pathlib import Path

from redline.audit import append_audit_event, file_reference, format_audit_events, read_audit_events, result_summary


class AuditTests(unittest.TestCase):
    def test_file_reference_records_path_and_hash_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text('{"cases": []}\n', encoding="utf-8")

            reference = file_reference(path)

            self.assertIsNotNone(reference)
            assert reference is not None
            self.assertEqual(reference["path"], str(path))
            self.assertEqual(len(reference["sha256"]), 64)
            self.assertNotIn("cases", json.dumps(reference))

    def test_append_audit_event_writes_jsonl_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".redline" / "audit.jsonl"

            append_audit_event(path, {"event": "case_marked", "case_id": "case_001"})

            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(row["version"], "0.1")
            self.assertEqual(row["event"], "case_marked")
            self.assertEqual(row["case_id"], "case_001")
            self.assertIn("timestamp", row)
            self.assertIn("operator", row)

    def test_append_audit_event_omits_none_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".redline" / "audit.jsonl"

            row = append_audit_event(path, {"event": "scan", "output": None})

            self.assertIsNotNone(row)
            assert row is not None
            self.assertNotIn("output", row)

    def test_read_missing_audit_log_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(read_audit_events(Path(directory) / "missing.jsonl"), [])

    def test_format_audit_events_prints_recent_event_summaries(self) -> None:
        output = format_audit_events(
            [
                {
                    "timestamp": "2026-05-25T00:00:00Z",
                    "event": "diff_run",
                    "summary": {"cases": 2, "regression": 1, "neutral": 1},
                    "exit_code": 1,
                },
                {
                    "timestamp": "2026-05-25T00:01:00Z",
                    "event": "case_marked",
                    "case_id": "case_001",
                },
            ]
        )

        self.assertIn("redline audit", output)
        self.assertIn("diff_run", output)
        self.assertIn("cases=2", output)
        self.assertIn("regression=1", output)
        self.assertIn("case=case_001", output)

    def test_result_summary_keeps_only_counts(self) -> None:
        summary = result_summary(
            {
                "summary": {
                    "cases": 2,
                    "regression": 1,
                    "neutral": 1,
                    "extra": "ignored",
                }
            }
        )

        self.assertEqual(summary, {"cases": 2, "regression": 1, "neutral": 1})


if __name__ == "__main__":
    unittest.main()
