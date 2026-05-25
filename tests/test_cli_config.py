import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from redline.cli import main


class CliConfigTests(unittest.TestCase):
    def test_bare_cli_prints_first_run_help(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.assertEqual(main([]), 0)

        text = output.getvalue()
        self.assertIn("Start here:", text)
        self.assertIn("redline demo", text)
        self.assertIn("redline init --runner stdio --copy-runner", text)
        self.assertIn("Review loop:", text)
        self.assertIn("redline suite add redline-suite.json", text)
        self.assertIn("redline eval redline-prompts.json", text)
        self.assertIn("redline <command> --help", text)

    def test_root_help_prints_first_run_help(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--help"]), 0)

        text = output.getvalue()
        self.assertIn("Start here:", text)
        self.assertIn("redline demo", text)
        self.assertNotIn("suite-add", text)
        self.assertNotIn("==SUPPRESS==", text)

    def test_cli_version_flag_prints_version(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("redline 0.1.0", output.getvalue())

    def test_init_help_lists_only_replay_runners(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                main(["init", "--help"])

        self.assertEqual(raised.exception.code, 0)
        text = output.getvalue()
        self.assertIn("{stdio,openai,anthropic,python-chain,http,litellm}", text)
        self.assertNotIn("jsonl-logs", text)

    def test_demo_command_can_print_compact_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(["demo", "--out", str(Path(directory) / "demo"), "--compact"]),
                    0,
                )

            text = output.getvalue()
            self.assertIn("redline demo: cases=5 regression=4", text)
            self.assertIn("REGRESSION", text)

    def test_demo_command_can_run_public_fixture_from_any_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["demo", "--public", "--compact"]), 0)

                text = output.getvalue()
                self.assertIn("redline public dogfood: cases=10 regression=10", text)
                self.assertIn("candidate lost valid JSON format", text)
                self.assertTrue((root / ".redline" / "demo" / "public_baseline.jsonl").exists())
                self.assertTrue((root / ".redline" / "demo" / "public_candidate.jsonl").exists())
            finally:
                os.chdir(previous)

    def test_runners_command_lists_adapter_commands(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["runners"]), 0)

        text = output.getvalue()
        self.assertIn("redline runners", text)
        self.assertIn("Custom stdio command", text)
        self.assertIn("OpenAI direct", text)
        self.assertIn("OpenAI SDK capture", text)
        self.assertIn("python runners/stdio_runner.py", text)
        self.assertIn("./runners/openai_runner.sh", text)
        self.assertIn("Capture: python runners/openai_watch_patch.py", text)

    def test_runners_command_can_copy_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(["runners", "--copy", "openai", "--out", str(root / "openai.sh")]),
                    0,
                )

            self.assertTrue((root / "openai.sh").exists())
            text = output.getvalue()
            self.assertIn("Replay:", text)
            self.assertIn("Setup:  Set OPENAI_API_KEY", text)
            self.assertIn("Next:   Configure replay: redline init --replay", text)

    def test_runners_command_prints_log_adapter_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(["runners", "--copy", "jsonl-logs", "--out", str(root / "adapter.py")]),
                    0,
                )

            self.assertTrue((root / "adapter.py").exists())
            text = output.getvalue()
            self.assertIn("Command:", text)
            self.assertIn("Setup:  Export app logs as JSONL", text)
            self.assertIn("Next:   Run adapter command, then build a suite", text)
            self.assertIn("redline suite .redline/logs/prompts.jsonl", text)

    def test_runners_command_can_copy_all_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["runners", "--copy", "all"]), 0)

                self.assertTrue((root / "runners" / "openai_runner.sh").exists())
                self.assertTrue((root / "runners" / "http_runner.py").exists())
                self.assertIn("Adapter commands:", output.getvalue())
                self.assertIn("jsonl-logs (command):", output.getvalue())
                self.assertIn("openai-sdk (capture):", output.getvalue())
                self.assertIn("Next:", output.getvalue())
                self.assertIn("Configure replay: redline init --replay", output.getvalue())
                self.assertIn("Run adapter command, then build a suite", output.getvalue())
                self.assertIn("Patch your app client", output.getvalue())
            finally:
                os.chdir(previous)

    def test_runners_command_refuses_out_with_copy_all(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["runners", "--copy", "all", "--out", "runner.sh"])

                self.assertEqual(code, 2)
                self.assertIn("--out can only be used", stderr.getvalue())
            finally:
                os.chdir(previous)

    def test_judges_command_lists_templates(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["judges"]), 0)

        text = output.getvalue()
        self.assertIn("redline judges", text)
        self.assertIn("OpenAI judge", text)
        self.assertIn("./judges/openai_judge.sh", text)
        self.assertIn("Support-agent rubric", text)
        self.assertIn("REDLINE_JUDGE_RUBRIC=judges/support_rubric.md", text)

    def test_judges_command_can_copy_model_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(["judges", "--copy", "openai", "--out", str(root / "openai_judge.sh")]),
                    0,
                )

            self.assertTrue((root / "openai_judge.sh").exists())
            text = output.getvalue()
            self.assertIn("Judge:", text)
            self.assertIn("Setup:  Set OPENAI_API_KEY", text)
            self.assertIn("Next:   Configure judge: redline init --judge", text)

    def test_judges_command_can_copy_rubric(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    main(["judges", "--copy", "support-rubric", "--out", str(root / "support.md")]),
                    0,
                )

            self.assertTrue((root / "support.md").exists())
            text = output.getvalue()
            self.assertIn("Rubric: REDLINE_JUDGE_RUBRIC=", text)
            self.assertIn("Setup:  Use through REDLINE_JUDGE_RUBRIC", text)
            self.assertIn("Next:   Use with a model judge", text)

    def test_judges_command_can_copy_all_templates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["judges", "--copy", "all"]), 0)

                self.assertTrue((root / "judges" / "openai_judge.sh").exists())
                self.assertTrue((root / "judges" / "support_rubric.md").exists())
                self.assertIn("Judge commands:", output.getvalue())
                self.assertIn("openai (judge):", output.getvalue())
                self.assertIn("support-rubric (rubric):", output.getvalue())
                self.assertIn("Configure judge: redline init --judge", output.getvalue())
                self.assertIn("Use with a model judge", output.getvalue())
            finally:
                os.chdir(previous)

    def test_judges_command_refuses_out_with_copy_all(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["judges", "--copy", "all", "--out", "judge.sh"])

                self.assertEqual(code, 2)
                self.assertIn("--out can only be used", stderr.getvalue())
            finally:
                os.chdir(previous)

    def test_init_can_write_github_action_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(["init", "--replay", "python runner.py", "--github-action"]),
                        0,
                    )

                workflow = root / ".github" / "workflows" / "redline.yml"
                config = json.loads((root / "redline.json").read_text(encoding="utf-8"))
                self.assertEqual(config["replay"], "python runner.py")
                self.assertEqual(config["suite"], "redline-suite.json")
                self.assertTrue(workflow.exists())
                self.assertIn("--github-annotations", workflow.read_text(encoding="utf-8"))
                self.assertIn('"redline-suite.json"', workflow.read_text(encoding="utf-8"))
                self.assertIn("Wrote redline.json.", output.getvalue())
                self.assertIn("Wrote .github/workflows/redline.yml.", output.getvalue())
                self.assertIn("regressions and missing outputs fail by default", output.getvalue())
                self.assertIn("Next:", output.getvalue())
                self.assertIn("redline suite path/to/log.jsonl", output.getvalue())
            finally:
                os.chdir(previous)

    def test_init_without_replay_suggests_runner_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["init"]), 0)

                text = output.getvalue()
                self.assertIn("Wrote redline.json.", text)
                self.assertIn("Connect a runner: redline init --runner stdio --copy-runner --force", text)
                self.assertIn("Check setup: redline doctor", text)
            finally:
                os.chdir(previous)

    def test_init_with_runner_prints_runner_setup_hint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["init", "--runner", "stdio", "--copy-runner"]), 0)

                text = output.getvalue()
                self.assertIn("Replay: python runners/stdio_runner.py", text)
                self.assertIn("Setup:  Set REDLINE_STDIO_COMMAND", text)
            finally:
                os.chdir(previous)

    def test_init_can_store_judge_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "init",
                                "--judge",
                                "python examples/judge_changed.py",
                                "--judge-timeout",
                                "6.5",
                            ]
                        ),
                        0,
                    )

                config = json.loads((root / "redline.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    config["judge"],
                    {
                        "command": "python examples/judge_changed.py",
                        "timeout_seconds": 6.5,
                    },
                )
            finally:
                os.chdir(previous)

    def test_init_refuses_judge_timeout_without_judge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["init", "--judge-timeout", "6.5"])

                self.assertEqual(code, 2)
                self.assertIn("use --judge-timeout with --judge", stderr.getvalue())
                self.assertFalse(Path("redline.json").exists())
            finally:
                os.chdir(previous)

    def test_init_can_store_runner_adapter_replay_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["init", "--runner", "openai"]), 0)

                config = json.loads((root / "redline.json").read_text(encoding="utf-8"))
                self.assertEqual(config["replay"], "./runners/openai_runner.sh")
            finally:
                os.chdir(previous)

    def test_init_can_copy_runner_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(["init", "--runner", "openai", "--copy-runner"]),
                        0,
                    )

                runner = root / "runners" / "openai_runner.sh"
                config = json.loads((root / "redline.json").read_text(encoding="utf-8"))
                self.assertEqual(config["replay"], "./runners/openai_runner.sh")
                self.assertTrue(runner.exists())
                self.assertTrue(runner.stat().st_mode & 0o111)
                self.assertIn("Wrote redline.json.", output.getvalue())
                self.assertIn("Wrote runners/openai_runner.sh.", output.getvalue())
                self.assertIn("Replay: ./runners/openai_runner.sh", output.getvalue())
            finally:
                os.chdir(previous)

    def test_init_refuses_runner_and_replay_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["init", "--runner", "openai", "--replay", "python runner.py"])

                self.assertEqual(code, 2)
                self.assertIn("use --replay or --runner", stderr.getvalue())
            finally:
                os.chdir(previous)

    def test_init_refuses_log_adapter_as_replay_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["init", "--runner", "jsonl-logs"])

                self.assertEqual(code, 2)
                self.assertIn("jsonl-logs converts logs", stderr.getvalue())
                self.assertFalse(Path("redline.json").exists())
            finally:
                os.chdir(previous)

    def test_init_refuses_copy_runner_without_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["init", "--copy-runner"])

                self.assertEqual(code, 2)
                self.assertIn("use --copy-runner with --runner", stderr.getvalue())
                self.assertFalse(Path("redline.json").exists())
            finally:
                os.chdir(previous)

    def test_init_refuses_existing_github_action_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                workflow = root / ".github" / "workflows" / "redline.yml"
                workflow.parent.mkdir(parents=True)
                workflow.write_text("existing\n", encoding="utf-8")

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["init", "--github-action"])

                self.assertEqual(code, 2)
                self.assertIn("already exists", stderr.getvalue())
                self.assertFalse((root / "redline.json").exists())
            finally:
                os.chdir(previous)

    def test_doctor_strict_fails_on_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["doctor", "--strict"])

                self.assertEqual(code, 1)
                self.assertIn("Warnings:", output.getvalue())
            finally:
                os.chdir(previous)

    def test_suite_and_diff_use_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "input_field": "input",
                            "output_field": "output",
                            "max_cases": 3,
                            "fail_on": "none",
                            "reports": {
                                "json": ".redline/reports/{command}.json",
                                "markdown": ".redline/reports/{command}.md",
                                "html": ".redline/reports/{command}.html",
                                "junit": ".redline/reports/{command}.xml",
                            },
                        }
                    ),
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
                self.assertTrue((root / ".redline" / "reports" / "diff.json").exists())
                self.assertTrue((root / ".redline" / "reports" / "diff.md").exists())
                self.assertTrue((root / ".redline" / "reports" / "diff.html").exists())
                self.assertTrue((root / ".redline" / "reports" / "diff.xml").exists())
                html = (root / ".redline" / "reports" / "diff.html").read_text(encoding="utf-8")
                self.assertIn("<!doctype html>", html)
                self.assertIn("candidate lost valid JSON format", html)
            finally:
                os.chdir(previous)

    def test_diff_profile_review_downgrades_number_and_entity_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "diff_profile": "review",
                            "fail_on": "none",
                            "reports": {"json": ".redline/reports/{command}.json"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Route this support ticket", "response": "Route Ada Lovelace to ACME support within 30 minutes."}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Route this support ticket", "response": "Route the customer to support soon."}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["diff", "candidate.jsonl"]), 0)

                report = json.loads((root / ".redline" / "reports" / "diff.json").read_text(encoding="utf-8"))
                self.assertEqual(report["profile"], "review")
                self.assertEqual(report["summary"]["regression"], 0)
                self.assertEqual(report["summary"]["changed"], 1)
                self.assertTrue(
                    any("candidate missing numbers" in reason for reason in report["diffs"][0]["reasons"])
                )
            finally:
                os.chdir(previous)

    def test_suite_all_cases_keeps_every_log_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON for Ada", "response": "{\\"name\\":\\"Ada\\"}"}\n'
                    '{"prompt": "Return JSON for Bob", "response": "{\\"name\\":\\"Bob\\"}"}\n'
                    '{"prompt": "Return JSON for Cy", "response": "{\\"name\\":\\"Cy\\"}"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(["suite", "baseline.jsonl", "--out", "suite.json", "--max-cases", "1"]),
                        0,
                    )
                representative = json.loads(Path("suite.json").read_text(encoding="utf-8"))

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "all.json", "--all-cases"]), 0)
                all_cases = json.loads(Path("all.json").read_text(encoding="utf-8"))

                self.assertEqual(representative["summary"]["cases"], 1)
                self.assertEqual(all_cases["summary"]["cases"], 3)
                self.assertEqual(all_cases["summary"]["selection"], "all")
            finally:
                os.chdir(previous)

    def test_suite_reports_skipped_duplicate_prompt_response_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON for Ada", "response": "{\\"name\\":\\"Ada\\"}"}\n'
                    '{"prompt": "Return JSON for Ada", "response": "{\\"name\\":\\"Ada\\"}"}\n'
                    '{"prompt": "Summarize", "response": "- one\\n- two"}\n',
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json", "--all-cases"]), 0)

                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                self.assertEqual(suite["summary"]["records_seen"], 3)
                self.assertEqual(suite["summary"]["unique_prompt_response_pairs"], 2)
                self.assertEqual(suite["summary"]["duplicate_prompt_response_pairs"], 1)
                self.assertEqual(suite["summary"]["cases"], 2)
                self.assertIn("Skipped 1 duplicate prompt-response pairs.", output.getvalue())
            finally:
                os.chdir(previous)

    def test_suite_and_diff_append_audit_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": "suite.json",
                            "fail_on": "none",
                            "audit": ".redline/audit.jsonl",
                            "reports": {"json": ".redline/reports/{command}.json"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "ok"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["diff", "candidate.jsonl"]), 0)

                rows = [
                    json.loads(line)
                    for line in (root / ".redline" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual([row["event"] for row in rows], ["suite_generated", "diff_run"])
                self.assertEqual(rows[1]["summary"]["regression"], 1)
                self.assertEqual(len(rows[1]["suite"]["sha256"]), 64)
                self.assertEqual(len(rows[1]["candidate"]["sha256"]), 64)
                self.assertEqual(len(rows[1]["reports"]["json"]["sha256"]), 64)
                self.assertNotIn("baseline_response", json.dumps(rows))
            finally:
                os.chdir(previous)

    def test_audit_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": "suite.json",
                            "audit": False,
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)

                self.assertFalse((root / ".redline" / "audit.jsonl").exists())
            finally:
                os.chdir(previous)

    def test_redact_command_sanitizes_jsonl_and_appends_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"audit": ".redline/audit.jsonl"}),
                    encoding="utf-8",
                )
                Path("raw.jsonl").write_text(
                    '{"prompt": "Email ada@example.com", "response": "ok", "api_key": "secret"}\n',
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["redact", "raw.jsonl", "--out", "clean.jsonl"]), 0)

                row = json.loads(Path("clean.jsonl").read_text(encoding="utf-8"))
                self.assertNotIn("ada@example.com", row["prompt"])
                self.assertEqual(row["api_key"], "[REDACTED]")
                self.assertIn("Redactions: 2", output.getvalue())
                audit = [
                    json.loads(line)
                    for line in (root / ".redline" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(audit[-1]["event"], "log_redacted")
                self.assertEqual(audit[-1]["records"], 1)
                self.assertEqual(audit[-1]["redactions"], 2)
                self.assertEqual(audit[-1]["patterns"], {"email": 1, "sensitive_field": 1})
            finally:
                os.chdir(previous)

    def test_redact_check_scans_without_output_and_appends_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"audit": ".redline/audit.jsonl"}),
                    encoding="utf-8",
                )
                Path("raw.jsonl").write_text(
                    '{"prompt": "Email ada@example.com", "response": "ok"}\n',
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["redact", "raw.jsonl", "--check"]), 0)

                self.assertIn("Mode:       check only", output.getvalue())
                self.assertIn("Redactions: 1", output.getvalue())
                self.assertFalse(Path("redacted.jsonl").exists())
                audit = [
                    json.loads(line)
                    for line in (root / ".redline" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(audit[-1]["event"], "log_redaction_checked")
                self.assertNotIn("output", audit[-1])
                self.assertEqual(audit[-1]["redactions"], 1)
            finally:
                os.chdir(previous)

    def test_redact_requires_output_unless_checking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("raw.jsonl").write_text('{"prompt": "ok", "response": "ok"}\n', encoding="utf-8")

                with contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(main(["redact", "raw.jsonl"]), 2)

                self.assertIn("requires --out unless --check", error.getvalue())
            finally:
                os.chdir(previous)

    def test_audit_command_lists_recent_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"audit": ".redline/audit.jsonl"}),
                    encoding="utf-8",
                )
                Path("raw.jsonl").write_text(
                    '{"prompt": "Email ada@example.com", "response": "ok"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["redact", "raw.jsonl", "--out", "clean.jsonl"]), 0)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["audit"]), 0)

                self.assertIn("redline audit", output.getvalue())
                self.assertIn("log_redacted", output.getvalue())
                self.assertIn("records=1", output.getvalue())
                self.assertIn("redactions=1", output.getvalue())
                verify_output = io.StringIO()
                with contextlib.redirect_stdout(verify_output):
                    self.assertEqual(
                        main(["audit", "--verify", "--out-checkpoint", ".redline/audit-checkpoint.json"]),
                        0,
                    )

                self.assertIn("redline audit verify", verify_output.getvalue())
                self.assertIn("Status:   OK", verify_output.getvalue())
                self.assertIn("Wrote audit checkpoint: .redline/audit-checkpoint.json", verify_output.getvalue())

                audit_rows = [
                    json.loads(line)
                    for line in (root / ".redline" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                checkpoint = json.loads((root / ".redline" / "audit-checkpoint.json").read_text(encoding="utf-8"))
                self.assertEqual(checkpoint["schema"], "redline-audit-checkpoint-v1")
                self.assertEqual(checkpoint["entries"], len(audit_rows))
                self.assertEqual(checkpoint["last_hash"], audit_rows[-1]["entry_hash"])

                checkpoint_output = io.StringIO()
                with contextlib.redirect_stdout(checkpoint_output):
                    self.assertEqual(
                        main(
                            [
                                "audit",
                                "--verify",
                                "--expect-last-hash",
                                checkpoint["last_hash"],
                                "--expect-entries",
                                str(checkpoint["entries"]),
                            ]
                        ),
                        0,
                    )

                self.assertIn("Status:   OK", checkpoint_output.getvalue())
                self.assertNotIn("local hash chains cannot prove", checkpoint_output.getvalue())

                checkpoint_file_output = io.StringIO()
                with contextlib.redirect_stdout(checkpoint_file_output):
                    self.assertEqual(
                        main(
                            [
                                "audit",
                                "--verify",
                                "--checkpoint",
                                ".redline/audit-checkpoint.json",
                            ]
                        ),
                        0,
                    )

                self.assertIn("Status:   OK", checkpoint_file_output.getvalue())
                self.assertNotIn("local hash chains cannot prove", checkpoint_file_output.getvalue())
            finally:
                os.chdir(previous)

    def test_audit_verify_exits_nonzero_when_hash_chain_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"audit": ".redline/audit.jsonl"}),
                    encoding="utf-8",
                )
                Path("raw.jsonl").write_text(
                    '{"prompt": "Email ada@example.com", "response": "ok"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["redact", "raw.jsonl", "--out", "clean.jsonl"]), 0)

                audit_path = root / ".redline" / "audit.jsonl"
                row = json.loads(audit_path.read_text(encoding="utf-8"))
                row["event"] = "tampered"
                audit_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["audit", "--verify"]), 1)

                self.assertIn("Status:   FAILED", output.getvalue())
                self.assertIn("entry_hash mismatch", output.getvalue())
            finally:
                os.chdir(previous)

    def test_judgment_requirement_and_acceptance_append_audit_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": "suite.json",
                            "audit": ".redline/audit.jsonl",
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": false}"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                case_id = suite["cases"][0]["id"]
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["mark", "suite.json", case_id, "--status", "expected", "--note", "intentional"]), 0)
                    self.assertEqual(main(["require", "suite.json", case_id, "--include", "ok", "--note", "must keep ok"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "accept",
                                "suite.json",
                                case_id,
                                "--candidate",
                                "candidate.jsonl",
                                "--note",
                                "approved",
                                "--approver",
                                "lead@example.com",
                            ]
                        ),
                        0,
                    )

                rows = [
                    json.loads(line)
                    for line in (root / ".redline" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(
                    [row["event"] for row in rows],
                    ["suite_generated", "case_marked", "requirements_updated", "baseline_accepted"],
                )
                self.assertEqual(rows[1]["case_id"], case_id)
                self.assertEqual(rows[1]["status"], "expected")
                self.assertEqual(rows[2]["requirements"], {"include": 1, "exclude": 0})
                self.assertEqual(rows[3]["case_ids"], [case_id])
                self.assertEqual(rows[3]["approver"], "lead@example.com")
                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                self.assertEqual(suite["accepted_baselines"][0]["approver"], "lead@example.com")
                self.assertNotIn("accepted_response", json.dumps(rows))
            finally:
                os.chdir(previous)

    def test_accept_can_require_approver_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": "suite.json",
                            "approval": {"require_approver": True},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": false}"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                case_id = suite["cases"][0]["id"]

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["accept", "suite.json", case_id, "--candidate", "candidate.jsonl"])

                self.assertEqual(code, 2)
                self.assertIn("accept requires --approver", stderr.getvalue())

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "accept",
                                "suite.json",
                                case_id,
                                "--candidate",
                                "candidate.jsonl",
                                "--approver",
                                "lead@example.com",
                            ]
                        ),
                        0,
                    )
                self.assertIn("Approver: lead@example.com", output.getvalue())
            finally:
                os.chdir(previous)

    def test_summary_on_jsonl_points_to_suite_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "1"}\n'
                    '{"prompt": "two", "response": "2"}\n',
                    encoding="utf-8",
                )
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(["summary", "baseline.jsonl"])

                self.assertEqual(code, 2)
                self.assertIn("expected one JSON object", stderr.getvalue())
                self.assertIn("redline suite baseline.jsonl --out redline-suite.json", stderr.getvalue())
            finally:
                os.chdir(previous)

    def test_benchmark_uses_config_timeout_and_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": "suite.json",
                            "timeout_seconds": 10,
                            "workers": 2,
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "1"}\n'
                    '{"prompt": "two", "response": "2"}\n'
                    '{"prompt": "three", "response": "3"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--all-cases"]), 0)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["benchmark"]), 0)

                self.assertIn("redline benchmark", output.getvalue())
                self.assertIn("Workers:               2", output.getvalue())
                self.assertIn("Timeout per case:      10s", output.getvalue())
                self.assertIn("Worst-case eval budget: 20s", output.getvalue())
            finally:
                os.chdir(previous)

    def test_benchmark_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "1"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["benchmark", "suite.json", "--json"]), 0)

                report = json.loads(output.getvalue())
                self.assertEqual(report["suite"], "suite.json")
                self.assertEqual(report["cases"], 1)
                self.assertEqual(report["workers"], 1)
            finally:
                os.chdir(previous)

    def test_benchmark_writes_report_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "1"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "benchmark",
                                "suite.json",
                                "--out-json",
                                "reports/benchmark.json",
                                "--out-md",
                                "reports/benchmark.md",
                            ]
                        ),
                        0,
                    )

                report = json.loads(Path("reports/benchmark.json").read_text(encoding="utf-8"))
                markdown = Path("reports/benchmark.md").read_text(encoding="utf-8")
                self.assertEqual(report["suite"], "suite.json")
                self.assertIn("## redline benchmark", markdown)
                self.assertIn("| Cases | 1 |", markdown)
            finally:
                os.chdir(previous)

    def test_benchmark_max_seconds_exits_nonzero_when_budget_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "1"}\n'
                    '{"prompt": "two", "response": "2"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json", "--all-cases"]), 0)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["benchmark", "suite.json", "--max-seconds", "30"]), 1)

                self.assertIn("Budget check:          FAIL", output.getvalue())
                self.assertIn("Max allowed budget:    30s", output.getvalue())
            finally:
                os.chdir(previous)

    def test_benchmark_appends_github_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            previous_summary = os.environ.get("GITHUB_STEP_SUMMARY")
            os.chdir(root)
            try:
                summary_path = root / "summary.md"
                os.environ["GITHUB_STEP_SUMMARY"] = str(summary_path)
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "1"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)
                    self.assertEqual(main(["benchmark", "suite.json", "--github-summary"]), 0)

                summary = summary_path.read_text(encoding="utf-8")
                self.assertIn("## redline benchmark", summary)
                self.assertIn("| Cases | 1 |", summary)
            finally:
                if previous_summary is None:
                    os.environ.pop("GITHUB_STEP_SUMMARY", None)
                else:
                    os.environ["GITHUB_STEP_SUMMARY"] = previous_summary
                os.chdir(previous)

    def test_cases_output_points_to_full_case_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON for Ada", "response": "{\\"name\\":\\"Ada\\"}"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["cases", "suite.json"]), 0)

                self.assertIn("Next:", output.getvalue())
                self.assertIn("redline case suite.json case_", output.getvalue())
            finally:
                os.chdir(previous)

    def test_suite_assigns_configured_case_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": "suite.json",
                            "owners": [{"match": "billing", "owner": "@billing-team"}],
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Route billing refund", "response": "Billing Ops handles refunds."}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["cases", "suite.json"]), 0)

                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                self.assertEqual(suite["cases"][0]["owner"], "@billing-team")
                self.assertEqual(suite["summary"]["owned_cases"], 1)
                self.assertIn("@billing-team", output.getvalue())
            finally:
                os.chdir(previous)

    def test_suite_all_cases_rejects_max_cases(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["suite", "baseline.jsonl", "--all-cases", "--max-cases", "1"])

        self.assertEqual(code, 2)
        self.assertIn("--all-cases cannot be combined with --max-cases", stderr.getvalue())

    def test_suite_add_pins_case_and_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "suite",
                                "add",
                                "suite.json",
                                "--prompt",
                                "Always mention refund URL",
                                "--response",
                                "Refund policy: https://example.com/refunds",
                                "--include",
                                "https://example.com/refunds",
                                "--owner",
                                "@billing-team",
                                "--note",
                                "critical policy edge case",
                            ]
                        ),
                        0,
                    )

                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                pinned = suite["cases"][-1]
                self.assertEqual(suite["summary"]["cases"], 2)
                self.assertEqual(suite["summary"]["pinned_cases"], 1)
                self.assertEqual(pinned["source"], "manual")
                self.assertTrue(pinned["pinned"])
                self.assertEqual(pinned["owner"], "@billing-team")
                self.assertIn("Owner: @billing-team", output.getvalue())
                self.assertIn("Added pinned case", output.getvalue())
                self.assertEqual(
                    suite["requirements"][pinned["id"]]["include"],
                    ["https://example.com/refunds"],
                )
            finally:
                os.chdir(previous)

    def test_suite_add_rejects_duplicate_prompt_response_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(
                        [
                            "suite",
                            "add",
                            "suite.json",
                            "--prompt",
                            "Return JSON",
                            "--response",
                            '{"ok": true}',
                        ]
                    )

                self.assertEqual(code, 2)
                self.assertIn("duplicate prompt-response pair", stderr.getvalue())
                self.assertIn("--allow-duplicate", stderr.getvalue())
            finally:
                os.chdir(previous)

    def test_suite_add_can_allow_duplicate_prompt_response_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "suite",
                                "add",
                                "suite.json",
                                "--prompt",
                                "Return JSON",
                                "--response",
                                '{"ok": true}',
                                "--allow-duplicate",
                            ]
                        ),
                        0,
                    )

                suite = json.loads(Path("suite.json").read_text(encoding="utf-8"))
                self.assertEqual(suite["summary"]["cases"], 2)
            finally:
                os.chdir(previous)

    def test_suite_add_reads_prompt_and_response_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("prompt.txt").write_text("Pinned prompt", encoding="utf-8")
                Path("response.txt").write_text("Pinned response", encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl", "--out", "suite.json"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "suite",
                                "add",
                                "suite.json",
                                "--prompt-file",
                                "prompt.txt",
                                "--response-file",
                                "response.txt",
                                "--out",
                                "updated.json",
                            ]
                        ),
                        0,
                    )

                suite = json.loads(Path("updated.json").read_text(encoding="utf-8"))
                self.assertEqual(suite["cases"][-1]["prompt"], "Pinned prompt")
                self.assertEqual(suite["cases"][-1]["baseline_response"], "Pinned response")
                self.assertEqual(json.loads(Path("suite.json").read_text(encoding="utf-8"))["summary"]["cases"], 1)
            finally:
                os.chdir(previous)

    def test_suite_add_reports_missing_prompt_file(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "suite",
                    "add",
                    "suite.json",
                    "--prompt-file",
                    "missing.txt",
                    "--response",
                    "expected",
                ]
            )

        self.assertEqual(code, 2)
        self.assertIn("prompt file not found: missing.txt", stderr.getvalue())

    def test_validate_reports_suite_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"suite": ".redline/suite.json"}),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["validate"]), 0)

                self.assertIn("redline validate", output.getvalue())
                self.assertIn("Status:   valid", output.getvalue())
            finally:
                os.chdir(previous)

    def test_diff_can_append_github_step_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            previous_summary = os.environ.get("GITHUB_STEP_SUMMARY")
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"suite": ".redline/suite.json", "fail_on": "none"}),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "ok"}\n',
                    encoding="utf-8",
                )
                summary_path = root / "github" / "summary.md"
                os.environ["GITHUB_STEP_SUMMARY"] = str(summary_path)

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["diff", "candidate.jsonl", "--github-summary"]), 0)

                summary = summary_path.read_text(encoding="utf-8")
                self.assertIn("# redline diff", summary)
                self.assertIn("**Confidence:** HIGH", summary)
                self.assertIn("candidate lost valid JSON format", summary)
            finally:
                if previous_summary is None:
                    os.environ.pop("GITHUB_STEP_SUMMARY", None)
                else:
                    os.environ["GITHUB_STEP_SUMMARY"] = previous_summary
                os.chdir(previous)

    def test_diff_can_emit_github_annotations_without_polluting_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"suite": ".redline/suite.json", "fail_on": "none"}),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "ok"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(
                        main(["diff", "candidate.jsonl", "--github-annotations", "--json"]),
                        0,
                    )

                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["summary"]["regression"], 1)
                self.assertIn("::error", stderr.getvalue())
                self.assertIn("candidate lost valid JSON format", stderr.getvalue())
            finally:
                os.chdir(previous)

    def test_diff_compact_prints_one_line_case_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps({"suite": ".redline/suite.json", "fail_on": "none"}),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "ok"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["diff", "candidate.jsonl", "--compact"]), 0)

                text = output.getvalue()
                self.assertIn("redline diff: cases=1 regression=1", text)
                self.assertIn("REGRESSION case_", text)
                self.assertIn("candidate lost valid JSON format", text)
                self.assertNotIn("REGRESSION\n-", text)
            finally:
                os.chdir(previous)

    def test_compare_reports_previous_and_current_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("before.json").write_text(
                    json.dumps(
                        {
                            "diffs": [
                                {
                                    "case_id": "case_001",
                                    "status": "changed",
                                    "prompt": "Return JSON",
                                    "reasons": ["content changed"],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                Path("after.json").write_text(
                    json.dumps(
                        {
                            "diffs": [
                                {
                                    "case_id": "case_001",
                                    "status": "regression",
                                    "prompt": "Return JSON",
                                    "reasons": ["candidate lost valid JSON format"],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["compare", "before.json", "after.json"]), 1)

                self.assertIn("redline compare", output.getvalue())
                self.assertIn("Worse:     1", output.getvalue())
            finally:
                os.chdir(previous)

    def test_compare_fail_on_none_keeps_report_only_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("before.json").write_text(
                    json.dumps(
                        {
                            "diffs": [
                                {
                                    "case_id": "case_001",
                                    "status": "changed",
                                    "prompt": "Return JSON",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                Path("after.json").write_text(
                    json.dumps(
                        {
                            "diffs": [
                                {
                                    "case_id": "case_001",
                                    "status": "regression",
                                    "prompt": "Return JSON",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(["compare", "before.json", "after.json", "--fail-on", "none"]),
                        0,
                    )
            finally:
                os.chdir(previous)

    def test_compare_can_write_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("before.json").write_text(
                    json.dumps({"diffs": []}),
                    encoding="utf-8",
                )
                Path("after.json").write_text(
                    json.dumps({"diffs": []}),
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "compare",
                                "before.json",
                                "after.json",
                                "--out-json",
                                ".redline/reports/compare.json",
                            ]
                        ),
                        0,
                    )

                report = json.loads(
                    (root / ".redline" / "reports" / "compare.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(report["summary"]["cases"], 0)
            finally:
                os.chdir(previous)

    def test_compare_can_write_markdown_and_github_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            previous_summary = os.environ.get("GITHUB_STEP_SUMMARY")
            try:
                Path("before.json").write_text(
                    json.dumps(
                        {
                            "diffs": [
                                {
                                    "case_id": "case_001",
                                    "status": "changed",
                                    "prompt": "Return JSON",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                Path("after.json").write_text(
                    json.dumps(
                        {
                            "diffs": [
                                {
                                    "case_id": "case_001",
                                    "status": "regression",
                                    "prompt": "Return JSON",
                                    "reasons": ["candidate lost valid JSON format"],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                summary_path = root / "github" / "summary.md"
                os.environ["GITHUB_STEP_SUMMARY"] = str(summary_path)

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "compare",
                                "before.json",
                                "after.json",
                                "--out-md",
                                ".redline/reports/compare.md",
                                "--out-html",
                                ".redline/reports/compare.html",
                                "--github-summary",
                                "--fail-on",
                                "none",
                            ]
                        ),
                        0,
                    )

                report = (root / ".redline" / "reports" / "compare.md").read_text(
                    encoding="utf-8"
                )
                html = (root / ".redline" / "reports" / "compare.html").read_text(
                    encoding="utf-8"
                )
                summary = summary_path.read_text(encoding="utf-8")
                self.assertIn("# redline compare", report)
                self.assertIn("candidate lost valid JSON format", report)
                self.assertIn("<title>redline compare</title>", html)
                self.assertIn("candidate lost valid JSON format", html)
                self.assertIn("# redline compare", summary)
            finally:
                if previous_summary is None:
                    os.environ.pop("GITHUB_STEP_SUMMARY", None)
                else:
                    os.environ["GITHUB_STEP_SUMMARY"] = previous_summary
                os.chdir(previous)

    def test_diff_uses_configured_judge_command_for_changed_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("judge.py").write_text(
                    "import json, sys\n"
                    "payload = json.loads(sys.stdin.read())\n"
                    "assert payload['deterministic_status'] == 'changed'\n"
                    "print(json.dumps({"
                    "'status': 'neutral', "
                    "'confidence': 'medium', "
                    "'reason': 'same routing intent'"
                    "}))\n",
                    encoding="utf-8",
                )
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "fail_on": "none",
                            "judge": {
                                "command": f"{sys.executable} judge.py",
                                "timeout_seconds": 2.0,
                            },
                            "reports": {"json": ".redline/reports/{command}.json"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "Route this ticket", "response": "billing"}\n',
                    encoding="utf-8",
                )
                Path("candidate.jsonl").write_text(
                    '{"prompt": "Route this ticket", "response": "security"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["diff", "candidate.jsonl"]), 0)

                report = json.loads((root / ".redline" / "reports" / "diff.json").read_text(encoding="utf-8"))
                self.assertEqual(report["suite"], ".redline/suite.json")
                self.assertEqual(report["candidate"], "candidate.jsonl")
                self.assertEqual(report["summary"]["neutral"], 1)
                self.assertEqual(report["summary"]["changed"], 0)
                self.assertEqual(report["judge"]["cases"], 1)
                self.assertEqual(report["diffs"][0]["judge"]["reason"], "same routing intent")
            finally:
                os.chdir(previous)

    def test_watch_uses_configured_observed_log_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "input_field": "input",
                            "output_field": "output",
                            "logs": {"observed": ".redline/logs/observed.jsonl"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("source.jsonl").write_text(
                    '{"input": "hello", "output": "world"}\n',
                    encoding="utf-8",
                )

                cluster_output = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["watch", "--log", "source.jsonl", "--replace"]), 0)
                    self.assertEqual(main(["suite"]), 0)
                with contextlib.redirect_stdout(cluster_output):
                    self.assertEqual(main(["cluster"]), 0)

                observed = root / ".redline" / "logs" / "observed.jsonl"
                self.assertTrue(observed.exists())
                self.assertIn('"source": "source.jsonl"', observed.read_text(encoding="utf-8"))
                self.assertTrue((root / "redline-suite.json").exists())
                self.assertIn("redline cluster", cluster_output.getvalue())
            finally:
                os.chdir(previous)

    def test_watch_follow_prints_live_collected_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(Path(directory))
            try:
                Path("source.jsonl").write_text(
                    '{"prompt": "hello from production", "response": "world"}\n',
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "watch",
                                "--log",
                                "source.jsonl",
                                "--follow",
                                "--max-records",
                                "1",
                                "--poll-interval",
                                "0",
                            ]
                        ),
                        0,
                    )

                text = output.getvalue()
                self.assertIn("Following source.jsonl.", text)
                self.assertIn(
                    "Writing new prompt-response pairs to .redline/logs/prompts.jsonl.",
                    text,
                )
                self.assertIn("+ line 1: hello from production", text)
                self.assertIn("Collected 1 new prompt-response pairs", text)
            finally:
                os.chdir(previous)

    def test_watch_reports_default_redaction_and_supports_raw_opt_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("source.jsonl").write_text(
                    '{"prompt": "Email ada@example.com", "response": "ok"}\n',
                    encoding="utf-8",
                )

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["watch", "--log", "source.jsonl", "--replace"]), 0)

                observed = root / ".redline" / "logs" / "prompts.jsonl"
                self.assertIn("Redacted 1 sensitive value", output.getvalue())
                self.assertNotIn("ada@example.com", observed.read_text(encoding="utf-8"))

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(["watch", "--log", "source.jsonl", "--replace", "--no-redact"]),
                        0,
                    )
                self.assertIn("ada@example.com", observed.read_text(encoding="utf-8"))
            finally:
                os.chdir(previous)

    def test_eval_uses_configured_replay_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "import sys\nprint(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "replay": replay,
                            "timeout_seconds": 3.5,
                            "fail_on": "none",
                            "runs": {
                                "candidate": ".redline/runs/candidate.jsonl",
                                "metadata": ".redline/runs/replay.json",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "hello", "response": "hello"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["eval"]), 0)

                candidate = root / ".redline" / "runs" / "candidate.jsonl"
                metadata_path = root / ".redline" / "runs" / "replay.json"
                self.assertTrue(candidate.exists())
                self.assertTrue(metadata_path.exists())
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["suite"], ".redline/suite.json")
                self.assertEqual(metadata["candidate"], ".redline/runs/candidate.jsonl")
                self.assertEqual(metadata["replay"]["command"], replay)
                self.assertEqual(metadata["replay"]["timeout_seconds"], 3.5)
                self.assertEqual(metadata["replay"]["workers"], 1)
                self.assertEqual(metadata["summary"]["neutral"], 1)
                self.assertEqual(metadata["decision"]["confidence"], "medium")
                self.assertIn("structural checks only", metadata["decision"]["scope"])
            finally:
                os.chdir(previous)

    def test_eval_prompt_file_renders_case_prompt_for_configured_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "import sys\nprint(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("prompts").mkdir()
                Path("prompts/v2.txt").write_text(
                    "System: answer exactly.\nUser: {prompt}\n",
                    encoding="utf-8",
                )
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "replay": replay,
                            "fail_on": "none",
                            "runs": {
                                "candidate": ".redline/runs/candidate.jsonl",
                                "metadata": ".redline/runs/replay.json",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "hello", "response": "hello"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["eval", "--prompt", "prompts/v2.txt"]), 0)

                candidate = (root / ".redline" / "runs" / "candidate.jsonl").read_text(encoding="utf-8")
                metadata = json.loads(
                    (root / ".redline" / "runs" / "replay.json").read_text(encoding="utf-8")
                )
                self.assertIn('"prompt": "hello"', candidate)
                self.assertIn('"rendered_prompt": "System: answer exactly.\\nUser: hello\\n"', candidate)
                self.assertEqual(metadata["replay"]["prompt"], "prompts/v2.txt")
            finally:
                os.chdir(previous)

    def test_eval_runs_prompt_manifest_as_multi_prompt_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "\n".join(
                        [
                            "import sys",
                            "text = sys.stdin.read()",
                            "if 'Return JSON' in text:",
                            "    print('not json')",
                            "elif 'Summarize as table' in text:",
                            "    print('| A | B |\\n| - | - |\\n| one | two |')",
                            "else:",
                            "    print('plain text')",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                Path("prompts").mkdir()
                Path("prompts/json.txt").write_text("System: {prompt}\n", encoding="utf-8")
                Path("prompts/table.txt").write_text("System: {prompt}\n", encoding="utf-8")
                Path("json-baseline.jsonl").write_text(
                    '{"prompt": "Return JSON", "response": "{\\"ok\\": true}"}\n',
                    encoding="utf-8",
                )
                Path("table-baseline.jsonl").write_text(
                    '{"prompt": "Summarize as table", "response": "| A | B |\\n| - | - |\\n| one | two |"}\n',
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "replay": replay,
                            "fail_on": "none",
                            "runs": {
                                "candidate": ".redline/runs/candidate.jsonl",
                                "metadata": ".redline/runs/replay.json",
                            },
                            "reports": {"json": ".redline/reports/{command}.json"},
                        }
                    ),
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(["suite", "json-baseline.jsonl", "--out", "suites/json.redline-suite.json"]),
                        0,
                    )
                    self.assertEqual(
                        main(["suite", "table-baseline.jsonl", "--out", "suites/table.redline-suite.json"]),
                        0,
                    )
                    self.assertEqual(
                        main(["prompts", "prompts", "--suite-dir", "suites", "--out", "redline-prompts.json"]),
                        0,
                    )
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["eval", "redline-prompts.json", "--compact"]), 0)

                text = output.getvalue()
                report = json.loads((root / ".redline" / "reports" / "eval.json").read_text(encoding="utf-8"))
                candidate = (root / ".redline" / "runs" / "candidate.jsonl").read_text(encoding="utf-8")
                metadata = json.loads((root / ".redline" / "runs" / "replay.json").read_text(encoding="utf-8"))
                self.assertIn("redline eval: cases=2", text)
                self.assertEqual(report["manifest"], "redline-prompts.json")
                self.assertEqual(report["prompt_count"], 2)
                self.assertEqual(report["summary"]["cases"], 2)
                self.assertEqual(report["summary"]["regression"], 1)
                self.assertEqual(len(report["prompt_evals"]), 2)
                self.assertTrue(
                    any(diff["case_id"].startswith("table/") for diff in report["diffs"]),
                    report["diffs"],
                )
                self.assertIn('"prompt_id": "json"', candidate)
                self.assertIn('"prompt_id": "table"', candidate)
                self.assertEqual(metadata["manifest"], "redline-prompts.json")
                self.assertEqual(metadata["summary"]["cases"], 2)
                self.assertEqual(len(metadata["prompt_evals"]), 2)
            finally:
                os.chdir(previous)

    def test_eval_warns_when_prompt_is_newer_than_suite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "import sys\nprint(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("prompts").mkdir()
                Path("prompts/v2.txt").write_text(
                    "System: answer exactly.\nUser: {prompt}\n",
                    encoding="utf-8",
                )
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "replay": replay,
                            "fail_on": "none",
                            "reports": {"json": ".redline/reports/eval.json"},
                            "runs": {"metadata": ".redline/runs/replay.json"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "hello", "response": "hello"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)

                suite_path = root / ".redline" / "suite.json"
                suite = json.loads(suite_path.read_text(encoding="utf-8"))
                suite["created_at"] = "2000-01-01T00:00:00+00:00"
                suite_path.write_text(json.dumps(suite), encoding="utf-8")

                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["eval", "--prompt", "prompts/v2.txt", "--compact"]), 0)

                report = json.loads((root / ".redline" / "reports" / "eval.json").read_text(encoding="utf-8"))
                metadata = json.loads((root / ".redline" / "runs" / "replay.json").read_text(encoding="utf-8"))
                self.assertIn("Warning: prompt file prompts/v2.txt is newer than suite", output.getvalue())
                self.assertIn("prompt file prompts/v2.txt is newer than suite", report["warnings"][0])
                self.assertEqual(metadata["warnings"], report["warnings"])
            finally:
                os.chdir(previous)

    def test_eval_timeout_flag_overrides_config_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "import sys\nprint(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "replay": replay,
                            "timeout_seconds": 9.0,
                            "fail_on": "none",
                            "runs": {"metadata": ".redline/runs/replay.json"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "hello", "response": "hello"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["eval", "--timeout", "1.25"]), 0)

                metadata = json.loads(
                    (root / ".redline" / "runs" / "replay.json").read_text(encoding="utf-8")
                )
                self.assertEqual(metadata["replay"]["timeout_seconds"], 1.25)
            finally:
                os.chdir(previous)

    def test_eval_workers_flag_overrides_config_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                Path("runner.py").write_text(
                    "import sys\nprint(sys.stdin.read())\n",
                    encoding="utf-8",
                )
                replay = f"{sys.executable} runner.py"
                Path("redline.json").write_text(
                    json.dumps(
                        {
                            "suite": ".redline/suite.json",
                            "replay": replay,
                            "workers": 1,
                            "fail_on": "none",
                            "runs": {"metadata": ".redline/runs/replay.json"},
                        }
                    ),
                    encoding="utf-8",
                )
                Path("baseline.jsonl").write_text(
                    '{"prompt": "one", "response": "one"}\n'
                    '{"prompt": "two", "response": "two"}\n',
                    encoding="utf-8",
                )

                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["suite", "baseline.jsonl"]), 0)
                    self.assertEqual(main(["eval", "--workers", "2"]), 0)

                metadata = json.loads(
                    (root / ".redline" / "runs" / "replay.json").read_text(encoding="utf-8")
                )
                self.assertEqual(metadata["replay"]["workers"], 2)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
