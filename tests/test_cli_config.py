import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from redline.cli import main


class CliConfigTests(unittest.TestCase):
    def test_suite_and_diff_use_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    '{"suite": ".redline/suite.json", "input_field": "input", '
                    '"output_field": "output", "max_cases": 3, "fail_on": "none"}',
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"input": "Return JSON", "output": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"input": "Return JSON", "output": "ok"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["diff", "candidate.jsonl"]), 0)

                self.assertTrue((root / ".redline" / "suite.json").exists())
            finally:
                os.chdir(previous)

    def test_eval_uses_configured_replay_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "import sys\nprint(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "replay": replay,
                            "fail_on": "none",
                            "runs": {
                                "candidate": ".redline/runs/candidate.jsonl",
                                "metadata": ".redline/runs/replay.json",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "hello", "response": "hello"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["eval"]), 0)

                candidate = root / ".redline" / "runs" / "candidate.jsonl"
                metadata_path = root / ".redline" / "runs" / "replay.json"
                self.assertTrue(candidate.exists())
                self.assertTrue(metadata_path.exists())
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["suite"], ".redline/suite.json")
                self.assertEqual(metadata["candidate"], ".redline/runs/candidate.jsonl")
                self.assertEqual(metadata["replay"]["command"], replay)
                self.assertEqual(metadata["summary"]["neutral"], 1)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
