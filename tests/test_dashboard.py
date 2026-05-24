import json
import tempfile
import unittest
from pathlib import Path

from redline.cli import main
from redline.dashboard import build_dashboard, format_dashboard_html
from redline.io import write_json


class DashboardTests(unittest.TestCase):
    def test_dashboard_collects_reports_history_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / ".redline" / "reports"
            report = {
                "summary": {
                    "cases": 2,
                    "regression": 1,
                    "changed": 1,
                    "missing": 0,
                    "neutral": 0,
                },
                "decision": {"recommended_action": "review changed cases before shipping"},
                "diffs": [],
            }
            write_json(reports / "eval.json", report)
            (reports / "eval.html").write_text("<!doctype html>\n", encoding="utf-8")
            history = root / ".redline" / "history.jsonl"
            history.parent.mkdir(parents=True, exist_ok=True)
            history.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-05-24T00:00:00Z",
                        "label": "prompt-v2",
                        "report": str(reports / "eval.json"),
                        "summary": report["summary"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            dashboard = build_dashboard(reports_dir=reports, history_path=history)
            html = format_dashboard_html(dashboard, output_path=root / ".redline" / "dashboard.html")

            self.assertEqual(len(dashboard["reports"]), 1)
            self.assertEqual(len(dashboard["history"]), 1)
            self.assertIn("<title>redline dashboard</title>", html)
            self.assertIn("eval.json", html)
            self.assertIn("regression 1", html)
            self.assertIn("prompt-v2", html)
            self.assertIn("reports/eval.html", html)
            self.assertIn("structural checks only", html)

    def test_dashboard_escapes_report_fields(self) -> None:
        dashboard = {
            "reports": [
                {
                    "name": "<script>alert(1)</script>.json",
                    "kind": "diff",
                    "summary": {"cases": 1},
                    "decision": {"recommended_action": "<b>ship</b>"},
                    "path": "report.json",
                }
            ],
            "history": [],
            "scope": "structural checks only",
        }

        html = format_dashboard_html(dashboard)

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;.json", html)
        self.assertIn("&lt;b&gt;ship&lt;/b&gt;", html)

    def test_dashboard_skips_invalid_local_files_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / ".redline" / "reports"
            reports.mkdir(parents=True)
            (reports / "bad.json").write_text("{not json\n", encoding="utf-8")
            write_json(reports / "note.json", {"not": "a redline report"})

            dashboard = build_dashboard(reports_dir=reports, history_path=root / "missing.jsonl")
            html = format_dashboard_html(dashboard)

            self.assertEqual(dashboard["reports"], [])
            self.assertEqual(len(dashboard["errors"]), 2)
            self.assertIn("Skipped Files", html)
            self.assertIn("bad.json", html)
            self.assertIn("missing summary object", html)

    def test_cli_writes_dashboard_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / ".redline" / "reports"
            write_json(
                reports / "diff.json",
                {
                    "summary": {"cases": 1, "regression": 1},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                    "diffs": [],
                },
            )
            output = root / ".redline" / "dashboard.html"

            current = Path.cwd()
            try:
                import os

                os.chdir(root)
                code = main(["dashboard", "--out", str(output)])
            finally:
                os.chdir(current)

            self.assertEqual(code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("redline dashboard", text)
            self.assertIn("diff.json", text)


if __name__ == "__main__":
    unittest.main()
