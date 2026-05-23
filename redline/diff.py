from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .features import extract_features
from .io import LogRecord
from .requirements import case_requirements, requirement_reasons


@dataclass(frozen=True)
class CaseDiff:
    case_id: str
    status: str
    source: str
    source_line: Any
    cluster: str
    prompt: str
    baseline_response: str
    candidate_response: str | None
    reasons: tuple[str, ...]
    baseline_features: dict[str, Any]
    candidate_features: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "source": self.source,
            "source_line": self.source_line,
            "cluster": self.cluster,
            "prompt": self.prompt,
            "baseline_response": self.baseline_response,
            "candidate_response": self.candidate_response,
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
    source = str(suite.get("source", ""))

    for case in suite.get("cases", []):
        case_id = str(case["id"])
        prompt = str(case["prompt"])
        baseline_response = str(case["baseline_response"])
        source_line = case.get("source_line")
        cluster = str(case.get("cluster", ""))
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
                    source=source,
                    source_line=source_line,
                    cluster=cluster,
                    prompt=prompt,
                    baseline_response=baseline_response,
                    candidate_response=None,
                    reasons=tuple(reasons),
                    baseline_features=dict(case.get("features", {})),
                    candidate_features=None,
                )
            )
            continue

        baseline = extract_features(baseline_response)
        candidate_features = extract_features(candidate.response)
        requirement_failures = requirement_reasons(
            case_requirements(suite, case_id),
            candidate.response,
        )
        status, reasons = classify_change(
            baseline.to_dict(),
            candidate_features.to_dict(),
            baseline_text=baseline_response,
            candidate_text=candidate.response,
        )
        if requirement_failures:
            status = "regression"
            reasons = requirement_failures + reasons
        status, reasons = apply_judgment(status, reasons, _case_judgment(judgments, case_id))
        diffs.append(
            CaseDiff(
                case_id=case_id,
                status=status,
                source=source,
                source_line=source_line,
                cluster=cluster,
                prompt=prompt,
                baseline_response=baseline_response,
                candidate_response=candidate.response,
                reasons=tuple(reasons),
                baseline_features=baseline.to_dict(),
                candidate_features=candidate_features.to_dict(),
            )
        )

    counts = Counter(diff.status for diff in diffs)
    summary = {
        "cases": len(diffs),
        "regression": counts["regression"],
        "changed": counts["changed"],
        "improved": counts["improved"],
        "accepted": counts["accepted"],
        "ignored": counts["ignored"],
        "neutral": counts["neutral"],
        "missing": counts["missing"],
    }
    return {
        "version": "0.1",
        "summary": summary,
        "decision": summarize_decision(summary),
        "diffs": [diff.to_dict() for diff in diffs],
    }


def classify_change(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    baseline_text: str | None = None,
    candidate_text: str | None = None,
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

    lost_urls = sorted(set(baseline.get("urls") or []) - set(candidate.get("urls") or []))
    if lost_urls:
        regression_reasons.append(f"candidate missing URLs: {', '.join(lost_urls[:4])}")

    lost_entities = sorted(set(baseline.get("entities") or []) - set(candidate.get("entities") or []))
    if lost_entities:
        regression_reasons.append(f"candidate missing entities: {', '.join(lost_entities[:8])}")

    length_reason = _length_reason(baseline["words"], candidate["words"])
    if length_reason:
        reasons.append(length_reason)

    if baseline["shape"] != candidate["shape"]:
        reasons.append(f"shape changed: {baseline['shape']} -> {candidate['shape']}")

    if baseline["shape"] == candidate["shape"]:
        content_reason = _content_reason(baseline_text, candidate_text)
        if content_reason:
            reasons.append(content_reason)

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
    decision = result.get("decision")
    if isinstance(decision, dict):
        confidence = str(decision.get("confidence") or "").upper()
        action = str(decision.get("recommended_action") or "")
        if confidence and action:
            lines.append(f"Confidence: {confidence}  |  Recommended action: {action}")
            lines.append("")

    for status in ("regression", "changed", "improved", "accepted", "ignored", "missing"):
        matching = [item for item in result["diffs"] if item["status"] == status]
        if not matching:
            continue
        lines.append(status.upper())
        for item in matching:
            lines.append(f"- {_case_label(item)}: {_preview(item['prompt'])}")
            for reason in item["reasons"]:
                lines.append(f"  - {reason}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def summarize_decision(summary: dict[str, Any]) -> dict[str, Any]:
    cases = _summary_count(summary, "cases")
    regression = _summary_count(summary, "regression")
    missing = _summary_count(summary, "missing")
    changed = _summary_count(summary, "changed")
    improved = _summary_count(summary, "improved")

    if cases == 0:
        return {
            "confidence": "low",
            "recommended_action": "collect baseline cases before relying on redline",
            "rationale": ["suite has no cases"],
        }
    if regression or missing:
        rationale = []
        if regression:
            rationale.append(f"{regression} regression case(s)")
        if missing:
            rationale.append(f"{missing} missing candidate output(s)")
        return {
            "confidence": "high",
            "recommended_action": "fix blocking cases before shipping",
            "rationale": rationale,
        }
    if changed:
        return {
            "confidence": "medium",
            "recommended_action": "review changed cases before shipping",
            "rationale": [f"{changed} changed case(s) need human review"],
        }
    if improved:
        return {
            "confidence": "high",
            "recommended_action": "ship candidate after reviewing improvements",
            "rationale": [f"{improved} improved case(s), no blocking cases"],
        }
    return {
        "confidence": "high",
        "recommended_action": "ship candidate; no blocking changes detected",
        "rationale": ["no regressions, missing outputs, or unreviewed changes"],
    }


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


def _case_label(item: dict[str, Any]) -> str:
    case_id = str(item.get("case_id", "unknown"))
    location = _source_location(item)
    cluster = str(item.get("cluster") or "")
    details = [value for value in (location, cluster) if value]
    if not details:
        return case_id
    return f"{case_id} [{', '.join(details)}]"


def _source_location(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "")
    source_line = item.get("source_line")
    if source and source_line is not None:
        return f"{source}:{source_line}"
    if source_line is not None:
        return f"line {source_line}"
    if source:
        return source
    return ""


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


def _content_reason(baseline_text: str | None, candidate_text: str | None) -> str | None:
    if baseline_text is None or candidate_text is None:
        return None
    baseline = " ".join(baseline_text.split())
    candidate = " ".join(candidate_text.split())
    if baseline == candidate or not baseline or not candidate:
        return None

    baseline_tokens = baseline.lower().split()
    candidate_tokens = candidate.lower().split()
    if len(baseline_tokens) <= 3 and len(candidate_tokens) <= 3:
        return "short answer changed"

    ratio = SequenceMatcher(None, baseline.lower(), candidate.lower()).ratio()
    if ratio < 0.85:
        return f"content changed substantially: similarity {ratio:.2f}"
    return None


def _summary_count(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else 0


def _preview(text: str, limit: int = 84) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."
