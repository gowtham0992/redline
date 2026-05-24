import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DogfoodNormalizerTests(unittest.TestCase):
    def test_normalizes_ai_session_logs_and_drops_recording_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts.jsonl"
            raw = root / "claude.jsonl"
            out = root / "normalized"
            prompts.write_text(
                '{"prompt": "Task one"}\n'
                '{"prompt": "Task two"}\n',
                encoding="utf-8",
            )
            raw.write_text(
                json.dumps(
                    {
                        "prompt": "I am dogfooding redline. For this session, record every substantive user task.",
                        "response": "Understood.",
                    }
                )
                + "\n"
                + json.dumps({"prompt": "1. Original one", "response": "Answer one"})
                + "\n"
                + json.dumps({"prompt": "2. Original two", "response": "Answer two"})
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/normalize_ai_session_logs.py",
                    "--prompts",
                    str(prompts),
                    "--out",
                    str(out),
                    f"claude={raw}",
                ],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
            )

            self.assertIn("wrote", completed.stdout)
            rows = [
                json.loads(line)
                for line in (out / "claude.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([row["case_id"] for row in rows], ["task_01", "task_02"])
            self.assertEqual([row["prompt"] for row in rows], ["Task one", "Task two"])
            self.assertEqual(rows[0]["metadata"]["original_prompt"], "1. Original one")
            self.assertEqual(rows[0]["metadata"]["tool"], "claude")


if __name__ == "__main__":
    unittest.main()
