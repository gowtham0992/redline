import sys
import unittest

from redline.diff import compare_suite_to_candidate
from redline.io import LogRecord
from redline.replay import render_prompt_template, replay_suite
from redline.suite import build_suite


class ReplayTests(unittest.TestCase):
    def test_replay_sends_prompt_on_stdin(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        replay = replay_suite(
            suite,
            f"{sys.executable} -c \"import sys; print(sys.stdin.read().upper())\"",
        )

        self.assertEqual(replay.records[0].prompt, "hello")
        self.assertEqual(replay.records[0].response, "HELLO")
        self.assertEqual(len(replay.records[0].raw["content_hash"]), 64)
        self.assertEqual(replay.records[0].raw["baseline_content_hash"], suite["cases"][0]["content_hash"])

    def test_replay_output_can_be_compared(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        replay = replay_suite(suite, f"{sys.executable} -c \"print('not json')\"")
        result = compare_suite_to_candidate(suite, replay.records)

        self.assertEqual(result["summary"]["regression"], 1)

    def test_replay_supports_prompt_placeholder(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        replay = replay_suite(
            suite,
            f"{sys.executable} -c \"import sys; print(sys.argv[1].upper())\" {{prompt}}",
        )

        self.assertEqual(replay.records[0].response, "HELLO")

    def test_replay_supports_prompt_template(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        replay = replay_suite(
            suite,
            f"{sys.executable} -c \"import sys; print(sys.stdin.read())\"",
            prompt_template="System: answer briefly\nUser: {prompt}",
            prompt_path="prompts/v2.txt",
        )

        self.assertEqual(replay.records[0].prompt, "hello")
        self.assertEqual(replay.records[0].raw["rendered_prompt"], "System: answer briefly\nUser: hello")
        self.assertEqual(replay.records[0].response, "System: answer briefly\nUser: hello")
        self.assertEqual(replay.to_metadata()["prompt"], "prompts/v2.txt")

    def test_replay_can_run_cases_with_workers_and_preserve_order(self) -> None:
        suite = {
            "cases": [
                {"id": "case_001", "prompt": "slow"},
                {"id": "case_002", "prompt": "fast"},
            ]
        }

        replay = replay_suite(
            suite,
            (
                f"{sys.executable} -c "
                "\"import sys, time; prompt=sys.stdin.read(); "
                "time.sleep(0.05 if prompt == 'slow' else 0); print(prompt.upper())\""
            ),
            workers=2,
        )

        self.assertEqual([record.prompt for record in replay.records], ["slow", "fast"])
        self.assertEqual([record.response for record in replay.records], ["SLOW", "FAST"])
        self.assertEqual(replay.to_metadata()["workers"], 2)

    def test_replay_rejects_non_positive_workers(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        with self.assertRaisesRegex(ValueError, "workers"):
            replay_suite(suite, f"{sys.executable} -c \"print('hello')\"", workers=0)

    def test_render_prompt_template_supports_case_fields(self) -> None:
        rendered = render_prompt_template(
            "Case {case_id} line {source_line}: {prompt} // {cluster} // {baseline_response} // {content_hash}",
            {
                "id": "case_001",
                "source_line": 7,
                "prompt": "hello",
                "cluster": "general|prose|short",
                "baseline_response": "world",
                "content_hash": "abc123",
            },
        )

        self.assertEqual(
            rendered,
            "Case case_001 line 7: hello // general|prose|short // world // abc123",
        )

    def test_render_prompt_template_rejects_unknown_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown prompt template field"):
            render_prompt_template("{missing}", {"prompt": "hello"})

    def test_render_prompt_template_allows_json_braces(self) -> None:
        rendered = render_prompt_template(
            'Return JSON like {"answer": "..."} for {prompt}',
            {"prompt": "hello"},
        )

        self.assertEqual(rendered, 'Return JSON like {"answer": "..."} for hello')

    def test_replay_exposes_case_context_as_environment(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]
        content_hash = suite["cases"][0]["content_hash"]

        replay = replay_suite(
            suite,
            (
                f"{sys.executable} -c "
                "\"import os; "
                "print(os.environ['REDLINE_CASE_ID'] + '|' + os.environ['REDLINE_CONTENT_HASH'])\""
            ),
        )

        self.assertEqual(replay.records[0].response, f"{case_id}|{content_hash}")

    def test_replay_error_includes_case_id(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        case_id = suite["cases"][0]["id"]

        with self.assertRaisesRegex(ValueError, case_id):
            replay_suite(suite, f"{sys.executable} -c \"raise SystemExit(7)\"")

    def test_replay_error_includes_stdout_and_stderr(self) -> None:
        suite = build_suite(
            [LogRecord(1, "hello", "hello", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        with self.assertRaisesRegex(ValueError, "stdout: out detail.*stderr: err detail|stderr: err detail.*stdout: out detail"):
            replay_suite(
                suite,
                (
                    f"{sys.executable} -c "
                    "\"import sys; print('out detail'); print('err detail', file=sys.stderr); raise SystemExit(7)\""
                ),
            )


if __name__ == "__main__":
    unittest.main()
