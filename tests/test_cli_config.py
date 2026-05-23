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
    def test_cli_version_flag_prints_version(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("redline 0.1.0", output.getvalue())

    def test_runners_command_lists_adapter_commands(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["runners"]), 0)

        text = output.getvalue()
        self.assertIn("redline runners", text)
        self.assertIn("OpenAI direct", text)
        self.assertIn("./runners/openai_runner.sh", text)

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
                self.assertTrue((root / ".redline" / "reports" / "diff.xml").exists())
            finally:
                os.chdir(previous)

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
                self.assertEqual(metadata["decision"]["confidence"], "high")
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
