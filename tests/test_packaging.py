import tomllib
import unittest
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_pyproject_declares_build_backend_and_cli_entrypoint(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(pyproject["project"]["scripts"]["redline"], "redline.cli:main")
        self.assertIn("Generate eval suites", pyproject["project"]["description"])
        self.assertEqual(pyproject["project"]["urls"]["Repository"], "https://github.com/gowtham0992/redline")

    def test_package_is_marked_typed(self) -> None:
        self.assertTrue(Path("redline/py.typed").exists())
        manifest = Path("MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("redline py.typed", manifest)
        self.assertIn("redline/runner_templates", manifest)
        self.assertIn("scripts *.sh", manifest)

    def test_shell_scripts_are_executable(self) -> None:
        for script_name in ("demo_terminal.sh", "release_check.sh"):
            with self.subTest(script=script_name):
                script = Path("scripts") / script_name

                self.assertTrue(script.exists())
                self.assertTrue(script.stat().st_mode & 0o111)

    def test_demo_recording_script_runs_compact_demo(self) -> None:
        script = Path("scripts/demo_terminal.sh")

        self.assertIn("redline demo --compact", script.read_text(encoding="utf-8"))

    def test_release_check_builds_and_smokes_installed_wheel(self) -> None:
        script = Path("scripts/release_check.sh").read_text(encoding="utf-8")

        self.assertIn("-m unittest discover", script)
        self.assertIn("-m compileall redline tests examples", script)
        self.assertIn("git diff --check", script)
        self.assertIn("-m pip wheel . --no-deps --no-build-isolation", script)
        self.assertIn("-m venv", script)
        self.assertIn("redline demo --compact", script)
        self.assertIn("redline doctor", script)

    def test_release_guide_documents_package_gate(self) -> None:
        guide = Path("docs/release.md").read_text(encoding="utf-8")

        self.assertIn("bash scripts/release_check.sh", guide)
        self.assertIn("docs/dogfood.md", guide)
        self.assertIn("pyproject.toml", guide)
        self.assertIn("redline/__init__.py", guide)
        self.assertIn("CHANGELOG.md", guide)
        self.assertIn("redline demo --compact", guide)

    def test_dogfood_protocol_exercises_first_run_loop(self) -> None:
        guide = Path("docs/dogfood.md").read_text(encoding="utf-8")

        self.assertIn("redline demo", guide)
        self.assertIn("redline runners", guide)
        self.assertIn("redline init --runner openai --copy-runner --github-action", guide)
        self.assertIn("redline suite .redline/demo/baseline.jsonl", guide)
        self.assertIn("severity: blocker | confusing | polish", guide)

    def test_pyproject_includes_runner_templates(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("runner_templates/*", pyproject["tool"]["setuptools"]["package-data"]["redline"])


if __name__ == "__main__":
    unittest.main()
