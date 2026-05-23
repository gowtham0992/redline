import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from redline.runners import format_runner_adapters, runner_adapters


class RunnerTests(unittest.TestCase):
    def test_runner_adapters_list_core_set(self) -> None:
        adapters = runner_adapters()
        ids = {adapter["id"] for adapter in adapters}

        self.assertIn("openai", ids)
        self.assertIn("anthropic", ids)
        self.assertIn("python-chain", ids)
        self.assertIn("http", ids)
        self.assertIn("jsonl-logs", ids)
        self.assertIn("litellm", ids)

    def test_format_runner_adapters_prints_replay_commands(self) -> None:
        output = format_runner_adapters()

        self.assertIn("redline runners", output)
        self.assertIn("./runners/openai_runner.sh", output)
        self.assertIn("python runners/http_runner.py", output)

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

    def test_litellm_runner_fails_clearly_without_api_key(self) -> None:
        runner = Path("runners/litellm_runner.sh")

        completed = subprocess.run(
            ["bash", str(runner)],
            input="hello",
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("LITELLM_API_KEY", completed.stderr)

    def test_runner_docs_include_litellm_wire_command(self) -> None:
        docs = Path("docs/runners.md").read_text(encoding="utf-8")

        self.assertIn("## LiteLLM Or Model Proxy", docs)
        self.assertIn('redline eval --prompt prompts/v2.txt --replay "./runners/litellm_runner.sh"', docs)

    def test_python_chain_runner_fails_clearly_without_target(self) -> None:
        completed = subprocess.run(
            ["python", "runners/python_chain_runner.py"],
            input="hello",
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("REDLINE_PYTHON_RUNNER", completed.stderr)

    def test_python_chain_runner_imports_configured_function(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "my_runner.py").write_text(
                "def run(prompt):\n"
                "    return prompt.upper()\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                ["python", "runners/python_chain_runner.py"],
                input="hello",
                text=True,
                capture_output=True,
                check=False,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": str(root),
                    "REDLINE_PYTHON_RUNNER": "my_runner:run",
                },
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "HELLO")

    def test_runner_docs_include_python_chain_wire_command(self) -> None:
        docs = Path("docs/runners.md").read_text(encoding="utf-8")

        self.assertIn("## LangChain Or LlamaIndex", docs)
        self.assertIn(
            'redline eval --prompt prompts/v2.txt --replay "python runners/python_chain_runner.py"',
            docs,
        )
