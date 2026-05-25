import json
import tempfile
import unittest
from pathlib import Path

from redline.audit import (
    append_audit_event,
    file_reference,
    format_audit_events,
    format_audit_verification,
    read_audit_events,
    result_summary,
    verify_audit_events,
    verify_audit_log,
)


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
            self.assertIn("entry_hash", row)
            self.assertEqual(len(row["entry_hash"]), 64)

    def test_append_audit_event_hash_chains_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".redline" / "audit.jsonl"

            first = append_audit_event(path, {"event": "suite_generated"})
            second = append_audit_event(path, {"event": "diff_run"})

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            assert first is not None
            assert second is not None
            self.assertNotIn("previous_hash", first)
            self.assertEqual(second["previous_hash"], first["entry_hash"])

            verification = verify_audit_log(path)

            self.assertTrue(verification["ok"])
            self.assertEqual(verification["signed_entries"], 2)
            self.assertEqual(verification["unsigned_entries"], 0)
            self.assertEqual(verification["last_hash"], second["entry_hash"])
            self.assertEqual(verification["events_by_type"], {"diff_run": 1, "suite_generated": 1})

    def test_verify_audit_log_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".redline" / "audit.jsonl"

            append_audit_event(path, {"event": "case_marked", "case_id": "case_001"})
            row = json.loads(path.read_text(encoding="utf-8"))
            row["case_id"] = "case_999"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")

            verification = verify_audit_log(path)

            self.assertFalse(verification["ok"])
            self.assertEqual(verification["errors"], ["line 1: entry_hash mismatch"])

    def test_verify_audit_log_can_check_expected_tail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".redline" / "audit.jsonl"

            append_audit_event(path, {"event": "suite_generated"})
            second = append_audit_event(path, {"event": "diff_run"})

            self.assertIsNotNone(second)
            assert second is not None
            verification = verify_audit_log(
                path,
                expected_last_hash=second["entry_hash"],
                expected_entries=2,
            )

            self.assertTrue(verification["ok"])
            self.assertEqual(verification["warnings"], [])

    def test_verify_audit_events_detects_tail_checkpoint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".redline" / "audit.jsonl"

            first = append_audit_event(path, {"event": "suite_generated"})
            second = append_audit_event(path, {"event": "diff_run"})
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            assert first is not None
            assert second is not None

            truncated_events = [first]
            verification = verify_audit_events(
                truncated_events,
                expected_last_hash=second["entry_hash"],
                expected_entries=2,
            )

            self.assertFalse(verification["ok"])
            self.assertIn("expected 2 entries, found 1", verification["errors"])
            self.assertIn("last_hash does not match expected hash", verification["errors"])

    def test_format_audit_verification_prints_status_and_errors(self) -> None:
        output = format_audit_verification(
            {
                "ok": False,
                "entries": 1,
                "signed_entries": 1,
                "unsigned_entries": 0,
                "last_hash": "abc123",
                "events_by_type": {"case_marked": 1},
                "errors": ["line 1: entry_hash mismatch"],
                "warnings": ["tail checkpoint missing"],
            }
        )

        self.assertIn("redline audit verify", output)
        self.assertIn("Status:   FAILED", output)
        self.assertIn("line 1: entry_hash mismatch", output)
        self.assertIn("tail checkpoint missing", output)
        self.assertIn("Events:   case_marked=1", output)
        self.assertIn(
            "redline audit --verify --expect-last-hash abc123 --expect-entries 1",
            output,
        )

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
                    "operator": "eng@example.com",
                    "approver": "lead@example.com",
                    "case_id": "case_001",
                },
            ]
        )

        self.assertIn("redline audit", output)
        self.assertIn("diff_run", output)
        self.assertIn("cases=2", output)
        self.assertIn("regression=1", output)
        self.assertIn("operator=eng@example.com", output)
        self.assertIn("approver=lead@example.com", output)
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
