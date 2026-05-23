import tempfile
import unittest
from pathlib import Path
from threading import Thread
from time import sleep

from redline.io import read_jsonl_records
from redline.watch import collect_log, follow_log, format_watch_stats, watch_stats


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

    def test_watch_stats_summarizes_observed_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text(
                '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n'
                '{"prompt": "Summarize", "response": "- one\\n- two"}\n',
                encoding="utf-8",
            )
            collect_log(source, output=output)

            stats = watch_stats(output)
            text = format_watch_stats(stats)

            self.assertEqual(stats["records"], 2)
            self.assertEqual(stats["sources"], 1)
            self.assertEqual(stats["behavior_patterns"], 2)
            self.assertIn("Behavior patterns: 2", text)
            self.assertIn("First observed:", text)

    def test_follow_log_collects_until_max_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text(
                '{"prompt": "one", "response": "1"}\n'
                '{"prompt": "two", "response": "2"}\n',
                encoding="utf-8",
            )

            result = follow_log(
                source,
                output=output,
                poll_interval=0,
                max_records=2,
            )

            records = read_jsonl_records(output, "prompt", "response")
            self.assertEqual(result["mode"], "followed")
            self.assertEqual(result["records"], 2)
            self.assertEqual(result["iterations"], 1)
            self.assertEqual(len(records), 2)

    def test_follow_log_can_stop_after_idle_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text('{"prompt": "one", "response": "1"}\n', encoding="utf-8")

            result = follow_log(
                source,
                output=output,
                poll_interval=0,
                max_records=2,
                idle_timeout=0,
            )

            self.assertEqual(result["records"], 1)
            self.assertGreaterEqual(result["iterations"], 2)
            self.assertEqual(result["skipped_duplicates"], 0)

    def test_follow_log_collects_lines_appended_after_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text('{"prompt": "one", "response": "1"}\n', encoding="utf-8")

            def append_later() -> None:
                sleep(0.02)
                with source.open("a", encoding="utf-8") as handle:
                    handle.write('{"prompt": "two", "response": "2"}\n')

            writer = Thread(target=append_later)
            writer.start()
            try:
                result = follow_log(
                    source,
                    output=output,
                    poll_interval=0.01,
                    max_records=2,
                )
            finally:
                writer.join()

            records = read_jsonl_records(output, "prompt", "response")
            self.assertEqual(result["records"], 2)
            self.assertEqual([record.prompt for record in records], ["one", "two"])
            self.assertEqual(records[1].raw["source_line"], 2)


if __name__ == "__main__":
    unittest.main()
