from __future__ import annotations

from math import ceil
from typing import Any


def benchmark_suite(
    suite: dict[str, Any],
    *,
    suite_path: str = "redline-suite.json",
    timeout_seconds: float = 30.0,
    workers: int = 1,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    summary = suite.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    cases = suite.get("cases")
    cases_count = len(cases) if isinstance(cases, list) else int(summary.get("cases", 0) or 0)
    clusters = suite.get("clusters")
    cluster_count = len(clusters) if isinstance(clusters, list) else int(summary.get("clusters", 0) or 0)
    requirements = suite.get("requirements")
    requirements_count = len(requirements) if isinstance(requirements, dict) else 0
    judgments = suite.get("judgments")
    judgments_count = len(judgments) if isinstance(judgments, dict) else 0

    waves = ceil(cases_count / workers) if cases_count else 0
    sequential_seconds = cases_count * timeout_seconds
    worst_case_seconds = waves * timeout_seconds
    result = {
        "suite": suite_path,
        "cases": cases_count,
        "clusters": cluster_count,
        "records_seen": int(summary.get("records_seen", cases_count) or 0),
        "workers": workers,
        "timeout_seconds": timeout_seconds,
        "parallel_waves": waves,
        "sequential_worst_case_seconds": sequential_seconds,
        "worst_case_seconds": worst_case_seconds,
        "requirements": requirements_count,
        "judgments": judgments_count,
        "size": _size_label(cases_count),
    }
    result["status"] = _status(result)
    result["next_steps"] = _next_steps(result)
    return result


def format_benchmark_report(report: dict[str, Any]) -> str:
    lines = [
        "redline benchmark",
        "",
        f"Suite:                 {report['suite']}",
        f"Cases:                 {report['cases']}",
        f"Behavioral clusters:   {report['clusters']}",
        f"Records seen:          {report['records_seen']}",
        f"Workers:               {report['workers']}",
        f"Timeout per case:      {_seconds(report['timeout_seconds'])}",
        f"Parallel waves:        {report['parallel_waves']}",
        f"Worst-case eval budget: {_duration(report['worst_case_seconds'])}",
        f"Sequential budget:     {_duration(report['sequential_worst_case_seconds'])}",
        f"Requirements:          {report['requirements']}",
        f"Judgments:             {report['judgments']}",
        f"Size:                  {str(report['size']).replace('_', ' ')}",
        f"Status:                {str(report['status']).upper()}",
    ]
    next_steps = report.get("next_steps") or []
    if next_steps:
        lines.extend(["", "Next:"])
        for step in next_steps:
            lines.append(f"- {step}")
    return "\n".join(lines).rstrip() + "\n"


def format_benchmark_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## redline benchmark",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Suite | `{report['suite']}` |",
        f"| Cases | {report['cases']} |",
        f"| Behavioral clusters | {report['clusters']} |",
        f"| Workers | {report['workers']} |",
        f"| Timeout per case | {_seconds(report['timeout_seconds'])} |",
        f"| Worst-case eval budget | {_duration(report['worst_case_seconds'])} |",
        f"| Sequential budget | {_duration(report['sequential_worst_case_seconds'])} |",
        f"| Size | {str(report['size']).replace('_', ' ')} |",
        f"| Status | {str(report['status']).upper()} |",
    ]
    next_steps = report.get("next_steps") or []
    if next_steps:
        lines.extend(["", "Next:"])
        for step in next_steps:
            lines.append(f"- {step}")
    return "\n".join(lines).rstrip() + "\n"


def _size_label(cases: int) -> str:
    if cases == 0:
        return "empty"
    if cases <= 25:
        return "small"
    if cases <= 100:
        return "medium"
    if cases <= 500:
        return "large"
    return "very_large"


def _status(report: dict[str, Any]) -> str:
    if int(report["cases"]) == 0:
        return "warn"
    if float(report["worst_case_seconds"]) > 600:
        return "warn"
    if int(report["workers"]) == 1 and int(report["cases"]) > 25:
        return "warn"
    return "ok"


def _next_steps(report: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    cases = int(report["cases"])
    workers = int(report["workers"])
    budget = float(report["worst_case_seconds"])
    if cases == 0:
        steps.append("Generate or add suite cases before relying on eval.")
    if workers == 1 and cases > 25:
        steps.append("Set workers in redline.json or pass --workers to keep CI feedback fast.")
    if budget > 600:
        steps.append("Split the suite, raise workers, or lower timeout before making this a required CI gate.")
    if not int(report["requirements"]):
        steps.append("Add requirements to high-value cases so scale does not dilute trust.")
    if cases > 0 and not int(report["judgments"]):
        steps.append("After the first eval, mark expected changes so future diffs stay focused.")
    return steps


def _seconds(value: Any) -> str:
    number = float(value)
    if number.is_integer():
        return f"{int(number)}s"
    return f"{number:.1f}s"


def _duration(value: Any) -> str:
    seconds = int(round(float(value)))
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"
