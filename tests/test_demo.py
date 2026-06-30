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
            self.assertTrue(Path(result["report_html"]).exists())
            self.assertGreaterEqual(result["summary"]["regression"], 1)
            self.assertEqual(result["decision"]["confidence"], "high")

            report = read_json(result["report_json"])
            self.assertEqual(report["summary"]["regression"], result["summary"]["regression"])
            self.assertEqual(report["suite"], result["suite"])

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
            self.assertIn("Inspect the HTML report", output)
            self.assertIn("redline history", output)
            self.assertIn("--label demo", output)
            self.assertIn("--out-md .redline/history.md", output)
            self.assertIn("redline mark", output)
            self.assertIn("--status expected", output)
            self.assertIn("redline accept", output)
            self.assertIn("--all-expected", output)
            self.assertIn("redline app --reports-dir", output)
            self.assertIn("redline init --runner stdio --copy-runner --github-action", output)
            self.assertIn("redline runners --copy all", output)
            self.assertIn("redline suite path/to/baseline.jsonl --out redline-suite.json", output)
            self.assertIn("redline doctor --strict", output)

    def test_format_demo_quotes_app_command_with_spaced_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory) / "demo output")

            output = format_demo(result)

            self.assertIn("redline app --reports-dir", output)
            self.assertIn("--reports-dir '", output)
            self.assertIn("demo output/reports", output)

    def test_format_demo_can_use_compact_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory) / "demo")

            output = format_demo(result, compact=True)

            self.assertIn("redline demo: cases=5 regression=4", output)
            self.assertIn("REGRESSION", output)
            self.assertIn("candidate missing JSON keys", output)
            self.assertNotIn("  REGRESSION", output)

    def test_run_public_demo_writes_self_contained_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory) / "demo", public=True)

            self.assertTrue(Path(result["baseline"]).exists())
            self.assertTrue(Path(result["candidate"]).exists())
            self.assertTrue(Path(result["suite"]).exists())
            self.assertTrue(Path(result["report_json"]).exists())
            self.assertTrue(Path(result["report_html"]).exists())
            self.assertEqual(result["summary"]["cases"], 10)
            self.assertEqual(result["summary"]["regression"], 10)
            self.assertTrue(result["public"])
            self.assertEqual(read_json(result["report_json"])["suite"], result["suite"])

            output = format_demo(result, compact=True)

            self.assertIn("redline public dogfood", output)
            self.assertIn("redline public dogfood: cases=10 regression=10", output)
            self.assertIn("candidate lost valid JSON format", output)


if __name__ == "__main__":
    unittest.main()
