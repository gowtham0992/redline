import tempfile
import unittest
from pathlib import Path

from redline.io import append_jsonl, read_jsonl_records, write_jsonl


class IoTests(unittest.TestCase):
    def test_write_jsonl_creates_replayable_candidate_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.jsonl"

            write_jsonl(path, [{"prompt": "hello", "response": "world", "case_id": "case_001"}])
            records = read_jsonl_records(path, "prompt", "response")

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].prompt, "hello")
            self.assertEqual(records[0].response, "world")
            self.assertEqual(records[0].raw["case_id"], "case_001")

    def test_missing_jsonl_file_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "not found"):
            read_jsonl_records("missing.jsonl", "prompt", "response")

    def test_append_jsonl_adds_rows_without_replacing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observed.jsonl"

            write_jsonl(path, [{"prompt": "one", "response": "1"}])
            append_jsonl(path, [{"prompt": "two", "response": "2"}])
            records = read_jsonl_records(path, "prompt", "response")

            self.assertEqual([record.prompt for record in records], ["one", "two"])

    def test_read_jsonl_records_supports_nested_field_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.jsonl"
            path.write_text(
                '{"request": {"prompt": "hello"}, "result": {"text": "world"}}\n',
                encoding="utf-8",
            )

            records = read_jsonl_records(path, "request.prompt", "result.text")

            self.assertEqual(records[0].prompt, "hello")
            self.assertEqual(records[0].response, "world")

    def test_exact_key_wins_over_nested_field_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.jsonl"
            path.write_text(
                '{"request.prompt": "exact", "request": {"prompt": "nested"}, "response": "ok"}\n',
                encoding="utf-8",
            )

            records = read_jsonl_records(path, "request.prompt", "response")

            self.assertEqual(records[0].prompt, "exact")


if __name__ == "__main__":
    unittest.main()
