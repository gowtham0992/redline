import tempfile
import unittest
from pathlib import Path

from redline.io import append_jsonl, append_text, read_json, read_jsonl_records, read_jsonl_records_from_offset, write_jsonl


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

    def test_missing_jsonl_fields_suggest_import_presets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider.jsonl"
            path.write_text('{"instruction": "Summarize", "completion": "Done"}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "redline import --list-presets"):
                read_jsonl_records(path, "prompt", "response")

    def test_read_json_gives_jsonl_next_step_for_extra_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.jsonl"
            path.write_text(
                '{"prompt": "one", "response": "1"}\n'
                '{"prompt": "two", "response": "2"}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "redline suite .* --out redline-suite.json"):
                read_json(path)

    def test_append_jsonl_adds_rows_without_replacing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observed.jsonl"

            write_jsonl(path, [{"prompt": "one", "response": "1"}])
            append_jsonl(path, [{"prompt": "two", "response": "2"}])
            records = read_jsonl_records(path, "prompt", "response")

            self.assertEqual([record.prompt for record in records], ["one", "two"])

    def test_append_text_creates_parent_and_appends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "summary.md"

            append_text(path, "one\n")
            append_text(path, "two\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "one\ntwo\n")

    def test_read_jsonl_records_from_offset_reads_only_new_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observed.jsonl"
            path.write_text('{"prompt": "one", "response": "1"}\n', encoding="utf-8")
            records, offset, next_line = read_jsonl_records_from_offset(path, "prompt", "response")
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"prompt": "two", "response": "2"}\n')

            new_records, new_offset, new_next_line = read_jsonl_records_from_offset(
                path,
                "prompt",
                "response",
                offset=offset,
                start_line_number=next_line,
            )

            self.assertEqual([record.prompt for record in records], ["one"])
            self.assertEqual([record.prompt for record in new_records], ["two"])
            self.assertEqual(new_records[0].line_number, 2)
            self.assertGreater(new_offset, offset)
            self.assertEqual(new_next_line, 3)

    def test_read_jsonl_records_from_offset_can_limit_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observed.jsonl"
            path.write_text(
                '{"prompt": "one", "response": "1"}\n'
                '{"prompt": "two", "response": "2"}\n',
                encoding="utf-8",
            )

            records, offset, next_line = read_jsonl_records_from_offset(
                path,
                "prompt",
                "response",
                max_records=1,
            )
            new_records, _, new_next_line = read_jsonl_records_from_offset(
                path,
                "prompt",
                "response",
                offset=offset,
                start_line_number=next_line,
            )

            self.assertEqual([record.prompt for record in records], ["one"])
            self.assertEqual(next_line, 2)
            self.assertEqual([record.prompt for record in new_records], ["two"])
            self.assertEqual(new_next_line, 3)

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
