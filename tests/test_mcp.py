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
        self.assertIn("local-first", response["result"]["instructions"])

    def test_tools_list_exposes_safe_redline_tools(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        )

        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("redline_doctor", names)
        self.assertIn("redline_suite", names)
        self.assertIn("redline_eval", names)
        self.assertIn("redline_diff", names)
        self.assertIn("redline_dashboard", names)
        self.assertNotIn("redline_accept", names)
        self.assertNotIn("redline_mark", names)
        self.assertNotIn("redline_require", names)

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
