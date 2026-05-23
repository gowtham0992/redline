import sys
import unittest

from redline.diff import compare_suite_to_candidate
from redline.io import LogRecord
from redline.replay import replay_suite
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


if __name__ == "__main__":
    unittest.main()
