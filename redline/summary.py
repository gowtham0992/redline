from __future__ import annotations

from collections import Counter
from typing import Any


def suite_summary(suite: dict[str, Any]) -> dict[str, Any]:
    clusters = suite.get("clusters", [])
    if not isinstance(clusters, list):
        clusters = []
    judgments = suite.get("judgments", {})
    if not isinstance(judgments, dict):
        judgments = {}
    requirements = suite.get("requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}

    judgment_counts: Counter[str] = Counter()
    for value in judgments.values():
        if isinstance(value, dict):
            judgment_counts[str(value.get("status", "unknown"))] += 1

    high_variance = [
        cluster
        for cluster in clusters
        if isinstance(cluster, dict) and bool(cluster.get("high_variance"))
    ]
    failure_patterns = [
        cluster
        for cluster in clusters
        if isinstance(cluster, dict) and bool(cluster.get("failure_patterns"))
    ]
    top_clusters = [
        {
            "signature": str(cluster.get("signature", "")),
            "size": int(cluster.get("size", 0)),
            "high_variance": bool(cluster.get("high_variance")),
            "failure_patterns": list(cluster.get("failure_patterns") or []),
        }
        for cluster in clusters[:5]
        if isinstance(cluster, dict)
    ]

    summary = suite.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    cases = suite.get("cases", [])
    if not isinstance(cases, list):
        cases = []

    return {
        "source": str(suite.get("source") or ""),
        "created_at": str(suite.get("created_at") or ""),
        "selection": str(summary.get("selection") or ""),
        "records_seen": int(summary.get("records_seen", 0)),
        "unique_prompt_response_pairs": int(summary.get("unique_prompt_response_pairs", summary.get("records_seen", 0))),
        "duplicate_prompt_response_pairs": int(summary.get("duplicate_prompt_response_pairs", 0)),
        "clusters": int(summary.get("clusters", len(clusters))),
        "cases": int(summary.get("cases", len(cases))),
        "max_cases": int(summary.get("max_cases", 0)),
        "pinned_cases": int(
            summary.get(
                "pinned_cases",
                len([case for case in cases if isinstance(case, dict) and case.get("pinned")]),
            )
        ),
        "high_variance_clusters": len(high_variance),
        "failure_pattern_clusters": len(failure_patterns),
        "judgments": dict(sorted(judgment_counts.items())),
        "requirements": len(requirements),
        "top_clusters": top_clusters,
    }


def format_suite_summary(suite: dict[str, Any]) -> str:
    summary = suite_summary(suite)
    lines = [
        "redline summary",
        "",
        f"Source:                 {summary['source'] or '<unknown>'}",
        f"Created:                {summary['created_at'] or '<unknown>'}",
        f"Selection:              {summary['selection'] or '<unknown>'}",
        f"Records seen:           {summary['records_seen']}",
        f"Unique pairs:           {summary['unique_prompt_response_pairs']}",
        f"Duplicate pairs:        {summary['duplicate_prompt_response_pairs']}",
        f"Behavioral clusters:    {summary['clusters']}",
        f"Representative cases:   {summary['cases']}",
        f"Pinned cases:           {summary['pinned_cases']}",
        f"Max cases:              {summary['max_cases']}",
        f"High-variance clusters: {summary['high_variance_clusters']}",
        f"Failure-pattern clusters: {summary['failure_pattern_clusters']:>2}",
        f"Cases with requirements: {summary['requirements']:>2}",
        "",
    ]

    judgments = summary["judgments"]
    if judgments:
        lines.append("Judgments:")
        for status, count in judgments.items():
            lines.append(f"  {status:<10} {count}")
        lines.append("")

    top_clusters = summary["top_clusters"]
    if top_clusters:
        lines.append("Top clusters:")
        for cluster in top_clusters:
            marker = " high-variance" if cluster["high_variance"] else ""
            flags = cluster["failure_patterns"]
            if flags:
                marker = f"{marker} flags={','.join(str(flag) for flag in flags)}"
            lines.append(f"  {cluster['size']:>4}  {cluster['signature']}{marker}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
