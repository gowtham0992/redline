import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Any

from redline import record as exported_record
from redline import watch as exported_watch
from redline.io import read_jsonl_records
from redline.watch import collect_log, follow_log, format_follow_records, format_watch_stats, record, watch, watch_stats


class WatchTests(unittest.TestCase):
    def test_record_appends_manual_prompt_response_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            row = record(
                "refund policy",
                {"text": "30 days"},
                log=log,
                source="python:test",
                source_line=12,
                metadata={"model": "test-model"},
            )

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(row["source"], "python:test")
            self.assertEqual(records[0].prompt, "refund policy")
            self.assertEqual(records[0].response, '{"text": "30 days"}')
            self.assertEqual(records[0].raw["source_line"], 12)
            self.assertEqual(records[0].raw["metadata"]["model"], "test-model")
            self.assertEqual(row["recorded"], True)
            self.assertIn("content_hash", records[0].raw)

    def test_record_skips_duplicate_prompt_response_observations_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            first = record("hello", "world", log=log)
            second = record("hello", "world", log=log)

            records = read_jsonl_records(log, "prompt", "response")
            self.assertTrue(first["recorded"])
            self.assertFalse(second["recorded"])
            self.assertEqual(first["content_hash"], second["content_hash"])
            self.assertEqual(len(records), 1)

    def test_record_allows_duplicate_prompt_response_observations_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            record("hello", "world", log=log)
            second = record("hello", "world", log=log, dedupe=False)

            records = read_jsonl_records(log, "prompt", "response")
            self.assertTrue(second["recorded"])
            self.assertEqual(len(records), 2)

    def test_record_keeps_same_prompt_with_changed_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            record("hello", "world", log=log)
            second = record("hello", "friend", log=log)

            records = read_jsonl_records(log, "prompt", "response")
            self.assertTrue(second["recorded"])
            self.assertEqual(len(records), 2)
            self.assertEqual(records[1].response, "friend")

    def test_record_extracts_openai_chat_response_text_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"
            response = {
                "id": "chatcmpl_test",
                "model": "gpt-test",
                "choices": [
                    {
                        "message": {"content": "Hello from the model"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 5,
                    "total_tokens": 9,
                },
            }

            record("hello", response, log=log)

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].response, "Hello from the model")
            metadata = records[0].raw["metadata"]
            self.assertEqual(metadata["id"], "chatcmpl_test")
            self.assertEqual(metadata["model"], "gpt-test")
            self.assertEqual(metadata["finish_reason"], "stop")
            self.assertEqual(metadata["prompt_tokens"], 4)
            self.assertEqual(metadata["completion_tokens"], 5)
            self.assertEqual(metadata["total_tokens"], 9)

    def test_record_extracts_anthropic_style_content_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"
            response = {
                "model": "claude-test",
                "content": [{"type": "text", "text": "First"}, {"type": "text", "text": "Second"}],
                "usage": {"input_tokens": 3, "output_tokens": 4},
            }

            record("hello", response, log=log)

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].response, "First\nSecond")
            metadata = records[0].raw["metadata"]
            self.assertEqual(metadata["model"], "claude-test")
            self.assertEqual(metadata["prompt_tokens"], 3)
            self.assertEqual(metadata["completion_tokens"], 4)

    def test_record_exports_from_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            exported_record("hello", "world", log=log)

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].prompt, "hello")
            self.assertEqual(records[0].response, "world")

    def test_watch_decorator_records_sync_function_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            @watch(log=log)
            def generate_response(prompt: str) -> str:
                return f"answer: {prompt}"

            result = generate_response("refund policy")

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(result, "answer: refund policy")
            self.assertEqual(records[0].prompt, "refund policy")
            self.assertEqual(records[0].response, "answer: refund policy")
            self.assertIn("python:", records[0].raw["source"])
            self.assertIn("observed_at", records[0].raw)
            self.assertEqual(
                records[0].raw["metadata"]["function"],
                "WatchTests.test_watch_decorator_records_sync_function_calls.<locals>.generate_response",
            )
            self.assertIsInstance(records[0].raw["metadata"]["latency_ms"], int)

    def test_watch_decorator_supports_custom_response_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            class Response:
                def __init__(self, text: str) -> None:
                    self.text = text

            @watch(log=log, response_extractor=lambda response: response.text)
            def generate_response(prompt: str) -> Response:
                return Response(f"answer: {prompt}")

            response = generate_response("refund policy")

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(response.text, "answer: refund policy")
            self.assertEqual(records[0].response, "answer: refund policy")

    def test_watch_decorator_skips_duplicate_prompt_response_observations_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            @watch(log=log)
            def generate_response(prompt: str) -> str:
                return f"answer: {prompt}"

            generate_response("refund policy")
            generate_response("refund policy")

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(len(records), 1)
            self.assertIsInstance(records[0].raw["content_hash"], str)
            self.assertEqual(len(records[0].raw["content_hash"]), 64)

    def test_watch_decorator_supports_import_from_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            @exported_watch(log=log, prompt_arg="question")
            def answer(question: str) -> dict[str, str]:
                return {"text": question.upper()}

            answer(question="hello")

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].prompt, "hello")
            self.assertEqual(records[0].response, '{"text": "HELLO"}')

    def test_watch_decorator_records_async_function_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            @watch(log=log)
            async def generate_response(prompt: str) -> str:
                return f"async: {prompt}"

            result = asyncio.run(generate_response("status update"))

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(result, "async: status update")
            self.assertEqual(records[0].prompt, "status update")
            self.assertEqual(records[0].response, "async: status update")

    def test_watch_decorator_can_be_used_without_parentheses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path.cwd()
            try:
                # Keep the default log path local to this temp project.
                os.chdir(directory)

                @watch
                def generate_response(prompt: str) -> str:
                    return "ok"

                generate_response("hello")

                records = read_jsonl_records(".redline/logs/prompts.jsonl", "prompt", "response")
                self.assertEqual(records[0].prompt, "hello")
                self.assertEqual(records[0].response, "ok")
            finally:
                os.chdir(root)

    def test_watch_decorator_metadata_can_be_static_or_callable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            @watch(log=log, metadata=lambda prompt: {"model": "test-model", "length": len(prompt)})
            def generate_response(prompt: str) -> str:
                return "ok"

            generate_response("hello")

            records = read_jsonl_records(log, "prompt", "response")
            metadata = records[0].raw["metadata"]
            self.assertEqual(metadata["model"], "test-model")
            self.assertEqual(metadata["length"], 5)

    def test_watch_decorator_stringifies_non_json_response_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            class Response:
                def __str__(self) -> str:
                    return "custom response"

            @watch(log=log)
            def generate_response(prompt: str) -> Response:
                return Response()

            generate_response("hello")

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].response, "custom response")

    def test_watch_decorator_requires_prompt_when_it_cannot_infer_one(self) -> None:
        @watch(log=Path(tempfile.gettempdir()) / "redline-missing-prompt.jsonl")
        def generate_response() -> str:
            return "ok"

        with self.assertRaisesRegex(ValueError, "could not infer prompt"):
            generate_response()

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
            self.assertEqual(stats["unique_prompt_response_pairs"], 2)
            self.assertEqual(stats["duplicate_prompt_response_pairs"], 0)
            self.assertEqual(stats["sources"], 1)
            self.assertEqual(stats["behavior_patterns"], 2)
            self.assertFalse(stats["readiness"]["ready"])
            self.assertIn("Behavior patterns: 2", text)
            self.assertIn("Unique pairs:      2", text)
            self.assertIn("First observed:", text)
            self.assertIn("Readiness:         collect more evidence", text)
            self.assertIn("Next:              redline watch --follow", text)

    def test_watch_stats_uses_unique_pairs_for_suite_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observed.jsonl"
            for _ in range(5):
                record("hello", "world", log=output, dedupe=False)

            stats = watch_stats(output)
            text = format_watch_stats(stats)

            self.assertEqual(stats["records"], 5)
            self.assertEqual(stats["unique_prompt_response_pairs"], 1)
            self.assertEqual(stats["duplicate_prompt_response_pairs"], 4)
            self.assertFalse(stats["readiness"]["ready"])
            self.assertIn("Duplicate pairs:   4", text)
            self.assertIn("collect more evidence", text)

    def test_watch_stats_reports_suite_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text(
                '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n'
                '{"prompt": "Summarize", "response": "- one\\n- two"}\n'
                '{"prompt": "Write code", "response": "```python\\nprint(1)\\n```"}\n'
                '{"prompt": "Answer policy", "response": "Policy URL: https://example.com"}\n'
                '{"prompt": "List steps", "response": "1. Start\\n2. Finish"}\n',
                encoding="utf-8",
            )
            collect_log(source, output=output)

            stats = watch_stats(output)
            text = format_watch_stats(stats)

            self.assertTrue(stats["readiness"]["ready"])
            self.assertEqual(stats["unique_prompt_response_pairs"], 5)
            self.assertEqual(stats["readiness"]["next_step"], "redline suite")
            self.assertIn("Readiness:         ready to generate suite", text)
            self.assertIn("Next:              redline suite", text)

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

    def test_follow_log_caps_initial_batch_to_max_records(self) -> None:
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
                max_records=1,
            )

            records = read_jsonl_records(output, "prompt", "response")
            self.assertEqual(result["records"], 1)
            self.assertEqual(result["records_seen"], 1)
            self.assertEqual([record.prompt for record in records], ["one"])

    def test_follow_log_notifies_when_records_are_collected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            output = root / "observed.jsonl"
            source.write_text('{"prompt": "one", "response": "1"}\n', encoding="utf-8")
            collected: list[dict[str, Any]] = []

            result = follow_log(
                source,
                output=output,
                poll_interval=0,
                max_records=1,
                on_records=collected.extend,
            )

            self.assertEqual(result["records"], 1)
            self.assertEqual(len(collected), 1)
            self.assertEqual(collected[0]["prompt"], "one")

    def test_format_follow_records_prints_live_prompt_preview(self) -> None:
        text = format_follow_records(
            [
                {
                    "source_line": 4,
                    "prompt": "Summarize the refund policy for enterprise customers",
                }
            ]
        )

        self.assertEqual(text, "+ line 4: Summarize the refund policy for enterprise customers\n")

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
