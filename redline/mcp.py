from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

from . import __version__
from .cli import main as redline_cli_main


PROTOCOL_VERSION = "2025-06-18"
DEFAULT_MAX_OUTPUT_BYTES = 60_000


@dataclass(frozen=True)
class ToolResult:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False

    @property
    def is_protocol_error(self) -> bool:
        return self.exit_code >= 2

    def text(self) -> str:
        lines = [
            f"$ {' '.join(self.command)}",
            f"cwd: {self.cwd}",
            f"exit_code: {self.exit_code}",
        ]
        if self.truncated:
            lines.append(f"output: truncated to {DEFAULT_MAX_OUTPUT_BYTES} bytes")
        if self.stdout:
            lines.extend(["", "stdout:", self.stdout.rstrip()])
        if self.stderr:
            lines.extend(["", "stderr:", self.stderr.rstrip()])
        return "\n".join(lines).rstrip() + "\n"

    def structured(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    build_args: Callable[[dict[str, Any]], list[str]]

    def as_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass(frozen=True)
class PromptArgument:
    name: str
    description: str
    required: bool = False

    def as_mcp_argument(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
        }


@dataclass(frozen=True)
class PromptSpec:
    name: str
    description: str
    arguments: tuple[PromptArgument, ...]
    build_text: Callable[[dict[str, Any]], str]

    def as_mcp_prompt(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [argument.as_mcp_argument() for argument in self.arguments],
        }


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help"}:
        print(
            "redline-mcp\n\n"
            "Local MCP stdio server for redline.\n\n"
            "Run this command from an MCP client. It exposes redline doctor, suite,\n"
            "validate, summary, diff, eval, history, dashboard, and cases tools.\n",
            end="",
        )
        return 0
    serve()
    return 0


def serve(
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    for raw_line in source:
        line = raw_line.strip()
        if not line:
            continue
        response = handle_jsonrpc_line(line)
        if response is None:
            continue
        sink.write(json.dumps(response, separators=(",", ":")) + "\n")
        sink.flush()


def handle_jsonrpc_line(line: str) -> dict[str, Any] | None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        return _error(None, -32700, f"parse error: {exc.msg}")
    if not isinstance(request, dict):
        return _error(None, -32600, "invalid request")
    return handle_request(request)


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "redline", "version": __version__},
                "instructions": (
                    "Use redline tools to generate prompt regression suites, "
                    "evaluate prompt changes, inspect reports, and review local setup. "
                    "redline is local-first and does not call cloud models unless a "
                    "project-configured replay or judge command does."
                ),
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": [tool.as_mcp_tool() for tool in _tools()]})
    if method == "tools/call":
        return _handle_tool_call(request_id, request.get("params"))
    if method == "prompts/list":
        return _result(
            request_id,
            {"prompts": [prompt.as_mcp_prompt() for prompt in _prompts()]},
        )
    if method == "prompts/get":
        return _handle_prompt_get(request_id, request.get("params"))
    return _error(request_id, -32601, f"method not found: {method}")


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    tool = _tool_by_name(name)
    if tool is None:
        raise ValueError(f"unknown tool: {name}")
    args = arguments or {}
    command_args = tool.build_args(args)
    result = _run_redline(command_args, cwd=_cwd(args), max_output_bytes=_max_output_bytes(args))
    return _tool_result_payload(result)


def _handle_tool_call(request_id: Any, params: object) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _error(request_id, -32602, "tools/call params must be an object")
    name = params.get("name")
    if not isinstance(name, str) or not name:
        return _error(request_id, -32602, "tools/call requires a tool name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "tools/call arguments must be an object")
    tool = _tool_by_name(name)
    if tool is None:
        return _error(request_id, -32602, f"unknown tool: {name}")
    try:
        command_args = tool.build_args(arguments)
        result = _run_redline(
            command_args,
            cwd=_cwd(arguments),
            max_output_bytes=_max_output_bytes(arguments),
        )
    except ValueError as exc:
        return _error(request_id, -32602, str(exc))
    return _result(request_id, _tool_result_payload(result))


def _handle_prompt_get(request_id: Any, params: object) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _error(request_id, -32602, "prompts/get params must be an object")
    name = params.get("name")
    if not isinstance(name, str) or not name:
        return _error(request_id, -32602, "prompts/get requires a prompt name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "prompts/get arguments must be an object")
    prompt = _prompt_by_name(name)
    if prompt is None:
        return _error(request_id, -32602, f"unknown prompt: {name}")
    try:
        text = prompt.build_text(arguments)
    except ValueError as exc:
        return _error(request_id, -32602, str(exc))
    return _result(
        request_id,
        {
            "description": prompt.description,
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        },
    )


def _tool_result_payload(result: ToolResult) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": result.text()}],
        "structuredContent": result.structured(),
        "isError": result.is_protocol_error,
    }


def _run_redline(
    args: list[str],
    *,
    cwd: Path,
    max_output_bytes: int,
) -> ToolResult:
    previous = Path.cwd()
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = 0
    try:
        os.chdir(cwd)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                exit_code = redline_cli_main(args)
            except SystemExit as exc:
                code = exc.code
                exit_code = code if isinstance(code, int) else 1
    except Exception as exc:  # pragma: no cover - defensive boundary for MCP clients.
        exit_code = 2
        stderr.write(f"redline-mcp: {exc}\n")
    finally:
        os.chdir(previous)

    out_text, err_text, truncated = _truncate(stdout.getvalue(), stderr.getvalue(), max_output_bytes)
    return ToolResult(
        command=["redline", *args],
        cwd=str(cwd),
        exit_code=exit_code,
        stdout=out_text,
        stderr=err_text,
        truncated=truncated,
    )


def _truncate(stdout: str, stderr: str, max_output_bytes: int) -> tuple[str, str, bool]:
    if max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be greater than 0")
    total = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
    if total <= max_output_bytes:
        return stdout, stderr, False
    truncated_stdout = _truncate_text_to_bytes(stdout, max_output_bytes)
    remaining = max_output_bytes - len(truncated_stdout.encode("utf-8"))
    truncated_stderr = _truncate_text_to_bytes(stderr, remaining)
    return truncated_stdout, truncated_stderr, True


def _truncate_text_to_bytes(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _cwd(arguments: dict[str, Any]) -> Path:
    value = arguments.get("cwd")
    path = Path(str(value)).expanduser() if isinstance(value, str) and value else Path.cwd()
    if not path.exists():
        raise ValueError(f"cwd not found: {path}")
    if not path.is_dir():
        raise ValueError(f"cwd is not a directory: {path}")
    return path.resolve()


def _max_output_bytes(arguments: dict[str, Any]) -> int:
    value = arguments.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_output_bytes must be an integer")
    return value


def _prompts() -> list[PromptSpec]:
    return [
        PromptSpec(
            "check_prompt_change",
            "Run the redline setup check and evaluate a changed prompt before shipping.",
            (
                PromptArgument("cwd", "Project directory where redline should run."),
                PromptArgument("prompt_path", "Changed prompt template file to evaluate."),
                PromptArgument("suite_path", "Optional suite JSON path."),
            ),
            _build_check_prompt_change_prompt,
        ),
        PromptSpec(
            "build_suite_from_logs",
            "Turn existing prompt-response logs into a suite and inspect coverage.",
            (
                PromptArgument("cwd", "Project directory where redline should run."),
                PromptArgument("log_path", "Baseline JSONL prompt-response log.", required=True),
                PromptArgument("suite_path", "Suite JSON output path."),
            ),
            _build_suite_from_logs_prompt,
        ),
        PromptSpec(
            "review_candidate_outputs",
            "Compare candidate JSONL outputs against a suite and summarize risky behavior changes.",
            (
                PromptArgument("cwd", "Project directory where redline should run."),
                PromptArgument("candidate_path", "Candidate JSONL outputs to compare.", required=True),
                PromptArgument("suite_path", "Optional suite JSON path."),
            ),
            _build_review_candidate_outputs_prompt,
        ),
    ]


def _prompt_by_name(name: str) -> PromptSpec | None:
    return next((prompt for prompt in _prompts() if prompt.name == name), None)


def _build_check_prompt_change_prompt(arguments: dict[str, Any]) -> str:
    cwd = _optional_prompt_argument(arguments, "cwd", "the current project")
    prompt_path = _optional_prompt_argument(arguments, "prompt_path", "the changed prompt file")
    suite_path = _optional_prompt_argument(arguments, "suite_path", "the configured suite")
    return (
        "Check whether my prompt change introduced regressions with redline.\n\n"
        f"- Run in: {cwd}\n"
        f"- Prompt file: {prompt_path}\n"
        f"- Suite: {suite_path}\n\n"
        "Use this workflow:\n"
        "1. Call `redline_doctor` first. If setup has errors, stop and tell me the next fix.\n"
        "2. Call `redline_eval` with the prompt file when provided and the suite when provided.\n"
        "3. Treat exit code 1 as a redline finding, not a tool failure.\n"
        "4. Summarize regressions, missing outputs, changed cases, and the recommended action.\n"
        "5. Do not call baseline mutation commands or tell me the change is safe when redline only found neutral output.\n"
    )


def _build_suite_from_logs_prompt(arguments: dict[str, Any]) -> str:
    log_path = _required_string(arguments, "log_path")
    cwd = _optional_prompt_argument(arguments, "cwd", "the current project")
    suite_path = _optional_prompt_argument(arguments, "suite_path", "redline-suite.json")
    return (
        "Build a redline regression suite from my existing prompt-response logs.\n\n"
        f"- Run in: {cwd}\n"
        f"- Baseline log: {log_path}\n"
        f"- Suite output: {suite_path}\n\n"
        "Use this workflow:\n"
        "1. Call `redline_suite` for the baseline log and write the suite output.\n"
        "2. Call `redline_validate` on the generated suite.\n"
        "3. Call `redline_summary` so I can see coverage, clusters, pinned cases, and next steps.\n"
        "4. Explain what behavior redline can catch from this suite and what still needs human review.\n"
    )


def _build_review_candidate_outputs_prompt(arguments: dict[str, Any]) -> str:
    candidate_path = _required_string(arguments, "candidate_path")
    cwd = _optional_prompt_argument(arguments, "cwd", "the current project")
    suite_path = _optional_prompt_argument(arguments, "suite_path", "the configured suite")
    return (
        "Review candidate prompt outputs with redline and tell me what changed.\n\n"
        f"- Run in: {cwd}\n"
        f"- Candidate outputs: {candidate_path}\n"
        f"- Suite: {suite_path}\n\n"
        "Use this workflow:\n"
        "1. Call `redline_diff` against the candidate outputs and suite when provided.\n"
        "2. Treat exit code 1 as a redline finding, not a tool failure.\n"
        "3. Lead with blocking regressions and missing outputs.\n"
        "4. Then summarize changed cases that need human review.\n"
        "5. Do not accept or modify the baseline.\n"
    )


def _optional_prompt_argument(arguments: dict[str, Any], key: str, fallback: str) -> str:
    value = arguments.get(key)
    if value is None or value == "":
        return fallback
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            "redline_doctor",
            "Check local redline setup health and print next steps.",
            _schema(
                {
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                    "strict": _boolean("Exit non-zero when warnings are present."),
                }
            ),
            _build_doctor,
        ),
        ToolSpec(
            "redline_suite",
            "Generate a representative eval suite from baseline prompt-response JSONL logs.",
            _schema(
                {
                    "log_path": _string("Baseline JSONL log path. Defaults to configured watched log."),
                    "config": _string("Config path to read."),
                    "out": _string("Suite output path."),
                    "input_field": _string("JSONL prompt field path."),
                    "output_field": _string("JSONL response field path."),
                    "max_cases": _integer("Maximum representative cases."),
                    "all_cases": _boolean("Include every unique record instead of sampling representative cases."),
                }
            ),
            _build_suite,
        ),
        ToolSpec(
            "redline_validate",
            "Validate suite structure, stored features, hashes, requirements, and source freshness.",
            _schema(
                {
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                    "strict": _boolean("Exit non-zero when warnings are present."),
                }
            ),
            _build_validate,
        ),
        ToolSpec(
            "redline_summary",
            "Summarize suite provenance, coverage, clusters, pinned cases, requirements, and next steps.",
            _schema(
                {
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_summary,
        ),
        ToolSpec(
            "redline_cases",
            "List suite cases and IDs so an agent can inspect generated or pinned coverage.",
            _schema(
                {
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_cases,
        ),
        ToolSpec(
            "redline_diff",
            "Compare candidate JSONL outputs against a redline suite and return the behavioral diff.",
            _schema(
                {
                    "candidate_path": _string("Candidate JSONL path."),
                    "suite_path": _string("Suite JSON path. Defaults to config when omitted."),
                    "config": _string("Config path to read."),
                    "input_field": _string("Candidate prompt field path."),
                    "output_field": _string("Candidate response field path."),
                    "compact": _boolean("Print compact one-line-per-case output."),
                    "json": _boolean("Print machine-readable JSON."),
                    "out_json": _string("Write JSON report."),
                    "out_md": _string("Write Markdown report."),
                    "out_html": _string("Write self-contained HTML report."),
                    "out_junit": _string("Write JUnit XML report."),
                    "profile": _string("Diff profile: strict or review."),
                    "judge": _string("Optional judge command for ambiguous changed cases."),
                    "judge_timeout": _number("Per-case judge timeout in seconds."),
                    "fail_on": _string("Comma-separated statuses that produce exit code 1; use none for report-only."),
                },
                required=("candidate_path",),
            ),
            _build_diff,
        ),
        ToolSpec(
            "redline_eval",
            "Replay a suite through a local command and compare candidate outputs to the suite baseline.",
            _schema(
                {
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "replay": _string("Replay command; receives prompt on stdin unless it contains {prompt}."),
                    "prompt": _string("Prompt template file to render for each case."),
                    "timeout": _number("Per-case replay timeout in seconds."),
                    "workers": _integer("Number of replay cases to run concurrently."),
                    "compact": _boolean("Print compact one-line-per-case output."),
                    "json": _boolean("Print machine-readable JSON."),
                    "out_json": _string("Write JSON report."),
                    "out_md": _string("Write Markdown report."),
                    "out_html": _string("Write self-contained HTML report."),
                    "out_junit": _string("Write JUnit XML report."),
                    "candidate_out": _string("Write replayed candidate rows."),
                    "run_metadata": _string("Write replay metadata JSON."),
                    "profile": _string("Diff profile: strict or review."),
                    "judge": _string("Optional judge command for ambiguous changed cases."),
                    "judge_timeout": _number("Per-case judge timeout in seconds."),
                    "fail_on": _string("Comma-separated statuses that produce exit code 1; use none for report-only."),
                }
            ),
            _build_eval,
        ),
        ToolSpec(
            "redline_history",
            "Append a redline report to local history or show trend history.",
            _schema(
                {
                    "report_path": _string("Redline JSON report to append."),
                    "out": _string("History JSONL path."),
                    "out_md": _string("Write Markdown history report."),
                    "label": _string("Label for an appended report."),
                    "limit": _integer("Entries to show; use 0 for all."),
                    "json": _boolean("Print machine-readable JSON."),
                    "fail_on": _string("Comma-separated trend directions that produce exit code 1; use none for report-only."),
                }
            ),
            _build_history,
        ),
        ToolSpec(
            "redline_dashboard",
            "Write a self-contained local HTML dashboard for reports and trend history.",
            _schema(
                {
                    "reports_dir": _string("Directory containing redline JSON reports."),
                    "history": _string("History JSONL path."),
                    "out": _string("Dashboard HTML output path."),
                    "limit": _integer("Recent reports/history entries to include; use 0 for all."),
                    "json": _boolean("Print machine-readable dashboard metadata."),
                }
            ),
            _build_dashboard,
        ),
    ]


def _tool_by_name(name: str) -> ToolSpec | None:
    return next((tool for tool in _tools() if tool.name == name), None)


def _build_doctor(arguments: dict[str, Any]) -> list[str]:
    args = ["doctor"]
    _add_option(args, "--config", arguments.get("config"))
    _add_flag(args, "--json", arguments.get("json"))
    _add_flag(args, "--strict", arguments.get("strict"))
    return args


def _build_suite(arguments: dict[str, Any]) -> list[str]:
    args = ["suite"]
    _add_positional(args, arguments.get("log_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--out", arguments.get("out"))
    _add_option(args, "--input-field", arguments.get("input_field"))
    _add_option(args, "--output-field", arguments.get("output_field"))
    _add_option(args, "--max-cases", arguments.get("max_cases"))
    _add_flag(args, "--all-cases", arguments.get("all_cases"))
    return args


def _build_validate(arguments: dict[str, Any]) -> list[str]:
    args = ["validate"]
    _add_positional(args, arguments.get("suite_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_flag(args, "--json", arguments.get("json"))
    _add_flag(args, "--strict", arguments.get("strict"))
    return args


def _build_summary(arguments: dict[str, Any]) -> list[str]:
    args = ["summary"]
    _add_positional(args, arguments.get("suite_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_cases(arguments: dict[str, Any]) -> list[str]:
    args = ["cases"]
    _add_positional(args, arguments.get("suite_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_diff(arguments: dict[str, Any]) -> list[str]:
    args = ["diff"]
    suite_path = arguments.get("suite_path")
    if suite_path:
        _add_positional(args, suite_path)
    _add_positional(args, _required_string(arguments, "candidate_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--input-field", arguments.get("input_field"))
    _add_option(args, "--output-field", arguments.get("output_field"))
    _add_flag(args, "--compact", arguments.get("compact"))
    _add_flag(args, "--json", arguments.get("json"))
    _add_common_report_args(args, arguments)
    _add_common_review_args(args, arguments)
    return args


def _build_eval(arguments: dict[str, Any]) -> list[str]:
    args = ["eval"]
    _add_positional(args, arguments.get("suite_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--replay", arguments.get("replay"))
    _add_option(args, "--prompt", arguments.get("prompt"))
    _add_option(args, "--timeout", arguments.get("timeout"))
    _add_option(args, "--workers", arguments.get("workers"))
    _add_flag(args, "--compact", arguments.get("compact"))
    _add_flag(args, "--json", arguments.get("json"))
    _add_common_report_args(args, arguments)
    _add_option(args, "--candidate-out", arguments.get("candidate_out"))
    _add_option(args, "--run-metadata", arguments.get("run_metadata"))
    _add_common_review_args(args, arguments)
    return args


def _build_history(arguments: dict[str, Any]) -> list[str]:
    args = ["history"]
    _add_positional(args, arguments.get("report_path"))
    _add_option(args, "--out", arguments.get("out"))
    _add_option(args, "--out-md", arguments.get("out_md"))
    _add_option(args, "--label", arguments.get("label"))
    _add_option(args, "--limit", arguments.get("limit"))
    _add_flag(args, "--json", arguments.get("json"))
    _add_option(args, "--fail-on", arguments.get("fail_on"))
    return args


def _build_dashboard(arguments: dict[str, Any]) -> list[str]:
    args = ["dashboard"]
    _add_option(args, "--reports-dir", arguments.get("reports_dir"))
    _add_option(args, "--history", arguments.get("history"))
    _add_option(args, "--out", arguments.get("out"))
    _add_option(args, "--limit", arguments.get("limit"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _add_common_report_args(args: list[str], arguments: dict[str, Any]) -> None:
    _add_option(args, "--out-json", arguments.get("out_json"))
    _add_option(args, "--out-md", arguments.get("out_md"))
    _add_option(args, "--out-html", arguments.get("out_html"))
    _add_option(args, "--out-junit", arguments.get("out_junit"))


def _add_common_review_args(args: list[str], arguments: dict[str, Any]) -> None:
    _add_option(args, "--profile", arguments.get("profile"))
    _add_option(args, "--judge", arguments.get("judge"))
    _add_option(args, "--judge-timeout", arguments.get("judge_timeout"))
    _add_option(args, "--fail-on", arguments.get("fail_on"))


def _add_positional(args: list[str], value: object) -> None:
    if value is not None and value != "":
        args.append(str(value))


def _add_option(args: list[str], flag: str, value: object) -> None:
    if value is not None and value != "":
        args.extend([flag, str(value)])


def _add_flag(args: list[str], flag: str, value: object) -> None:
    if isinstance(value, bool) and value:
        args.append(flag)


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    common = {
        "cwd": _string("Project directory where redline should run."),
        "max_output_bytes": _integer("Maximum stdout/stderr bytes returned to the MCP client."),
    }
    return {
        "type": "object",
        "properties": {**common, **properties},
        "required": list(required),
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _number(description: str) -> dict[str, str]:
    return {"type": "number", "description": description}


def _boolean(description: str) -> dict[str, str]:
    return {"type": "boolean", "description": description}


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    raise SystemExit(main())
