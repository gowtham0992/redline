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

    def test_demo_recording_script_is_executable(self) -> None:
        script = Path("scripts/demo_terminal.sh")

        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111)
        self.assertIn("redline demo --compact", script.read_text(encoding="utf-8"))

    def test_pyproject_includes_runner_templates(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("runner_templates/*", pyproject["tool"]["setuptools"]["package-data"]["redline"])


if __name__ == "__main__":
    unittest.main()
