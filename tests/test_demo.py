import tempfile
import unittest
from pathlib import Path

from redline.demo import format_demo, run_demo
from redline.io import read_json


class DemoTests(unittest.TestCase):
    def test_run_demo_writes_artifacts_and_finds_regressions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory) / "demo")

            self.assertTrue(Path(result["baseline"]).exists())
            self.assertTrue(Path(result["candidate"]).exists())
            self.assertTrue(Path(result["prompt"]).exists())
            self.assertTrue(Path(result["suite"]).exists())
            self.assertTrue(Path(result["report_json"]).exists())
            self.assertTrue(Path(result["report_markdown"]).exists())
            self.assertGreaterEqual(result["summary"]["regression"], 1)
            self.assertEqual(result["decision"]["confidence"], "high")

            report = read_json(result["report_json"])
            self.assertEqual(report["summary"]["regression"], result["summary"]["regression"])

    def test_format_demo_includes_regression_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory) / "demo")

            output = format_demo(result)

            self.assertIn("redline demo", output)
            self.assertIn("support-agent regression demo", output)
            self.assertIn("drops required production details", output)
            self.assertIn("REGRESSION", output)
            self.assertIn("candidate missing JSON keys", output)
            self.assertIn("candidate missing URLs", output)
            self.assertIn("Next steps", output)
            self.assertIn("redline init --runner openai --copy-runner --github-action", output)
            self.assertIn("redline runners --copy all", output)
            self.assertIn("redline suite path/to/baseline.jsonl --out redline-suite.json", output)
            self.assertIn("redline doctor --strict", output)

    def test_format_demo_can_use_compact_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory) / "demo")

            output = format_demo(result, compact=True)

            self.assertIn("redline demo: cases=5 regression=4", output)
            self.assertIn("REGRESSION", output)
            self.assertIn("candidate missing JSON keys", output)
            self.assertNotIn("  REGRESSION", output)


if __name__ == "__main__":
    unittest.main()
