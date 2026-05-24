import json
import tomllib
import unittest
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_pyproject_declares_build_backend_and_cli_entrypoint(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(pyproject["project"]["name"], "redline-ai")
        self.assertEqual(pyproject["project"]["license"], "MIT")
        self.assertEqual(pyproject["project"]["scripts"]["redline"], "redline.cli:main")
        self.assertIn("Generate eval suites", pyproject["project"]["description"])
        self.assertEqual(pyproject["project"]["urls"]["Repository"], "https://github.com/gowtham0992/redline")
        self.assertNotIn(
            "License :: OSI Approved :: MIT License",
            pyproject["project"]["classifiers"],
        )

    def test_dev_dependencies_include_release_tools(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]

        self.assertIn("build>=1.2", dev_dependencies)
        self.assertIn("twine>=5", dev_dependencies)

    def test_package_is_marked_typed(self) -> None:
        self.assertTrue(Path("redline/py.typed").exists())
        manifest = Path("MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("redline py.typed", manifest)
        self.assertIn("redline/runner_templates", manifest)
        self.assertIn("examples *.jsonl *.md", manifest)
        self.assertIn("scripts *.sh", manifest)

    def test_shell_scripts_are_executable(self) -> None:
        for script_name in ("build_release.sh", "demo_terminal.sh", "release_check.sh"):
            with self.subTest(script=script_name):
                script = Path("scripts") / script_name

                self.assertTrue(script.exists())
                self.assertTrue(script.stat().st_mode & 0o111)

    def test_demo_recording_script_runs_compact_demo(self) -> None:
        script = Path("scripts/demo_terminal.sh")
        text = script.read_text(encoding="utf-8")

        self.assertIn("redline demo --compact", text)
        self.assertIn("redline history", text)
        self.assertIn("--out-md", text)

    def test_release_check_builds_and_smokes_installed_wheel(self) -> None:
        script = Path("scripts/release_check.sh").read_text(encoding="utf-8")

        self.assertIn("-m unittest discover", script)
        self.assertIn("-m compileall redline tests examples", script)
        self.assertIn("git diff --check", script)
        self.assertIn("examples/public_dogfood_baseline.jsonl", script)
        self.assertIn("examples/public_dogfood_candidate.jsonl", script)
        self.assertIn("-m pip wheel . --no-deps --no-build-isolation", script)
        self.assertIn("-m venv", script)
        self.assertIn("redline --version", script)
        self.assertIn("$ redline\\n", script)
        self.assertIn("redline demo --compact", script)
        self.assertIn("redline demo --public --compact", script)
        self.assertIn("redline history .redline/demo/reports/diff.json", script)
        self.assertIn("--out-md history.md", script)
        self.assertIn("--github-summary", script)
        self.assertIn("--all-cases", script)
        self.assertIn("redline suite add all-suite.json", script)
        self.assertIn("redline validate pinned-suite.json", script)
        self.assertIn("--out-html diff.html", script)
        self.assertIn("--profile review", script)
        self.assertIn("redline doctor", script)

    def test_release_build_script_uses_fresh_output_dir(self) -> None:
        script = Path("scripts/build_release.sh").read_text(encoding="utf-8")

        self.assertIn("-m build --no-isolation --outdir", script)
        self.assertIn("output directory is not empty", script)
        self.assertIn("redline_ai-*.whl", script)
        self.assertIn("redline_ai-*.tar.gz", script)
        self.assertIn("-m twine check", script)

    def test_release_guide_documents_package_gate(self) -> None:
        guide = Path("docs/release.md").read_text(encoding="utf-8")

        self.assertIn("bash scripts/release_check.sh", guide)
        self.assertIn("bash scripts/build_release.sh", guide)
        self.assertIn("Do not upload an ignored local `dist/*`", guide)
        self.assertIn("docs/dogfood.md", guide)
        self.assertIn("pyproject.toml", guide)
        self.assertIn("redline/__init__.py", guide)
        self.assertIn("CHANGELOG.md", guide)
        self.assertIn("redline demo --compact", guide)
        self.assertIn("redline demo --public --compact", guide)
        self.assertIn("redline init --runner stdio --copy-runner", guide)

    def test_changelog_mentions_release_ready_workflows(self) -> None:
        changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("Markdown history reports", changelog)
        self.assertIn("self-contained HTML", changelog)
        self.assertIn("GitHub step summaries", changelog)
        self.assertIn("suite generation commands", changelog)
        self.assertIn("review` diff profile", changelog)
        self.assertIn("suite --all-cases", changelog)
        self.assertIn("redline suite add", changelog)

    def test_dogfood_protocol_exercises_first_run_loop(self) -> None:
        guide = Path("docs/dogfood.md").read_text(encoding="utf-8")

        self.assertIn("redline demo", guide)
        self.assertIn("redline demo --public --compact", guide)
        self.assertIn("redline runners", guide)
        self.assertIn("redline init --runner stdio --copy-runner --github-action", guide)
        self.assertIn("redline suite .redline/demo/baseline.jsonl", guide)
        self.assertIn("examples/public_dogfood_baseline.jsonl", guide)
        self.assertIn("public_dogfood_sources.md", guide)
        self.assertIn("normalize_ai_session_logs.py", guide)
        self.assertIn("ai-session-dogfood-prompts.jsonl", guide)
        self.assertIn("severity: blocker | confusing | polish", guide)

    def test_public_dogfood_fixture_documents_source_inspiration(self) -> None:
        sources = Path("examples/public_dogfood_sources.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("synthetic", sources)
        self.assertIn("Databricks Dolly 15k", sources)
        self.assertIn("OpenAssistant OASST1", sources)
        self.assertIn("Anthropic HH-RLHF", sources)
        self.assertIn("WildChat", sources)
        self.assertIn("examples/public_dogfood_baseline.jsonl", readme)
        self.assertIn("examples/public_dogfood_candidate.jsonl", readme)

    def test_ai_session_prompt_set_has_ten_prompts(self) -> None:
        prompts = Path("docs/ai-session-dogfood-prompts.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(prompts), 10)
        self.assertTrue(all(json.loads(line)["prompt"] for line in prompts))

    def test_pyproject_includes_runner_templates(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("runner_templates/*", pyproject["tool"]["setuptools"]["package-data"]["redline"])


if __name__ == "__main__":
    unittest.main()
