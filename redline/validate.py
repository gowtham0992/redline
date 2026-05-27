from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .features import extract_features
from .hashes import prompt_response_hash
from .io import read_json
from .judgments import JUDGMENT_STATUSES


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
    _validate_judgments(items, suite.get("judgments"), case_ids)
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


def validate_prompt_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: str = "redline-prompts.json",
) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    prompts = manifest.get("prompts")
    if not isinstance(prompts, list):
        _add(items, "error", "prompts", "expected a list of prompt manifest entries")
        prompts = []
    elif not prompts:
        _add(items, "warning", "prompts", "manifest has no prompt entries")

    prompt_ids: set[str] = set()
    suite_paths: set[str] = set()
    suite_count = 0
    for index, prompt in enumerate(prompts):
        path = f"prompts[{index}]"
        if not isinstance(prompt, dict):
            _add(items, "error", path, "expected prompt manifest entry object")
            continue

        prompt_id = str(prompt.get("id") or "").strip()
        prompt_path = str(prompt.get("path") or "").strip()
        suite_path = str(prompt.get("suite") or "").strip()
        if not prompt_id:
            _add(items, "error", f"{path}.id", "expected non-empty string")
        elif prompt_id in prompt_ids:
            _add(items, "error", f"{path}.id", f"duplicate prompt id: {prompt_id}")
        else:
            prompt_ids.add(prompt_id)
        if not prompt_path:
            _add(items, "error", f"{path}.path", "expected non-empty prompt path")
        elif not Path(prompt_path).is_file():
            _add(items, "warning", f"{path}.path", f"prompt file not found: {prompt_path}")
        if not suite_path:
            _add(items, "error", f"{path}.suite", "expected non-empty suite path")
            continue
        if suite_path in suite_paths:
            _add(items, "warning", f"{path}.suite", f"duplicate mapped suite path: {suite_path}")
        else:
            suite_paths.add(suite_path)
        if not Path(suite_path).is_file():
            _add(items, "error", f"{path}.suite", f"mapped suite not found: {suite_path}")
            continue
        suite_count += 1
        try:
            suite_report = validate_suite(read_json(suite_path), suite_path=suite_path)
        except ValueError as exc:
            _add(items, "error", f"{path}.suite", f"mapped suite is not valid JSON: {exc}")
            continue
        for child in suite_report.get("items", []):
            if not isinstance(child, dict):
                continue
            level = str(child.get("level") or "warning")
            child_path = str(child.get("path") or "suite")
            message = str(child.get("message") or "check mapped suite")
            _add(items, level, f"{path}.suite::{child_path}", message)

    error_count = _count(items, "error")
    warning_count = _count(items, "warning")
    return {
        "version": "0.1",
        "manifest": manifest_path,
        "valid": error_count == 0,
        "errors": error_count,
        "warnings": warning_count,
        "prompt_count": len(prompts),
        "suite_count": suite_count,
        "items": items,
        "next_steps": _manifest_next_steps(items, manifest_path=manifest_path),
    }


def format_validation_report(report: dict[str, Any]) -> str:
    lines = [
        "redline validate",
        "",
    ]
    manifest = str(report.get("manifest") or "")
    suite = str(report.get("suite") or "")
    if manifest:
        lines.append(f"Prompt manifest: {manifest}")
        lines.append(f"Prompts:  {int(report.get('prompt_count', 0))}")
        lines.append(f"Suites:   {int(report.get('suite_count', 0))}/{int(report.get('prompt_count', 0))}")
    elif suite:
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


def _manifest_next_steps(items: list[dict[str, str]], *, manifest_path: str) -> list[str]:
    steps: list[str] = []
    for item in items:
        if (
            item["level"] == "error"
            and item["path"].endswith(".suite")
            and "mapped suite not found" in item["message"]
        ):
            suite_path = item["message"].split("mapped suite not found: ", 1)[-1]
            steps.append(f"Build missing suite: redline suite path/to/baseline.jsonl --out {suite_path}")
        if item["level"] == "error" and ".suite::" in item["path"]:
            steps.append(f"Fix invalid mapped suites, then rerun: redline validate {manifest_path} --strict")
        if item["level"] == "warning" and item["path"].endswith(".path"):
            steps.append("Restore missing prompt files or regenerate the manifest with redline prompts.")
    if items and not steps:
        steps.append(f"Fix manifest findings, then rerun: redline validate {manifest_path} --strict")
    return _dedupe(steps)


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
    if any(
        item["level"] == "error" and item["path"].startswith("judgments.") and "unknown status" in item["message"]
        for item in items
    ):
        steps.append(f"Use a supported judgment status, then rerun: redline validate {suite_arg}")
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
    if any(
        item["level"] == "warning" and item["path"].startswith("judgments.") and item["path"].endswith(".note")
        for item in items
    ):
        steps.append(f"Add judgment notes before team rollout, then rerun: redline validate {suite_arg}")

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


def _validate_judgments(
    items: list[dict[str, str]],
    value: object,
    case_ids: set[str],
) -> None:
    _validate_references(items, value, case_ids, "judgments")
    if value is None or not isinstance(value, dict):
        return
    for case_id, judgment in value.items():
        path = f"judgments.{case_id}"
        if not isinstance(judgment, dict):
            _add(items, "error", path, "expected judgment object")
            continue
        status = str(judgment.get("status") or "").strip()
        if status not in JUDGMENT_STATUSES:
            allowed = ", ".join(JUDGMENT_STATUSES)
            _add(items, "error", f"{path}.status", f"unknown status {status or '<empty>'}; expected one of: {allowed}")
        note = str(judgment.get("note") or "").strip()
        if status in {"expected", "ignored"} and not note:
            _add(items, "warning", f"{path}.note", "expected or ignored judgments should include a reason")
        updated_at = judgment.get("updated_at")
        if not isinstance(updated_at, str) or _parse_created_at(updated_at) is None:
            _add(items, "warning", f"{path}.updated_at", "missing or invalid judgment timestamp")


def _add(items: list[dict[str, str]], level: str, path: str, message: str) -> None:
    items.append({"level": level, "path": path, "message": message})


def _count(items: list[dict[str, str]], level: str) -> int:
    return sum(1 for item in items if item["level"] == level)
