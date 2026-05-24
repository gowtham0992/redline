from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .features import extract_features
from .hashes import prompt_response_hash


_FEATURE_KEYS = (
    "empty",
    "valid_json",
    "json_type",
    "json_keys",
    "has_code_block",
    "has_bullets",
    "has_numbered_list",
    "has_markdown_table",
    "refusal",
    "urls",
    "numbers",
    "entities",
    "shape",
    "length_bucket",
)


def validate_suite(suite: dict[str, Any], *, suite_path: str = "") -> dict[str, Any]:
    items: list[dict[str, str]] = []
    cases = suite.get("cases")
    if not isinstance(cases, list):
        _add(items, "error", "cases", "expected a list of suite cases")
        cases = []
    elif not cases:
        _add(items, "warning", "cases", "suite has no cases")

    case_ids: set[str] = set()
    prompt_response_pairs: dict[tuple[str, str], str] = {}
    for index, case in enumerate(cases):
        path = f"cases[{index}]"
        if not isinstance(case, dict):
            _add(items, "error", path, "expected case object")
            continue

        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            _add(items, "error", f"{path}.id", "expected non-empty string")
        elif case_id in case_ids:
            _add(items, "error", f"{path}.id", f"duplicate case id: {case_id}")
        else:
            case_ids.add(case_id)

        prompt = case.get("prompt")
        if not isinstance(prompt, str):
            _add(items, "error", f"{path}.prompt", "expected string")

        baseline = case.get("baseline_response")
        if not isinstance(baseline, str):
            _add(items, "error", f"{path}.baseline_response", "expected string")
            baseline = None
        if isinstance(prompt, str) and isinstance(baseline, str):
            pair = (prompt, baseline)
            if pair in prompt_response_pairs:
                _add(
                    items,
                    "warning",
                    path,
                    f"duplicate prompt-response pair already covered by {prompt_response_pairs[pair]}",
                )
            else:
                prompt_response_pairs[pair] = path
            content_hash = case.get("content_hash")
            if content_hash is None:
                _add(items, "warning", f"{path}.content_hash", "missing stable prompt-response hash")
            elif content_hash != prompt_response_hash(prompt, baseline):
                _add(items, "error", f"{path}.content_hash", "does not match prompt and baseline_response")

        features = case.get("features")
        if not isinstance(features, dict):
            _add(items, "error", f"{path}.features", "expected feature object")
            continue
        if baseline is not None:
            _validate_features(items, path, features, baseline)

    _validate_summary(items, suite, len(cases))
    _validate_references(items, suite.get("requirements"), case_ids, "requirements")
    _validate_references(items, suite.get("judgments"), case_ids, "judgments")
    _validate_source_staleness(items, suite)

    error_count = _count(items, "error")
    warning_count = _count(items, "warning")
    return {
        "version": "0.1",
        "suite": suite_path,
        "valid": error_count == 0,
        "errors": error_count,
        "warnings": warning_count,
        "items": items,
        "next_steps": _next_steps(
            items,
            suite_path=suite_path,
            source=suite.get("source"),
        ),
    }


def format_validation_report(report: dict[str, Any]) -> str:
    lines = [
        "redline validate",
        "",
    ]
    suite = str(report.get("suite") or "")
    if suite:
        lines.append(f"Suite:    {suite}")
    status = "valid" if report.get("valid") else "invalid"
    lines.extend(
        [
            f"Status:   {status}",
            f"Errors:   {int(report.get('errors', 0))}",
            f"Warnings: {int(report.get('warnings', 0))}",
        ]
    )

    items = report.get("items")
    if isinstance(items, list) and items:
        lines.append("")
        lines.append("Findings:")
        for item in items:
            if not isinstance(item, dict):
                continue
            level = str(item.get("level", "warning")).upper()
            path = str(item.get("path", "suite"))
            message = str(item.get("message", "check suite"))
            lines.append(f"- {level} {path}: {message}")

    next_steps = report.get("next_steps")
    if isinstance(next_steps, list) and next_steps:
        lines.append("")
        lines.append("Next:")
        for step in next_steps:
            lines.append(f"- {step}")

    return "\n".join(lines).rstrip() + "\n"


def _next_steps(items: list[dict[str, str]], *, suite_path: str, source: object) -> list[str]:
    suite_arg = suite_path or "redline-suite.json"
    source_arg = _source_arg(source)
    steps: list[str] = []

    if any(item["level"] == "error" and ".features." in item["path"] for item in items):
        steps.append(
            f"Refresh stale stored features: redline suite {source_arg} --out {suite_arg}"
        )
    if any(
        item["level"] == "error" and item["path"].endswith(".content_hash")
        for item in items
    ):
        steps.append(
            f"Refresh stale content hashes: redline suite {source_arg} --out {suite_arg}"
        )
    if any(
        item["level"] == "error" and "duplicate case id" in item["message"]
        for item in items
    ):
        steps.append(
            f"Give duplicate cases unique IDs or remove them, then rerun: redline validate {suite_arg}"
        )
    if any(
        item["level"] == "error" and "references unknown case id" in item["message"]
        for item in items
    ):
        steps.append(
            f"Update requirement or judgment case IDs, then rerun: redline validate {suite_arg}"
        )
    if any(item["level"] == "error" and item["path"] == "cases" for item in items):
        steps.append(f"Fix suite JSON shape, then rerun: redline validate {suite_arg}")

    if any(
        item["level"] == "warning" and "duplicate prompt-response pair" in item["message"]
        for item in items
    ):
        steps.append(
            f"Remove duplicate prompt-response cases or regenerate: redline suite {source_arg} --out {suite_arg}"
        )
    if any(
        item["level"] == "warning"
        and (
            item["path"].endswith(".content_hash")
            or ".features." in item["path"]
            or item["path"] == "summary"
        )
        for item in items
    ):
        steps.append(
            f"Regenerate suite metadata from trusted logs: redline suite {source_arg} --out {suite_arg}"
        )
    if any(
        item["level"] == "warning" and item["path"] == "source" and "newer than suite" in item["message"]
        for item in items
    ):
        steps.append(f"Regenerate suite from newer source log: redline suite {source_arg} --out {suite_arg}")

    if items and not steps:
        steps.append(f"Fix findings, then rerun: redline validate {suite_arg}")

    return _dedupe(steps)


def _source_arg(source: object) -> str:
    if isinstance(source, str) and source.strip() and source not in {"manual", "memory"}:
        return source
    return "path/to/baseline.jsonl"


def _validate_source_staleness(items: list[dict[str, str]], suite: dict[str, Any]) -> None:
    source = suite.get("source")
    if not isinstance(source, str) or not source.strip() or source in {"manual", "memory"}:
        return
    source_path = Path(source)
    if not source_path.exists() or not source_path.is_file():
        return
    created_at = _parse_created_at(suite.get("created_at"))
    if created_at is None:
        _add(items, "warning", "created_at", "missing or invalid suite creation timestamp")
        return
    source_updated_at = datetime.fromtimestamp(source_path.stat().st_mtime, timezone.utc)
    if source_updated_at > created_at:
        _add(
            items,
            "warning",
            "source",
            f"source log {source} is newer than suite created_at; regenerate before relying on coverage",
        )


def _parse_created_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _validate_features(
    items: list[dict[str, str]],
    path: str,
    features: dict[str, Any],
    baseline: str,
) -> None:
    expected = extract_features(baseline).to_dict()
    for key in _FEATURE_KEYS:
        if key not in features:
            _add(items, "warning", f"{path}.features.{key}", "missing stored feature")
            continue
        if features[key] != expected[key]:
            _add(items, "error", f"{path}.features.{key}", "does not match baseline_response")


def _validate_summary(items: list[dict[str, str]], suite: dict[str, Any], case_count: int) -> None:
    summary = suite.get("summary")
    if not isinstance(summary, dict):
        _add(items, "warning", "summary", "missing suite summary")
        return
    expected_cases = summary.get("cases")
    if isinstance(expected_cases, int) and expected_cases != case_count:
        _add(items, "warning", "summary.cases", f"expected {case_count}, found {expected_cases}")


def _validate_references(
    items: list[dict[str, str]],
    value: object,
    case_ids: set[str],
    path: str,
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        _add(items, "error", path, "expected object keyed by case id")
        return
    for case_id in value:
        if str(case_id) not in case_ids:
            _add(items, "error", f"{path}.{case_id}", "references unknown case id")


def _add(items: list[dict[str, str]], level: str, path: str, message: str) -> None:
    items.append({"level": level, "path": path, "message": message})


def _count(items: list[dict[str, str]], level: str) -> int:
    return sum(1 for item in items if item["level"] == level)
