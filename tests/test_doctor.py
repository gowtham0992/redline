import os
import tempfile
import unittest
from pathlib import Path

from redline.doctor import doctor_report, format_doctor_report


class DoctorTests(unittest.TestCase):
    def test_doctor_report_warns_for_missing_config_and_suite(self) -> None:
        report = doctor_report(
            config_path="missing.json",
            config={},
            suite=None,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["warnings"], 3)
        self.assertIn(
            "Create config: redline init --runner openai --copy-runner",
            report["next_steps"],
        )
        self.assertIn(
            "Generate suite: redline suite path/to/log.jsonl --out redline-suite.json",
            report["next_steps"],
        )

    def test_doctor_report_errors_for_unreadable_suite(self) -> None:
        report = doctor_report(
            config_path="redline.json",
            config={"suite": ".redline/suite.json"},
            suite=None,
            suite_error="invalid JSON",
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["errors"], 1)

    def test_format_doctor_report_is_readable(self) -> None:
        report = doctor_report(
            config_path="pyproject.toml",
            config={
                "replay": "python runner.py",
                "reports": {
                    "json": ".redline/reports/doctor.json",
                    "junit": ".redline/reports/doctor.xml",
                },
                "runs": {
                    "candidate": ".redline/runs/candidate.jsonl",
                    "metadata": ".redline/runs/replay.json",
                },
            },
            suite={"cases": [{}, {}]},
        )

        output = format_doctor_report(report)

        self.assertIn("redline doctor", output)
        self.assertIn("suite: found", output)
        self.assertIn("replay: configured", output)
        self.assertIn("reports: json=.redline/reports/doctor.json", output)
        self.assertIn("junit=.redline/reports/doctor.xml", output)
        self.assertIn("runs: candidate=.redline/runs/candidate.jsonl", output)
        self.assertNotIn("Next:", output)

    def test_format_doctor_report_prints_next_steps(self) -> None:
        report = doctor_report(
            config_path="missing.json",
            config={},
            suite=None,
        )

        output = format_doctor_report(report)

        self.assertIn("Next:", output)
        self.assertIn("redline init --runner openai --copy-runner", output)

    def test_doctor_warns_for_empty_artifact_sections(self) -> None:
        report = doctor_report(
            config_path="pyproject.toml",
            config={"reports": {}, "runs": {}},
            suite={"cases": []},
        )

        self.assertEqual(report["warnings"], 3)
        self.assertTrue(any(check["name"] == "reports" for check in report["checks"]))
        self.assertTrue(any(check["name"] == "runs" for check in report["checks"]))

    def test_doctor_warns_when_suite_is_git_ignored(self) -> None:
        report = doctor_report(
            config_path="pyproject.toml",
            config={"suite": ".redline/suite.json", "replay": "python runner.py"},
            suite={"cases": [{}]},
            suite_git_ignored=True,
        )

        self.assertEqual(report["warnings"], 1)
        self.assertTrue(any(check["name"] == "suite-git" for check in report["checks"]))

    def test_doctor_errors_for_missing_replay_command_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                report = doctor_report(
                    config_path=".",
                    config={"replay": "./runners/openai_runner.sh"},
                    suite={"cases": []},
                )

                self.assertFalse(report["ok"])
                self.assertEqual(report["errors"], 1)
                self.assertTrue(
                    any(
                        check["name"] == "replay"
                        and "command path not found" in check["message"]
                        for check in report["checks"]
                    )
                )
                self.assertIn(
                    "Copy missing runner: redline runners --copy openai",
                    report["next_steps"],
                )
            finally:
                os.chdir(previous)

    def test_doctor_errors_for_missing_replay_script_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                report = doctor_report(
                    config_path=".",
                    config={"replay": "python runners/http_runner.py"},
                    suite={"cases": []},
                )

                self.assertFalse(report["ok"])
                self.assertEqual(report["errors"], 1)
                self.assertTrue(
                    any(
                        check["name"] == "replay"
                        and "referenced file not found" in check["message"]
                        for check in report["checks"]
                    )
                )
            finally:
                os.chdir(previous)

    def test_doctor_accepts_existing_replay_command_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                runner = root / "runners" / "openai_runner.sh"
                runner.parent.mkdir()
                runner.write_text("#!/bin/sh\ncat\n", encoding="utf-8")
                runner.chmod(0o755)

                report = doctor_report(
                    config_path=".",
                    config={"replay": "./runners/openai_runner.sh"},
                    suite={"cases": []},
                )

                self.assertTrue(report["ok"])
                self.assertEqual(report["errors"], 0)
                self.assertTrue(
                    any(
                        check["name"] == "replay"
                        and check["status"] == "ok"
                        and check["message"] == "configured"
                        for check in report["checks"]
                    )
                )
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
