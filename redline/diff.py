from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any

from .features import extract_features
from .io import LogRecord
from .requirements import case_requirements, requirement_reasons


DIFF_PROFILES = ("strict", "review")
REPORT_SCHEMA_URL = "https://raw.githubusercontent.com/gowtham0992/redline/main/redline-report.schema.json"
TRUST_SCOPE = (
    "structural checks only; review factual correctness, tone, hallucinations, "
    "and subtle reasoning separately"
)
_POSITIVE_POLICY_RE = re.compile(
    r"\b(?:"
    r"allow(?:ed|s)?|"
    r"approv(?:e|ed|es)|"
    r"accept(?:ed|s)?|"
    r"permit(?:ted|s)?|"
    r"eligible|"
    r"(?:can|may)\s+(?:be\s+)?(?:refund(?:ed)?|return(?:ed)?|approve(?:d)?|"
    r"accept(?:ed)?|allow(?:ed)?|proceed|use|access|delete|update|retry|reset|rotate|share)|"
    r"should\s+(?:approve|accept|allow|proceed|refund|use|retry|reset|rotate|share)"
    r")\b",
    re.IGNORECASE,
)
_NEGATIVE_POLICY_RE = re.compile(
    r"\b(?:"
    r"not\s+(?:allowed|eligible|permitted|approved|accepted)|"
    r"(?:cannot|can't|can not|may not|should not|must not)\s+(?:be\s+)?\w+|"
    r"never\s+(?:approve|accept|allow|proceed|refund|use|retry|reset|rotate|share)|"
    r"den(?:y|ied|ies)|"
    r"reject(?:ed|s)?|"
    r"refus(?:e|ed|es)"
    r")\b",
    re.IGNORECASE,
)
_POLICY_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "by",
    "can",
    "for",
    "if",
    "in",
    "is",
    "it",
    "may",
    "must",
    "not",
    "of",
    "or",
    "should",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
}
_HEDGE_RE = re.compile(
    r"\b(?:"
    r"appear(?:s|ed)?|"
    r"approximately|"
    r"around|"
    r"could|"
    r"i\s+(?:believe|think)|"
    r"likely|"
    r"may|"
    r"might|"
    r"possibly|"
    r"probably|"
    r"roughly|"
    r"seem(?:s|ed)?|"
    r"suggest(?:s|ed)?|"
    r"unlikely|"
    r"not\s+sure"
    r")\b",
    re.IGNORECASE,
)
_DEFINITIVE_RE = re.compile(
    r"\b(?:"
    r"always|"
    r"certainly|"
    r"definitely|"
    r"guarantee(?:d|s)?|"
    r"must|"
    r"never|"
    r"require(?:d|s)?|"
    r"will"
    r")\b",
    re.IGNORECASE,
)
_APOLOGETIC_TONE_RE = re.compile(
    r"\b(?:apolog(?:y|ize|ise|ies)|sorry|unfortunately|regret)\b",
    re.IGNORECASE,
)
_DISMISSIVE_TONE_RE = re.compile(
    r"\b(?:"
    r"as\s+i\s+already\s+said|"
    r"as\s+stated|"
    r"clearly\s+you|"
    r"just\s+read|"
    r"not\s+(?:our|my)\s+problem|"
    r"obviously|"
    r"you\s+(?:failed|should\s+have)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CaseDiff:
    case_id: str
    status: str
    source: str
    source_line: Any
    cluster: str
    owner: str
    owner_rule: dict[str, Any] | None
    prompt: str
    baseline_response: str
    candidate_response: str | None
    reasons: tuple[str, ...]
    confidence: str
    signal: str
    baseline_features: dict[str, Any]
    candidate_features: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "source": self.source,
            "source_line": self.source_line,
            "cluster": self.cluster,
            "owner": self.owner,
            "owner_rule": self.owner_rule,
            "prompt": self.prompt,
            "baseline_response": self.baseline_response,
            "candidate_response": self.candidate_response,
            "reasons": list(self.reasons),
            "confidence": self.confidence,
            "signal": self.signal,
            "baseline_features": self.baseline_features,
            "candidate_features": self.candidate_features,
        }


def compare_suite_to_candidate(
    suite: dict[str, Any],
    candidate_records: list[LogRecord],
    *,
    profile: str = "strict",
) -> dict[str, Any]:
    profile = _diff_profile(profile)
    candidate_case_index = _index_by_case_id(candidate_records)
    candidate_index = _index_by_prompt(candidate_records)
    judgments = suite.get("judgments", {})
    if not isinstance(judgments, dict):
        judgments = {}
    diffs: list[CaseDiff] = []
    suite_source = str(suite.get("source", ""))

    for case in suite.get("cases", []):
        case_id = str(case["id"])
        prompt = str(case["prompt"])
        baseline_response = str(case["baseline_response"])
        source_line = case.get("source_line")
        source = str(case.get("source") or suite_source)
        cluster = str(case.get("cluster", ""))
        owner = str(case.get("owner") or "")
        owner_rule = case.get("owner_rule") if isinstance(case.get("owner_rule"), dict) else None
        candidate = _pop_candidate_by_case_id(candidate_case_index, case_id)
        if candidate is None:
            candidate = _pop_candidate(candidate_index, prompt)
        if candidate is None:
            status, reasons = apply_judgment(
                "missing",
                ["candidate output missing for exact prompt"],
                _case_judgment(judgments, case_id),
            )
            confidence, signal = _case_confidence_signal(status, reasons)
            diffs.append(
                CaseDiff(
                    case_id=case_id,
                    status=status,
                    source=source,
                    source_line=source_line,
                    cluster=cluster,
                    owner=owner,
                    owner_rule=owner_rule,
                    prompt=prompt,
                    baseline_response=baseline_response,
                    candidate_response=None,
                    reasons=tuple(reasons),
                    confidence=confidence,
                    signal=signal,
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
            profile=profile,
        )
        if requirement_failures:
            status = "regression"
            reasons = requirement_failures + reasons
        status, reasons = apply_judgment(status, reasons, _case_judgment(judgments, case_id))
        confidence, signal = _case_confidence_signal(status, reasons)
        diffs.append(
            CaseDiff(
                case_id=case_id,
                status=status,
                source=source,
                source_line=source_line,
                cluster=cluster,
                owner=owner,
                owner_rule=owner_rule,
                prompt=prompt,
                baseline_response=baseline_response,
                candidate_response=candidate.response,
                reasons=tuple(reasons),
                confidence=confidence,
                signal=signal,
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
    decision = summarize_result_decision(summary, [diff.to_dict() for diff in diffs])
    return {
        "$schema": REPORT_SCHEMA_URL,
        "version": "0.1",
        "profile": profile,
        "summary": summary,
        "decision": decision,
        "diffs": [diff.to_dict() for diff in diffs],
    }


def classify_change(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    baseline_text: str | None = None,
    candidate_text: str | None = None,
    profile: str = "strict",
) -> tuple[str, list[str]]:
    profile = _diff_profile(profile)
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

    lost_numbers = _missing_values(baseline.get("numbers"), candidate.get("numbers"))
    if lost_numbers:
        _append_loss_reason(
            profile,
            regression_reasons,
            reasons,
            f"candidate missing numbers: {', '.join(lost_numbers[:8])}",
        )

    lost_urls = _missing_values(baseline.get("urls"), candidate.get("urls"))
    if lost_urls:
        regression_reasons.append(f"candidate missing URLs: {', '.join(lost_urls[:4])}")

    lost_entities = _missing_values(baseline.get("entities"), candidate.get("entities"))
    if lost_entities:
        _append_loss_reason(
            profile,
            regression_reasons,
            reasons,
            f"candidate missing entities: {', '.join(lost_entities[:8])}",
        )

    length_reason = _length_reason(baseline["words"], candidate["words"])
    if length_reason:
        reasons.append(length_reason)

    if baseline["shape"] != candidate["shape"]:
        reasons.append(f"shape changed: {baseline['shape']} -> {candidate['shape']}")

    if baseline["shape"] == candidate["shape"]:
        polarity_reason = _policy_polarity_reason(baseline_text, candidate_text)
        if polarity_reason:
            reasons.append(polarity_reason)
        confidence_reason = _confidence_drift_reason(baseline_text, candidate_text)
        if confidence_reason:
            reasons.append(confidence_reason)
        tone_reason = _tone_shift_reason(baseline_text, candidate_text)
        if tone_reason:
            reasons.append(tone_reason)
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


def _append_loss_reason(
    profile: str,
    regression_reasons: list[str],
    reasons: list[str],
    reason: str,
) -> None:
    if profile == "review":
        reasons.append(reason)
    else:
        regression_reasons.append(reason)


def _missing_values(baseline_values: object, candidate_values: object) -> list[str]:
    baseline_items = _string_sequence(baseline_values)
    candidate_items = set(_string_sequence(candidate_values))
    missing: list[str] = []
    seen: set[str] = set()
    for value in baseline_items:
        if value in candidate_items or value in seen:
            continue
        missing.append(value)
        seen.add(value)
    return missing


def _string_sequence(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value]


def _diff_profile(value: str) -> str:
    if value not in DIFF_PROFILES:
        joined = ", ".join(DIFF_PROFILES)
        raise ValueError(f"diff profile must be one of: {joined}")
    return value


def _confidence_drift_reason(
    baseline_text: str | None,
    candidate_text: str | None,
) -> str | None:
    if not baseline_text or not candidate_text:
        return None
    baseline_hedges = _marker_count(_HEDGE_RE, baseline_text)
    candidate_hedges = _marker_count(_HEDGE_RE, candidate_text)
    baseline_definitive = _marker_count(_DEFINITIVE_RE, baseline_text)
    candidate_definitive = _marker_count(_DEFINITIVE_RE, candidate_text)
    if candidate_hedges >= baseline_hedges + 2 and baseline_definitive > candidate_definitive:
        return (
            "confidence wording changed: candidate hedges more "
            f"({baseline_hedges} -> {candidate_hedges} hedge markers)"
        )
    if candidate_definitive >= baseline_definitive + 2 and baseline_hedges > candidate_hedges:
        return (
            "confidence wording changed: candidate is more definitive "
            f"({baseline_definitive} -> {candidate_definitive} definitive markers)"
        )
    return None


def _tone_shift_reason(
    baseline_text: str | None,
    candidate_text: str | None,
) -> str | None:
    if not baseline_text or not candidate_text:
        return None
    baseline_dismissive = _marker_count(_DISMISSIVE_TONE_RE, baseline_text)
    candidate_dismissive = _marker_count(_DISMISSIVE_TONE_RE, candidate_text)
    if candidate_dismissive > baseline_dismissive:
        return (
            "tone changed: candidate uses more dismissive wording "
            f"({baseline_dismissive} -> {candidate_dismissive} markers)"
        )

    baseline_apologetic = _marker_count(_APOLOGETIC_TONE_RE, baseline_text)
    candidate_apologetic = _marker_count(_APOLOGETIC_TONE_RE, candidate_text)
    if candidate_apologetic >= baseline_apologetic + 2:
        return (
            "tone changed: candidate is more apologetic "
            f"({baseline_apologetic} -> {candidate_apologetic} markers)"
        )
    return None


def _marker_count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text))


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


def _case_confidence_signal(status: str, reasons: list[str]) -> tuple[str, str]:
    if any(reason.startswith("judge ") for reason in reasons):
        return "medium", "judge"
    if any("suite judgment" in reason for reason in reasons):
        return "high", "human_judgment"
    if status == "neutral":
        return "medium", "none"
    if status == "missing":
        return "high", "structural"
    if any(_is_requirement_reason(reason) for reason in reasons):
        return "high" if status == "regression" else "medium", "requirement"
    if any(_is_structural_reason(reason) for reason in reasons):
        return "high" if status in {"regression", "improved"} else "medium", "structural"
    return "medium", "shallow_semantic"


def _is_requirement_reason(reason: str) -> bool:
    return reason.startswith("candidate missing required text:") or reason.startswith(
        "candidate includes forbidden text:"
    )


def _is_structural_reason(reason: str) -> bool:
    return reason.startswith(
        (
            "candidate became empty",
            "candidate is no longer empty",
            "candidate lost valid JSON format",
            "candidate gained valid JSON format",
            "candidate missing JSON keys:",
            "candidate added JSON keys:",
            "candidate newly refuses",
            "candidate no longer refuses",
            "candidate lost code block structure",
            "candidate lost bullet list structure",
            "candidate lost numbered list structure",
            "candidate lost markdown table structure",
            "candidate added code block structure",
            "candidate added bullet list structure",
            "candidate added numbered list structure",
            "candidate added markdown table structure",
            "candidate missing numbers:",
            "candidate missing URLs:",
            "candidate missing entities:",
            "shape changed:",
        )
    )


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
    profile = str(result.get("profile") or "")
    if profile:
        lines.append(f"Profile: {profile} ({_profile_description(profile)})")
        lines.append("")
    decision = result.get("decision")
    if isinstance(decision, dict):
        confidence = str(decision.get("confidence") or "").upper()
        action = str(decision.get("recommended_action") or "")
        if confidence and action:
            lines.append(f"Confidence: {confidence}  |  Recommended action: {action}")
            scope = str(decision.get("scope") or "")
            if scope:
                lines.append(f"Scope: {scope}")
            diagnosis = str(decision.get("diagnosis") or "")
            if diagnosis:
                lines.append(f"Diagnosis: {diagnosis}")
            lines.append("")

    warnings = _result_warnings(result)
    if warnings:
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    prompt_eval_lines = _prompt_eval_lines(result.get("prompt_evals"))
    if prompt_eval_lines:
        lines.append("PROMPT EVALS")
        lines.extend(prompt_eval_lines)
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


def format_compact_report(result: dict[str, Any], *, title: str = "redline diff") -> str:
    summary = result["summary"]
    lines = [
        (
            f"{title}: cases={summary['cases']} "
            f"regression={summary['regression']} changed={summary['changed']} "
            f"improved={summary['improved']} accepted={summary['accepted']} "
            f"ignored={summary['ignored']} missing={summary['missing']} "
            f"neutral={summary['neutral']}"
        )
    ]
    profile = str(result.get("profile") or "")
    if profile:
        lines.append(f"Profile: {profile} ({_profile_description(profile)})")
    decision = result.get("decision")
    if isinstance(decision, dict):
        confidence = str(decision.get("confidence") or "").upper()
        action = str(decision.get("recommended_action") or "")
        if confidence and action:
            lines.append(f"Confidence: {confidence} | {action}")
            scope = str(decision.get("scope") or "")
            if scope:
                lines.append(f"Scope: {scope}")
            diagnosis = str(decision.get("diagnosis") or "")
            if diagnosis:
                lines.append(f"Diagnosis: {diagnosis}")
    for warning in _result_warnings(result):
        lines.append(f"Warning: {warning}")

    prompt_eval_lines = _prompt_eval_lines(result.get("prompt_evals"))
    if prompt_eval_lines:
        lines.append("")
        lines.append("Prompt evals:")
        lines.extend(prompt_eval_lines)

    actionable = [
        item
        for item in result.get("diffs", [])
        if isinstance(item, dict) and item.get("status") != "neutral"
    ]
    if not actionable:
        lines.append("No structural blockers or reviewable cases.")
        return "\n".join(lines) + "\n"

    lines.append("")
    for item in actionable:
        status = str(item.get("status", "unknown")).upper()
        case_id = str(item.get("case_id", "unknown"))
        location = _source_location(item)
        location_text = f" [{location}]" if location else ""
        owner = str(item.get("owner") or "")
        owner_text = f" owner={owner}" if owner else ""
        confidence = str(item.get("confidence") or "")
        signal = str(item.get("signal") or "")
        trust_text = f" [{confidence}/{signal}]" if confidence and signal else ""
        reasons = item.get("reasons")
        reason = str(reasons[0]) if isinstance(reasons, list) and reasons else status.lower()
        prompt = _preview(str(item.get("prompt") or ""), limit=64)
        lines.append(
            f"{status:<10} {case_id}{location_text}{owner_text}{trust_text}: "
            f"{_preview(reason, 96)} | {prompt}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _prompt_eval_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        decision = item.get("decision")
        action = ""
        if isinstance(decision, dict):
            action = str(decision.get("recommended_action") or "")
        prompt = str(item.get("prompt") or "")
        prompt_context = f" [{prompt}]" if prompt else ""
        action_context = f" | {action}" if action else ""
        rows.append(
            f"{_prompt_eval_status(summary):<10} {str(item.get('id') or '-')}{prompt_context}: "
            f"{_summary_inline(summary)}{action_context}"
        )
    return rows


def _profile_description(profile: str) -> str:
    if profile == "review":
        return "detail/entity loss becomes reviewable changed signal"
    if profile == "strict":
        return "detail/entity loss is blocking"
    return "custom"


def _prompt_eval_status(summary: dict[str, Any]) -> str:
    if _summary_count(summary, "regression") or _summary_count(summary, "missing"):
        return "REGRESSION"
    if _summary_count(summary, "changed"):
        return "CHANGED"
    if _summary_count(summary, "improved"):
        return "IMPROVED"
    if _summary_count(summary, "accepted"):
        return "ACCEPTED"
    if _summary_count(summary, "ignored"):
        return "IGNORED"
    return "CLEAN"


def _summary_inline(summary: dict[str, Any]) -> str:
    keys = ("cases", "regression", "changed", "improved", "missing", "neutral")
    parts = [f"{key}={_summary_count(summary, key)}" for key in keys if key in summary]
    return " ".join(parts) if parts else "cases=0"


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
            "scope": TRUST_SCOPE,
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
            "scope": TRUST_SCOPE,
            "rationale": rationale,
        }
    if changed:
        return {
            "confidence": "medium",
            "recommended_action": "review changed cases before shipping",
            "scope": TRUST_SCOPE,
            "rationale": [f"{changed} changed case(s) need human review"],
        }
    if improved:
        return {
            "confidence": "medium",
            "recommended_action": "review improvements and semantic risks before shipping",
            "scope": TRUST_SCOPE,
            "rationale": [
                f"{improved} improved case(s), no structural blockers",
                "redline does not prove factual correctness, tone, hallucination safety, or reasoning quality",
            ],
        }
    return {
        "confidence": "medium",
        "recommended_action": "no structural blockers detected; review semantic risks before shipping",
        "scope": TRUST_SCOPE,
        "rationale": [
            "no regressions, missing outputs, or unreviewed changes detected by structural checks",
            "neutral does not prove identical meaning, factual correctness, tone, hallucination safety, or reasoning quality",
        ],
    }


def summarize_result_decision(summary: dict[str, Any], diffs: list[dict[str, Any]]) -> dict[str, Any]:
    decision = summarize_decision(summary)
    decision["diagnosis"] = _diagnosis(summary, diffs)
    return decision


def _diagnosis(summary: dict[str, Any], diffs: list[dict[str, Any]]) -> str:
    cases = _summary_count(summary, "cases")
    regression = _summary_count(summary, "regression")
    missing = _summary_count(summary, "missing")
    changed = _summary_count(summary, "changed")
    improved = _summary_count(summary, "improved")
    if cases == 0:
        return "No baseline cases are available yet; generate or add cases before relying on redline."

    reasons = _actionable_reasons(diffs)
    if regression or missing:
        fragments = _diagnosis_fragments(reasons, missing=bool(missing))
        if fragments:
            return f"Candidate {_join_fragments(fragments)}; fix blocking cases before shipping."
        return "Candidate introduced blocking behavioral regressions; fix blocking cases before shipping."
    if changed:
        fragments = _diagnosis_fragments(reasons, missing=False)
        if fragments:
            return f"Candidate {_join_fragments(fragments)}; review changed cases before shipping."
        return "Candidate changed behavior without structural blockers; review changed cases before shipping."
    if improved:
        return (
            "Candidate improved one or more structural checks; review the changes and semantic risks before "
            "shipping."
        )
    return (
        "No structural blockers were detected; still review factual correctness, tone, hallucinations, "
        "and reasoning separately."
    )


def _actionable_reasons(diffs: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for item in diffs:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"regression", "changed", "missing"}:
            continue
        raw_reasons = item.get("reasons")
        if not isinstance(raw_reasons, list):
            continue
        reasons.extend(str(reason) for reason in raw_reasons)
    return reasons


def _diagnosis_fragments(reasons: list[str], *, missing: bool) -> list[str]:
    fragments: list[str] = []
    if any("much shorter" in reason for reason in reasons):
        fragments.append("got shorter")
    if any(_is_structure_loss_reason(reason) for reason in reasons):
        fragments.append("lost required structure")
    if any(_is_detail_loss_reason(reason) for reason in reasons):
        fragments.append("dropped concrete details")
    if any("newly refuses" in reason for reason in reasons):
        fragments.append("started refusing prompts")
    if any("became empty" in reason for reason in reasons):
        fragments.append("returned empty outputs")
    if missing or any("output missing" in reason for reason in reasons):
        fragments.append("missed candidate outputs")
    if any(reason.startswith(("tone changed:", "confidence wording changed:")) for reason in reasons):
        fragments.append("changed tone or confidence wording")
    if any(reason.startswith("policy meaning changed:") for reason in reasons):
        fragments.append("changed policy meaning")
    if any(reason.startswith("content changed substantially:") for reason in reasons):
        fragments.append("changed content substantially")
    return fragments[:5]


def _is_structure_loss_reason(reason: str) -> bool:
    return reason.startswith(
        (
            "candidate lost valid JSON format",
            "candidate missing JSON keys:",
            "candidate lost code block structure",
            "candidate lost bullet list structure",
            "candidate lost numbered list structure",
            "candidate lost markdown table structure",
            "shape changed:",
        )
    )


def _is_detail_loss_reason(reason: str) -> bool:
    return reason.startswith(
        (
            "candidate missing required text:",
            "candidate missing numbers:",
            "candidate missing URLs:",
            "candidate missing entities:",
        )
    )


def _join_fragments(fragments: list[str]) -> str:
    if not fragments:
        return "changed behavior"
    if len(fragments) == 1:
        return fragments[0]
    if len(fragments) == 2:
        return f"{fragments[0]} and {fragments[1]}"
    return f"{', '.join(fragments[:-1])}, and {fragments[-1]}"


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
    owner = str(item.get("owner") or "")
    details = [value for value in (location, owner, cluster) if value]
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


def _result_warnings(result: dict[str, Any]) -> list[str]:
    warnings = result.get("warnings")
    if not isinstance(warnings, list):
        return []
    return [str(warning) for warning in warnings if str(warning).strip()]


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


def _policy_polarity_reason(baseline_text: str | None, candidate_text: str | None) -> str | None:
    if baseline_text is None or candidate_text is None:
        return None
    baseline = " ".join(baseline_text.lower().split())
    candidate = " ".join(candidate_text.lower().split())
    if not baseline or not candidate or baseline == candidate:
        return None

    baseline_polarity = _policy_polarity(baseline)
    candidate_polarity = _policy_polarity(candidate)
    if not baseline_polarity or not candidate_polarity or baseline_polarity == candidate_polarity:
        return None
    if not _shares_policy_subject(baseline, candidate):
        return None
    return "policy polarity changed: allow/approve wording differs from deny/reject wording"


def _policy_polarity(text: str) -> str | None:
    negative = bool(_NEGATIVE_POLICY_RE.search(text))
    without_negative = _NEGATIVE_POLICY_RE.sub(" ", text)
    positive = bool(_POSITIVE_POLICY_RE.search(without_negative))
    if positive == negative:
        return None
    return "positive" if positive else "negative"


def _shares_policy_subject(baseline: str, candidate: str) -> bool:
    baseline_tokens = _policy_subject_tokens(baseline)
    candidate_tokens = _policy_subject_tokens(candidate)
    if not baseline_tokens or not candidate_tokens:
        return False
    shared = baseline_tokens & candidate_tokens
    needed = 1 if min(len(baseline_tokens), len(candidate_tokens)) <= 4 else 2
    return len(shared) >= needed


def _policy_subject_tokens(text: str) -> set[str]:
    stripped = _POSITIVE_POLICY_RE.sub(" ", _NEGATIVE_POLICY_RE.sub(" ", text))
    return {
        token
        for token in re.findall(r"[a-z0-9]+", stripped)
        if len(token) > 2 and token not in _POLICY_TOKEN_STOPWORDS
    }


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
