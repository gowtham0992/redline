from __future__ import annotations

from collections import Counter
from typing import Any

from .labels import behavior_label


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
    high_risk = [
        cluster
        for cluster in clusters
        if isinstance(cluster, dict) and str(cluster.get("risk") or "") == "high"
    ]
    medium_risk = [
        cluster
        for cluster in clusters
        if isinstance(cluster, dict) and str(cluster.get("risk") or "") == "medium"
    ]
    top_clusters = [
        {
            "signature": str(cluster.get("signature", "")),
            "behavior": behavior_label(str(cluster.get("signature", ""))),
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
    covered_clusters = {
        str(case.get("cluster"))
        for case in cases
        if isinstance(case, dict) and case.get("cluster")
    }
    records_seen = int(summary.get("records_seen", 0))
    unique_pairs = int(summary.get("unique_prompt_response_pairs", summary.get("records_seen", 0)))
    clusters_count = int(summary.get("clusters", len(clusters)))
    cases_count = int(summary.get("cases", len(cases)))
    requirements_count = len(requirements)
    pinned_cases = int(
        summary.get(
            "pinned_cases",
            len([case for case in cases if isinstance(case, dict) and case.get("pinned")]),
        )
    )
    owner_counts: Counter[str] = Counter(
        str(case.get("owner") or "").strip()
        for case in cases
        if isinstance(case, dict) and str(case.get("owner") or "").strip()
    )
    top_owners = [
        {"owner": owner, "cases": count}
        for owner, count in sorted(owner_counts.items(), key=lambda item: (-item[1], item[0].lower()))[:5]
    ]
    owned_cases = sum(owner_counts.values())
    accepted_baselines = suite.get("accepted_baselines", [])
    if not isinstance(accepted_baselines, list):
        accepted_baselines = []
    approved_baselines = len(
        [
            item
            for item in accepted_baselines
            if isinstance(item, dict) and str(item.get("approver") or "").strip()
        ]
    )
    accepted_baseline_count = len([item for item in accepted_baselines if isinstance(item, dict)])

    result = {
        "source": str(suite.get("source") or ""),
        "created_at": str(suite.get("created_at") or ""),
        "selection": str(summary.get("selection") or ""),
        "records_seen": records_seen,
        "unique_prompt_response_pairs": unique_pairs,
        "duplicate_prompt_response_pairs": int(summary.get("duplicate_prompt_response_pairs", 0)),
        "clusters": clusters_count,
        "covered_clusters": len(covered_clusters),
        "cases": cases_count,
        "case_coverage": _ratio(cases_count, unique_pairs),
        "cluster_coverage": _ratio(len(covered_clusters), clusters_count),
        "max_cases": int(summary.get("max_cases", 0)),
        "pinned_cases": pinned_cases,
        "owned_cases": owned_cases,
        "unowned_cases": max(0, cases_count - owned_cases),
        "owners": dict(sorted(owner_counts.items())),
        "top_owners": top_owners,
        "accepted_baselines": accepted_baseline_count,
        "approved_baselines": approved_baselines,
        "unapproved_baselines": max(0, accepted_baseline_count - approved_baselines),
        "high_risk_clusters": len(high_risk),
        "medium_risk_clusters": len(medium_risk),
        "high_variance_clusters": len(high_variance),
        "failure_pattern_clusters": len(failure_patterns),
        "judgments": dict(sorted(judgment_counts.items())),
        "requirements": requirements_count,
        "top_clusters": top_clusters,
    }
    result["next_steps"] = _summary_next_steps(result)
    return result


def format_suite_summary(suite: dict[str, Any], *, suite_path: str | None = None) -> str:
    summary = suite_summary(suite)
    if suite_path:
        summary = {**summary, "next_steps": _summary_next_steps(summary, suite_path=suite_path)}
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
        f"Cluster coverage:       {summary['covered_clusters']}/{summary['clusters']} ({_percent(summary['cluster_coverage'])})",
        f"Representative cases:   {summary['cases']}",
        f"Case coverage:          {summary['cases']}/{summary['unique_prompt_response_pairs']} ({_percent(summary['case_coverage'])})",
        f"Pinned cases:           {summary['pinned_cases']}",
        f"Owned cases:            {summary['owned_cases']}/{summary['cases']}",
        f"Accepted baselines:     {summary['accepted_baselines']}",
        f"Approved baselines:     {summary['approved_baselines']}/{summary['accepted_baselines']}",
        f"Max cases:              {summary['max_cases']}",
        f"High-risk clusters:     {summary['high_risk_clusters']}",
        f"Medium-risk clusters:   {summary['medium_risk_clusters']}",
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

    top_owners = summary["top_owners"]
    if top_owners:
        lines.append("Owners:")
        for owner in top_owners:
            lines.append(f"  {owner['owner']:<20} {owner['cases']}")
        lines.append("")

    top_clusters = summary["top_clusters"]
    if top_clusters:
        lines.append("Top clusters:")
        for cluster in top_clusters:
            marker = " high-variance" if cluster["high_variance"] else ""
            flags = cluster["failure_patterns"]
            if flags:
                marker = f"{marker} flags={','.join(str(flag) for flag in flags)}"
            lines.append(f"  {cluster['size']:>4}  {cluster['behavior']}{marker}")
        lines.append("")

    next_steps = summary["next_steps"]
    if next_steps:
        lines.append("Next:")
        for step in next_steps:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _summary_next_steps(summary: dict[str, Any], *, suite_path: str | None = None) -> list[str]:
    steps = []
    if int(summary["covered_clusters"]) < int(summary["clusters"]):
        if suite_path:
            steps.append(
                "Increase --max-cases or pin a must-cover edge case: "
                f"redline suite add {suite_path} --prompt-file path/to/prompt.txt "
                '--response-file path/to/baseline.txt --include "must keep text"'
            )
        else:
            steps.append("Increase --max-cases or pin edge cases with redline suite add.")
    if int(summary["high_risk_clusters"]) and int(summary["requirements"]) == 0:
        steps.append("Add requirements for must-keep details in high-risk cases.")
    if int(summary["cases"]) and int(summary["owned_cases"]) == 0:
        steps.append("Add owners with --owner or redline.json owner rules before team rollout.")
    elif int(summary["unowned_cases"]):
        steps.append("Assign owners to remaining unowned cases before team rollout.")
    if int(summary["unapproved_baselines"]):
        steps.append("Record approvers for accepted baselines before team rollout.")
    if int(summary["cases"]) and not summary["judgments"]:
        steps.append("After the first eval, mark expected or ignored changes to train the suite.")
    if int(summary["cases"]) == 0:
        steps.append("Generate or add at least one suite case before running eval.")
    return steps


def _ratio(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return part / total


def _percent(value: Any) -> str:
    if isinstance(value, float):
        return f"{value * 100:.1f}%"
    return "n/a"
