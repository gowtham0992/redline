import tempfile
import unittest
from pathlib import Path

from redline.io import read_jsonl_records
from redline.watch import collect_log


class WatchTests(unittest.TestCase):
    def test_collect_log_writes_normalized_observed_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text(
                '{"request": {"prompt": "hello"}, "result": {"text": "world"}}\n',
                encoding="utf-8",
            )

            result = collect_log(
                source,
                output=output,
                input_field="request.prompt",
                output_field="result.text",
                append=False,
            )

            records = read_jsonl_records(output, "prompt", "response")
            self.assertEqual(result["records"], 1)
            self.assertEqual(result["records_seen"], 1)
            self.assertEqual(result["skipped_duplicates"], 0)
            self.assertEqual(result["mode"], "wrote")
            self.assertEqual(records[0].prompt, "hello")
            self.assertEqual(records[0].response, "world")
            self.assertEqual(records[0].raw["request.prompt"], "hello")
            self.assertEqual(records[0].raw["result.text"], "world")
            self.assertEqual(records[0].raw["source"], str(source))
            self.assertEqual(records[0].raw["source_line"], 1)
            self.assertIn("observed_at", records[0].raw)

    def test_collect_log_skips_duplicate_source_lines_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text('{"prompt": "hello", "response": "world"}\n', encoding="utf-8")

            collect_log(source, output=output)
            result = collect_log(source, output=output)

            records = read_jsonl_records(output, "prompt", "response")
            self.assertEqual(result["mode"], "appended")
            self.assertEqual(result["records"], 0)
            self.assertEqual(result["records_seen"], 1)
            self.assertEqual(result["skipped_duplicates"], 1)
            self.assertEqual(len(records), 1)

    def test_collect_log_can_allow_duplicate_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text('{"prompt": "hello", "response": "world"}\n', encoding="utf-8")

            collect_log(source, output=output)
            result = collect_log(source, output=output, dedupe=False)

            records = read_jsonl_records(output, "prompt", "response")
            self.assertFalse(result["dedupe"])
            self.assertEqual(result["records"], 1)
            self.assertEqual(result["skipped_duplicates"], 0)
            self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
