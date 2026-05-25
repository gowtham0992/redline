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
                "diffs": [
                    {
                        "case_id": "case_001",
                        "status": "regression",
                        "owner": "@platform-team",
                        "confidence": "high",
                        "signal": "structural",
                    },
                    {
                        "case_id": "case_002",
                        "status": "changed",
                        "owner": "@support-team",
                        "confidence": "medium",
                        "signal": "judge",
                    },
                ],
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
            checkpoint = root / ".redline" / "audit-checkpoint.json"
            write_json(
                checkpoint,
                {
                    "schema": "redline-audit-checkpoint-v1",
                    "ok": True,
                    "entries": 3,
                    "signed_entries": 3,
                    "unsigned_entries": 0,
                    "last_hash": "abc123",
                    "events_by_type": {"eval_run": 1, "suite_generated": 1},
                },
            )

            dashboard = build_dashboard(reports_dir=reports, history_path=history, checkpoint_path=checkpoint)
            html = format_dashboard_html(dashboard, output_path=root / ".redline" / "dashboard.html")

            self.assertEqual(len(dashboard["reports"]), 1)
            self.assertEqual(len(dashboard["history"]), 1)
            self.assertEqual(dashboard["trend"]["direction"], "baseline")
            self.assertEqual(
                dashboard["owners"],
                [
                    {"owner": "@platform-team", "blocking": 1, "changed": 0, "total": 1},
                    {"owner": "@support-team", "blocking": 0, "changed": 1, "total": 1},
                ],
            )
            self.assertEqual(
                dashboard["trust"],
                {
                    "cases": 2,
                    "confidence": {"high": 1, "medium": 1},
                    "signal": {"judge": 1, "structural": 1},
                },
            )
            self.assertEqual(
                dashboard["reports"][0]["review"],
                {"reviewable": 2, "blocking": 1, "changed": 1},
            )
            self.assertEqual(dashboard["checkpoint"]["entries"], 3)
            self.assertIn("<title>redline dashboard</title>", html)
            self.assertIn("eval.json", html)
            self.assertIn("<th>Review</th>", html)
            self.assertIn("blocking 1", html)
            self.assertIn("changed 1", html)
            self.assertIn("<h2>Trend</h2>", html)
            self.assertIn("<h2>Trust Signals</h2>", html)
            self.assertIn("<h2>Audit Checkpoint</h2>", html)
            self.assertIn("abc123", html)
            self.assertIn("eval run 1", html)
            self.assertIn("high 1", html)
            self.assertIn("structural 1", html)
            self.assertIn("<h2>Owner Review</h2>", html)
            self.assertIn("@platform-team", html)
            self.assertIn("@support-team", html)
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

    def test_dashboard_reports_invalid_checkpoint_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / ".redline" / "audit-checkpoint.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text("{not json\n", encoding="utf-8")

            dashboard = build_dashboard(
                reports_dir=root / ".redline" / "reports",
                history_path=root / ".redline" / "history.jsonl",
                checkpoint_path=checkpoint,
            )
            html = format_dashboard_html(dashboard)

            self.assertIsNone(dashboard["checkpoint"])
            self.assertEqual(len(dashboard["errors"]), 1)
            self.assertIn("Skipped Files", html)
            self.assertIn("audit-checkpoint.json", html)

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
