from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .features import behavior_signature, extract_features
from .io import LogRecord


def build_suite(
    records: list[LogRecord],
    *,
    source: str | Path,
    input_field: str,
    output_field: str,
    max_cases: int = 42,
) -> dict[str, Any]:
    if max_cases < 1:
        raise ValueError("max_cases must be at least 1")

    grouped: dict[str, list[LogRecord]] = defaultdict(list)
    for record in records:
        grouped[behavior_signature(record.prompt, record.response)].append(record)

    selected = _select_representatives(grouped, max_cases)
    cases = []
    for index, record in enumerate(selected, 1):
        signature = behavior_signature(record.prompt, record.response)
        features = extract_features(record.response)
        cases.append(
            {
                "id": _case_id(record, index),
                "source_line": record.line_number,
                "cluster": signature,
                "prompt": record.prompt,
                "baseline_response": record.response,
                "features": features.to_dict(),
            }
        )

    clusters = []
    for signature, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        lengths = [len(record.response.split()) for record in group]
        clusters.append(
            {
                "signature": signature,
                "size": len(group),
                "word_count_min": min(lengths),
                "word_count_max": max(lengths),
                "high_variance": _is_high_variance(lengths),
            }
        )

    return {
        "version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "input_field": input_field,
        "output_field": output_field,
        "summary": {
            "records_seen": len(records),
            "clusters": len(grouped),
            "cases": len(cases),
            "max_cases": max_cases,
        },
        "clusters": clusters,
        "cases": cases,
    }


def _select_representatives(
    grouped: dict[str, list[LogRecord]],
    max_cases: int,
) -> list[LogRecord]:
    selected: list[LogRecord] = []
    selected_keys: set[tuple[str, int]] = set()

    groups = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    for signature, group in groups:
        record = _median_length_record(group)
        selected.append(record)
        selected_keys.add((signature, record.line_number))
        if len(selected) >= max_cases:
            return selected

    # Add useful edge representatives from high-variance clusters if budget remains.
    for signature, group in groups:
        if len(selected) >= max_cases:
            break
        lengths = [len(record.response.split()) for record in group]
        if not _is_high_variance(lengths):
            continue
        for record in _edge_records(group):
            key = (signature, record.line_number)
            if key in selected_keys:
                continue
            selected.append(record)
            selected_keys.add(key)
            if len(selected) >= max_cases:
                break

    return selected


def _median_length_record(group: list[LogRecord]) -> LogRecord:
    ranked = sorted(group, key=lambda record: len(record.response.split()))
    return ranked[len(ranked) // 2]


def _edge_records(group: list[LogRecord]) -> list[LogRecord]:
    ranked = sorted(group, key=lambda record: len(record.response.split()))
    if len(ranked) <= 1:
        return ranked
    return [ranked[0], ranked[-1]]


def _is_high_variance(lengths: list[int]) -> bool:
    if len(lengths) < 3:
        return False
    minimum = max(1, min(lengths))
    maximum = max(lengths)
    return maximum / minimum >= 3


def _case_id(record: LogRecord, index: int) -> str:
    digest = hashlib.sha256()
    digest.update(record.prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(record.response.encode("utf-8"))
    return f"case_{index:03d}_{digest.hexdigest()[:10]}"
