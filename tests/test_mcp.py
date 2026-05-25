import json
import tempfile
import unittest
from pathlib import Path

from redline.mcp import _truncate, call_tool, handle_jsonrpc_line


class McpServerTests(unittest.TestCase):
    def test_initialize_advertises_tools_capability(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        )

        assert response is not None
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["serverInfo"]["name"], "redline")
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertIn("prompts", response["result"]["capabilities"])
        self.assertIn("local-first", response["result"]["instructions"])

    def test_tools_list_exposes_safe_redline_tools(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        )

        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("redline_doctor", names)
        self.assertIn("redline_suite", names)
        self.assertIn("redline_redact", names)
        self.assertIn("redline_benchmark", names)
        self.assertIn("redline_eval", names)
        self.assertIn("redline_diff", names)
        self.assertIn("redline_dashboard", names)
        self.assertIn("redline_audit", names)
        self.assertNotIn("redline_accept", names)
        self.assertNotIn("redline_mark", names)
        self.assertNotIn("redline_require", names)

    def test_prompts_list_exposes_agent_workflows(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 30, "method": "prompts/list"})
        )

        assert response is not None
        names = {prompt["name"] for prompt in response["result"]["prompts"]}
        self.assertIn("check_prompt_change", names)
        self.assertIn("build_suite_from_logs", names)
        self.assertIn("review_candidate_outputs", names)

    def test_prompt_get_builds_check_prompt_change_workflow(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 31,
                    "method": "prompts/get",
                    "params": {
                        "name": "check_prompt_change",
                        "arguments": {"prompt_path": "prompts/v2.txt", "suite_path": "redline-suite.json"},
                    },
                }
            )
        )

        assert response is not None
        text = response["result"]["messages"][0]["content"]["text"]
        self.assertIn("redline_doctor", text)
        self.assertIn("redline_eval", text)
        self.assertIn("prompts/v2.txt", text)
        self.assertIn("redline-suite.json", text)
        self.assertIn("Do not call baseline mutation commands", text)

    def test_prompt_get_build_suite_workflow_includes_benchmark(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 33,
                    "method": "prompts/get",
                    "params": {
                        "name": "build_suite_from_logs",
                        "arguments": {"log_path": "logs/baseline.jsonl"},
                    },
                }
            )
        )

        assert response is not None
        text = response["result"]["messages"][0]["content"]["text"]
        self.assertIn("redline_suite", text)
        self.assertIn("redline_summary", text)
        self.assertIn("redline_benchmark", text)

    def test_unknown_prompt_returns_jsonrpc_error(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 32,
                    "method": "prompts/get",
                    "params": {"name": "missing_prompt", "arguments": {}},
                }
            )
        )

        assert response is not None
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("unknown prompt", response["error"]["message"])

    def test_tool_call_runs_doctor_and_returns_structured_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            response = handle_jsonrpc_line(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "redline_doctor",
                            "arguments": {"cwd": directory},
                        },
                    }
                )
            )

        assert response is not None
        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertIn("redline doctor", result["content"][0]["text"])
        self.assertIn("redline init --runner stdio --copy-runner", result["content"][0]["text"])

    def test_diff_regressions_are_product_findings_not_mcp_errors(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        baseline = repo / "examples" / "baseline.jsonl"
        candidate = repo / "examples" / "candidate.jsonl"

        with tempfile.TemporaryDirectory() as directory:
            suite_path = Path(directory) / "redline-suite.json"
            suite_result = call_tool(
                "redline_suite",
                {
                    "cwd": directory,
                    "log_path": str(baseline),
                    "out": str(suite_path),
                    "all_cases": True,
                },
            )
            self.assertFalse(suite_result["isError"])
            self.assertEqual(suite_result["structuredContent"]["exit_code"], 0)

            diff_result = call_tool(
                "redline_diff",
                {
                    "cwd": directory,
                    "suite_path": str(suite_path),
                    "candidate_path": str(candidate),
                    "compact": True,
                },
            )

        self.assertFalse(diff_result["isError"])
        self.assertEqual(diff_result["structuredContent"]["exit_code"], 1)
        self.assertIn("regression=4", diff_result["content"][0]["text"])
        self.assertIn("candidate missing JSON keys", diff_result["content"][0]["text"])

    def test_benchmark_tool_reports_ci_scale(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        baseline = repo / "examples" / "baseline.jsonl"

        with tempfile.TemporaryDirectory() as directory:
            suite_path = Path(directory) / "redline-suite.json"
            suite_result = call_tool(
                "redline_suite",
                {
                    "cwd": directory,
                    "log_path": str(baseline),
                    "out": str(suite_path),
                    "all_cases": True,
                },
            )
            self.assertFalse(suite_result["isError"])

            benchmark_result = call_tool(
                "redline_benchmark",
                {
                    "cwd": directory,
                    "suite_path": str(suite_path),
                    "timeout": 10,
                    "workers": 2,
                    "max_seconds": 5,
                },
            )

        self.assertFalse(benchmark_result["isError"])
        self.assertEqual(benchmark_result["structuredContent"]["exit_code"], 1)
        self.assertIn("redline benchmark", benchmark_result["content"][0]["text"])
        self.assertIn("Workers:               2", benchmark_result["content"][0]["text"])
        self.assertIn("Budget check:          FAIL", benchmark_result["content"][0]["text"])
        self.assertIn("Worst-case eval budget:", benchmark_result["content"][0]["text"])

    def test_redact_and_audit_tools_cover_privacy_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.jsonl"
            raw.write_text(
                '{"prompt": "Email ada@example.com", "response": "ok", "token": "secret"}\n',
                encoding="utf-8",
            )

            redact_result = call_tool(
                "redline_redact",
                {"cwd": directory, "log_path": "raw.jsonl", "check": True},
            )
            audit_result = call_tool(
                "redline_audit",
                {"cwd": directory, "limit": 0, "verify": True},
            )

        self.assertFalse(redact_result["isError"])
        self.assertEqual(redact_result["structuredContent"]["exit_code"], 0)
        self.assertIn("Mode:       check only", redact_result["content"][0]["text"])
        self.assertIn("Redactions: 2", redact_result["content"][0]["text"])
        self.assertFalse(audit_result["isError"])
        self.assertIn("log_redaction_checked", audit_result["content"][0]["text"])
        self.assertIn("redactions=2", audit_result["content"][0]["text"])
        self.assertIn("redline audit verify", audit_result["content"][0]["text"])
        self.assertIn("Status:   OK", audit_result["content"][0]["text"])

    def test_unknown_tool_returns_jsonrpc_error(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "redline_accept", "arguments": {}},
                }
            )
        )

        assert response is not None
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("unknown tool", response["error"]["message"])

    def test_output_truncation_preserves_utf8_boundaries(self) -> None:
        stdout, stderr, truncated = _truncate("safe ✓ output", "error", 8)

        output_size = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
        self.assertLessEqual(output_size, 8)
        self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
