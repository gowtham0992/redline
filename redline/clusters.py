from __future__ import annotations

from typing import Any


def cluster_report(suite: dict[str, Any]) -> dict[str, Any]:
    clusters = suite.get("clusters", [])
    if not isinstance(clusters, list):
        clusters = []

    summary = suite.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    rows = [
        _cluster_row(cluster)
        for cluster in clusters
        if isinstance(cluster, dict)
    ]
    high_variance = [cluster for cluster in rows if cluster["high_variance"]]
    failure_patterns = [cluster for cluster in rows if cluster["failure_patterns"]]
    return {
        "records_seen": int(summary.get("records_seen", 0)),
        "clusters": len(rows),
        "suggested_cases": int(summary.get("cases", 0)),
        "max_cases": int(summary.get("max_cases", 0)),
        "high_variance_clusters": len(high_variance),
        "failure_pattern_clusters": len(failure_patterns),
        "top_clusters": rows,
    }


def format_cluster_report(suite: dict[str, Any]) -> str:
    report = cluster_report(suite)
    lines = [
        "redline cluster",
        "",
        f"Identified {report['clusters']} behavioral clusters from {report['records_seen']} pairs.",
        f"High-variance clusters: {report['high_variance_clusters']}",
        f"Failure-pattern clusters: {report['failure_pattern_clusters']}",
        f"Suggested eval suite: {report['suggested_cases']} representative cases.",
        "",
    ]

    clusters = report["top_clusters"]
    if clusters:
        lines.append(f"{'SIZE':>4} {'WORDS':>11} {'VAR':>3}  {'FLAGS':<32} SIGNATURE")
        lines.append(f"{'-' * 4} {'-' * 11} {'-' * 3}  {'-' * 32} {'-' * 60}")
        for cluster in clusters:
            marker = "yes" if cluster["high_variance"] else ""
            word_range = f"{cluster['word_count_min']}-{cluster['word_count_max']}"
            flags = ", ".join(cluster["failure_patterns"])
            lines.append(
                f"{cluster['size']:>4} {word_range:>11} {marker:>3}  "
                f"{flags:<32} {cluster['signature']}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _cluster_row(cluster: dict[str, Any]) -> dict[str, Any]:
    return {
        "signature": str(cluster.get("signature", "")),
        "size": int(cluster.get("size", 0)),
        "word_count_min": int(cluster.get("word_count_min", 0)),
        "word_count_max": int(cluster.get("word_count_max", 0)),
        "high_variance": bool(cluster.get("high_variance")),
        "failure_patterns": _string_list(cluster.get("failure_patterns")),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
