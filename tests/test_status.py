import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from redline.cli import main
from redline.io import LogRecord, write_json
from redline.suite import build_suite


class StatusTests(unittest.TestCase):
    def test_status_guides_uninitialized_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["status"]), 0)
            finally:
                os.chdir(previous)

        text = output.getvalue()
        self.assertIn("redline status", text)
        self.assertIn("State: SETUP - project is not initialized", text)
        self.assertIn("Next:  redline init --runner stdio --copy-runner", text)
        self.assertIn(
            "App:   redline app --reports-dir .redline/reports --history .redline/history.jsonl --checkpoint .redline/audit-checkpoint.json",
            text,
        )
        self.assertIn("- Config: warn - redline.json not found", text)
        self.assertIn("- No redline report found yet.", text)

    def test_status_surfaces_blocking_latest_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(
                root / "redline.json",
                {
                    "suite": "redline-suite.json",
                    "replay": f"{sys.executable} -c 'import sys; print(sys.stdin.read())'",
                    "reports": {"json": ".redline/reports/eval.json"},
                },
            )
            suite = build_suite(
                [LogRecord(1, "Return JSON with owner.", '{"owner":"support"}', {})],
                source="baseline.jsonl",
                input_field="prompt",
                output_field="response",
                all_cases=True,
            )
            write_json(root / "redline-suite.json", suite)
            write_json(
                root / ".redline" / "reports" / "eval.json",
                {
                    "suite": "redline-suite.json",
                    "summary": {"cases": 1, "regression": 1, "missing": 0, "changed": 0, "neutral": 0},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                    "diffs": [
                        {
                            "case_id": "case_001",
                            "suite_case_id": "case_001",
                            "status": "regression",
                            "prompt": "Return JSON with owner.",
                            "reasons": ["candidate lost valid JSON format"],
                        }
                    ],
                },
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["status"]), 0)
                json_output = io.StringIO()
                with contextlib.redirect_stdout(json_output):
                    self.assertEqual(main(["status", "--json"]), 0)
            finally:
                os.chdir(previous)

        text = output.getvalue()
        self.assertIn("State: BLOCKED - latest report has 1 blocking case(s)", text)
        self.assertIn("Next:  redline case redline-suite.json case_001", text)
        self.assertIn(
            "App:   redline app --reports-dir .redline/reports --history .redline/history.jsonl --checkpoint .redline/audit-checkpoint.json",
            text,
        )
        self.assertIn("- Reports: 1 in .redline/reports", text)
        self.assertIn("- Summary: cases=1 regression=1 missing=0 changed=0 neutral=0", text)
        self.assertIn("- Decision: fix blocking cases before shipping", text)
        self.assertIn("First review case", text)
        self.assertIn("- Case: case_001 (regression)", text)
        self.assertIn("- Reason: candidate lost valid JSON format", text)
        self.assertIn(
            "- Impact: Downstream code may fail if consumers expect parseable JSON or required fields.",
            text,
        )
        self.assertIn("- Command: redline case redline-suite.json case_001", text)

        payload = json.loads(json_output.getvalue())
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["blocking"], 1)
        self.assertEqual(payload["next_command"], "redline case redline-suite.json case_001")
        self.assertEqual(
            payload["app_command"],
            "redline app --reports-dir .redline/reports --history .redline/history.jsonl --checkpoint .redline/audit-checkpoint.json",
        )
        self.assertEqual(
            payload["first_review_case"],
            {
                "case_id": "case_001",
                "status": "regression",
                "reason": "candidate lost valid JSON format",
                "impact": "Downstream code may fail if consumers expect parseable JSON or required fields.",
                "command": "redline case redline-suite.json case_001",
            },
        )

    def test_status_quotes_app_command_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "status",
                                "--reports-dir",
                                "redline reports",
                                "--history",
                                "history file.jsonl",
                                "--checkpoint",
                                "audit checkpoint.json",
                            ]
                        ),
                        0,
                    )
            finally:
                os.chdir(previous)

        self.assertIn(
            "App:   redline app --reports-dir 'redline reports' --history 'history file.jsonl' --checkpoint 'audit checkpoint.json'",
            output.getvalue(),
        )

    def test_status_quotes_review_case_command_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite_path = "suite files/redline suite.json"
            write_json(
                root / "redline.json",
                {
                    "suite": suite_path,
                    "replay": f"{sys.executable} -c 'import sys; print(sys.stdin.read())'",
                    "reports": {"json": ".redline/reports/eval.json"},
                },
            )
            suite = build_suite(
                [LogRecord(1, "Return JSON with owner.", '{"owner":"support"}', {})],
                source="baseline.jsonl",
                input_field="prompt",
                output_field="response",
                all_cases=True,
            )
            write_json(root / suite_path, suite)
            write_json(
                root / ".redline" / "reports" / "eval.json",
                {
                    "suite": suite_path,
                    "summary": {"cases": 1, "regression": 1},
                    "decision": {"recommended_action": "fix blocking cases before shipping"},
                    "diffs": [
                        {
                            "case_id": "case needs review",
                            "status": "regression",
                            "prompt": "Return JSON with owner.",
                            "reasons": ["candidate lost valid JSON format"],
                            "suite": suite_path,
                        }
                    ],
                },
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["status"]), 0)
            finally:
                os.chdir(previous)

        text = output.getvalue()
        self.assertIn("Next:  redline case 'suite files/redline suite.json' 'case needs review'", text)
        self.assertIn("- Command: redline case 'suite files/redline suite.json' 'case needs review'", text)
