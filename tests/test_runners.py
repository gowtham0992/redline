import os
import subprocess
import unittest
from pathlib import Path


class RunnerTests(unittest.TestCase):
    def test_openai_runner_fails_clearly_without_api_key(self) -> None:
        runner = Path("runners/openai_runner.sh")

        completed = subprocess.run(
            ["bash", str(runner)],
            input="hello",
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("OPENAI_API_KEY", completed.stderr)

    def test_runner_docs_include_openai_wire_command(self) -> None:
        docs = Path("docs/runners.md").read_text(encoding="utf-8")

        self.assertIn("## OpenAI Direct", docs)
        self.assertIn('redline eval --prompt prompts/v2.txt --replay "./runners/openai_runner.sh"', docs)
