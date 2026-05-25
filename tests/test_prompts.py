import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from redline.cli import main
from redline.prompts import build_prompt_manifest, check_prompt_suites, format_prompt_manifest


class PromptManifestTests(unittest.TestCase):
    def test_build_prompt_manifest_scans_prompt_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts"
            (prompts / "support").mkdir(parents=True)
            (prompts / "billing").mkdir()
            (prompts / ".scratch").mkdir()
            (prompts / "support" / "triage.txt").write_text("triage prompt\n", encoding="utf-8")
            (prompts / "billing" / "refund.md").write_text("refund prompt\n", encoding="utf-8")
            (prompts / "support" / "notes.py").write_text("not a prompt\n", encoding="utf-8")
            (prompts / ".scratch" / "draft.txt").write_text("hidden\n", encoding="utf-8")

            manifest = build_prompt_manifest(prompts, suite_dir="suites")

            self.assertEqual(manifest["schema"], "redline-prompt-manifest-v1")
            self.assertEqual(manifest["prompt_count"], 2)
            self.assertNotIn("created_at", manifest)
            records = manifest["prompts"]
            assert isinstance(records, list)
            ids = [record["id"] for record in records if isinstance(record, dict)]
            self.assertEqual(ids, ["billing/refund", "support/triage"])
            suites = [record["suite"] for record in records if isinstance(record, dict)]
            self.assertEqual(
                suites,
                [
                    "suites/billing/refund.redline-suite.json",
                    "suites/support/triage.redline-suite.json",
                ],
            )
            for record in records:
                self.assertIsInstance(record, dict)
                self.assertNotIn("modified_at", record)
                self.assertEqual(len(str(record["sha256"])), 64)

    def test_build_prompt_manifest_is_stable_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "support.txt"
            prompt.write_text("support prompt\n", encoding="utf-8")

            first = build_prompt_manifest(root, suite_dir="suites")
            second = build_prompt_manifest(root, suite_dir="suites")

            self.assertEqual(first, second)

    def test_build_prompt_manifest_supports_custom_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "agent.prompt"
            prompt.write_text("system prompt\n", encoding="utf-8")

            manifest = build_prompt_manifest(prompt, suite_dir="suites", extensions=["prompt"])

            self.assertEqual(manifest["prompt_count"], 1)
            records = manifest["prompts"]
            assert isinstance(records, list)
            record = records[0]
            assert isinstance(record, dict)
            self.assertEqual(record["id"], "agent")
            self.assertEqual(record["suite"], "suites/agent.redline-suite.json")

    def test_build_prompt_manifest_fails_when_no_prompts_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.py").write_text("print('no prompt')\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "no prompt files found"):
                build_prompt_manifest(root, extensions=["txt"])

    def test_format_prompt_manifest_includes_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "support.txt"
            prompt.write_text("support prompt\n", encoding="utf-8")
            manifest = build_prompt_manifest(prompt)

            output = format_prompt_manifest(manifest, output_path="redline-prompts.json")

            self.assertIn("redline prompts", output)
            self.assertIn("Wrote:     redline-prompts.json", output)
            self.assertIn("redline suite path/to/baseline.jsonl --out suites/support.redline-suite.json", output)
            self.assertIn("redline eval suites/support.redline-suite.json --prompt", output)

    def test_prompts_cli_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                prompts = root / "prompts"
                prompts.mkdir()
                (prompts / "support.txt").write_text("support prompt\n", encoding="utf-8")
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(
                        main(["prompts", "prompts", "--suite-dir", "suites", "--out", "redline-prompts.json"]),
                        0,
                    )

                self.assertTrue((root / "redline-prompts.json").exists())
                manifest = json.loads((root / "redline-prompts.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["prompt_count"], 1)
                self.assertIn("redline prompts", output.getvalue())
            finally:
                os.chdir(previous)

    def test_prompts_cli_check_accepts_current_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                prompts = root / "prompts"
                prompts.mkdir()
                (prompts / "support.txt").write_text("support prompt\n", encoding="utf-8")
                self.assertEqual(main(["prompts", "prompts", "--out", "redline-prompts.json"]), 0)
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["prompts", "prompts", "--out", "redline-prompts.json", "--check"]), 0)

                self.assertIn("Status:   OK", output.getvalue())
            finally:
                os.chdir(previous)

    def test_prompts_cli_check_fails_when_manifest_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                prompts = root / "prompts"
                prompts.mkdir()
                prompt = prompts / "support.txt"
                prompt.write_text("support prompt\n", encoding="utf-8")
                self.assertEqual(main(["prompts", "prompts", "--out", "redline-prompts.json"]), 0)
                prompt.write_text("changed support prompt\n", encoding="utf-8")
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    code = main(["prompts", "prompts", "--out", "redline-prompts.json", "--check"])

                self.assertEqual(code, 1)
                self.assertIn("Status:   OUTDATED", output.getvalue())
                self.assertIn("Changed:   support", output.getvalue())
                self.assertIn("Regenerate manifest: redline prompts prompts", output.getvalue())
            finally:
                os.chdir(previous)

    def test_check_prompt_suites_reports_missing_suite_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompts" / "support.txt"
            prompt.parent.mkdir()
            prompt.write_text("support prompt\n", encoding="utf-8")
            manifest = build_prompt_manifest(prompt, suite_dir=root / "suites")

            status = check_prompt_suites(manifest)

            self.assertEqual(status["status"], "missing_suites")
            self.assertEqual(status["prompt_count"], 1)
            self.assertEqual(status["suite_count"], 0)
            self.assertEqual(status["valid_suite_count"], 0)
            missing = status["missing_suites"]
            self.assertIsInstance(missing, list)
            assert isinstance(missing, list)
            self.assertEqual(len(missing), 1)

            suite = root / "suites" / "support.redline-suite.json"
            suite.parent.mkdir()
            suite.write_text('{"cases": [], "summary": {"cases": 0}}\n', encoding="utf-8")

            status = check_prompt_suites(manifest)
            self.assertEqual(status["status"], "ok")
            self.assertEqual(status["suite_count"], 1)
            self.assertEqual(status["valid_suite_count"], 1)

    def test_check_prompt_suites_reports_invalid_suite_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompts" / "support.txt"
            prompt.parent.mkdir()
            prompt.write_text("support prompt\n", encoding="utf-8")
            manifest = build_prompt_manifest(prompt, suite_dir=root / "suites")
            suite = root / "suites" / "support.redline-suite.json"
            suite.parent.mkdir()
            suite.write_text("{}\n", encoding="utf-8")

            status = check_prompt_suites(manifest)

            self.assertEqual(status["status"], "invalid_suites")
            self.assertEqual(status["suite_count"], 1)
            self.assertEqual(status["valid_suite_count"], 0)
            invalid = status["invalid_suites"]
            self.assertIsInstance(invalid, list)
            assert isinstance(invalid, list)
            self.assertEqual(invalid[0]["id"], "support")
            self.assertEqual(invalid[0]["errors"], 1)

    def test_prompts_cli_check_suites_fails_when_suite_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                prompts = root / "prompts"
                prompts.mkdir()
                (prompts / "support.txt").write_text("support prompt\n", encoding="utf-8")
                self.assertEqual(
                    main(["prompts", "prompts", "--suite-dir", "suites", "--out", "redline-prompts.json"]),
                    0,
                )
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    code = main(
                        [
                            "prompts",
                            "prompts",
                            "--suite-dir",
                            "suites",
                            "--out",
                            "redline-prompts.json",
                            "--check",
                            "--check-suites",
                        ]
                    )

                self.assertEqual(code, 1)
                self.assertIn("Suites:   0/1 present", output.getvalue())
                self.assertIn("Valid:    0/1 valid", output.getvalue())
                self.assertIn("Missing suites: support -> suites/support.redline-suite.json", output.getvalue())
                self.assertIn("Build missing suite:", output.getvalue())
            finally:
                os.chdir(previous)

    def test_prompts_cli_check_suites_fails_when_suite_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = Path.cwd()
            os.chdir(root)
            try:
                prompts = root / "prompts"
                prompts.mkdir()
                (prompts / "support.txt").write_text("support prompt\n", encoding="utf-8")
                self.assertEqual(
                    main(["prompts", "prompts", "--suite-dir", "suites", "--out", "redline-prompts.json"]),
                    0,
                )
                suite = root / "suites" / "support.redline-suite.json"
                suite.parent.mkdir()
                suite.write_text("{}\n", encoding="utf-8")
                output = io.StringIO()

                with contextlib.redirect_stdout(output):
                    code = main(
                        [
                            "prompts",
                            "prompts",
                            "--suite-dir",
                            "suites",
                            "--out",
                            "redline-prompts.json",
                            "--check",
                            "--check-suites",
                        ]
                    )

                self.assertEqual(code, 1)
                self.assertIn("Suites:   1/1 present", output.getvalue())
                self.assertIn("Valid:    0/1 valid", output.getvalue())
                self.assertIn("Invalid suites: support -> suites/support.redline-suite.json", output.getvalue())
                self.assertIn("Fix invalid suite: redline validate suites/support.redline-suite.json --strict", output.getvalue())
            finally:
                os.chdir(previous)

    def test_prompts_cli_check_requires_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "support.txt"
            prompt.write_text("support prompt\n", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = main(["prompts", str(prompt), "--check"])

            self.assertEqual(code, 2)
            self.assertIn("prompts --check requires --out", stderr.getvalue())

    def test_prompts_cli_prints_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "agent.txt"
            prompt.write_text("agent prompt\n", encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["prompts", str(prompt), "--json"]), 0)

            payload = json.loads(output.getvalue())
            self.assertEqual(payload["prompt_count"], 1)
            self.assertEqual(payload["prompts"][0]["id"], "agent")
