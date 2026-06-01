from __future__ import annotations

from typing import Any

from .labels import behavior_label


def cluster_report(suite: dict[str, Any]) -> dict[str, Any]:
    clusters = suite.get("clusters", [])
    if not isinstance(clusters, list):
        clusters = []
    cases = suite.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    selected_cases = _selected_case_counts(cases)

    summary = suite.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    rows = [
        _cluster_row(cluster, selected_cases=selected_cases.get(str(cluster.get("signature", "")), 0))
        for cluster in clusters
        if isinstance(cluster, dict)
    ]
    high_variance = [cluster for cluster in rows if cluster["high_variance"]]
    failure_patterns = [cluster for cluster in rows if cluster["failure_patterns"]]
    high_risk = [cluster for cluster in rows if cluster["risk"] == "high"]
    return {
        "records_seen": int(summary.get("records_seen", 0)),
        "unique_prompt_response_pairs": int(summary.get("unique_prompt_response_pairs", summary.get("records_seen", 0))),
        "duplicate_prompt_response_pairs": int(summary.get("duplicate_prompt_response_pairs", 0)),
        "clusters": len(rows),
        "suggested_cases": int(summary.get("cases", 0)),
        "case_coverage": _ratio(int(summary.get("cases", 0)), int(summary.get("unique_prompt_response_pairs", 0))),
        "max_cases": int(summary.get("max_cases", 0)),
        "high_variance_clusters": len(high_variance),
        "failure_pattern_clusters": len(failure_patterns),
        "high_risk_clusters": len(high_risk),
        "top_clusters": rows,
    }


def format_cluster_report(suite: dict[str, Any]) -> str:
    report = cluster_report(suite)
    lines = [
        "redline cluster",
        "",
        f"Identified {report['clusters']} behavior-signature groups from {report['unique_prompt_response_pairs']} unique pairs.",
        f"Records seen: {report['records_seen']}  Duplicate pairs: {report['duplicate_prompt_response_pairs']}",
        f"High-risk groups: {report['high_risk_clusters']}",
        f"High-variance groups: {report['high_variance_clusters']}",
        f"Failure-pattern groups: {report['failure_pattern_clusters']}",
        f"Suggested eval suite: {report['suggested_cases']} representative cases.",
        f"Case coverage: {report['suggested_cases']}/{report['unique_prompt_response_pairs']} ({_percent(report['case_coverage'])})",
        "",
    ]

    clusters = report["top_clusters"]
    if clusters:
        lines.append(f"{'SIZE':>4} {'SEL':>3} {'WORDS':>11} {'RISK':>6} {'VAR':>3}  {'FLAGS':<32} BEHAVIOR")
        lines.append(f"{'-' * 4} {'-' * 3} {'-' * 11} {'-' * 6} {'-' * 3}  {'-' * 32} {'-' * 60}")
        for cluster in clusters:
            marker = "yes" if cluster["high_variance"] else ""
            word_range = f"{cluster['word_count_min']}-{cluster['word_count_max']}"
            flags = ", ".join(cluster["failure_patterns"])
            lines.append(
                f"{cluster['size']:>4} {cluster['selected_cases']:>3} {word_range:>11} {cluster['risk']:>6} {marker:>3}  "
                f"{flags:<32} {cluster['behavior']}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _cluster_row(cluster: dict[str, Any], *, selected_cases: int) -> dict[str, Any]:
    return {
        "signature": str(cluster.get("signature", "")),
        "behavior": behavior_label(str(cluster.get("signature", ""))),
        "size": int(cluster.get("size", 0)),
        "selected_cases": selected_cases,
        "word_count_min": int(cluster.get("word_count_min", 0)),
        "word_count_max": int(cluster.get("word_count_max", 0)),
        "high_variance": bool(cluster.get("high_variance")),
        "risk": _cluster_risk(cluster.get("risk")),
        "failure_patterns": _string_list(cluster.get("failure_patterns")),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _cluster_risk(value: object) -> str:
    if value in {"high", "medium", "low"}:
        return str(value)
    return "low"


def _selected_case_counts(cases: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        signature = str(case.get("cluster") or "")
        if signature:
            counts[signature] = counts.get(signature, 0) + 1
    return counts


def _ratio(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return part / total


def _percent(value: Any) -> str:
    if isinstance(value, float):
        return f"{value * 100:.1f}%"
    return "n/a"
