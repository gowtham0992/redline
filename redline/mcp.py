from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

from . import __version__
from .judgments import JUDGMENT_STATUSES

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
        payload: dict[str, Any] = {
            "command": self.command,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
        }
        parsed_stdout = _parse_json_stdout(self.stdout)
        if parsed_stdout is not None:
            payload["json"] = parsed_stdout
        return payload


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
            "watch stats, prompts, runners, judges, redact, audit, SBOM, benchmark, validate, summary, diff, eval, history, dashboard, cases, case, and guarded mark tools.\n",
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
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "redline", *args],
            cwd=cwd,
            env=_subprocess_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except Exception as exc:  # pragma: no cover - defensive boundary for MCP clients.
        exit_code = 2
        stdout = ""
        stderr = f"redline-mcp: {exc}\n"

    out_text, err_text, truncated = _truncate(stdout, stderr, max_output_bytes)
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


def _parse_json_stdout(stdout: str) -> Any | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    package_root = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{package_root}{os.pathsep}{existing}" if existing else package_root
    return env


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
        PromptSpec(
            "setup_redline_project",
            "Guide first-time redline setup from app shape to runner, suite, and optional judge.",
            (
                PromptArgument("cwd", "Project directory where redline should run."),
                PromptArgument("log_path", "Existing prompt-response JSONL log, if available."),
                PromptArgument("prompt_path", "Prompt file or directory to scan, if available."),
                PromptArgument("runner", "Preferred runner adapter id, such as stdio, openai, http, or all."),
                PromptArgument("judge", "Optional judge template id, such as openai or support-rubric."),
            ),
            _build_setup_redline_project_prompt,
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
        "3. Call `redline_summary` so I can see coverage, behavior groups, pinned cases, and next steps.\n"
        "4. If coverage is low or cases look unclear, call `redline_cases` and `redline_case` to inspect representative cases before recommending pins.\n"
        "5. Call `redline_budget` so I can see expected CI runtime before enabling a gate.\n"
        "6. Explain what behavior redline can catch, what still needs human review, and the exact `redline suite add` command I can run for must-cover edge cases.\n"
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


def _build_setup_redline_project_prompt(arguments: dict[str, Any]) -> str:
    cwd = _optional_prompt_argument(arguments, "cwd", "the current project")
    log_path = _optional_prompt_argument(arguments, "log_path", "an existing prompt-response JSONL log")
    prompt_path = _optional_prompt_argument(arguments, "prompt_path", "the project's prompt files")
    runner = _optional_prompt_argument(arguments, "runner", "the runner adapter that matches my app")
    judge = _optional_prompt_argument(arguments, "judge", "only if semantic review is needed")
    return (
        "Set up redline for this project as a first-time user.\n\n"
        f"- Run in: {cwd}\n"
        f"- Prompt/log source: {prompt_path} and {log_path}\n"
        f"- Runner preference: {runner}\n"
        f"- Judge preference: {judge}\n\n"
        "Use this workflow:\n"
        "1. Call `redline_doctor` first and explain the next setup gap in plain language.\n"
        "2. Call `redline_runners` to show adapter choices. If I named a runner, copy that runner; otherwise recommend the safest adapter for my app shape before copying anything.\n"
        "3. If I do not already have logs, call `redline_watch_snippets` for the app shape so I can add local capture first.\n"
        "4. If prompt files are available, call `redline_prompts` to create or check a prompt-to-suite manifest.\n"
        "5. If logs are available, call `redline_suite`, then `redline_validate` and `redline_summary` so I can inspect coverage before trusting the suite.\n"
        "6. If summary reports coverage gaps, call `redline_cases` or `redline_case` and recommend a `redline suite add` command I can run; do not mutate the suite yourself.\n"
        "7. Call `redline_budget` before recommending CI gating.\n"
        "8. Call `redline_judges` only when structural checks cannot cover factual, tone, hallucination, or reasoning risk; copy a judge template only after naming why it is needed.\n"
        "9. Finish by re-running `redline_doctor` with strict setup when possible and list the exact next commands I should run.\n"
        "10. Do not call baseline mutation commands, do not upload private logs, and do not say green or neutral means semantically safe.\n"
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
            "redline_redact",
            "Scan or redact common secrets and PII from JSONL prompt-response logs.",
            _schema(
                {
                    "log_path": _string("JSONL prompt-response log to scan or redact."),
                    "config": _string("Config path to read."),
                    "out": _string("Redacted JSONL output path. Required unless check is true."),
                    "check": _boolean("Scan only; do not write a redacted file."),
                    "placeholder": _string("Replacement text for redacted values."),
                    "json": _boolean("Print machine-readable JSON."),
                },
                required=("log_path",),
            ),
            _build_redact,
        ),
        ToolSpec(
            "redline_import",
            "Normalize exported JSONL fields into redline prompt/response JSONL.",
            _schema(
                {
                    "path": _string("Source JSONL file to normalize."),
                    "out": _string("Redline JSONL output path."),
                    "input_field": _string("Source field path containing prompt text."),
                    "output_field": _string("Source field path containing response text."),
                    "context_field": _string("Optional source field path appended to the prompt as Context."),
                    "id_field": _string("Optional source field path copied to the redline id field."),
                    "metadata_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Source field paths copied into metadata.",
                    },
                    "limit": _integer("Maximum records to import."),
                    "no_redact": _boolean("Write raw values without import redaction."),
                    "redaction_placeholder": _string("Replacement text for import redaction."),
                    "json": _boolean("Print machine-readable JSON."),
                },
                required=("path", "out"),
            ),
            _build_import,
        ),
        ToolSpec(
            "redline_watch_stats",
            "Summarize observed prompt-response captures, readiness, duplicates, and middleware skip diagnostics.",
            _schema(
                {
                    "log_path": _string("Observed prompt-response JSONL log path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "input_field": _string("JSONL prompt field path."),
                    "output_field": _string("JSONL response field path."),
                    "skip_log": _string("Middleware skip diagnostics JSONL to include."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_watch_stats,
        ),
        ToolSpec(
            "redline_watch_snippets",
            "Print copy-paste local capture snippets for decorators, SDK patching, or FastAPI middleware.",
            _schema(
                {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "decorator", "openai", "anthropic", "fastapi"],
                        "description": "Capture setup snippet to print. Defaults to all.",
                    },
                }
            ),
            _build_watch_snippets,
        ),
        ToolSpec(
            "redline_prompts",
            "Scan prompt files, write or check a prompt-to-suite manifest, and verify mapped suites exist.",
            _schema(
                {
                    "path": _string("Prompt file or directory to scan."),
                    "suite_dir": _string("Suite directory to map prompt files into."),
                    "out": _string("Manifest JSON path to write or check."),
                    "check": _boolean("Exit non-zero when the manifest is stale."),
                    "check_suites": _boolean("Also exit non-zero when mapped suite files are missing."),
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Prompt extensions to include.",
                    },
                    "json": _boolean("Print machine-readable JSON."),
                },
                required=("path",),
            ),
            _build_prompts,
        ),
        ToolSpec(
            "redline_judges",
            "List or copy optional judge templates for semantic review of changed cases.",
            _schema(
                {
                    "copy": _string("Template id to copy, or all."),
                    "out": _string("Output path for one copied template."),
                    "force": _boolean("Overwrite existing output path."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_judges,
        ),
        ToolSpec(
            "redline_runners",
            "List or copy runner adapters for replay commands, log import, and SDK capture.",
            _schema(
                {
                    "copy": _string("Runner adapter id to copy, or all."),
                    "out": _string("Output path for one copied adapter."),
                    "force": _boolean("Overwrite existing output path."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_runners,
        ),
        ToolSpec(
            "redline_validate",
            "Validate suite or prompt-manifest structure, mapped suites, hashes, requirements, and source freshness.",
            _schema(
                {
                    "suite_path": _string("Suite or prompt manifest JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                    "strict": _boolean("Exit non-zero when warnings are present."),
                }
            ),
            _build_validate,
        ),
        ToolSpec(
            "redline_summary",
            "Summarize suite or prompt-manifest provenance, coverage, behavior groups, owners, requirements, and next steps.",
            _schema(
                {
                    "suite_path": _string("Suite or prompt manifest JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_summary,
        ),
        ToolSpec(
            "redline_benchmark",
            "Compatibility alias for redline_budget. Estimate suite or prompt-manifest eval runtime before enabling a gate.",
            _schema(
                {
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "timeout": _number("Per-case timeout in seconds."),
                    "workers": _integer("Number of replay workers."),
                    "max_seconds": _number("Exit 1 when worst-case eval budget exceeds this."),
                    "out_json": _string("Write benchmark report JSON."),
                    "out_md": _string("Write benchmark report Markdown."),
                    "github_summary": _boolean("Append benchmark Markdown to GITHUB_STEP_SUMMARY."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_benchmark,
        ),
        ToolSpec(
            "redline_budget",
            "Estimate suite or prompt-manifest eval runtime, timeout budget, and CI scale before enabling a gate. Does not replay prompts or call models.",
            _schema(
                {
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "timeout": _number("Per-case timeout in seconds."),
                    "workers": _integer("Number of replay workers."),
                    "max_seconds": _number("Exit 1 when worst-case eval budget exceeds this."),
                    "out_json": _string("Write budget report JSON."),
                    "out_md": _string("Write budget report Markdown."),
                    "github_summary": _boolean("Append budget Markdown to GITHUB_STEP_SUMMARY."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_budget,
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
            "redline_case",
            "Show full detail for one suite case, including owner, requirements, source, and baseline response.",
            _schema(
                {
                    "case_id": _string("Suite case ID to inspect."),
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "json": _boolean("Print machine-readable JSON."),
                },
                required=("case_id",),
            ),
            _build_case,
        ),
        ToolSpec(
            "redline_mark",
            "Mark a case expected, accepted, or ignored after explicit user approval.",
            _schema(
                {
                    "case_id": _string("Suite case ID to mark."),
                    "status": {
                        "type": "string",
                        "enum": list(JUDGMENT_STATUSES),
                        "description": "Judgment status to record.",
                    },
                    "note": _string("Required human-readable reason for the judgment."),
                    "suite_path": _string("Suite JSON path. Defaults to config."),
                    "config": _string("Config path to read."),
                    "out": _string("Write updated suite to a new path."),
                    "allow_write": _boolean("Must be true because this mutates a local suite file."),
                },
                required=("case_id", "status", "note", "allow_write"),
            ),
            _build_mark,
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
                    "out_comment": _string("Write concise PR-comment Markdown report."),
                    "out_html": _string("Write self-contained HTML report."),
                    "out_junit": _string("Write JUnit XML report."),
                    "out_slack": _string("Write Slack Block Kit JSON report."),
                    "profile": _string("Diff profile: strict or review."),
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
                    "prompt": _string("Prompt template file to render for each case."),
                    "timeout": _number("Per-case replay timeout in seconds."),
                    "workers": _integer("Number of replay cases to run concurrently."),
                    "compact": _boolean("Print compact one-line-per-case output."),
                    "json": _boolean("Print machine-readable JSON."),
                    "out_json": _string("Write JSON report."),
                    "out_md": _string("Write Markdown report."),
                    "out_comment": _string("Write concise PR-comment Markdown report."),
                    "out_html": _string("Write self-contained HTML report."),
                    "out_junit": _string("Write JUnit XML report."),
                    "out_slack": _string("Write Slack Block Kit JSON report."),
                    "candidate_out": _string("Write replayed candidate rows."),
                    "run_metadata": _string("Write replay metadata JSON."),
                    "profile": _string("Diff profile: strict or review."),
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
                    "checkpoint": _string("Audit checkpoint JSON path."),
                    "out": _string("Dashboard HTML output path."),
                    "limit": _integer("Recent reports/history entries to include; use 0 for all."),
                    "json": _boolean("Print machine-readable dashboard metadata."),
                }
            ),
            _build_dashboard,
        ),
        ToolSpec(
            "redline_audit",
            "Read recent local audit events for evals, redactions, approvals, and requirements.",
            _schema(
                {
                    "config": _string("Config path to read."),
                    "path": _string("Audit JSONL path. Defaults to config."),
                    "limit": _integer("Recent audit events to show; use 0 for all."),
                    "verify": _boolean("Verify the audit hash chain."),
                    "checkpoint": _string("JSON checkpoint produced by audit --out-checkpoint."),
                    "expect_last_hash": _string("Expected final audit entry hash for tail checks."),
                    "expect_entries": _integer("Expected audit entry count for tail checks."),
                    "out_checkpoint": _string("Write a JSON audit checkpoint after verification."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_audit,
        ),
        ToolSpec(
            "redline_sbom",
            "Write CycloneDX SBOM release evidence for redline.",
            _schema(
                {
                    "out": _string("Write SBOM JSON to this path."),
                    "json": _boolean("Print machine-readable JSON."),
                }
            ),
            _build_sbom,
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


def _build_redact(arguments: dict[str, Any]) -> list[str]:
    args = ["redact"]
    _add_positional(args, _required_string(arguments, "log_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--out", arguments.get("out"))
    _add_flag(args, "--check", arguments.get("check"))
    _add_option(args, "--placeholder", arguments.get("placeholder"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_import(arguments: dict[str, Any]) -> list[str]:
    args = ["import"]
    _add_positional(args, _required_string(arguments, "path"))
    _add_option(args, "--out", _required_string(arguments, "out"))
    _add_option(args, "--input-field", arguments.get("input_field"))
    _add_option(args, "--output-field", arguments.get("output_field"))
    _add_option(args, "--context-field", arguments.get("context_field"))
    _add_option(args, "--id-field", arguments.get("id_field"))
    _add_repeated_options(args, "--metadata-field", arguments.get("metadata_fields"))
    _add_option(args, "--limit", arguments.get("limit"))
    _add_flag(args, "--no-redact", arguments.get("no_redact"))
    _add_option(args, "--redaction-placeholder", arguments.get("redaction_placeholder"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_watch_stats(arguments: dict[str, Any]) -> list[str]:
    args = ["watch", "--stats"]
    _add_option(args, "--out", arguments.get("log_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--input-field", arguments.get("input_field"))
    _add_option(args, "--output-field", arguments.get("output_field"))
    _add_option(args, "--skip-log", arguments.get("skip_log"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_watch_snippets(arguments: dict[str, Any]) -> list[str]:
    return ["watch", "--snippet", str(arguments.get("kind") or "all")]


def _build_prompts(arguments: dict[str, Any]) -> list[str]:
    args = ["prompts"]
    _add_positional(args, _required_string(arguments, "path"))
    _add_option(args, "--suite-dir", arguments.get("suite_dir"))
    _add_option(args, "--out", arguments.get("out"))
    _add_flag(args, "--check", arguments.get("check"))
    _add_flag(args, "--check-suites", arguments.get("check_suites"))
    _add_repeated_options(args, "--ext", arguments.get("extensions"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_judges(arguments: dict[str, Any]) -> list[str]:
    args = ["judges"]
    _add_option(args, "--copy", arguments.get("copy"))
    _add_option(args, "--out", arguments.get("out"))
    _add_flag(args, "--force", arguments.get("force"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_runners(arguments: dict[str, Any]) -> list[str]:
    args = ["runners"]
    _add_option(args, "--copy", arguments.get("copy"))
    _add_option(args, "--out", arguments.get("out"))
    _add_flag(args, "--force", arguments.get("force"))
    _add_flag(args, "--json", arguments.get("json"))
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


def _build_benchmark(arguments: dict[str, Any]) -> list[str]:
    args = ["benchmark"]
    return _build_budget_like(args, arguments)


def _build_budget(arguments: dict[str, Any]) -> list[str]:
    args = ["budget"]
    return _build_budget_like(args, arguments)


def _build_budget_like(args: list[str], arguments: dict[str, Any]) -> list[str]:
    _add_positional(args, arguments.get("suite_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--timeout", arguments.get("timeout"))
    _add_option(args, "--workers", arguments.get("workers"))
    _add_option(args, "--max-seconds", arguments.get("max_seconds"))
    _add_option(args, "--out-json", arguments.get("out_json"))
    _add_option(args, "--out-md", arguments.get("out_md"))
    _add_flag(args, "--github-summary", arguments.get("github_summary"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_cases(arguments: dict[str, Any]) -> list[str]:
    args = ["cases"]
    _add_positional(args, arguments.get("suite_path"))
    _add_option(args, "--config", arguments.get("config"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_case(arguments: dict[str, Any]) -> list[str]:
    args = ["case"]
    suite_path = arguments.get("suite_path")
    if suite_path:
        _add_positional(args, suite_path)
    _add_positional(args, _required_string(arguments, "case_id"))
    _add_option(args, "--config", arguments.get("config"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_mark(arguments: dict[str, Any]) -> list[str]:
    if arguments.get("allow_write") is not True:
        raise ValueError("redline_mark mutates suite files; pass allow_write=true after user approval")
    note = _required_string(arguments, "note")
    status = _required_string(arguments, "status")
    if status not in JUDGMENT_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(JUDGMENT_STATUSES)}")
    args = ["mark"]
    suite_path = arguments.get("suite_path")
    if suite_path:
        _add_positional(args, suite_path)
    _add_positional(args, _required_string(arguments, "case_id"))
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--status", status)
    _add_option(args, "--note", note)
    _add_option(args, "--out", arguments.get("out"))
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
    _add_option(args, "--checkpoint", arguments.get("checkpoint"))
    _add_option(args, "--out", arguments.get("out"))
    _add_option(args, "--limit", arguments.get("limit"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_audit(arguments: dict[str, Any]) -> list[str]:
    args = ["audit"]
    _add_option(args, "--config", arguments.get("config"))
    _add_option(args, "--path", arguments.get("path"))
    _add_option(args, "--limit", arguments.get("limit"))
    _add_flag(args, "--verify", arguments.get("verify"))
    _add_option(args, "--checkpoint", arguments.get("checkpoint"))
    _add_option(args, "--expect-last-hash", arguments.get("expect_last_hash"))
    _add_option(args, "--expect-entries", arguments.get("expect_entries"))
    _add_option(args, "--out-checkpoint", arguments.get("out_checkpoint"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _build_sbom(arguments: dict[str, Any]) -> list[str]:
    args = ["sbom"]
    _add_option(args, "--out", arguments.get("out"))
    _add_flag(args, "--json", arguments.get("json"))
    return args


def _add_common_report_args(args: list[str], arguments: dict[str, Any]) -> None:
    _add_option(args, "--out-json", arguments.get("out_json"))
    _add_option(args, "--out-md", arguments.get("out_md"))
    _add_option(args, "--out-comment", arguments.get("out_comment"))
    _add_option(args, "--out-html", arguments.get("out_html"))
    _add_option(args, "--out-junit", arguments.get("out_junit"))
    _add_option(args, "--out-slack", arguments.get("out_slack"))


def _add_common_review_args(args: list[str], arguments: dict[str, Any]) -> None:
    _add_option(args, "--profile", arguments.get("profile"))
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


def _add_repeated_options(args: list[str], flag: str, values: object) -> None:
    if values is None or values == "":
        return
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        raise ValueError(f"{flag} values must be a list of strings")
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{flag} values must be strings")
        if value:
            args.extend([flag, value])


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
