import json
import subprocess
import sys
import unittest
from pathlib import Path


class JudgeExampleTests(unittest.TestCase):
    def test_local_judge_example_flags_route_changes(self) -> None:
        payload = {
            "case_id": "case_001",
            "prompt": "Route this ticket.",
            "baseline_response": "billing",
            "candidate_response": "security",
            "deterministic_status": "changed",
            "deterministic_reasons": ["content changed substantially"],
        }

        completed = subprocess.run(
            [sys.executable, "examples/judge_changed.py"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        judgment = json.loads(completed.stdout)
        self.assertEqual(judgment["status"], "regression")
        self.assertEqual(judgment["confidence"], "high")
        self.assertIn("billing -> security", judgment["reason"])

    def test_local_judge_example_is_documented(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("examples/judge_changed.py", readme)
        self.assertIn("examples/anthropic_judge.sh", readme)
        self.assertIn("examples/litellm_judge.sh", readme)
        self.assertIn("examples/openai_judge.sh", readme)

    def test_anthropic_judge_template_is_executable_and_packaged(self) -> None:
        script = Path("examples/anthropic_judge.sh")
        manifest = Path("MANIFEST.in").read_text(encoding="utf-8")

        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111)
        self.assertIn("ANTHROPIC_JUDGE_MODEL", script.read_text(encoding="utf-8"))
        self.assertIn("examples *.jsonl *.md *.py *.sh *.yml", manifest)

    def test_openai_judge_template_is_executable_and_packaged(self) -> None:
        script = Path("examples/openai_judge.sh")
        manifest = Path("MANIFEST.in").read_text(encoding="utf-8")

        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111)
        self.assertIn("OPENAI_JUDGE_MODEL", script.read_text(encoding="utf-8"))
        self.assertIn("examples *.jsonl *.md *.py *.sh *.yml", manifest)

    def test_litellm_judge_template_is_executable_and_packaged(self) -> None:
        script = Path("examples/litellm_judge.sh")
        manifest = Path("MANIFEST.in").read_text(encoding="utf-8")

        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111)
        content = script.read_text(encoding="utf-8")
        self.assertIn("LITELLM_JUDGE_MODEL", content)
        self.assertIn("/v1/chat/completions", content)
        self.assertIn("examples *.jsonl *.md *.py *.sh *.yml", manifest)


if __name__ == "__main__":
    unittest.main()
