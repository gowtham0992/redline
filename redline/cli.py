from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .accept import accept_candidate_baseline, expected_case_ids
from .cases import format_suite_case_detail, format_suite_cases, suite_case_detail, suite_case_rows
from .ci import default_github_workflow
from .clusters import cluster_report, format_cluster_report
from .compare import (
    compare_reports,
    format_markdown_comparison,
    format_report_comparison,
    parse_compare_fail_on,
    should_fail_comparison,
)
from .config import DEFAULT_CONFIG_PATH, create_config, load_config
from .demo import format_demo, run_demo
from .diff import DIFF_PROFILES, compare_suite_to_candidate, format_compact_report, format_report
from .doctor import doctor_report, format_doctor_report
from .history import format_history, format_markdown_history, history_entry, read_history
from .io import append_jsonl, append_text, read_json, read_jsonl_records, write_json, write_jsonl, write_text
from .judge import apply_judge
from .judgments import JUDGMENT_STATUSES, clear_suite_case_judgment, mark_suite_case
from .policy import parse_fail_on, should_fail
from .reports import format_github_annotations, format_html_report, format_junit_report, format_markdown_report
from .requirements import add_case_requirement, clear_case_requirements
from .replay import read_prompt_template, replay_suite
from .runners import (
    copy_all_runner_adapters,
    copy_runner_adapter,
    format_runner_adapters,
    runner_adapters,
)
from .summary import format_suite_summary, suite_summary
from .suite import add_suite_case, build_suite
from .validate import format_validation_report, validate_suite
from .watch import collect_log, follow_log, format_follow_records, format_watch_stats, watch_stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = sys.argv[1:] if argv is None else list(argv)
    arguments = _normalize_command_aliases(arguments)
    if not arguments:
        print(_root_help(), end="")
        return 0
    args = parser.parse_args(arguments)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"redline: {exc}", file=sys.stderr)
        return 2


def _root_help() -> str:
    return """redline

Local-first prompt regression diffs from JSONL logs.

Start here:
  redline demo
  redline init --runner stdio --copy-runner
  redline runners
  redline doctor

Core loop:
  redline suite path/to/baseline.jsonl --out redline-suite.json
  redline eval --prompt prompts/v2.txt
  redline diff redline-suite.json path/to/candidate.jsonl

Run `redline <command> --help` for command details.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redline",
        description="Local-first prompt regression diffs from JSONL logs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a redline config file")
    init_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to create")
    init_parser.add_argument("--input-field", default="prompt", help="default JSONL input field")
    init_parser.add_argument("--output-field", default="response", help="default JSONL output field")
    init_parser.add_argument("--max-cases", type=int, default=42, help="default maximum suite cases")
    init_parser.add_argument("--timeout", type=float, default=30.0, help="default replay timeout in seconds")
    init_parser.add_argument("--replay", help="default eval replay command")
    init_parser.add_argument("--judge", help="default judge command for ambiguous changed cases")
    init_parser.add_argument("--judge-timeout", type=float, help="default judge timeout in seconds")
    init_parser.add_argument(
        "--runner",
        choices=[adapter["id"] for adapter in runner_adapters()],
        help="set replay from a built-in runner adapter",
    )
    init_parser.add_argument(
        "--copy-runner",
        action="store_true",
        help="copy the selected built-in runner adapter into this project",
    )
    init_parser.add_argument("--github-action", action="store_true", help="also write a GitHub Actions workflow")
    init_parser.add_argument("--workflow", default=".github/workflows/redline.yml", help="workflow path for --github-action")
    init_parser.add_argument("--force", action="store_true", help="overwrite an existing config file")
    init_parser.set_defaults(func=cmd_init)

    doctor_parser = subparsers.add_parser("doctor", help="check redline setup health")
    doctor_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    doctor_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    doctor_parser.add_argument("--strict", action="store_true", help="exit non-zero when warnings are present")
    doctor_parser.set_defaults(func=cmd_doctor)

    demo_parser = subparsers.add_parser("demo", help="run a first-use prompt regression demo")
    demo_parser.add_argument("--out", default=".redline/demo", help="demo output directory")
    demo_parser.add_argument(
        "--public",
        action="store_true",
        help="run the public-pattern dogfood fixture that works from any install",
    )
    demo_parser.add_argument("--compact", action="store_true", help="print compact one-line-per-case output")
    demo_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    demo_parser.set_defaults(func=cmd_demo)

    runners_parser = subparsers.add_parser("runners", help="list replay runner adapters")
    runners_parser.add_argument(
        "--copy",
        choices=["all", *[adapter["id"] for adapter in runner_adapters()]],
        help="copy one runner adapter, or all adapters, into this project",
    )
    runners_parser.add_argument("--out", help="output path for --copy; defaults to adapter file path")
    runners_parser.add_argument("--force", action="store_true", help="overwrite existing output path for --copy")
    runners_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    runners_parser.set_defaults(func=cmd_runners)

    watch_parser = subparsers.add_parser("watch", help="collect prompt-response records from a JSONL log")
    watch_parser.add_argument("--log", help="JSONL prompt-response log to collect")
    watch_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    watch_parser.add_argument("--out", help="observed log output path")
    watch_parser.add_argument("--input-field", help="JSONL input field")
    watch_parser.add_argument("--output-field", help="JSONL output field")
    watch_parser.add_argument("--replace", action="store_true", help="replace the observed log instead of appending")
    watch_parser.add_argument("--allow-duplicates", action="store_true", help="append records even if source lines were already collected")
    watch_parser.add_argument("--stats", action="store_true", help="summarize the observed watch log")
    watch_parser.add_argument("--follow", action="store_true", help="keep polling the source log for new records")
    watch_parser.add_argument("--poll-interval", type=float, default=1.0, help="seconds between follow polls")
    watch_parser.add_argument("--max-records", type=int, help="stop follow mode after collecting this many new records")
    watch_parser.add_argument("--idle-timeout", type=float, help="stop follow mode after this many idle seconds")
    watch_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    watch_parser.set_defaults(func=cmd_watch)

    cluster_parser = subparsers.add_parser("cluster", help="analyze behavioral clusters in a log")
    cluster_parser.add_argument("log", nargs="?", help="JSONL prompt-response log; defaults to watched log")
    cluster_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    cluster_parser.add_argument("--input-field", help="JSONL input field")
    cluster_parser.add_argument("--output-field", help="JSONL output field")
    cluster_parser.add_argument("--max-cases", type=int, help="maximum representative cases")
    cluster_parser.add_argument("--all-cases", action="store_true", help="select every record instead of representatives")
    cluster_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    cluster_parser.set_defaults(func=cmd_cluster)

    suite_parser = subparsers.add_parser("suite", help="generate a representative suite")
    suite_parser.add_argument("log", nargs="?", help="baseline JSONL file; defaults to watched log")
    suite_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    suite_parser.add_argument("--out", help="suite output path")
    suite_parser.add_argument("--input-field", help="JSONL input field")
    suite_parser.add_argument("--output-field", help="JSONL output field")
    suite_parser.add_argument("--max-cases", type=int, help="maximum suite cases")
    suite_parser.add_argument("--all-cases", action="store_true", help="include every record instead of representative cases")
    suite_parser.set_defaults(func=cmd_suite)

    suite_add_parser = subparsers.add_parser("suite-add", prog="redline suite add", help=argparse.SUPPRESS)
    suite_add_parser.add_argument("suite", nargs="?", help="suite JSON to update; defaults to configured suite")
    suite_add_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    suite_add_parser.add_argument("--prompt", help="prompt text to pin")
    suite_add_parser.add_argument("--prompt-file", help="file containing prompt text to pin")
    suite_add_parser.add_argument("--response", help="baseline response text to pin")
    suite_add_parser.add_argument("--response-file", help="file containing baseline response text to pin")
    suite_add_parser.add_argument("--case-id", help="explicit case id; defaults to generated id")
    suite_add_parser.add_argument("--include", action="append", default=[], help="text candidate output must include")
    suite_add_parser.add_argument("--exclude", action="append", default=[], help="text candidate output must not include")
    suite_add_parser.add_argument("--note", default="", help="short reason for pinning the case")
    suite_add_parser.add_argument("--out", help="write updated suite to a new path")
    suite_add_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    suite_add_parser.set_defaults(func=cmd_suite_add)

    cases_parser = subparsers.add_parser("cases", help="list cases in a suite")
    cases_parser.add_argument("suite", nargs="?", help="suite JSON generated by redline suite")
    cases_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    cases_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    cases_parser.set_defaults(func=cmd_cases)

    case_parser = subparsers.add_parser("case", help="show one suite case")
    case_parser.add_argument("paths", nargs="+", help="case id, or suite JSON plus case id")
    case_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    case_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    case_parser.set_defaults(func=cmd_case)

    summary_parser = subparsers.add_parser("summary", help="summarize a suite")
    summary_parser.add_argument("suite", nargs="?", help="suite JSON generated by redline suite")
    summary_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    summary_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    summary_parser.set_defaults(func=cmd_summary)

    validate_parser = subparsers.add_parser("validate", help="validate suite structure and stored features")
    validate_parser.add_argument("suite", nargs="?", help="suite JSON generated by redline suite")
    validate_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    validate_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_parser.add_argument("--strict", action="store_true", help="exit non-zero when warnings are present")
    validate_parser.set_defaults(func=cmd_validate)

    diff_parser = subparsers.add_parser("diff", help="compare candidate JSONL to a suite")
    diff_parser.add_argument(
        "paths",
        nargs="+",
        help="candidate JSONL, or suite JSON plus candidate JSONL",
    )
    diff_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    diff_parser.add_argument("--input-field", help="candidate input field; defaults to suite input field")
    diff_parser.add_argument("--output-field", help="candidate output field; defaults to suite output field")
    diff_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    diff_parser.add_argument("--compact", action="store_true", help="print compact one-line-per-case output")
    diff_parser.add_argument("--out-json", help="write machine-readable JSON report")
    diff_parser.add_argument("--out-md", help="write Markdown report")
    diff_parser.add_argument("--out-html", help="write self-contained HTML report")
    diff_parser.add_argument("--out-junit", help="write JUnit XML report")
    diff_parser.add_argument("--profile", choices=DIFF_PROFILES, help="diff signal profile; default comes from config or strict")
    diff_parser.add_argument("--github-summary", action="store_true", help="append Markdown report to GITHUB_STEP_SUMMARY")
    diff_parser.add_argument("--github-annotations", action="store_true", help="emit GitHub error/warning annotations")
    diff_parser.add_argument("--judge", help="command that judges ambiguous changed cases from JSON on stdin")
    diff_parser.add_argument("--judge-timeout", type=float, help="per-case judge timeout in seconds")
    diff_parser.add_argument(
        "--fail-on",
        default=None,
        help="comma-separated statuses that produce exit code 1; use 'none' for report-only",
    )
    diff_parser.set_defaults(func=cmd_diff)

    compare_parser = subparsers.add_parser("compare", help="compare two redline JSON reports")
    compare_parser.add_argument("previous", help="previous redline JSON report")
    compare_parser.add_argument("current", help="current redline JSON report")
    compare_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    compare_parser.add_argument("--out-json", help="write machine-readable JSON comparison report")
    compare_parser.add_argument("--out-md", help="write Markdown comparison report")
    compare_parser.add_argument("--github-summary", action="store_true", help="append Markdown comparison to GITHUB_STEP_SUMMARY")
    compare_parser.add_argument(
        "--fail-on",
        default=None,
        help="comma-separated comparison directions that produce exit code 1; use 'none' for report-only",
    )
    compare_parser.set_defaults(func=cmd_compare)

    history_parser = subparsers.add_parser("history", help="append or show report history")
    history_parser.add_argument("report", nargs="?", help="redline JSON report to append to history")
    history_parser.add_argument("--out", default=".redline/history.jsonl", help="history JSONL path")
    history_parser.add_argument("--out-md", help="write Markdown history report")
    history_parser.add_argument("--github-summary", action="store_true", help="append Markdown history to GITHUB_STEP_SUMMARY")
    history_parser.add_argument("--label", default="", help="label for an appended report")
    history_parser.add_argument("--limit", type=int, default=10, help="entries to show; use 0 for all")
    history_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    history_parser.set_defaults(func=cmd_history)

    eval_parser = subparsers.add_parser("eval", help="replay a suite with a local command")
    eval_parser.add_argument("suite", nargs="?", help="suite JSON generated by redline suite")
    eval_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    eval_parser.add_argument(
        "--replay",
        help="command to run for each case; receives prompt on stdin unless argv contains {prompt}",
    )
    eval_parser.add_argument("--prompt", help="prompt template file to render for each case")
    eval_parser.add_argument("--timeout", type=float, help="per-case timeout in seconds")
    eval_parser.add_argument("--workers", type=int, help="number of replay cases to run concurrently")
    eval_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    eval_parser.add_argument("--compact", action="store_true", help="print compact one-line-per-case output")
    eval_parser.add_argument("--out-json", help="write machine-readable JSON report")
    eval_parser.add_argument("--out-md", help="write Markdown report")
    eval_parser.add_argument("--out-html", help="write self-contained HTML report")
    eval_parser.add_argument("--out-junit", help="write JUnit XML report")
    eval_parser.add_argument("--profile", choices=DIFF_PROFILES, help="diff signal profile; default comes from config or strict")
    eval_parser.add_argument("--github-summary", action="store_true", help="append Markdown report to GITHUB_STEP_SUMMARY")
    eval_parser.add_argument("--github-annotations", action="store_true", help="emit GitHub error/warning annotations")
    eval_parser.add_argument("--judge", help="command that judges ambiguous changed cases from JSON on stdin")
    eval_parser.add_argument("--judge-timeout", type=float, help="per-case judge timeout in seconds")
    eval_parser.add_argument("--candidate-out", help="write replayed candidate prompt-response JSONL")
    eval_parser.add_argument("--run-metadata", help="write replay run metadata JSON")
    eval_parser.add_argument(
        "--fail-on",
        default=None,
        help="comma-separated statuses that produce exit code 1; use 'none' for report-only",
    )
    eval_parser.set_defaults(func=cmd_eval)

    mark_parser = subparsers.add_parser("mark", help="mark a suite case judgment")
    mark_parser.add_argument("paths", nargs="+", help="case id, or suite JSON plus case id")
    mark_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    mark_parser.add_argument("--status", choices=JUDGMENT_STATUSES, required=True)
    mark_parser.add_argument("--note", default="", help="short reason for the judgment")
    mark_parser.add_argument("--out", help="write updated suite to a new path")
    mark_parser.set_defaults(func=cmd_mark)

    clear_parser = subparsers.add_parser("clear", help="clear a suite case judgment")
    clear_parser.add_argument("paths", nargs="+", help="case id, or suite JSON plus case id")
    clear_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    clear_parser.add_argument("--out", help="write updated suite to a new path")
    clear_parser.set_defaults(func=cmd_clear)

    accept_parser = subparsers.add_parser("accept", help="promote candidate output into a suite baseline")
    accept_parser.add_argument("paths", nargs="*", help="case id, or suite JSON plus case id")
    accept_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    accept_parser.add_argument("--candidate", help="candidate JSONL file; defaults to configured run output")
    accept_parser.add_argument("--all-expected", action="store_true", help="accept every case marked expected")
    accept_parser.add_argument("--input-field", help="candidate input field; defaults to suite/config field")
    accept_parser.add_argument("--output-field", help="candidate output field; defaults to suite/config field")
    accept_parser.add_argument("--note", default="", help="short reason for accepting the baseline")
    accept_parser.add_argument("--out", help="write updated suite to a new path")
    accept_parser.set_defaults(func=cmd_accept)

    require_parser = subparsers.add_parser("require", help="add or clear deterministic case requirements")
    require_parser.add_argument("paths", nargs="+", help="case id, or suite JSON plus case id")
    require_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="config path to read")
    require_parser.add_argument("--include", action="append", default=[], help="text that candidate output must include")
    require_parser.add_argument("--exclude", action="append", default=[], help="text that candidate output must not include")
    require_parser.add_argument("--note", default="", help="short reason for the requirement")
    require_parser.add_argument("--clear", action="store_true", help="clear requirements for the case")
    require_parser.add_argument("--out", help="write updated suite to a new path")
    require_parser.set_defaults(func=cmd_require)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    if args.github_action and Path(args.workflow).exists() and not args.force:
        raise ValueError(f"{Path(args.workflow)} already exists; pass --force to overwrite")
    if args.replay and args.runner:
        raise ValueError("use --replay or --runner, not both")
    if args.copy_runner and not args.runner:
        raise ValueError("use --copy-runner with --runner")
    if args.judge_timeout is not None and not args.judge:
        raise ValueError("use --judge-timeout with --judge")
    replay = args.replay or _runner_replay(args.runner)
    config = create_config(
        args.config,
        input_field=args.input_field,
        output_field=args.output_field,
        max_cases=args.max_cases,
        timeout_seconds=args.timeout,
        replay=replay,
        judge=args.judge,
        judge_timeout_seconds=args.judge_timeout,
        force=args.force,
    )
    runner_result = None
    if args.copy_runner:
        runner_result = copy_runner_adapter(args.runner, force=args.force)
    write_json(args.config, config)
    print(f"Wrote {Path(args.config)}.")
    if runner_result:
        print(f"Wrote {Path(runner_result['path'])}.")
        print(f"Replay: {runner_result['replay']}")
    if args.github_action:
        write_text(args.workflow, default_github_workflow())
        print(f"Wrote {Path(args.workflow)}.")
    print()
    print("Next:")
    if not replay:
        print("- Connect a runner: redline init --runner stdio --copy-runner --force")
    print(f"- Generate suite: redline suite path/to/log.jsonl --out {config['suite']}")
    if replay:
        print("- Run eval: redline eval")
    print("- Check setup: redline doctor")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path = str(config.get("suite") or "redline-suite.json")
    suite = None
    suite_error = None
    if Path(suite_path).exists():
        try:
            suite = read_json(suite_path)
        except ValueError as exc:
            suite_error = str(exc)
    report = doctor_report(
        config_path=args.config,
        config=config,
        suite=suite,
        suite_error=suite_error,
        suite_git_ignored=_is_git_ignored(suite_path),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_doctor_report(report), end="")
    if report["errors"] > 0:
        return 1
    if args.strict and report["warnings"] > 0:
        return 1
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    result = run_demo(args.out, public=args.public)
    if args.json:
        payload = {key: value for key, value in result.items() if key != "diff"}
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_demo(result, compact=args.compact), end="")
    return 0


def cmd_runners(args: argparse.Namespace) -> int:
    if args.copy:
        if args.copy == "all":
            if args.out:
                raise ValueError("--out can only be used when copying one runner")
            results = copy_all_runner_adapters(force=args.force)
            if args.json:
                print(json.dumps({"runners": results}, indent=2, sort_keys=True))
            else:
                for result in results:
                    print(f"Wrote {Path(result['path'])}.")
                print("Replay commands:")
                for result in results:
                    print(f"  {result['id']}: {result['replay']}")
            return 0
        result = copy_runner_adapter(args.copy, output=args.out, force=args.force)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Wrote {Path(result['path'])}.")
            print(f"Replay: {result['replay']}")
        return 0
    adapters = runner_adapters()
    if args.json:
        print(json.dumps({"runners": adapters}, indent=2, sort_keys=True))
    else:
        print(format_runner_adapters(adapters), end="")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    input_field = str(_config_value(args.input_field, config, "input_field", "prompt"))
    output_field = str(_config_value(args.output_field, config, "output_field", "response"))
    output = args.out or _config_observed_log_path(config) or ".redline/logs/prompts.jsonl"
    if args.stats:
        result = watch_stats(output, input_field=input_field, output_field=output_field)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(format_watch_stats(result), end="")
        return 0
    if not args.log:
        raise ValueError("watch requires --log unless --stats is used")
    if args.follow:
        if not args.json:
            print(f"Following {Path(args.log)}.")
            print(f"Writing new prompt-response pairs to {Path(output)}.")

        def on_records(rows) -> None:
            print(format_follow_records(rows), end="", flush=True)

        result = follow_log(
            args.log,
            output=output,
            input_field=input_field,
            output_field=output_field,
            poll_interval=args.poll_interval,
            max_records=args.max_records,
            idle_timeout=args.idle_timeout,
            dedupe=not args.allow_duplicates,
            replace=args.replace,
            on_records=on_records if not args.json else None,
        )
    else:
        result = collect_log(
            args.log,
            output=output,
            input_field=input_field,
            output_field=output_field,
            append=not args.replace,
            dedupe=not args.allow_duplicates,
        )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Collected {result['records']} new prompt-response pairs from {Path(args.log)}.")
        if result["skipped_duplicates"]:
            print(f"Skipped {result['skipped_duplicates']} duplicate records.")
        print(f"{str(result['mode']).title()} {Path(str(result['output']))}.")
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    if args.all_cases and args.max_cases is not None:
        raise ValueError("--all-cases cannot be combined with --max-cases")
    config = load_config(args.config)
    input_field = str(_config_value(args.input_field, config, "input_field", "prompt"))
    output_field = str(_config_value(args.output_field, config, "output_field", "response"))
    max_cases = int(_config_value(args.max_cases, config, "max_cases", 42))
    log_path = args.log or _config_observed_log_path(config) or ".redline/logs/prompts.jsonl"
    records = read_jsonl_records(log_path, input_field, output_field)
    suite = build_suite(
        records,
        source=log_path,
        input_field=input_field,
        output_field=output_field,
        max_cases=max_cases,
        all_cases=args.all_cases,
    )
    if args.json:
        print(json.dumps(cluster_report(suite), indent=2, sort_keys=True))
    else:
        print(format_cluster_report(suite), end="")
    return 0


def cmd_suite(args: argparse.Namespace) -> int:
    if args.all_cases and args.max_cases is not None:
        raise ValueError("--all-cases cannot be combined with --max-cases")
    config = load_config(args.config)
    input_field = _config_value(args.input_field, config, "input_field", "prompt")
    output_field = _config_value(args.output_field, config, "output_field", "response")
    max_cases = int(_config_value(args.max_cases, config, "max_cases", 42))
    output = str(_config_value(args.out, config, "suite", "redline-suite.json"))
    log_path = args.log or _config_observed_log_path(config) or ".redline/logs/prompts.jsonl"
    records = read_jsonl_records(log_path, input_field, output_field)
    suite = build_suite(
        records,
        source=log_path,
        input_field=input_field,
        output_field=output_field,
        max_cases=max_cases,
        all_cases=args.all_cases,
    )
    write_json(output, suite)
    summary = suite["summary"]
    print(f"Generated {summary['cases']} cases from {summary['records_seen']} records.")
    print(f"Detected {summary['clusters']} behavioral clusters.")
    print(f"Wrote {Path(output)}.")
    print()
    print("Next:")
    print(f"- Inspect cases: redline cases {Path(output)}")
    print(f"- Compare a candidate log: redline diff {Path(output)} path/to/candidate.jsonl")
    print("- Configure replay when ready: redline init --runner stdio --copy-runner")
    return 0


def cmd_suite_add(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path = _suite_arg(args.suite, config)
    output = args.out or suite_path
    prompt = _text_arg(args.prompt, args.prompt_file, "prompt")
    response = _text_arg(args.response, args.response_file, "response")
    suite = read_json(suite_path)
    case = add_suite_case(
        suite,
        prompt=prompt,
        baseline_response=response,
        source="manual",
        case_id=args.case_id,
        note=args.note,
    )
    requirements = None
    if args.include or args.exclude:
        requirements = add_case_requirement(
            suite,
            str(case["id"]),
            include=args.include,
            exclude=args.exclude,
            note=args.note,
        )
    write_json(output, suite)
    if args.json:
        print(
            json.dumps(
                {
                    "suite": str(output),
                    "case": case,
                    "requirements": requirements,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Added pinned case {case['id']} to {Path(output)}.")
        if requirements:
            rules = len(requirements.get("include") or []) + len(requirements.get("exclude") or [])
            print(f"Added {rules} requirement rule(s).")
        print()
        print("Next:")
        print(f"- Inspect case: redline case {Path(output)} {case['id']}")
        print(f"- Validate suite: redline validate {Path(output)}")
        print(f"- Compare candidate: redline diff {Path(output)} path/to/candidate.jsonl")
    return 0


def cmd_cases(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path = _suite_arg(args.suite, config)
    suite = read_json(suite_path)
    if args.json:
        print(json.dumps({"cases": suite_case_rows(suite)}, indent=2, sort_keys=True))
    else:
        print(format_suite_cases(suite), end="")
    return 0


def cmd_case(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path, case_id = _suite_case_args(args.paths, config)
    suite = read_json(suite_path)
    if args.json:
        print(json.dumps(suite_case_detail(suite, case_id), indent=2, sort_keys=True))
    else:
        print(format_suite_case_detail(suite, case_id), end="")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path = _suite_arg(args.suite, config)
    suite = read_json(suite_path)
    if args.json:
        print(json.dumps(suite_summary(suite), indent=2, sort_keys=True))
    else:
        print(format_suite_summary(suite), end="")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path = _suite_arg(args.suite, config)
    suite = read_json(suite_path)
    report = validate_suite(suite, suite_path=suite_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_validation_report(report), end="")
    if report["errors"] > 0:
        return 1
    if args.strict and report["warnings"] > 0:
        return 1
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path, candidate_path = _suite_candidate_args(args.paths, config)
    suite = read_json(suite_path)
    input_field = args.input_field or str(suite.get("input_field") or config.get("input_field", "prompt"))
    output_field = args.output_field or str(suite.get("output_field") or config.get("output_field", "response"))
    candidate = read_jsonl_records(candidate_path, input_field, output_field)
    result = compare_suite_to_candidate(suite, candidate, profile=_config_diff_profile(args.profile, config))
    result = _maybe_apply_judge(args, result, config)

    return _emit_result(args, result, title="redline diff", config=config, report_key="diff")


def cmd_compare(args: argparse.Namespace) -> int:
    previous = read_json(args.previous)
    current = read_json(args.current)
    result = compare_reports(
        previous,
        current,
        previous_path=args.previous,
        current_path=args.current,
    )
    if args.out_json:
        write_json(args.out_json, result)
    markdown_report = format_markdown_comparison(result)
    if args.out_md:
        write_text(args.out_md, markdown_report)
    if args.github_summary:
        _append_github_step_summary(markdown_report)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_report_comparison(result), end="")
    fail_on = parse_compare_fail_on(args.fail_on or "worse")
    return 1 if should_fail_comparison(result, fail_on) else 0


def cmd_history(args: argparse.Namespace) -> int:
    if args.limit < 0:
        raise ValueError("history --limit must be 0 or greater")
    if not args.report and not Path(args.out).exists():
        raise ValueError(f"{args.out} not found; pass a report to create history")
    if args.report:
        report = read_json(args.report)
        entry = history_entry(report, report_path=args.report, label=args.label)
        append_jsonl(args.out, [entry])

    entries = read_history(args.out)
    limit = None if args.limit == 0 else args.limit
    shown = entries[-limit:] if limit is not None and limit > 0 else entries
    markdown_history = format_markdown_history(shown)
    if args.out_md:
        write_text(args.out_md, markdown_history)
    if args.github_summary:
        _append_github_step_summary(markdown_history)
    if args.json:
        print(json.dumps({"version": "0.1", "history": shown}, indent=2, sort_keys=True))
    else:
        if args.report:
            print(f"Recorded {Path(args.report)} in {Path(args.out)}.")
            print()
        print(format_history(shown), end="")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path = _suite_arg(args.suite, config)
    replay_command = args.replay or _config_replay(config)
    if not replay_command:
        raise ValueError("replay command required; pass --replay or set replay in redline.json")
    suite = read_json(suite_path)
    timeout_seconds = float(_config_value(args.timeout, config, "timeout_seconds", 30.0))
    workers = int(_config_value(args.workers, config, "workers", 1))
    prompt_template = read_prompt_template(args.prompt) if args.prompt else None
    replay = replay_suite(
        suite,
        replay_command,
        timeout_seconds=timeout_seconds,
        workers=workers,
        prompt_template=prompt_template,
        prompt_path=args.prompt,
    )
    candidate_out = args.candidate_out or _config_candidate_path(config)
    if candidate_out:
        write_jsonl(candidate_out, (record.raw for record in replay.records))
    result = compare_suite_to_candidate(suite, replay.records, profile=_config_diff_profile(args.profile, config))
    result = _maybe_apply_judge(args, result, config)
    result["replay"] = replay.to_metadata()
    run_metadata_out = args.run_metadata or _config_run_metadata_path(config)
    if run_metadata_out:
        write_json(
            run_metadata_out,
            _run_metadata(replay.to_metadata(), suite_path, candidate_out, result),
        )

    return _emit_result(args, result, title="redline eval", config=config, report_key="eval")


def cmd_mark(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path, case_id = _suite_case_args(args.paths, config)
    suite = read_json(suite_path)
    mark_suite_case(suite, case_id, status=args.status, note=args.note)
    output = args.out or suite_path
    write_json(output, suite)
    print(f"Marked {case_id} as {args.status} in {Path(output)}.")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path, case_id = _suite_case_args(args.paths, config)
    suite = read_json(suite_path)
    removed = clear_suite_case_judgment(suite, case_id)
    output = args.out or suite_path
    write_json(output, suite)
    if removed:
        print(f"Cleared judgment for {case_id} in {Path(output)}.")
    else:
        print(f"No judgment found for {case_id} in {Path(output)}.")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path, case_ids = _accept_args(args.paths, config, all_expected=args.all_expected)
    suite = read_json(suite_path)
    if args.all_expected:
        case_ids = expected_case_ids(suite)
        if not case_ids:
            raise ValueError("no expected judgments found to accept")
    candidate_path = args.candidate or _config_candidate_path(config)
    if not candidate_path:
        raise ValueError("candidate JSONL required; pass --candidate or set runs.candidate in redline.json")
    input_field = args.input_field or str(suite.get("input_field") or config.get("input_field", "prompt"))
    output_field = args.output_field or str(suite.get("output_field") or config.get("output_field", "response"))
    candidate = read_jsonl_records(candidate_path, input_field, output_field)
    results = [
        accept_candidate_baseline(suite, candidate, case_id, note=args.note)
        for case_id in case_ids
    ]
    output = args.out or suite_path
    write_json(output, suite)
    for result in results:
        print(f"Accepted {result['case_id']} from {Path(candidate_path)} line {result['candidate_line']}.")
    print(f"Wrote {Path(output)}.")
    return 0


def cmd_require(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    suite_path, case_id = _suite_case_args(args.paths, config)
    suite = read_json(suite_path)
    if args.clear:
        removed = clear_case_requirements(suite, case_id)
        action = "Cleared" if removed else "No requirements found for"
        print(f"{action} {case_id}.")
    else:
        if not args.include and not args.exclude:
            raise ValueError("require needs --include, --exclude, or --clear")
        add_case_requirement(suite, case_id, include=args.include, exclude=args.exclude, note=args.note)
        print(f"Updated requirements for {case_id}.")
    output = args.out or suite_path
    write_json(output, suite)
    print(f"Wrote {Path(output)}.")
    return 0


def _emit_result(
    args: argparse.Namespace,
    result: dict[str, object],
    *,
    title: str,
    config: dict[str, object],
    report_key: str,
) -> int:
    fail_on = parse_fail_on(_config_fail_on(args.fail_on, config))
    out_json = args.out_json or _config_report_path(config, "json", report_key)
    out_md = args.out_md or _config_report_path(config, "markdown", report_key)
    out_html = args.out_html or _config_report_path(config, "html", report_key)
    out_junit = args.out_junit or _config_report_path(config, "junit", report_key)
    markdown_report = format_markdown_report(result, title=title)
    if out_json:
        write_json(out_json, result)
    if out_md:
        write_text(out_md, markdown_report)
    if out_html:
        write_text(out_html, format_html_report(result, title=title))
    if out_junit:
        write_text(out_junit, format_junit_report(result, suite_name=title.replace(" ", ".")))
    if getattr(args, "github_summary", False):
        _append_github_step_summary(markdown_report)
    if getattr(args, "github_annotations", False):
        annotations = format_github_annotations(result, title=title)
        if annotations:
            print(annotations, end="", file=sys.stderr)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif getattr(args, "compact", False):
        print(format_compact_report(result, title=title), end="")
    else:
        print(format_report(result, title=title), end="")

    return 1 if should_fail(result, fail_on) else 0


def _append_github_step_summary(markdown_report: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        raise ValueError("--github-summary requires GITHUB_STEP_SUMMARY")
    text = markdown_report if markdown_report.endswith("\n") else f"{markdown_report}\n"
    append_text(summary_path, text)


def _normalize_command_aliases(arguments: list[str]) -> list[str]:
    if len(arguments) >= 2 and arguments[0] == "suite" and arguments[1] == "add":
        return ["suite-add", *arguments[2:]]
    return arguments


def _text_arg(value: str | None, path: str | None, label: str) -> str:
    if value is not None and path is not None:
        raise ValueError(f"use --{label} or --{label}-file, not both")
    if path is not None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ValueError(f"{label} file not found: {path}") from exc
    if value is not None:
        return value
    raise ValueError(f"--{label} or --{label}-file is required")


def _maybe_apply_judge(
    args: argparse.Namespace,
    result: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    judge_command = args.judge or _config_judge(config)
    if not judge_command:
        return result
    return apply_judge(
        result,
        judge_command,
        timeout_seconds=float(_config_judge_timeout(args.judge_timeout, config)),
    )


def _is_git_ignored(path: str) -> bool:
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return completed.returncode == 0


def _config_value(
    explicit: object | None,
    config: dict[str, object],
    key: str,
    default: object,
) -> object:
    if explicit is not None:
        return explicit
    return config.get(key, default)


def _suite_arg(explicit: str | None, config: dict[str, object]) -> str:
    suite = explicit or config.get("suite")
    if not suite:
        raise ValueError("suite path required; pass it explicitly or run redline init")
    return str(suite)


def _suite_candidate_args(paths: list[str], config: dict[str, object]) -> tuple[str, str]:
    if len(paths) == 1:
        return _suite_arg(None, config), paths[0]
    if len(paths) == 2:
        return paths[0], paths[1]
    raise ValueError("diff expects candidate JSONL, or suite JSON plus candidate JSONL")


def _suite_case_args(paths: list[str], config: dict[str, object]) -> tuple[str, str]:
    if len(paths) == 1:
        return _suite_arg(None, config), paths[0]
    if len(paths) == 2:
        return paths[0], paths[1]
    raise ValueError("expected case id, or suite JSON plus case id")


def _accept_args(
    paths: list[str],
    config: dict[str, object],
    *,
    all_expected: bool,
) -> tuple[str, list[str]]:
    if all_expected:
        if len(paths) == 0:
            return _suite_arg(None, config), []
        if len(paths) == 1:
            return paths[0], []
        raise ValueError("accept --all-expected expects an optional suite JSON path")
    suite_path, case_id = _suite_case_args(paths, config)
    return suite_path, [case_id]


def _config_fail_on(explicit: str | None, config: dict[str, object]) -> str | None:
    if explicit is not None:
        return explicit
    value = config.get("fail_on")
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if value is None:
        return None
    return str(value)


def _config_diff_profile(explicit: str | None, config: dict[str, object]) -> str:
    value = explicit if explicit is not None else config.get("diff_profile", "strict")
    profile = str(value)
    if profile not in DIFF_PROFILES:
        joined = ", ".join(DIFF_PROFILES)
        raise ValueError(f"diff profile must be one of: {joined}")
    return profile


def _config_report_path(config: dict[str, object], format_key: str, report_key: str) -> str | None:
    reports = config.get("reports")
    if not isinstance(reports, dict):
        return None
    value = reports.get(format_key)
    if not isinstance(value, str) or not value:
        return None
    if "{command}" in value:
        return value.replace("{command}", report_key)
    return value


def _config_observed_log_path(config: dict[str, object]) -> str | None:
    logs = config.get("logs")
    if not isinstance(logs, dict):
        return None
    value = logs.get("observed")
    if isinstance(value, str) and value:
        return value
    return None


def _config_candidate_path(config: dict[str, object]) -> str | None:
    runs = config.get("runs")
    if not isinstance(runs, dict):
        return None
    value = runs.get("candidate")
    if isinstance(value, str) and value:
        return value
    return None


def _config_run_metadata_path(config: dict[str, object]) -> str | None:
    runs = config.get("runs")
    if not isinstance(runs, dict):
        return None
    value = runs.get("metadata")
    if isinstance(value, str) and value:
        return value
    return None


def _config_replay(config: dict[str, object]) -> str | None:
    value = config.get("replay")
    if isinstance(value, str) and value:
        return value
    return None


def _config_judge(config: dict[str, object]) -> str | None:
    value = config.get("judge")
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str) and command:
            return command
    return None


def _config_judge_timeout(explicit: float | None, config: dict[str, object]) -> float:
    if explicit is not None:
        return explicit
    value = config.get("judge_timeout_seconds")
    if isinstance(value, (int, float)):
        return float(value)
    judge = config.get("judge")
    if isinstance(judge, dict):
        timeout = judge.get("timeout_seconds")
        if isinstance(timeout, (int, float)):
            return float(timeout)
    return 30.0


def _run_metadata(
    replay: dict[str, object],
    suite_path: str,
    candidate_path: str | None,
    result: dict[str, object],
) -> dict[str, object]:
    metadata = {
        "version": "0.1",
        "suite": suite_path,
        "replay": replay,
        "summary": result.get("summary", {}),
        "decision": result.get("decision", {}),
    }
    if result.get("judge"):
        metadata["judge"] = result["judge"]
    if candidate_path:
        metadata["candidate"] = candidate_path
    return metadata


def _runner_replay(runner_id: str | None) -> str | None:
    if runner_id is None:
        return None
    for adapter in runner_adapters():
        if adapter["id"] == runner_id:
            return adapter["replay"]
    raise ValueError(f"unknown runner adapter: {runner_id}")
