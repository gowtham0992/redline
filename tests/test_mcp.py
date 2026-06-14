import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from redline.mcp import _run_redline, _truncate, call_tool, handle_jsonrpc_line


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

    def test_tools_list_exposes_redline_tools_with_guarded_writes(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        )

        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("redline_doctor", names)
        self.assertIn("redline_suite", names)
        self.assertIn("redline_quick_check", names)
        self.assertIn("redline_redact", names)
        self.assertIn("redline_import", names)
        self.assertIn("redline_import_presets", names)
        self.assertIn("redline_watch_stats", names)
        self.assertIn("redline_watch_snippets", names)
        self.assertIn("redline_prompts", names)
        self.assertIn("redline_judges", names)
        self.assertIn("redline_runners", names)
        self.assertIn("redline_budget", names)
        self.assertIn("redline_benchmark", names)
        self.assertIn("redline_eval", names)
        self.assertIn("redline_diff", names)
        self.assertIn("redline_dashboard", names)
        self.assertIn("redline_audit", names)
        self.assertIn("redline_sbom", names)
        self.assertIn("redline_case", names)
        self.assertIn("redline_mark", names)
        self.assertNotIn("redline_accept", names)
        self.assertNotIn("redline_require", names)

    def test_quick_check_tool_generates_suite_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.jsonl"
            candidate = root / "candidate.jsonl"
            baseline.write_text(
                '{"prompt": "Return JSON with owner and priority.", "response": "{\\"owner\\": \\"Support\\", \\"priority\\": \\"high\\"}"}\n',
                encoding="utf-8",
            )
            candidate.write_text(
                '{"prompt": "Return JSON with owner and priority.", "response": "Support should handle this."}\n',
                encoding="utf-8",
            )

            result = call_tool(
                "redline_quick_check",
                {
                    "cwd": directory,
                    "baseline_path": "baseline.jsonl",
                    "candidate_path": "candidate.jsonl",
                    "fail_on": "none",
                    "json": True,
                },
            )
            report_dir = root / ".redline" / "quick-check"
            suite_exists = (report_dir / "suite.json").exists()
            json_exists = (report_dir / "diff.json").exists()
            html_exists = (report_dir / "diff.html").exists()

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        payload = result["structuredContent"]["json"]
        self.assertEqual(payload["summary"]["regression"], 1)
        self.assertEqual(payload["artifacts"]["html"], ".redline/quick-check/diff.html")
        self.assertTrue(suite_exists)
        self.assertTrue(json_exists)
        self.assertTrue(html_exists)

    def test_import_tool_normalizes_external_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            output = root / "baseline.jsonl"
            source.write_text(
                '{"instruction": "Classify", "context": "Ticket text", "response": "billing", "category": "classification"}\n',
                encoding="utf-8",
            )

            result = call_tool(
                "redline_import",
                {
                    "cwd": directory,
                    "path": str(source),
                    "out": str(output),
                    "preset": "dolly",
                    "input_field": "instruction",
                    "output_field": "response",
                    "context_field": "context",
                    "metadata_fields": ["category"],
                    "json": True,
                },
            )
            wrote_output = output.exists()

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertEqual(result["structuredContent"]["json"]["records"], 1)
        self.assertEqual(result["structuredContent"]["json"]["preset"], "dolly")
        self.assertTrue(result["structuredContent"]["json"]["redacted"])
        self.assertTrue(wrote_output)

    def test_import_tool_previews_external_jsonl_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "downloaded.jsonl"
            output = root / "baseline.jsonl"
            source.write_text(
                '{"instruction": "Classify", "response": "billing"}\n',
                encoding="utf-8",
            )

            result = call_tool(
                "redline_import",
                {
                    "cwd": directory,
                    "path": str(source),
                    "input_field": "instruction",
                    "output_field": "response",
                    "preview": 1,
                    "json": True,
                },
            )
            wrote_output = output.exists()

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertEqual(result["structuredContent"]["json"]["previewed"], 1)
        self.assertEqual(result["structuredContent"]["json"]["rows"][0]["prompt"], "Classify")
        self.assertFalse(wrote_output)

    def test_import_tool_detects_external_jsonl_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "export.jsonl"
            source.write_text('{"input": "Classify", "output": "billing"}\n', encoding="utf-8")

            result = call_tool(
                "redline_import",
                {
                    "cwd": directory,
                    "path": str(source),
                    "detect": True,
                    "json": True,
                },
            )

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertEqual(result["structuredContent"]["json"]["suggestions"][0]["input_field"], "input")
        self.assertEqual(result["structuredContent"]["json"]["suggestions"][0]["output_field"], "output")

    def test_import_presets_tool_lists_mappings(self) -> None:
        result = call_tool("redline_import_presets", {"json": True})

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        presets = result["structuredContent"]["json"]["presets"]
        self.assertTrue(any(row["id"] == "langfuse" for row in presets))
        self.assertTrue(any(row["id"] == "openai-chat" for row in presets))

    def test_eval_and_diff_tools_do_not_accept_dynamic_commands(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 20, "method": "tools/list"})
        )

        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        diff_props = tools["redline_diff"]["inputSchema"]["properties"]
        eval_props = tools["redline_eval"]["inputSchema"]["properties"]

        self.assertNotIn("judge", diff_props)
        self.assertNotIn("judge_timeout", diff_props)
        self.assertNotIn("replay", eval_props)
        self.assertNotIn("judge", eval_props)
        self.assertNotIn("judge_timeout", eval_props)

    def test_prompts_list_exposes_agent_workflows(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps({"jsonrpc": "2.0", "id": 30, "method": "prompts/list"})
        )

        assert response is not None
        names = {prompt["name"] for prompt in response["result"]["prompts"]}
        self.assertIn("check_prompt_change", names)
        self.assertIn("build_suite_from_logs", names)
        self.assertIn("review_candidate_outputs", names)
        self.assertIn("setup_redline_project", names)

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
        self.assertIn("redline_cases", text)
        self.assertIn("redline_case", text)
        self.assertIn("redline suite add", text)
        self.assertIn("redline_budget", text)

    def test_prompt_get_builds_first_time_setup_workflow(self) -> None:
        response = handle_jsonrpc_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 34,
                    "method": "prompts/get",
                    "params": {
                        "name": "setup_redline_project",
                        "arguments": {
                            "log_path": "logs/baseline.jsonl",
                            "prompt_path": "prompts",
                            "runner": "http",
                            "judge": "support-rubric",
                        },
                    },
                }
            )
        )

        assert response is not None
        text = response["result"]["messages"][0]["content"]["text"]
        self.assertIn("redline_doctor", text)
        self.assertIn("redline_runners", text)
        self.assertIn("redline_watch_snippets", text)
        self.assertIn("redline_prompts", text)
        self.assertIn("redline_suite", text)
        self.assertIn("redline_validate", text)
        self.assertIn("redline_summary", text)
        self.assertIn("redline_cases", text)
        self.assertIn("redline_case", text)
        self.assertIn("redline_budget", text)
        self.assertIn("redline_judges", text)
        self.assertIn("logs/baseline.jsonl", text)
        self.assertIn("prompts", text)
        self.assertIn("http", text)
        self.assertIn("support-rubric", text)
        self.assertIn("do not say green or neutral means semantically safe", text)

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

    def test_watch_snippets_tool_prints_capture_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = call_tool(
                "redline_watch_snippets",
                {
                    "cwd": directory,
                    "kind": "fastapi",
                },
            )

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertIn("FastAPI or ASGI middleware", result["content"][0]["text"])
        self.assertIn("RedlineMiddleware", result["content"][0]["text"])
        self.assertIn("redline watch --stats", result["content"][0]["text"])

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
                    "out_comment": "diff-comment.md",
                    "out_slack": "diff.slack.json",
                },
            )
            wrote_comment = (Path(directory) / "diff-comment.md").exists()
            wrote_slack = (Path(directory) / "diff.slack.json").exists()

        self.assertFalse(diff_result["isError"])
        self.assertEqual(diff_result["structuredContent"]["exit_code"], 1)
        self.assertIn("regression=4", diff_result["content"][0]["text"])
        self.assertIn("candidate missing JSON keys", diff_result["content"][0]["text"])
        self.assertTrue(wrote_comment)
        self.assertTrue(wrote_slack)

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
                "redline_budget",
                {
                    "cwd": directory,
                    "suite_path": str(suite_path),
                    "timeout": 10,
                    "workers": 2,
                    "max_seconds": 5,
                    "out_json": "benchmark.json",
                    "out_md": "benchmark.md",
                },
            )
            wrote_json = (Path(directory) / "benchmark.json").exists()
            wrote_markdown = (Path(directory) / "benchmark.md").exists()

        self.assertFalse(benchmark_result["isError"])
        self.assertEqual(benchmark_result["structuredContent"]["exit_code"], 1)
        self.assertIn("redline budget", benchmark_result["content"][0]["text"])
        self.assertIn("Workers:               2", benchmark_result["content"][0]["text"])
        self.assertIn("Budget check:          FAIL", benchmark_result["content"][0]["text"])
        self.assertIn("Worst-case eval budget:", benchmark_result["content"][0]["text"])
        self.assertTrue(wrote_json)
        self.assertTrue(wrote_markdown)

    def test_case_tool_shows_one_suite_case_detail(self) -> None:
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
            suite = json.loads(suite_path.read_text(encoding="utf-8"))
            case_id = suite["cases"][0]["id"]

            case_result = call_tool(
                "redline_case",
                {
                    "cwd": directory,
                    "suite_path": str(suite_path),
                    "case_id": case_id,
                },
            )

        self.assertFalse(case_result["isError"])
        self.assertEqual(case_result["structuredContent"]["exit_code"], 0)
        self.assertIn("redline case", case_result["content"][0]["text"])
        self.assertIn(case_id, case_result["content"][0]["text"])
        self.assertIn("Baseline response:", case_result["content"][0]["text"])

    def test_mark_tool_requires_write_approval_and_records_judgment(self) -> None:
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
            suite = json.loads(suite_path.read_text(encoding="utf-8"))
            case_id = suite["cases"][0]["id"]

            denied = handle_jsonrpc_line(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 35,
                        "method": "tools/call",
                        "params": {
                            "name": "redline_mark",
                            "arguments": {
                                "cwd": directory,
                                "suite_path": str(suite_path),
                                "case_id": case_id,
                                "status": "expected",
                                "note": "intentional behavior change",
                            },
                        },
                    }
                )
            )
            marked = call_tool(
                "redline_mark",
                {
                    "cwd": directory,
                    "suite_path": str(suite_path),
                    "case_id": case_id,
                    "status": "expected",
                    "note": "intentional behavior change",
                    "allow_write": True,
                },
            )
            updated = json.loads(suite_path.read_text(encoding="utf-8"))

        assert denied is not None
        self.assertEqual(denied["error"]["code"], -32602)
        self.assertIn("allow_write=true", denied["error"]["message"])
        self.assertFalse(marked["isError"])
        self.assertEqual(marked["structuredContent"]["exit_code"], 0)
        self.assertIn(f"Marked {case_id} as expected", marked["content"][0]["text"])
        self.assertEqual(updated["judgments"][case_id]["status"], "expected")
        self.assertEqual(updated["judgments"][case_id]["note"], "intentional behavior change")

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
                {
                    "cwd": directory,
                    "limit": 0,
                    "verify": True,
                    "out_checkpoint": ".redline/audit-checkpoint.json",
                },
            )
            checkpoint = json.loads((root / ".redline" / "audit-checkpoint.json").read_text(encoding="utf-8"))

        self.assertFalse(redact_result["isError"])
        self.assertEqual(redact_result["structuredContent"]["exit_code"], 0)
        self.assertIn("Mode:       check only", redact_result["content"][0]["text"])
        self.assertIn("Redactions: 2", redact_result["content"][0]["text"])
        self.assertFalse(audit_result["isError"])
        self.assertIn("log_redaction_checked", audit_result["content"][0]["text"])
        self.assertIn("redactions=2", audit_result["content"][0]["text"])
        self.assertIn("redline audit verify", audit_result["content"][0]["text"])
        self.assertIn("Status:   OK", audit_result["content"][0]["text"])
        self.assertEqual(checkpoint["schema"], "redline-audit-checkpoint-v1")
        self.assertEqual(checkpoint["entries"], 1)

    def test_watch_stats_tool_surfaces_capture_readiness_and_skips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "observed.jsonl"
            skip_log = root / "skips.jsonl"
            log.write_text(
                '{"prompt":"hello","response":"world","observed_at":"2026-05-25T00:00:00+00:00","source":"test","content_hash":"abc"}\n',
                encoding="utf-8",
            )
            skip_log.write_text(
                '{"event":"middleware_capture_skipped","reason":"response_streaming","observed_at":"2026-05-25T00:00:01+00:00","source":"asgi:POST /chat","metadata":{}}\n',
                encoding="utf-8",
            )

            result = call_tool(
                "redline_watch_stats",
                {
                    "cwd": directory,
                    "log_path": "observed.jsonl",
                    "skip_log": "skips.jsonl",
                },
            )

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertIn("redline watch", result["content"][0]["text"])
        self.assertIn("Records:           1", result["content"][0]["text"])
        self.assertIn("Skipped captures:  1", result["content"][0]["text"])
        self.assertIn("response_streaming=1", result["content"][0]["text"])

    def test_prompts_tool_checks_manifest_suite_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts"
            prompts.mkdir()
            (prompts / "support.txt").write_text("support prompt\n", encoding="utf-8")

            create_result = call_tool(
                "redline_prompts",
                {
                    "cwd": directory,
                    "path": "prompts",
                    "suite_dir": "suites",
                    "out": "redline-prompts.json",
                },
            )
            check_result = call_tool(
                "redline_prompts",
                {
                    "cwd": directory,
                    "path": "prompts",
                    "suite_dir": "suites",
                    "out": "redline-prompts.json",
                    "check": True,
                    "check_suites": True,
                },
            )

        self.assertFalse(create_result["isError"])
        self.assertEqual(create_result["structuredContent"]["exit_code"], 0)
        self.assertFalse(check_result["isError"])
        self.assertEqual(check_result["structuredContent"]["exit_code"], 1)
        self.assertIn("redline prompts check", check_result["content"][0]["text"])
        self.assertIn("Suites:   0/1 present", check_result["content"][0]["text"])

    def test_judges_tool_lists_and_copies_semantic_templates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            list_result = call_tool("redline_judges", {"cwd": directory})
            copy_result = call_tool(
                "redline_judges",
                {
                    "cwd": directory,
                    "copy": "support-rubric",
                    "out": "judges/support.md",
                },
            )
            copied = Path(directory) / "judges" / "support.md"
            copied_exists = copied.exists()

        self.assertFalse(list_result["isError"])
        self.assertIn("redline judges", list_result["content"][0]["text"])
        self.assertIn("Support-agent rubric", list_result["content"][0]["text"])
        self.assertFalse(copy_result["isError"])
        self.assertEqual(copy_result["structuredContent"]["exit_code"], 0)
        self.assertTrue(copied_exists)
        self.assertIn("Wrote judges/support.md.", copy_result["content"][0]["text"])
        self.assertIn("REDLINE_JUDGE_RUBRIC=judges/support.md", copy_result["content"][0]["text"])

    def test_runners_tool_lists_and_copies_replay_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            list_result = call_tool("redline_runners", {"cwd": directory})
            copy_result = call_tool(
                "redline_runners",
                {
                    "cwd": directory,
                    "copy": "http",
                    "out": "runners/http.py",
                },
            )
            copied = Path(directory) / "runners" / "http.py"
            copied_exists = copied.exists()

        self.assertFalse(list_result["isError"])
        self.assertIn("redline runners", list_result["content"][0]["text"])
        self.assertIn("HTTP API", list_result["content"][0]["text"])
        self.assertFalse(copy_result["isError"])
        self.assertEqual(copy_result["structuredContent"]["exit_code"], 0)
        self.assertTrue(copied_exists)
        self.assertIn("Wrote runners/http.py.", copy_result["content"][0]["text"])
        self.assertIn("Replay: python runners/http.py", copy_result["content"][0]["text"])

    def test_sbom_tool_writes_release_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = call_tool(
                "redline_sbom",
                {
                    "cwd": directory,
                    "out": "redline-sbom.json",
                },
            )
            sbom_path = Path(directory) / "redline-sbom.json"
            payload = json.loads(sbom_path.read_text(encoding="utf-8"))

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertIn("redline sbom", result["content"][0]["text"])
        self.assertIn("Wrote redline-sbom.json.", result["content"][0]["text"])
        self.assertEqual(payload["bomFormat"], "CycloneDX")

    def test_json_tool_output_is_exposed_as_structured_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = call_tool(
                "redline_sbom",
                {
                    "cwd": directory,
                    "json": True,
                },
            )

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["exit_code"], 0)
        self.assertEqual(result["structuredContent"]["json"]["bomFormat"], "CycloneDX")
        self.assertEqual(
            result["structuredContent"]["json"]["metadata"]["component"]["name"],
            "redline-ai",
        )

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

    def test_run_redline_passes_cwd_without_changing_process_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path.cwd()
            completed = subprocess.CompletedProcess(
                args=["python", "-m", "redline", "doctor"],
                returncode=0,
                stdout="ok\n",
                stderr="",
            )

            with patch("redline.mcp.subprocess.run", return_value=completed) as run:
                result = _run_redline(["doctor"], cwd=Path(directory), max_output_bytes=1000)

        self.assertEqual(Path.cwd(), cwd)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "ok\n")
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["cwd"], Path(directory))
        self.assertTrue(run.call_args.kwargs["capture_output"])


if __name__ == "__main__":
    unittest.main()
