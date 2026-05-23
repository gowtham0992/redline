import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

from redline.cli import main


class QuickstartTests(unittest.TestCase):
    def test_readme_quickstart_path_catches_realistic_regressions(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        baseline = repo / "examples" / "baseline.jsonl"
        candidate = repo / "examples" / "candidate.jsonl"
        replay = f"{sys.executable} {repo / 'examples' / 'replay_candidate.py'}"
        judge = f"{sys.executable} {repo / 'examples' / 'judge_changed.py'}"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                demo_output = _run_cli(["demo", "--out", ".redline/demo", "--compact"])
                self.assertIn("redline demo: cases=5 regression=4", demo_output)

                suite_output = _run_cli(
                    [
                        "suite",
                        str(baseline),
                        "--out",
                        "redline-suite.json",
                    ]
                )
                self.assertIn("Generated 5 cases", suite_output)

                diff_output = _run_cli(
                    [
                        "diff",
                        "redline-suite.json",
                        str(candidate),
                        "--compact",
                        "--fail-on",
                        "none",
                    ]
                )
                self.assertIn("regression=4", diff_output)
                self.assertIn("candidate missing JSON keys", diff_output)

                eval_output = _run_cli(
                    [
                        "eval",
                        "redline-suite.json",
                        "--replay",
                        replay,
                        "--compact",
                        "--fail-on",
                        "none",
                    ]
                )
                self.assertIn("redline eval: cases=5 regression=4", eval_output)

                init_output = _run_cli(
                    [
                        "init",
                        "--replay",
                        replay,
                        "--judge",
                        judge,
                        "--github-action",
                    ]
                )
                self.assertIn("Wrote redline.json.", init_output)
                doctor_output = _run_cli(["doctor", "--strict"])
                self.assertIn("OK    config", doctor_output)
                self.assertIn("OK    suite", doctor_output)
                self.assertIn("OK    replay", doctor_output)
                self.assertIn("OK    judge", doctor_output)
            finally:
                os.chdir(previous)


def _run_cli(args: list[str]) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(args)
    if code != 0:
        raise AssertionError(f"redline {' '.join(args)} exited {code}: {output.getvalue()}")
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
