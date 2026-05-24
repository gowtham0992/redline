from __future__ import annotations

import hashlib
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


def build_suite(
    records: list[LogRecord],
    *,
    source: str | Path,
    input_field: str,
    output_field: str,
    max_cases: int = 42,
    all_cases: bool = False,
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
    cases = []
    for index, (record, selection_reason) in enumerate(selected, 1):
        signature = signatures[id(record)]
        cluster_info = cluster_infos[signature]
        features = _record_features(record, feature_cache)
        cases.append(
            {
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
        "summary": {
            "records_seen": len(records),
            "unique_prompt_response_pairs": len(unique_records),
            "duplicate_prompt_response_pairs": len(records) - len(unique_records),
            "clusters": len(grouped),
            "cases": len(cases),
            "max_cases": len(unique_records) if all_cases else max_cases,
            "selection": "all" if all_cases else "representative",
            "high_risk_clusters": _risk_count(cluster_infos, "high"),
            "medium_risk_clusters": _risk_count(cluster_infos, "medium"),
            "high_variance_clusters": sum(1 for info in cluster_infos.values() if info["high_variance"]),
            "failure_pattern_clusters": sum(1 for info in cluster_infos.values() if info["failure_patterns"]),
        },
        "clusters": clusters,
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


def _case_id(record: LogRecord, index: int) -> str:
    digest = hashlib.sha256()
    digest.update(record.prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(record.response.encode("utf-8"))
    return f"case_{index:03d}_{digest.hexdigest()[:10]}"
