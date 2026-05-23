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


if __name__ == "__main__":
    unittest.main()
