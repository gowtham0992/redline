import tempfile
import unittest
from pathlib import Path

from redline.io import read_jsonl_records, write_jsonl


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


if __name__ == "__main__":
    unittest.main()
