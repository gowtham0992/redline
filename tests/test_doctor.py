import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from redline.audit import append_audit_event
from redline.doctor import doctor_report, format_doctor_report
from redline.io import LogRecord
from redline.suite import build_suite


class DoctorTests(unittest.TestCase):
    def test_doctor_report_warns_for_missing_config_and_suite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                report = doctor_report(
                    config_path="missing.json",
                    config={},
                    suite=None,
                )
            finally:
                os.chdir(previous)

        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["warnings"], 3)
        self.assertIn(
            "Create config: redline init --runner stdio --copy-runner",
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

    def test_doctor_explains_demo_suite_is_separate_from_project_suite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                demo_suite = root / ".redline" / "demo" / "suite.json"
                demo_suite.parent.mkdir(parents=True)
                demo_suite.write_text('{"cases": []}\n', encoding="utf-8")

                report = doctor_report(
                    config_path="redline.json",
                    config={"suite": "redline-suite.json"},
                    suite=None,
                )

                suite_check = next(check for check in report["checks"] if check["name"] == "suite")
                self.assertIn("redline-suite.json not found", suite_check["message"])
                self.assertIn("demo suite exists at .redline/demo/suite.json", suite_check["message"])
                self.assertIn("project CI needs its own suite", suite_check["message"])
            finally:
                os.chdir(previous)

    def test_format_doctor_report_is_readable(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        report = doctor_report(
            config_path="pyproject.toml",
            config={
                "replay": f"{sys.executable} -c pass",
                "judge": f"{sys.executable} -c pass",
                "reports": {
                    "json": ".redline/reports/doctor.json",
                    "comment": ".redline/reports/doctor-comment.md",
                    "html": ".redline/reports/doctor.html",
                    "junit": ".redline/reports/doctor.xml",
                    "slack": ".redline/reports/doctor.slack.json",
                },
                "runs": {
                    "candidate": ".redline/runs/candidate.jsonl",
                    "metadata": ".redline/runs/replay.json",
                },
            },
            suite=suite,
        )

        output = format_doctor_report(report)

        self.assertIn("redline doctor", output)
        self.assertIn("suite: found", output)
        self.assertIn("suite-validation: valid", output)
        self.assertIn("replay: configured", output)
        self.assertIn("judge: configured", output)
        self.assertIn("coverage: structural checks only", output)
        self.assertIn("requirements=0; judge=yes", output)
        self.assertIn("explicit guards=0/1", output)
        self.assertIn(
            "team-workflow: owners=0/1; owner rules=0; owner rule provenance=0/0; approval required=no",
            output,
        )
        self.assertIn("reports: json=.redline/reports/doctor.json", output)
        self.assertIn("comment=.redline/reports/doctor-comment.md", output)
        self.assertIn("html=.redline/reports/doctor.html", output)
        self.assertIn("junit=.redline/reports/doctor.xml", output)
        self.assertIn("slack=.redline/reports/doctor.slack.json", output)
        self.assertIn("runs: candidate=.redline/runs/candidate.jsonl", output)
        self.assertIn("audit: enabled at .redline/audit.jsonl", output)
        self.assertNotIn("Next:", output)

    def test_doctor_surfaces_non_ascii_suite_calibration(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Resume el caso de José", "Envíalo a soporte", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = doctor_report(
            config_path="redline.json",
            config={"replay": f"{sys.executable} -c pass"},
            suite=suite,
        )
        output = format_doctor_report(report)

        self.assertIn("non-ASCII records=1", output)
        self.assertIn("entity/refusal heuristics are English-oriented", output)

    def test_doctor_reports_prompt_manifest_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text("{}", encoding="utf-8")
                prompt_path = Path("prompts") / "support.txt"
                prompt_path.parent.mkdir()
                prompt_path.write_text("Support prompt", encoding="utf-8")
                suite_path = Path("suites") / "support.redline-suite.json"
                suite_path.parent.mkdir()
                suite = build_suite(
                    [LogRecord(1, "Return JSON", '{"ok": true}', {})],
                    source="logs/support.jsonl",
                    input_field="prompt",
                    output_field="response",
                    max_cases=10,
                )
                suite_path.write_text(json.dumps(suite), encoding="utf-8")
                manifest = {
                    "schema": "redline-prompt-manifest-v1",
                    "root": "prompts",
                    "suite_dir": "suites",
                    "prompts": [
                        {
                            "id": "support",
                            "path": str(prompt_path),
                            "suite": str(suite_path),
                        }
                    ],
                }

                report = doctor_report(
                    config_path="redline.json",
                    config={
                        "suite": "redline-prompts.json",
                        "replay": f"{sys.executable} -c pass",
                    },
                    suite=manifest,
                )
            finally:
                os.chdir(previous)

        self.assertTrue(report["ok"])
        suite_check = next(check for check in report["checks"] if check["name"] == "suite")
        self.assertEqual(suite_check["status"], "ok")
        self.assertIn(
            "found prompt manifest redline-prompts.json with 1 prompts and 1/1 mapped suites ready",
            suite_check["message"],
        )
        validation = next(check for check in report["checks"] if check["name"] == "suite-validation")
        self.assertEqual(validation["status"], "ok")
        coverage = next(check for check in report["checks"] if check["name"] == "coverage")
        self.assertIn("requirements=0; judge=no", coverage["message"])
        self.assertIn("explicit guards=0/1", coverage["message"])
        self.assertIn("no explicit requirements or recorded judgments yet", coverage["message"])
        self.assertIn(
            "Inspect explicit guard gaps: redline summary redline-prompts.json",
            report["next_steps"],
        )
        workflow = next(check for check in report["checks"] if check["name"] == "team-workflow")
        self.assertIn("owners=0/1", workflow["message"])
        self.assertIn("owner rule provenance=0/0", workflow["message"])

    def test_doctor_reports_prompt_manifest_missing_suites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text("{}", encoding="utf-8")
                prompt_path = Path("prompts") / "support.txt"
                prompt_path.parent.mkdir()
                prompt_path.write_text("Support prompt", encoding="utf-8")
                manifest = {
                    "schema": "redline-prompt-manifest-v1",
                    "root": "prompts",
                    "suite_dir": "suites",
                    "prompts": [
                        {
                            "id": "support",
                            "path": str(prompt_path),
                            "suite": "suites/support.redline-suite.json",
                        }
                    ],
                }

                report = doctor_report(
                    config_path="redline.json",
                    config={
                        "suite": "redline-prompts.json",
                        "replay": f"{sys.executable} -c pass",
                    },
                    suite=manifest,
                )
            finally:
                os.chdir(previous)

        self.assertFalse(report["ok"])
        suite_check = next(check for check in report["checks"] if check["name"] == "suite")
        self.assertIn("missing=1; invalid=0", suite_check["message"])
        validation = next(check for check in report["checks"] if check["name"] == "suite-validation")
        self.assertEqual(validation["status"], "error")
        self.assertIn("Review suite health: redline validate redline-prompts.json", report["next_steps"])

    def test_doctor_warns_when_audit_is_disabled(self) -> None:
        report = doctor_report(
            config_path="pyproject.toml",
            config={
                "replay": f"{sys.executable} -c pass",
                "audit": False,
            },
            suite={"cases": []},
        )

        audit = next(check for check in report["checks"] if check["name"] == "audit")
        self.assertEqual(audit["status"], "warn")
        self.assertIn("disabled", audit["message"])

    def test_doctor_verifies_signed_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            append_audit_event(audit_path, {"event": "suite_generated"})

            report = doctor_report(
                config_path="pyproject.toml",
                config={
                    "replay": f"{sys.executable} -c pass",
                    "audit": str(audit_path),
                },
                suite={"cases": []},
            )

        audit = next(check for check in report["checks"] if check["name"] == "audit")
        self.assertEqual(audit["status"], "ok")
        self.assertIn("hash chain ok", audit["message"])
        self.assertIn("signed events=1", audit["message"])

    def test_doctor_errors_when_audit_hash_chain_is_broken(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            append_audit_event(audit_path, {"event": "case_marked", "case_id": "case_001"})
            row = json.loads(audit_path.read_text(encoding="utf-8"))
            row["case_id"] = "case_999"
            audit_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

            report = doctor_report(
                config_path="pyproject.toml",
                config={
                    "replay": f"{sys.executable} -c pass",
                    "audit": str(audit_path),
                },
                suite={"cases": []},
            )

        audit = next(check for check in report["checks"] if check["name"] == "audit")
        self.assertEqual(audit["status"], "error")
        self.assertIn("hash chain failed", audit["message"])
        self.assertIn("Inspect audit integrity: redline audit --verify", report["next_steps"])

    def test_doctor_warns_for_legacy_unsigned_audit_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            audit_path.write_text('{"event": "legacy"}\n', encoding="utf-8")

            report = doctor_report(
                config_path="pyproject.toml",
                config={
                    "replay": f"{sys.executable} -c pass",
                    "audit": str(audit_path),
                },
                suite={"cases": []},
            )

        audit = next(check for check in report["checks"] if check["name"] == "audit")
        self.assertEqual(audit["status"], "warn")
        self.assertIn("unsigned legacy event", audit["message"])

    def test_doctor_errors_when_audit_path_is_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = doctor_report(
                config_path="pyproject.toml",
                config={
                    "replay": f"{sys.executable} -c pass",
                    "audit": directory,
                },
                suite={"cases": []},
            )

        audit = next(check for check in report["checks"] if check["name"] == "audit")
        self.assertEqual(audit["status"], "error")
        self.assertIn("is a directory", audit["message"])

    def test_doctor_calibrates_coverage_for_high_risk_suite_without_semantic_checks(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", "not json", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )

        report = doctor_report(
            config_path="pyproject.toml",
            config={"replay": f"{sys.executable} -c pass"},
            suite=suite,
        )

        coverage = next(check for check in report["checks"] if check["name"] == "coverage")
        self.assertEqual(coverage["status"], "ok")
        self.assertIn("high-risk groups=1", coverage["message"])
        self.assertIn("requirements=0; judge=no", coverage["message"])
        self.assertIn("explicit guards=0/1", coverage["message"])
        self.assertIn("add requirements or a judge", coverage["message"])
        guard_step = (
            "Add explicit guards: redline cases redline-suite.json, then "
            'redline require redline-suite.json <case_id> --include "must keep text"'
        )
        self.assertIn(guard_step, report["next_steps"])

    def test_doctor_surfaces_team_workflow_posture(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Route billing", "Billing Ops handles it.", {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
            owner_rules=[{"match": "billing", "owner": "@billing-team"}],
        )

        report = doctor_report(
            config_path="pyproject.toml",
            config={
                "replay": f"{sys.executable} -c pass",
                "owners": [{"match": "billing", "owner": "@billing-team"}],
                "approval": {"require_approver": True},
            },
            suite=suite,
        )

        team = next(check for check in report["checks"] if check["name"] == "team-workflow")
        self.assertEqual(team["status"], "ok")
        self.assertEqual(
            team["message"],
            "owners=1/1; owner rules=1; owner rule provenance=1/1; approval required=yes",
        )

    def test_doctor_warns_when_middleware_only_records_skips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                skip_log = root / ".redline" / "logs" / "middleware-skips.jsonl"
                skip_log.parent.mkdir(parents=True)
                skip_log.write_text(
                    '{"event":"middleware_capture_skipped","reason":"response_streaming","observed_at":"2026-05-25T00:00:00+00:00","source":"asgi:POST /chat","metadata":{}}\n',
                    encoding="utf-8",
                )

                report = doctor_report(
                    config_path="redline.json",
                    config={
                        "logs": {
                            "observed": ".redline/logs/prompts.jsonl",
                            "middleware_skips": ".redline/logs/middleware-skips.jsonl",
                        },
                    },
                    suite={"cases": []},
                )

                capture = next(check for check in report["checks"] if check["name"] == "capture")
                self.assertEqual(capture["status"], "warn")
                self.assertIn("observed rows=0", capture["message"])
                self.assertIn("middleware skips=1", capture["message"])
                self.assertIn("response_streaming=1", capture["message"])
                self.assertIn(
                    "Inspect capture skips: redline watch --stats --skip-log .redline/logs/middleware-skips.jsonl",
                    report["next_steps"],
                )
            finally:
                os.chdir(previous)

    def test_doctor_reports_capture_skips_as_ok_when_observations_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                logs = root / ".redline" / "logs"
                logs.mkdir(parents=True)
                (logs / "prompts.jsonl").write_text(
                    '{"prompt":"hello","response":"world","observed_at":"2026-05-25T00:00:00+00:00","source":"asgi:POST /chat","content_hash":"abc"}\n',
                    encoding="utf-8",
                )
                (logs / "middleware-skips.jsonl").write_text(
                    '{"event":"middleware_capture_skipped","reason":"prompt_field_missing","observed_at":"2026-05-25T00:00:01+00:00","source":"asgi:POST /chat","metadata":{}}\n',
                    encoding="utf-8",
                )

                report = doctor_report(
                    config_path="redline.json",
                    config={"logs": {"observed": ".redline/logs/prompts.jsonl"}},
                    suite={"cases": []},
                )

                capture = next(check for check in report["checks"] if check["name"] == "capture")
                self.assertEqual(capture["status"], "ok")
                self.assertIn("observed rows=1", capture["message"])
                self.assertIn("middleware skips=1", capture["message"])
                self.assertNotIn("Inspect capture skips", report["next_steps"])
            finally:
                os.chdir(previous)

    def test_format_doctor_report_prints_next_steps(self) -> None:
        report = doctor_report(
            config_path="missing.json",
            config={},
            suite=None,
        )

        output = format_doctor_report(report)

        self.assertIn("Next:", output)
        self.assertIn("redline init --runner stdio --copy-runner", output)

    def test_doctor_warns_for_empty_artifact_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = doctor_report(
                config_path="pyproject.toml",
                config={"reports": {}, "runs": {}, "audit": str(Path(directory) / "audit.jsonl")},
                suite={"cases": []},
            )

        self.assertEqual(report["warnings"], 4)
        self.assertTrue(any(check["name"] == "reports" for check in report["checks"]))
        self.assertTrue(any(check["name"] == "runs" for check in report["checks"]))

    def test_doctor_warns_when_suite_is_git_ignored(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        with tempfile.TemporaryDirectory() as directory:
            report = doctor_report(
                config_path="pyproject.toml",
                config={
                    "suite": ".redline/suite.json",
                    "replay": f"{sys.executable} -c pass",
                    "audit": str(Path(directory) / "audit.jsonl"),
                },
                suite=suite,
                suite_git_ignored=True,
            )

        self.assertEqual(report["warnings"], 1)
        self.assertTrue(any(check["name"] == "suite-git" for check in report["checks"]))

    def test_doctor_surfaces_suite_validation_warnings(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        del suite["cases"][0]["content_hash"]

        report = doctor_report(
            config_path="pyproject.toml",
            config={"replay": f"{sys.executable} -c pass"},
            suite=suite,
        )

        validation = next(check for check in report["checks"] if check["name"] == "suite-validation")
        self.assertEqual(validation["status"], "warn")
        self.assertIn("1 warning", validation["message"])
        self.assertIn(
            "Review suite health: redline validate redline-suite.json",
            report["next_steps"],
        )

    def test_doctor_surfaces_suite_validation_errors(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        suite["cases"][0]["features"]["valid_json"] = False

        report = doctor_report(
            config_path="pyproject.toml",
            config={"replay": f"{sys.executable} -c pass"},
            suite=suite,
        )

        validation = next(check for check in report["checks"] if check["name"] == "suite-validation")
        self.assertFalse(report["ok"])
        self.assertEqual(validation["status"], "error")
        self.assertIn("1 error", validation["message"])
        self.assertIn(
            "Review suite health: redline validate redline-suite.json",
            report["next_steps"],
        )

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

    def test_doctor_errors_for_missing_stdio_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                report = doctor_report(
                    config_path=".",
                    config={"replay": "python runners/stdio_runner.py"},
                    suite={"cases": []},
                )

                self.assertFalse(report["ok"])
                self.assertIn(
                    "Copy missing runner: redline runners --copy stdio",
                    report["next_steps"],
                )
            finally:
                os.chdir(previous)

    def test_doctor_warns_for_missing_runner_environment(self) -> None:
        suite = build_suite(
            [LogRecord(1, "Return JSON", '{"ok": true}', {})],
            source="memory",
            input_field="prompt",
            output_field="response",
            max_cases=10,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            previous_env = os.environ.pop("REDLINE_STDIO_COMMAND", None)
            os.chdir(root)
            try:
                runner = root / "runners" / "stdio_runner.py"
                runner.parent.mkdir()
                runner.write_text("print('ok')\n", encoding="utf-8")

                report = doctor_report(
                    config_path=".",
                    config={"replay": f"{sys.executable} runners/stdio_runner.py"},
                    suite=suite,
                )

                self.assertTrue(report["ok"])
                self.assertEqual(report["warnings"], 1)
                env_check = next(check for check in report["checks"] if check["name"] == "replay-env")
                self.assertEqual(env_check["status"], "warn")
                self.assertIn("REDLINE_STDIO_COMMAND", env_check["message"])
                self.assertIn(
                    "Set runner environment: missing REDLINE_STDIO_COMMAND for stdio_runner.py",
                    report["next_steps"],
                )
            finally:
                os.chdir(previous)
                if previous_env is not None:
                    os.environ["REDLINE_STDIO_COMMAND"] = previous_env

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

    def test_doctor_rejects_log_adapter_as_replay(self) -> None:
        report = doctor_report(
            config_path="redline.json",
            config={
                "replay": (
                    "python runners/jsonl_log_adapter.py logs/export.jsonl "
                    "--input-field request.prompt --output-field response.text "
                    "--out .redline/logs/prompts.jsonl"
                )
            },
            suite={"cases": []},
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["errors"], 1)
        replay_check = next(check for check in report["checks"] if check["name"] == "replay")
        self.assertEqual(replay_check["status"], "error")
        self.assertIn("jsonl-logs", replay_check["message"])
        self.assertIn("cannot be used as eval replay", replay_check["message"])
        self.assertIn(
            "Convert exported logs first: redline runners --copy jsonl-logs, "
            "then redline suite .redline/logs/prompts.jsonl --out redline-suite.json",
            report["next_steps"],
        )

    def test_doctor_errors_for_missing_replay_script_without_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                report = doctor_report(
                    config_path=".",
                    config={"replay": "python runner.py"},
                    suite={"cases": []},
                )

                self.assertFalse(report["ok"])
                self.assertTrue(
                    any(
                        check["name"] == "replay"
                        and "referenced file not found: runner.py" in check["message"]
                        for check in report["checks"]
                    )
                )
            finally:
                os.chdir(previous)

    def test_doctor_checks_configured_judge_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                judge = root / "judge.py"
                judge.write_text(
                    "import json\nprint(json.dumps({'status': 'neutral'}))\n",
                    encoding="utf-8",
                )

                report = doctor_report(
                    config_path=".",
                    config={
                        "replay": f"{sys.executable} -c pass",
                        "judge": "python judge.py",
                    },
                    suite={"cases": []},
                )

                self.assertTrue(report["ok"])
                self.assertTrue(
                    any(
                        check["name"] == "judge"
                        and check["status"] == "ok"
                        and check["message"] == "configured"
                        for check in report["checks"]
                    )
                )
            finally:
                os.chdir(previous)

    def test_doctor_errors_for_missing_judge_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                report = doctor_report(
                    config_path=".",
                    config={
                        "replay": f"{sys.executable} -c pass",
                        "judge": {"command": "python judge.py"},
                    },
                    suite={"cases": []},
                )

                self.assertFalse(report["ok"])
                self.assertTrue(
                    any(
                        check["name"] == "judge"
                        and "referenced file not found: judge.py" in check["message"]
                        for check in report["checks"]
                    )
                )
                self.assertIn(
                    "Fix judge command in redline.json, then rerun: redline doctor",
                    report["next_steps"],
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
