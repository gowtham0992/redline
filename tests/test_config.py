import tempfile
import unittest
import json
from pathlib import Path

from redline.config import create_config, default_config, load_config


class ConfigTests(unittest.TestCase):
    def test_default_config_contains_project_defaults(self) -> None:
        config = default_config()

        self.assertEqual(
            config["$schema"],
            "https://raw.githubusercontent.com/gowtham0992/redline/main/redline.schema.json",
        )
        self.assertEqual(config["suite"], "redline-suite.json")
        self.assertEqual(config["input_field"], "prompt")
        self.assertEqual(config["output_field"], "response")
        self.assertEqual(config["timeout_seconds"], 30.0)
        self.assertEqual(config["workers"], 1)
        self.assertEqual(config["diff_profile"], "strict")
        self.assertEqual(config["owners"], [])
        self.assertEqual(config["approval"], {"require_approver": False})
        self.assertEqual(config["fail_on"], ["regression", "missing"])
        self.assertEqual(config["reports"]["json"], ".redline/reports/{command}.json")
        self.assertEqual(config["reports"]["html"], ".redline/reports/{command}.html")
        self.assertEqual(config["reports"]["junit"], ".redline/reports/{command}.xml")
        self.assertEqual(config["logs"]["observed"], ".redline/logs/prompts.jsonl")
        self.assertEqual(config["runs"]["candidate"], ".redline/runs/candidate.jsonl")
        self.assertEqual(config["runs"]["metadata"], ".redline/runs/replay.json")
        self.assertEqual(config["audit"], ".redline/audit.jsonl")

    def test_create_config_refuses_existing_file_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "redline.json"
            path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "already exists"):
                create_config(path)

    def test_create_config_allows_custom_fields(self) -> None:
        config = create_config(
            "redline.json",
            input_field="input",
            output_field="output",
            max_cases=12,
            timeout_seconds=4.5,
            replay="python runner.py",
            judge="python judge.py",
            judge_timeout_seconds=6.5,
        )

        self.assertEqual(config["input_field"], "input")
        self.assertEqual(config["output_field"], "output")
        self.assertEqual(config["max_cases"], 12)
        self.assertEqual(config["timeout_seconds"], 4.5)
        self.assertEqual(config["replay"], "python runner.py")
        self.assertEqual(
            config["judge"],
            {"command": "python judge.py", "timeout_seconds": 6.5},
        )

    def test_create_config_allows_judge_string_without_timeout(self) -> None:
        config = create_config("redline.json", judge="python judge.py")

        self.assertEqual(config["judge"], "python judge.py")

    def test_create_config_refuses_non_positive_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            create_config("redline.json", timeout_seconds=0)

    def test_create_config_refuses_non_positive_judge_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "judge_timeout_seconds"):
            create_config("redline.json", judge="python judge.py", judge_timeout_seconds=0)

    def test_load_config_returns_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_config(Path(directory) / "missing.json"), {})

    def test_load_config_reads_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "redline.json"
            path.write_text('{"suite": "suite.json"}', encoding="utf-8")

            self.assertEqual(load_config(path), {"suite": "suite.json"})

    def test_schema_file_documents_generated_config_keys(self) -> None:
        schema = json.loads(Path("redline.schema.json").read_text(encoding="utf-8"))
        config = default_config()

        self.assertEqual(schema["$id"], config["$schema"])
        self.assertIn("structural and high-signal", schema["description"])
        for key in config:
            self.assertIn(key, schema["properties"])
        for section in ("reports", "logs", "runs"):
            for key in config[section]:
                self.assertIn(key, schema["properties"][section]["properties"])
        self.assertIn("replay", schema["properties"])
        self.assertIn("judge", schema["properties"])
        self.assertIn("judge_timeout_seconds", schema["properties"])


if __name__ == "__main__":
    unittest.main()
