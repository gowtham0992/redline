from __future__ import annotations

import hashlib
from fnmatch import fnmatchcase
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .features import TextFeatures, extract_features, input_intent
from .hashes import prompt_response_hash
from .io import LogRecord


FeatureCache = dict[int, TextFeatures]
ClusterInfo = dict[str, Any]
SUITE_SCHEMA_URL = "https://raw.githubusercontent.com/gowtham0992/redline/main/redline-suite.schema.json"
PROMPT_DIVERSITY_EDGE_TARGET = 8
SELECTION_METHODOLOGY_VERSION = "behavior-signature-v1"
EXCLUDED_CASE_PREVIEW_LIMIT = 50
SELECTION_METHODOLOGY = {
    "name": "deterministic behavior-signature grouping",
    "version": SELECTION_METHODOLOGY_VERSION,
    "trust_scope": "structural checks only; review factual, tone, hallucination, policy, and reasoning risks separately",
    "case_selection": [
        "one representative per behavior-signature group",
        "high-risk groups first when case budget is tight",
        "high-variance edge cases when budget remains",
        "prompt-diverse samples from large groups when budget remains",
    ],
}


def _ratio(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return part / total


def build_suite(
    records: list[LogRecord],
    *,
    source: str | Path,
    input_field: str,
    output_field: str,
    max_cases: int = 42,
    all_cases: bool = False,
    owner: str | None = None,
    owner_rules: object = None,
) -> dict[str, Any]:
    if max_cases < 1:
        raise ValueError("max_cases must be at least 1")

    unique_records = _unique_prompt_response_records(records)
    feature_cache: FeatureCache = {}
    signatures: dict[int, str] = {}
    grouped: dict[str, list[LogRecord]] = defaultdict(list)
    for record in unique_records:
        features = _record_features(record, feature_cache)
        signature = _behavior_signature(record.prompt, features)
        signatures[id(record)] = signature
        grouped[signature].append(record)

    cluster_infos = _cluster_infos(grouped, feature_cache)
    selected = (
        [(record, "all_cases") for record in unique_records]
        if all_cases
        else _select_representatives(grouped, max_cases, feature_cache, cluster_infos)
    )
    selected_record_ids = {id(record) for record, _ in selected}
    selected_clusters = {signatures[id(record)] for record, _ in selected}
    non_ascii_records = sum(1 for record in unique_records if _has_non_ascii(record.prompt) or _has_non_ascii(record.response))
    stochastic_prompt_groups = _stochastic_prompt_groups(unique_records)
    cases = []
    selected_case_by_cluster: dict[str, str] = {}
    for index, (record, selection_reason) in enumerate(selected, 1):
        signature = signatures[id(record)]
        cluster_info = cluster_infos[signature]
        features = _record_features(record, feature_cache)
        case = {
            "id": _case_id(record, index),
            "source_line": record.line_number,
            "cluster": signature,
            "cluster_risk": cluster_info["risk"],
            "selection_reason": selection_reason,
            "prompt": record.prompt,
            "baseline_response": record.response,
            "content_hash": prompt_response_hash(record.prompt, record.response),
            "features": features.to_dict(),
        }
        owner_match = _case_owner_match(
            record,
            source=str(source),
            cluster=signature,
            explicit_owner=owner,
            owner_rules=owner_rules,
        )
        if owner_match.get("owner"):
            case["owner"] = owner_match["owner"]
        if owner_match.get("owner_rule"):
            case["owner_rule"] = owner_match["owner_rule"]
        cases.append(case)
        selected_case_by_cluster.setdefault(signature, str(case["id"]))

    excluded_cases = _excluded_case_previews(
        unique_records,
        selected_record_ids=selected_record_ids,
        signatures=signatures,
        selected_case_by_cluster=selected_case_by_cluster,
        cluster_infos=cluster_infos,
        feature_cache=feature_cache,
    )

    clusters = []
    for signature, info in sorted(cluster_infos.items(), key=_cluster_info_rank):
        clusters.append(
            {
                "signature": signature,
                "size": info["size"],
                "word_count_min": info["word_count_min"],
                "word_count_max": info["word_count_max"],
                "high_variance": info["high_variance"],
                "failure_patterns": info["failure_patterns"],
                "risk": info["risk"],
            }
        )

    return {
        "$schema": SUITE_SCHEMA_URL,
        "version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "input_field": input_field,
        "output_field": output_field,
        "methodology": dict(SELECTION_METHODOLOGY),
        "summary": {
            "records_seen": len(records),
            "unique_prompt_response_pairs": len(unique_records),
            "duplicate_prompt_response_pairs": len(records) - len(unique_records),
            "clusters": len(grouped),
            "cases": len(cases),
            "excluded_prompt_response_pairs": len(unique_records) - len(cases),
            "excluded_case_previews": len(excluded_cases),
            "case_coverage": _ratio(len(cases), len(unique_records)),
            "cluster_coverage": _ratio(len(selected_clusters), len(grouped)),
            "max_cases": len(unique_records) if all_cases else max_cases,
            "selection": "all" if all_cases else "representative",
            "high_risk_clusters": _risk_count(cluster_infos, "high"),
            "medium_risk_clusters": _risk_count(cluster_infos, "medium"),
            "high_variance_clusters": sum(1 for info in cluster_infos.values() if info["high_variance"]),
            "failure_pattern_clusters": sum(1 for info in cluster_infos.values() if info["failure_patterns"]),
            "prompt_diversity_cases": sum(1 for _, reason in selected if reason == "prompt_diversity_edge"),
            "non_ascii_records": non_ascii_records,
            "stochastic_prompt_groups": stochastic_prompt_groups,
            "owned_cases": _owned_case_count(cases),
        },
        "clusters": clusters,
        "excluded_cases": excluded_cases,
        "cases": cases,
    }


def add_suite_case(
    suite: dict[str, Any],
    *,
    prompt: str,
    baseline_response: str,
    source: str = "manual",
    source_line: int | None = None,
    case_id: str | None = None,
    note: str = "",
    allow_duplicate: bool = False,
    owner: str | None = None,
) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt must not be empty")
    if not baseline_response.strip():
        raise ValueError("response must not be empty")

    cases = suite.setdefault("cases", [])
    if not isinstance(cases, list):
        raise ValueError("suite cases must be a JSON array")

    existing_ids = {
        str(case.get("id"))
        for case in cases
        if isinstance(case, dict) and case.get("id")
    }
    index = len(cases) + 1
    record = LogRecord(source_line or 0, prompt, baseline_response, {})
    new_id = case_id.strip() if case_id else _case_id(record, index)
    if not new_id:
        raise ValueError("case id must not be empty")
    if new_id in existing_ids:
        raise ValueError(f"case id already exists: {new_id}")

    content_hash = prompt_response_hash(prompt, baseline_response)
    duplicate_id = _duplicate_case_id(cases, prompt, baseline_response, content_hash)
    if duplicate_id and not allow_duplicate:
        raise ValueError(
            f"duplicate prompt-response pair already covered by {duplicate_id}; "
            "pass --allow-duplicate to pin it anyway"
        )

    features = extract_features(baseline_response)
    signature = _behavior_signature(prompt, features)
    case: dict[str, Any] = {
        "id": new_id,
        "source": source,
        "source_line": source_line,
        "cluster": signature,
        "cluster_risk": "low",
        "selection_reason": "manual_pin",
        "prompt": prompt,
        "baseline_response": baseline_response,
        "content_hash": content_hash,
        "features": features.to_dict(),
        "pinned": True,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    if note.strip():
        case["note"] = note.strip()
    if owner and owner.strip():
        case["owner"] = owner.strip()
    cases.append(case)
    _upsert_manual_cluster(suite, signature, baseline_response)
    _refresh_summary(suite, len(cases))
    return case


def _select_representatives(
    grouped: dict[str, list[LogRecord]],
    max_cases: int,
    feature_cache: FeatureCache,
    cluster_infos: dict[str, ClusterInfo],
) -> list[tuple[LogRecord, str]]:
    selected: list[tuple[LogRecord, str]] = []
    selected_ids: set[int] = set()

    groups = sorted(grouped.items(), key=lambda item: _group_rank(item, cluster_infos))
    for signature, group in groups:
        record = _median_length_record(group)
        selected.append((record, "cluster_representative"))
        selected_ids.add(id(record))
        if len(selected) >= max_cases:
            return selected

    # Add useful edge representatives from high-variance clusters if budget remains.
    for signature, group in groups:
        if len(selected) >= max_cases:
            break
        lengths = [len(record.response.split()) for record in group]
        if not _is_high_variance(lengths):
            continue
        for record, reason in _edge_records(group):
            if id(record) in selected_ids:
                continue
            selected.append((record, reason))
            selected_ids.add(id(record))
            if len(selected) >= max_cases:
                break

    # Large same-shape clusters can still hide prompt-specific edge cases.
    # Add prompt-diverse representatives after structural/risk coverage.
    for signature, group in groups:
        if len(selected) >= max_cases:
            break
        if len(group) < 5:
            continue
        for record, reason in _prompt_diversity_records(group):
            if id(record) in selected_ids:
                continue
            selected.append((record, reason))
            selected_ids.add(id(record))
            if len(selected) >= max_cases:
                break

    return selected


def _unique_prompt_response_records(records: list[LogRecord]) -> list[LogRecord]:
    unique = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record.prompt, record.response)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _stochastic_prompt_groups(records: list[LogRecord]) -> int:
    responses_by_prompt: dict[str, set[str]] = defaultdict(set)
    for record in records:
        responses_by_prompt[record.prompt].add(record.response)
    return sum(1 for responses in responses_by_prompt.values() if len(responses) > 1)


def _has_non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


def _duplicate_case_id(
    cases: list[Any],
    prompt: str,
    baseline_response: str,
    content_hash: str,
) -> str | None:
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            continue
        if case.get("content_hash") == content_hash:
            return case_id
        if case.get("prompt") == prompt and case.get("baseline_response") == baseline_response:
            return case_id
    return None


def _cluster_infos(
    grouped: dict[str, list[LogRecord]],
    feature_cache: FeatureCache,
) -> dict[str, ClusterInfo]:
    infos: dict[str, ClusterInfo] = {}
    for signature, group in grouped.items():
        lengths = [len(record.response.split()) for record in group]
        high_variance = _is_high_variance(lengths)
        failure_patterns = _failure_patterns(signature, group, high_variance, feature_cache)
        infos[signature] = {
            "size": len(group),
            "word_count_min": min(lengths),
            "word_count_max": max(lengths),
            "high_variance": high_variance,
            "failure_patterns": failure_patterns,
            "risk": _cluster_risk(failure_patterns),
        }
    return infos


def _median_length_record(group: list[LogRecord]) -> LogRecord:
    ranked = sorted(group, key=lambda record: len(record.response.split()))
    return ranked[len(ranked) // 2]


def _group_rank(
    item: tuple[str, list[LogRecord]],
    cluster_infos: dict[str, ClusterInfo],
) -> tuple[int, int, str]:
    signature, group = item
    info = cluster_infos[signature]
    risk_rank = {"high": 0, "medium": 1, "low": 2}[str(info["risk"])]
    return risk_rank, -len(group), signature


def _cluster_info_rank(item: tuple[str, ClusterInfo]) -> tuple[int, int, str]:
    signature, info = item
    risk_rank = {"high": 0, "medium": 1, "low": 2}[str(info["risk"])]
    return risk_rank, -int(info["size"]), signature


def _risk_count(infos: dict[str, ClusterInfo], risk: str) -> int:
    return sum(1 for info in infos.values() if info["risk"] == risk)


def _edge_records(group: list[LogRecord]) -> list[tuple[LogRecord, str]]:
    ranked = sorted(group, key=lambda record: len(record.response.split()))
    if len(ranked) <= 1:
        return [(ranked[0], "high_variance_edge")]
    return [
        (ranked[0], "high_variance_short_edge"),
        (ranked[-1], "high_variance_long_edge"),
    ]


def _prompt_diversity_records(group: list[LogRecord]) -> list[tuple[LogRecord, str]]:
    ranked = sorted(group, key=lambda record: (len(record.prompt), record.prompt, record.line_number))
    if len(ranked) <= 1:
        return [(ranked[0], "prompt_diversity_edge")]
    limit = min(PROMPT_DIVERSITY_EDGE_TARGET, len(ranked))
    return [(ranked[index], "prompt_diversity_edge") for index in _spread_indexes(len(ranked), limit)]


def _spread_indexes(size: int, count: int) -> list[int]:
    if size <= 0 or count <= 0:
        return []
    if count == 1:
        return [size // 2]
    indexes = []
    for step in range(count):
        indexes.append(round(step * (size - 1) / (count - 1)))
    return list(dict.fromkeys(indexes))


def _excluded_case_previews(
    records: list[LogRecord],
    *,
    selected_record_ids: set[int],
    signatures: dict[int, str],
    selected_case_by_cluster: dict[str, str],
    cluster_infos: dict[str, ClusterInfo],
    feature_cache: FeatureCache,
) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for record in records:
        if id(record) in selected_record_ids:
            continue
        signature = signatures[id(record)]
        info = cluster_infos[signature]
        represented_by = selected_case_by_cluster.get(signature, "")
        reason = (
            "similar behavior-signature group already represented"
            if represented_by
            else "case budget exhausted before this behavior-signature group was selected"
        )
        features = _record_features(record, feature_cache)
        previews.append(
            {
                "source_line": record.line_number,
                "cluster": signature,
                "cluster_risk": str(info["risk"]),
                "reason": reason,
                "represented_by": represented_by,
                "risk_flags": _record_risk_flags(features),
                "prompt_preview": _preview(record.prompt),
                "baseline_preview": _preview(record.response),
            }
        )
        if len(previews) >= EXCLUDED_CASE_PREVIEW_LIMIT:
            break
    return previews


def _record_risk_flags(features: TextFeatures) -> list[str]:
    flags = []
    if features.empty:
        flags.append("empty_response")
    if features.refusal:
        flags.append("refusal_response")
    return flags


def _preview(value: str, limit: int = 96) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _is_high_variance(lengths: list[int]) -> bool:
    if len(lengths) < 3:
        return False
    minimum = max(1, min(lengths))
    maximum = max(lengths)
    return maximum / minimum >= 3


def _failure_patterns(
    signature: str,
    group: list[LogRecord],
    high_variance: bool,
    feature_cache: FeatureCache,
) -> list[str]:
    features = [_record_features(record, feature_cache) for record in group]
    patterns = []
    intent = signature.split("|", 1)[0]

    if any(item.empty for item in features):
        patterns.append("empty_response")
    if any(item.refusal for item in features):
        patterns.append("refusal_response")
    if intent == "structured_json" and any(not item.valid_json for item in features):
        patterns.append("invalid_json_for_json_prompt")
    if intent == "structured_table" and any(not item.has_markdown_table for item in features):
        patterns.append("missing_table_for_table_prompt")
    if high_variance:
        patterns.append("high_length_variance")

    return patterns


def _record_features(record: LogRecord, feature_cache: FeatureCache) -> TextFeatures:
    key = id(record)
    if key not in feature_cache:
        feature_cache[key] = extract_features(record.response)
    return feature_cache[key]


def _behavior_signature(prompt: str, features: TextFeatures) -> str:
    parts = [
        input_intent(prompt),
        features.shape,
        features.length_bucket,
    ]
    if features.valid_json and features.json_type:
        parts.append(f"json:{features.json_type}:{','.join(features.json_keys[:8])}")
    return "|".join(parts)


def _cluster_risk(failure_patterns: list[str]) -> str:
    high_risk = {
        "empty_response",
        "refusal_response",
        "invalid_json_for_json_prompt",
        "missing_table_for_table_prompt",
    }
    if any(pattern in high_risk for pattern in failure_patterns):
        return "high"
    if "high_length_variance" in failure_patterns:
        return "medium"
    return "low"


def _upsert_manual_cluster(suite: dict[str, Any], signature: str, response: str) -> None:
    clusters = suite.setdefault("clusters", [])
    if not isinstance(clusters, list):
        suite["clusters"] = []
        clusters = suite["clusters"]

    word_count = len(response.split())
    for cluster in clusters:
        if not isinstance(cluster, dict) or cluster.get("signature") != signature:
            continue
        size = int(cluster.get("size", 0))
        cluster["size"] = size + 1
        minimum = cluster.get("word_count_min")
        maximum = cluster.get("word_count_max")
        if isinstance(minimum, int):
            cluster["word_count_min"] = min(minimum, word_count)
        else:
            cluster["word_count_min"] = word_count
        if isinstance(maximum, int):
            cluster["word_count_max"] = max(maximum, word_count)
        else:
            cluster["word_count_max"] = word_count
        return

    clusters.append(
        {
            "signature": signature,
            "size": 1,
            "word_count_min": word_count,
            "word_count_max": word_count,
            "high_variance": False,
            "failure_patterns": [],
            "risk": "low",
            "manual": True,
        }
    )


def _refresh_summary(suite: dict[str, Any], case_count: int) -> None:
    summary = suite.setdefault("summary", {})
    if not isinstance(summary, dict):
        summary = {}
        suite["summary"] = summary
    clusters = suite.get("clusters")
    cases = suite.get("cases")
    summary["cases"] = case_count
    summary["clusters"] = len(clusters) if isinstance(clusters, list) else 0
    if isinstance(cases, list):
        summary["pinned_cases"] = sum(
            1
            for case in cases
            if isinstance(case, dict) and bool(case.get("pinned"))
        )
        summary["owned_cases"] = _owned_case_count(cases)


def _case_id(record: LogRecord, index: int) -> str:
    digest = hashlib.sha256()
    digest.update(record.prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(record.response.encode("utf-8"))
    return f"case_{index:03d}_{digest.hexdigest()[:10]}"


def _case_owner_match(
    record: LogRecord,
    *,
    source: str,
    cluster: str,
    explicit_owner: str | None,
    owner_rules: object,
) -> dict[str, Any]:
    if explicit_owner and explicit_owner.strip():
        return {"owner": explicit_owner.strip()}
    if isinstance(owner_rules, str):
        owner = owner_rules.strip()
        if owner:
            return {"owner": owner, "owner_rule": {"source": "config"}}
        return {}
    for rule in _owner_rule_items(owner_rules):
        owner = rule["owner"]
        pattern = rule["match"]
        field = rule["field"]
        target = {
            "prompt": record.prompt,
            "source": source,
            "cluster": cluster,
            "any": "\n".join([record.prompt, source, cluster]),
        }.get(field, "\n".join([record.prompt, source, cluster]))
        if _owner_pattern_matches(pattern, target):
            return {
                "owner": owner,
                "owner_rule": {
                    "match": pattern,
                    "field": field,
                },
            }
    return {}


def _owner_rule_items(owner_rules: object) -> list[dict[str, str]]:
    if isinstance(owner_rules, dict):
        return [
            {"match": str(pattern), "owner": str(owner), "field": "any"}
            for pattern, owner in owner_rules.items()
            if str(pattern).strip() and str(owner).strip()
        ]
    if not isinstance(owner_rules, list):
        return []
    rows = []
    for item in owner_rules:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("match") or "").strip()
        owner = str(item.get("owner") or "").strip()
        field = str(item.get("field") or "any").strip().lower()
        if pattern and owner:
            rows.append({"match": pattern, "owner": owner, "field": field})
    return rows


def _owner_pattern_matches(pattern: str, target: str) -> bool:
    normalized_pattern = pattern.lower()
    normalized_target = target.lower()
    return (
        fnmatchcase(normalized_target, normalized_pattern)
        or normalized_pattern in normalized_target
    )


def _owned_case_count(cases: list[Any]) -> int:
    return sum(
        1
        for case in cases
        if isinstance(case, dict) and str(case.get("owner") or "").strip()
    )
