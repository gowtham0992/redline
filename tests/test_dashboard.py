import contextlib
import io
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
                    "cases": 5,
                    "regression": 1,
                    "changed": 1,
                    "missing": 0,
                    "neutral": 3,
                },
                "decision": {"recommended_action": "review changed cases before shipping"},
                "prompt_evals": [
                    {
                        "id": "support/triage",
                        "prompt": "prompts/support/triage.txt",
                        "suite": "suites/support/triage.redline-suite.json",
                        "summary": {"cases": 2, "regression": 1, "changed": 1},
                        "decision": {"recommended_action": "fix blocking cases before shipping"},
                    },
                    {
                        "id": "billing/refund",
                        "prompt": "prompts/billing/refund.txt",
                        "suite": "suites/billing/refund.redline-suite.json",
                        "summary": {"cases": 3, "neutral": 3},
                        "decision": {"recommended_action": "ship candidate; no blocking changes detected"},
                    }
                ],
                "diffs": [
                    {
                        "case_id": "case_001",
                        "status": "regression",
                        "owner": "@platform-team",
                        "confidence": "high",
                        "signal": "structural",
                        "prompt": "Return JSON with owner and priority.",
                        "reasons": ["candidate lost valid JSON format"],
                        "prompt_path": "prompts/support/triage.txt",
                        "suite": "suites/support/triage.redline-suite.json",
                    },
                    {
                        "case_id": "case_002",
                        "status": "changed",
                        "owner": "@support-team",
                        "confidence": "medium",
                        "signal": "judge",
                        "prompt": "Summarize the support ticket.",
                        "reasons": ["judge marked behavior changed"],
                    },
                ],
            }
            write_json(reports / "eval.json", report)
            (reports / "eval.html").write_text("<!doctype html>\n", encoding="utf-8")
            write_json(
                reports / "benchmark.json",
                {
                    "mode": "static_eval_budget_estimate",
                    "suite": "redline-suite.json",
                    "cases": 5,
                    "workers": 2,
                    "timeout_seconds": 30,
                    "worst_case_seconds": 90,
                    "sequential_worst_case_seconds": 150,
                    "within_budget": True,
                    "status": "ok",
                    "local_measurement": {
                        "mode": "deterministic_baseline_self_check",
                        "iterations": 1,
                        "cases": 5,
                        "cases_processed": 5,
                        "seconds": 0.005,
                        "cases_per_second": 1000,
                    },
                },
            )
            (reports / "benchmark.md").write_text("## redline benchmark\n", encoding="utf-8")
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
            self.assertEqual(len(dashboard["benchmarks"]), 1)
            self.assertEqual(dashboard["notices"], [])
            self.assertEqual(dashboard["benchmarks"][0]["suite"], "redline-suite.json")
            self.assertEqual(dashboard["benchmarks"][0]["cases"], 5)
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
            self.assertEqual(dashboard["reports"][0]["review_cases"][0]["case_id"], "case_001")
            self.assertEqual(
                dashboard["reports"][0]["review_cases"][0]["reason"],
                "candidate lost valid JSON format",
            )
            self.assertEqual(dashboard["checkpoint"]["entries"], 3)
            self.assertEqual(
                dashboard["reports"][0]["prompt_evals"],
                [
                    {
                        "id": "support/triage",
                        "prompt": "prompts/support/triage.txt",
                        "suite": "suites/support/triage.redline-suite.json",
                        "summary": {"cases": 2, "regression": 1, "changed": 1},
                        "decision": {"recommended_action": "fix blocking cases before shipping"},
                    },
                    {
                        "id": "billing/refund",
                        "prompt": "prompts/billing/refund.txt",
                        "suite": "suites/billing/refund.redline-suite.json",
                        "summary": {"cases": 3, "neutral": 3},
                        "decision": {"recommended_action": "ship candidate; no blocking changes detected"},
                    }
                ],
            )
            self.assertEqual(
                dashboard["reports"][0]["prompt_groups"],
                [
                    {
                        "feature": "support",
                        "prompt_count": 1,
                        "summary": {"cases": 2, "regression": 1, "changed": 1},
                        "action": "fix blocking cases before shipping",
                    },
                    {
                        "feature": "billing",
                        "prompt_count": 1,
                        "summary": {"cases": 3, "neutral": 3},
                        "action": "clean",
                    },
                ],
            )
            self.assertIn("<title>redline dashboard</title>", html)
            self.assertIn("eval.json", html)
            self.assertIn("<span>Benchmarks</span><strong>1</strong>", html)
            self.assertIn("<h2>Ship Readiness</h2>", html)
            self.assertIn("Blocked", html)
            self.assertIn("Fix blocking cases or mark intentional changes before shipping.", html)
            self.assertIn("redline mark suites/support/triage.redline-suite.json case_001", html)
            self.assertIn("<h2>Feature Summary</h2>", html)
            self.assertIn("support", html)
            self.assertIn("billing", html)
            self.assertIn("fix blocking cases before shipping", html)
            self.assertIn("clean", html)
            self.assertIn("<h2>Prompt Evals</h2>", html)
            self.assertIn("support/triage", html)
            self.assertIn("billing/refund", html)
            self.assertIn("prompts/support/triage.txt", html)
            self.assertIn("suites/support/triage.redline-suite.json", html)
            self.assertIn("<h2>Review Queue</h2>", html)
            self.assertIn("case_001", html)
            self.assertIn("candidate lost valid JSON format", html)
            self.assertIn("Return JSON with owner and priority.", html)
            self.assertIn("<th>Review</th>", html)
            self.assertIn("blocking 1", html)
            self.assertIn("changed 1", html)
            self.assertIn("<h2>Trend</h2>", html)
            self.assertIn("<h2>Benchmark Evidence</h2>", html)
            self.assertIn("benchmark.json", html)
            self.assertIn("redline-suite.json", html)
            self.assertIn("1m 30s", html)
            self.assertIn("5ms for 5 cases", html)
            self.assertIn("1000 cases/sec", html)
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
            self.assertNotIn("Missing benchmark evidence", html)

    def test_dashboard_warns_when_reports_have_no_benchmark_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / ".redline" / "reports"
            write_json(
                reports / "eval.json",
                {
                    "summary": {"cases": 2, "regression": 1, "neutral": 1},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                    "diffs": [],
                },
            )

            dashboard = build_dashboard(reports_dir=reports, history_path=root / ".redline" / "history.jsonl")
            html = format_dashboard_html(dashboard)

            self.assertEqual(len(dashboard["reports"]), 1)
            self.assertEqual(dashboard["benchmarks"], [])
            self.assertEqual(len(dashboard["notices"]), 1)
            self.assertEqual(dashboard["notices"][0]["kind"], "benchmark_missing")
            self.assertIn("Missing benchmark evidence", html)
            self.assertIn("Reports exist, but no benchmark artifact was found.", html)
            self.assertIn("redline benchmark redline-suite.json --measure-local", html)
            self.assertIn("<span>Benchmarks</span><strong>0</strong>", html)

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
            write_json(
                reports / "benchmark.json",
                {
                    "mode": "static_eval_budget_estimate",
                    "suite": "redline-suite.json",
                    "cases": 1,
                    "workers": 1,
                    "worst_case_seconds": 30,
                    "within_budget": True,
                },
            )
            output = root / ".redline" / "dashboard.html"

            current = Path.cwd()
            stdout = io.StringIO()
            try:
                import os

                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = main(["dashboard", "--out", str(output)])
            finally:
                os.chdir(current)

            self.assertEqual(code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("redline dashboard", text)
            self.assertIn("diff.json", text)
            self.assertIn("<span>Benchmarks</span><strong>1</strong>", text)
            self.assertIn("Benchmarks: 1", stdout.getvalue())
            self.assertIn("Notices: 0", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
