import sys
import tempfile
import unittest
from pathlib import Path

from redline.diff import compare_suite_to_candidate
from redline.io import LogRecord
from redline.judge import apply_judge
from redline.suite import build_suite


class JudgeTests(unittest.TestCase):
    def test_apply_judge_reclassifies_changed_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "judge.py"
            script.write_text(
                "import json, sys\n"
                "payload = json.loads(sys.stdin.read())\n"
                "assert payload['deterministic_status'] == 'changed'\n"
                "print(json.dumps({"
                "'status': 'regression', "
                "'confidence': 'high', "
                "'reason': 'candidate routes to the wrong queue'"
                "}))\n",
                encoding="utf-8",
            )
            suite = build_suite(
                [LogRecord(1, "Route the ticket", "billing", {})],
                source="memory",
                input_field="prompt",
                output_field="response",
                max_cases=10,
            )
            result = compare_suite_to_candidate(
                suite,
                [LogRecord(1, "Route the ticket", "security", {})],
            )

            judged = apply_judge(result, f"{sys.executable} {script}")

            self.assertEqual(judged["summary"]["regression"], 1)
            self.assertEqual(judged["summary"]["changed"], 0)
            self.assertEqual(judged["decision"]["recommended_action"], "fix blocking cases before shipping")
            self.assertEqual(judged["judge"]["cases"], 1)
            self.assertEqual(judged["diffs"][0]["judge"]["status"], "regression")
            self.assertEqual(judged["diffs"][0]["confidence"], "high")
            self.assertEqual(judged["diffs"][0]["signal"], "judge")
            self.assertIn("judge regression", judged["diffs"][0]["reasons"][0])

    def test_apply_judge_skips_deterministic_regressions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "judge.py"
            script.write_text("raise SystemExit('should not be called')\n", encoding="utf-8")
            suite = build_suite(
                [LogRecord(1, "Return JSON", '{"ok": true}', {})],
                source="memory",
                input_field="prompt",
                output_field="response",
                max_cases=10,
            )
            result = compare_suite_to_candidate(
                suite,
                [LogRecord(1, "Return JSON", "ok", {})],
            )

            judged = apply_judge(result, f"{sys.executable} {script}")

            self.assertEqual(judged["summary"]["regression"], 1)
            self.assertEqual(judged["judge"]["cases"], 0)

    def test_apply_judge_rejects_invalid_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "judge.py"
            script.write_text(
                "import json\nprint(json.dumps({'status': 'bad'}))\n",
                encoding="utf-8",
            )
            result = {
                "summary": {"cases": 1, "changed": 1},
                "diffs": [
                    {
                        "case_id": "case_001",
                        "status": "changed",
                        "prompt": "hello",
                        "baseline_response": "one",
                        "candidate_response": "two",
                        "reasons": ["short answer changed"],
                    }
                ],
            }

            with self.assertRaisesRegex(ValueError, "judge status"):
                apply_judge(result, f"{sys.executable} {script}")

    def test_apply_judge_error_includes_stdout_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "judge.py"
            script.write_text(
                "import sys\n"
                "print('out detail')\n"
                "print('err detail', file=sys.stderr)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            result = {
                "summary": {"cases": 1, "changed": 1},
                "diffs": [
                    {
                        "case_id": "case_001",
                        "status": "changed",
                        "prompt": "hello",
                        "baseline_response": "one",
                        "candidate_response": "two",
                        "reasons": ["short answer changed"],
                    }
                ],
            }

            with self.assertRaisesRegex(ValueError, "stderr: err detail.*stdout: out detail"):
                apply_judge(result, f"{sys.executable} {script}")


if __name__ == "__main__":
    unittest.main()
