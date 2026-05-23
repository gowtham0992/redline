from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from .features import extract_features
from .io import LogRecord


@dataclass(frozen=True)
class CaseDiff:
    case_id: str
    status: str
    prompt: str
    reasons: tuple[str, ...]
    baseline_features: dict[str, Any]
    candidate_features: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "prompt": self.prompt,
            "reasons": list(self.reasons),
            "baseline_features": self.baseline_features,
            "candidate_features": self.candidate_features,
        }


def compare_suite_to_candidate(
    suite: dict[str, Any],
    candidate_records: list[LogRecord],
) -> dict[str, Any]:
    candidate_case_index = _index_by_case_id(candidate_records)
    candidate_index = _index_by_prompt(candidate_records)
    judgments = suite.get("judgments", {})
    if not isinstance(judgments, dict):
        judgments = {}
    diffs: list[CaseDiff] = []

    for case in suite.get("cases", []):
        case_id = str(case["id"])
        prompt = str(case["prompt"])
        candidate = _pop_candidate_by_case_id(candidate_case_index, case_id)
        if candidate is None:
            candidate = _pop_candidate(candidate_index, prompt)
        if candidate is None:
            status, reasons = apply_judgment(
                "missing",
                ["candidate output missing for exact prompt"],
                _case_judgment(judgments, case_id),
            )
            diffs.append(
                CaseDiff(
                    case_id=case_id,
                    status=status,
                    prompt=prompt,
                    reasons=tuple(reasons),
                    baseline_features=dict(case.get("features", {})),
                    candidate_features=None,
                )
            )
            continue

        baseline_response = str(case["baseline_response"])
        baseline = extract_features(baseline_response)
        candidate_features = extract_features(candidate.response)
        status, reasons = classify_change(baseline.to_dict(), candidate_features.to_dict())
        status, reasons = apply_judgment(status, reasons, _case_judgment(judgments, case_id))
        diffs.append(
            CaseDiff(
                case_id=case_id,
                status=status,
                prompt=prompt,
                reasons=tuple(reasons),
                baseline_features=baseline.to_dict(),
                candidate_features=candidate_features.to_dict(),
            )
        )

    counts = Counter(diff.status for diff in diffs)
    return {
        "version": "0.1",
        "summary": {
            "cases": len(diffs),
            "regression": counts["regression"],
            "changed": counts["changed"],
            "improved": counts["improved"],
            "accepted": counts["accepted"],
            "ignored": counts["ignored"],
            "neutral": counts["neutral"],
            "missing": counts["missing"],
        },
        "diffs": [diff.to_dict() for diff in diffs],
    }


def classify_change(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    regression_reasons: list[str] = []
    improvement_reasons: list[str] = []

    if not baseline["empty"] and candidate["empty"]:
        regression_reasons.append("candidate became empty")
    if baseline["empty"] and not candidate["empty"]:
        improvement_reasons.append("candidate is no longer empty")

    if baseline["valid_json"] and not candidate["valid_json"]:
        regression_reasons.append("candidate lost valid JSON format")
    if not baseline["valid_json"] and candidate["valid_json"]:
        improvement_reasons.append("candidate gained valid JSON format")

    baseline_keys = set(baseline.get("json_keys") or [])
    candidate_keys = set(candidate.get("json_keys") or [])
    missing_keys = sorted(baseline_keys - candidate_keys)
    added_keys = sorted(candidate_keys - baseline_keys)
    if missing_keys:
        regression_reasons.append(f"candidate missing JSON keys: {', '.join(missing_keys)}")
    if added_keys and baseline["valid_json"] and candidate["valid_json"]:
        reasons.append(f"candidate added JSON keys: {', '.join(added_keys)}")

    if not baseline["refusal"] and candidate["refusal"]:
        regression_reasons.append("candidate newly refuses")
    if baseline["refusal"] and not candidate["refusal"]:
        improvement_reasons.append("candidate no longer refuses")

    for feature, label in (
        ("has_code_block", "code block"),
        ("has_bullets", "bullet list"),
        ("has_numbered_list", "numbered list"),
        ("has_markdown_table", "markdown table"),
    ):
        if baseline[feature] and not candidate[feature]:
            regression_reasons.append(f"candidate lost {label} structure")
        elif not baseline[feature] and candidate[feature]:
            reasons.append(f"candidate added {label} structure")

    lost_numbers = sorted(set(baseline.get("numbers") or []) - set(candidate.get("numbers") or []))
    if lost_numbers:
        regression_reasons.append(f"candidate missing numbers: {', '.join(lost_numbers[:8])}")

    length_reason = _length_reason(baseline["words"], candidate["words"])
    if length_reason:
        reasons.append(length_reason)

    if baseline["shape"] != candidate["shape"]:
        reasons.append(f"shape changed: {baseline['shape']} -> {candidate['shape']}")

    if regression_reasons:
        return "regression", regression_reasons + reasons
    if improvement_reasons:
        return "improved", improvement_reasons + reasons
    if reasons:
        return "changed", reasons
    return "neutral", ["no high-signal behavioral change detected"]


def apply_judgment(
    status: str,
    reasons: list[str],
    judgment: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    if not judgment:
        return status, reasons

    judgment_status = judgment.get("status")
    note = str(judgment.get("note", "")).strip()
    suffix = f": {note}" if note else ""

    if judgment_status == "ignored":
        return "ignored", [f"ignored by suite judgment{suffix}"] + reasons
    if judgment_status == "expected" and status in {"regression", "changed", "improved"}:
        return "accepted", [f"accepted by suite judgment{suffix}"] + reasons
    if judgment_status == "regression" and status != "missing":
        return "regression", [f"confirmed regression by suite judgment{suffix}"] + reasons
    return status, reasons


def format_report(result: dict[str, Any], *, title: str = "redline diff") -> str:
    summary = result["summary"]
    lines = [
        title,
        "",
        f"  REGRESSION {summary['regression']:>3}",
        f"  CHANGED    {summary['changed']:>3}",
        f"  IMPROVED   {summary['improved']:>3}",
        f"  ACCEPTED   {summary['accepted']:>3}",
        f"  IGNORED    {summary['ignored']:>3}",
        f"  NEUTRAL    {summary['neutral']:>3}",
        f"  MISSING    {summary['missing']:>3}",
        "",
    ]

    for status in ("regression", "changed", "improved", "accepted", "ignored", "missing"):
        matching = [item for item in result["diffs"] if item["status"] == status]
        if not matching:
            continue
        lines.append(status.upper())
        for item in matching:
            lines.append(f"- {item['case_id']}: {_preview(item['prompt'])}")
            for reason in item["reasons"]:
                lines.append(f"  - {reason}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _index_by_prompt(records: list[LogRecord]) -> dict[str, list[LogRecord]]:
    indexed: dict[str, list[LogRecord]] = defaultdict(list)
    for record in records:
        indexed[record.prompt].append(record)
    return indexed


def _index_by_case_id(records: list[LogRecord]) -> dict[str, list[LogRecord]]:
    indexed: dict[str, list[LogRecord]] = defaultdict(list)
    for record in records:
        case_id = record.raw.get("case_id")
        if isinstance(case_id, str) and case_id:
            indexed[case_id].append(record)
    return indexed


def _pop_candidate_by_case_id(
    indexed: dict[str, list[LogRecord]],
    case_id: str,
) -> LogRecord | None:
    records = indexed.get(case_id)
    if not records:
        return None
    return records.pop(0)


def _pop_candidate(indexed: dict[str, list[LogRecord]], prompt: str) -> LogRecord | None:
    records = indexed.get(prompt)
    if not records:
        return None
    return records.pop(0)


def _case_judgment(judgments: dict[Any, Any], case_id: str) -> dict[str, Any] | None:
    judgment = judgments.get(case_id)
    if isinstance(judgment, dict):
        return judgment
    return None


def _length_reason(baseline_words: int, candidate_words: int) -> str | None:
    if baseline_words == 0 and candidate_words == 0:
        return None
    if baseline_words == 0:
        return "candidate added text"
    ratio = candidate_words / baseline_words
    if ratio <= 0.5:
        return f"candidate much shorter: {baseline_words} -> {candidate_words} words"
    if ratio >= 2.0 and candidate_words - baseline_words >= 40:
        return f"candidate much longer: {baseline_words} -> {candidate_words} words"
    return None


def _preview(text: str, limit: int = 84) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."
