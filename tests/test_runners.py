import importlib.util
import json
import os
import subprocess
import tempfile
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

    def test_anthropic_runner_fails_clearly_without_api_key(self) -> None:
        runner = Path("runners/anthropic_runner.sh")

        completed = subprocess.run(
            ["bash", str(runner)],
            input="hello",
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ANTHROPIC_API_KEY", completed.stderr)

    def test_runner_docs_include_anthropic_wire_command(self) -> None:
        docs = Path("docs/runners.md").read_text(encoding="utf-8")

        self.assertIn("## Anthropic Direct", docs)
        self.assertIn(
            'redline eval --prompt prompts/v2.txt --replay "./runners/anthropic_runner.sh"',
            docs,
        )

    def test_http_runner_fails_clearly_without_url(self) -> None:
        completed = subprocess.run(
            ["python", "runners/http_runner.py"],
            input="hello",
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("REDLINE_HTTP_URL", completed.stderr)

    def test_http_runner_supports_nested_response_fields(self) -> None:
        spec = importlib.util.spec_from_file_location("http_runner", "runners/http_runner.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module._get_field({"result": {"text": "runner ok"}}, "result.text"), "runner ok")

    def test_runner_docs_include_http_wire_command(self) -> None:
        docs = Path("docs/runners.md").read_text(encoding="utf-8")

        self.assertIn("## HTTP API", docs)
        self.assertIn('redline eval --prompt prompts/v2.txt --replay "python runners/http_runner.py"', docs)

    def test_jsonl_log_adapter_converts_nested_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "export.jsonl"
            output = root / "prompts.jsonl"
            source.write_text(
                '{"request": {"prompt": "hello"}, "response": {"text": "world"}}\n',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python",
                    "runners/jsonl_log_adapter.py",
                    str(source),
                    "--input-field",
                    "request.prompt",
                    "--output-field",
                    "response.text",
                    "--out",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0)
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["prompt"], "hello")
            self.assertEqual(row["response"], "world")
            self.assertEqual(row["source_line"], 1)

    def test_runner_docs_include_app_logs_adapter(self) -> None:
        docs = Path("docs/runners.md").read_text(encoding="utf-8")

        self.assertIn("## App Logs To JSONL", docs)
        self.assertIn("python runners/jsonl_log_adapter.py logs/export.jsonl", docs)
