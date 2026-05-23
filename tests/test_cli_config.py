import contextlib
import io
import os
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


if __name__ == "__main__":
    unittest.main()
