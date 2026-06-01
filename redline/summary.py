from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .io import read_json
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
    owner_rule_cases = _owner_rule_case_count(cases)
    accepted_baselines = suite.get("accepted_baselines", [])
    if not isinstance(accepted_baselines, list):
        accepted_baselines = []
    case_ids = {
        str(case.get("id") or "").strip()
        for case in cases
        if isinstance(case, dict) and str(case.get("id") or "").strip()
    }
    requirement_case_ids = {
        str(case_id).strip()
        for case_id in requirements
        if str(case_id).strip() in case_ids
    }
    judgment_case_ids = {
        str(case_id).strip()
        for case_id, value in judgments.items()
        if str(case_id).strip() in case_ids and isinstance(value, dict)
    }
    explicit_guard_case_ids = requirement_case_ids | judgment_case_ids
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
        "owner_rule_cases": owner_rule_cases,
        "unexplained_owner_cases": max(0, owned_cases - owner_rule_cases),
        "owner_rule_coverage": _ratio(owner_rule_cases, owned_cases),
        "owners": dict(sorted(owner_counts.items())),
        "top_owners": top_owners,
        "accepted_baselines": accepted_baseline_count,
        "approved_baselines": approved_baselines,
        "unapproved_baselines": max(0, accepted_baseline_count - approved_baselines),
        "requirement_cases": len(requirement_case_ids),
        "judgment_cases": len(judgment_case_ids),
        "explicit_guard_cases": len(explicit_guard_case_ids),
        "explicit_guard_coverage": _ratio(len(explicit_guard_case_ids), cases_count),
        "high_risk_clusters": len(high_risk),
        "medium_risk_clusters": len(medium_risk),
        "high_variance_clusters": len(high_variance),
        "failure_pattern_clusters": len(failure_patterns),
        "non_ascii_records": int(summary.get("non_ascii_records", 0)),
        "judgments": dict(sorted(judgment_counts.items())),
        "requirements": requirements_count,
        "top_clusters": top_clusters,
    }
    result["suite_readiness"] = _suite_readiness(result)
    result["next_steps"] = _summary_next_steps(result)
    return result


def prompt_manifest_summary(
    manifest: dict[str, Any],
    *,
    manifest_path: str = "redline-prompts.json",
) -> dict[str, Any]:
    prompts = manifest.get("prompts")
    if not isinstance(prompts, list):
        raise ValueError("prompt manifest missing prompts list")

    prompt_rows: list[dict[str, Any]] = []
    owner_counts: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    missing_suites: list[dict[str, str]] = []
    invalid_suites: list[dict[str, str]] = []

    for index, item in enumerate(prompts, 1):
        if not isinstance(item, dict):
            raise ValueError(f"prompt manifest entry {index} must be an object")
        prompt_id = str(item.get("id") or "").strip()
        prompt_path = str(item.get("path") or "").strip()
        suite_path = str(item.get("suite") or "").strip()
        if not prompt_id or not prompt_path or not suite_path:
            raise ValueError(f"prompt manifest entry {index} requires id, path, and suite")

        prompt_row: dict[str, Any] = {
            "id": prompt_id,
            "path": prompt_path,
            "suite": suite_path,
            "status": "missing",
            "cases": 0,
            "clusters": 0,
            "records_seen": 0,
            "owned_cases": 0,
            "owner_rule_cases": 0,
            "requirements": 0,
            "requirement_cases": 0,
            "judgment_cases": 0,
            "explicit_guard_cases": 0,
            "judgments": {},
        }
        if not Path(suite_path).is_file():
            missing_suites.append({"id": prompt_id, "path": prompt_path, "suite": suite_path})
            prompt_rows.append(prompt_row)
            continue

        try:
            child_summary = suite_summary(read_json(suite_path))
        except ValueError as exc:
            invalid_suites.append(
                {
                    "id": prompt_id,
                    "path": prompt_path,
                    "suite": suite_path,
                    "error": str(exc),
                }
            )
            prompt_row["status"] = "invalid"
            prompt_row["error"] = str(exc)
            prompt_rows.append(prompt_row)
            continue

        for key in (
            "records_seen",
            "unique_prompt_response_pairs",
            "duplicate_prompt_response_pairs",
            "clusters",
            "covered_clusters",
            "cases",
            "pinned_cases",
            "owned_cases",
            "owner_rule_cases",
            "accepted_baselines",
            "approved_baselines",
            "unapproved_baselines",
            "requirement_cases",
            "judgment_cases",
            "explicit_guard_cases",
            "high_risk_clusters",
            "medium_risk_clusters",
            "high_variance_clusters",
            "failure_pattern_clusters",
            "non_ascii_records",
            "requirements",
        ):
            totals[key] += int(child_summary.get(key) or 0)
        child_owners = child_summary.get("owners")
        if isinstance(child_owners, dict):
            for owner, count in child_owners.items():
                owner_counts[str(owner)] += int(count)
        prompt_row.update(
            {
                "status": "ready",
                "cases": int(child_summary.get("cases") or 0),
                "clusters": int(child_summary.get("clusters") or 0),
                "records_seen": int(child_summary.get("records_seen") or 0),
                "owned_cases": int(child_summary.get("owned_cases") or 0),
                "owner_rule_cases": int(child_summary.get("owner_rule_cases") or 0),
                "requirements": int(child_summary.get("requirements") or 0),
                "requirement_cases": int(child_summary.get("requirement_cases") or 0),
                "judgment_cases": int(child_summary.get("judgment_cases") or 0),
                "explicit_guard_cases": int(child_summary.get("explicit_guard_cases") or 0),
                "judgments": child_summary.get("judgments") or {},
            }
        )
        prompt_rows.append(prompt_row)

    top_owners = [
        {"owner": owner, "cases": count}
        for owner, count in sorted(owner_counts.items(), key=lambda item: (-item[1], item[0].lower()))[:5]
    ]
    ready_suite_count = len([row for row in prompt_rows if row.get("status") == "ready"])
    result = {
        "schema": "redline-prompt-manifest-summary-v1",
        "manifest": manifest_path,
        "root": str(manifest.get("root") or ""),
        "suite_dir": str(manifest.get("suite_dir") or ""),
        "prompt_count": len(prompt_rows),
        "suite_count": ready_suite_count,
        "missing_suite_count": len(missing_suites),
        "invalid_suite_count": len(invalid_suites),
        "records_seen": totals["records_seen"],
        "unique_prompt_response_pairs": totals["unique_prompt_response_pairs"],
        "duplicate_prompt_response_pairs": totals["duplicate_prompt_response_pairs"],
        "clusters": totals["clusters"],
        "covered_clusters": totals["covered_clusters"],
        "cases": totals["cases"],
        "pinned_cases": totals["pinned_cases"],
        "owned_cases": totals["owned_cases"],
        "unowned_cases": max(0, totals["cases"] - totals["owned_cases"]),
        "owner_rule_cases": totals["owner_rule_cases"],
        "unexplained_owner_cases": max(0, totals["owned_cases"] - totals["owner_rule_cases"]),
        "owners": dict(sorted(owner_counts.items())),
        "top_owners": top_owners,
        "accepted_baselines": totals["accepted_baselines"],
        "approved_baselines": totals["approved_baselines"],
        "unapproved_baselines": totals["unapproved_baselines"],
        "requirement_cases": totals["requirement_cases"],
        "judgment_cases": totals["judgment_cases"],
        "explicit_guard_cases": totals["explicit_guard_cases"],
        "high_risk_clusters": totals["high_risk_clusters"],
        "medium_risk_clusters": totals["medium_risk_clusters"],
        "high_variance_clusters": totals["high_variance_clusters"],
        "failure_pattern_clusters": totals["failure_pattern_clusters"],
        "non_ascii_records": totals["non_ascii_records"],
        "requirements": totals["requirements"],
        "prompts": prompt_rows,
        "missing_suites": missing_suites,
        "invalid_suites": invalid_suites,
    }
    result["case_coverage"] = _ratio(totals["cases"], totals["unique_prompt_response_pairs"])
    result["cluster_coverage"] = _ratio(totals["covered_clusters"], totals["clusters"])
    result["explicit_guard_coverage"] = _ratio(totals["explicit_guard_cases"], totals["cases"])
    result["owner_rule_coverage"] = _ratio(totals["owner_rule_cases"], totals["owned_cases"])
    result["status"] = _manifest_summary_status(result)
    result["next_steps"] = _manifest_summary_next_steps(result)
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
        f"Behavior groups:        {summary['clusters']}",
        f"Group coverage:         {summary['covered_clusters']}/{summary['clusters']} ({_percent(summary['cluster_coverage'])})",
        f"Representative cases:   {summary['cases']}",
        f"Case coverage:          {summary['cases']}/{summary['unique_prompt_response_pairs']} ({_percent(summary['case_coverage'])})",
        f"Suite readiness:        {_format_readiness(summary['suite_readiness'])}",
        "Readiness scope:        suite health, not model quality or candidate safety",
        f"Pinned cases:           {summary['pinned_cases']}",
        f"Owned cases:            {summary['owned_cases']}/{summary['cases']}",
        f"Owner rule coverage:    {summary['owner_rule_cases']}/{summary['owned_cases']} ({_percent(summary['owner_rule_coverage'])})",
        f"Accepted baselines:     {summary['accepted_baselines']}",
        f"Approved baselines:     {summary['approved_baselines']}/{summary['accepted_baselines']}",
        f"Explicit guard coverage: {summary['explicit_guard_cases']}/{summary['cases']} ({_percent(summary['explicit_guard_coverage'])})",
        f"Max cases:              {summary['max_cases']}",
        f"High-risk groups:       {summary['high_risk_clusters']}",
        f"Medium-risk groups:     {summary['medium_risk_clusters']}",
        f"High-variance groups:   {summary['high_variance_clusters']}",
        f"Failure-pattern groups: {summary['failure_pattern_clusters']:>2}",
        f"Non-ASCII records:      {summary['non_ascii_records']}",
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
        lines.append("Top groups:")
        for cluster in top_clusters:
            marker = " high-variance" if cluster["high_variance"] else ""
            flags = cluster["failure_patterns"]
            if flags:
                marker = f"{marker} flags={','.join(str(flag) for flag in flags)}"
            lines.append(f"  {cluster['size']:>4}  {cluster['behavior']}{marker}")
        lines.append("")

    readiness = summary.get("suite_readiness")
    if isinstance(readiness, dict):
        reasons = readiness.get("reasons")
        if isinstance(reasons, list) and reasons:
            lines.append("Readiness signals:")
            for reason in reasons:
                lines.append(f"- {reason}")
            lines.append("")

    next_steps = summary["next_steps"]
    if next_steps:
        lines.append("Next:")
        for step in next_steps:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_prompt_manifest_summary(report: dict[str, Any]) -> str:
    lines = [
        "redline summary",
        "",
        f"Prompt manifest:        {report['manifest']}",
        f"Status:                 {str(report['status']).upper()}",
        f"Root:                   {report['root'] or '<unknown>'}",
        f"Suite dir:              {report['suite_dir'] or '<unknown>'}",
        f"Prompts:                {report['prompt_count']}",
        f"Suites ready:           {report['suite_count']}/{report['prompt_count']}",
        f"Missing suites:         {report['missing_suite_count']}",
        f"Invalid suites:         {report['invalid_suite_count']}",
        f"Records seen:           {report['records_seen']}",
        f"Unique pairs:           {report['unique_prompt_response_pairs']}",
        f"Behavior groups:        {report['clusters']}",
        f"Group coverage:         {report['covered_clusters']}/{report['clusters']} ({_percent(report['cluster_coverage'])})",
        f"Representative cases:   {report['cases']}",
        f"Case coverage:          {report['cases']}/{report['unique_prompt_response_pairs']} ({_percent(report['case_coverage'])})",
        f"Pinned cases:           {report['pinned_cases']}",
        f"Owned cases:            {report['owned_cases']}/{report['cases']}",
        f"Owner rule coverage:    {report['owner_rule_cases']}/{report['owned_cases']} ({_percent(report['owner_rule_coverage'])})",
        f"Accepted baselines:     {report['accepted_baselines']}",
        f"Approved baselines:     {report['approved_baselines']}/{report['accepted_baselines']}",
        f"Explicit guard coverage: {report['explicit_guard_cases']}/{report['cases']} ({_percent(report['explicit_guard_coverage'])})",
        f"High-risk groups:       {report['high_risk_clusters']}",
        f"Medium-risk groups:     {report['medium_risk_clusters']}",
        f"Non-ASCII records:      {report['non_ascii_records']}",
        f"Cases with requirements: {report['requirements']:>2}",
        "",
    ]

    top_owners = report["top_owners"]
    if top_owners:
        lines.append("Owners:")
        for owner in top_owners:
            lines.append(f"  {owner['owner']:<20} {owner['cases']}")
        lines.append("")

    prompt_rows = report.get("prompts")
    if isinstance(prompt_rows, list) and prompt_rows:
        lines.append("Prompt suites:")
        for row in prompt_rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "unknown").upper()
            lines.append(
                f"  {status:<7} {str(row.get('id') or ''):<28} "
                f"cases={int(row.get('cases') or 0):<3} "
                f"owners={int(row.get('owned_cases') or 0):<3} "
                f"guards={int(row.get('explicit_guard_cases') or 0):<3} "
                f"requirements={int(row.get('requirements') or 0):<3} "
                f"suite={row.get('suite')}"
            )
        lines.append("")

    next_steps = report["next_steps"]
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
    if int(summary.get("unexplained_owner_cases") or 0):
        steps.append("Prefer redline.json owner rules so shared suites explain case routing.")
    if int(summary["unapproved_baselines"]):
        steps.append("Record approvers for accepted baselines before team rollout.")
    if int(summary["cases"]) and int(summary.get("explicit_guard_cases") or 0) == 0:
        steps.append("Add requirements or recorded judgments for high-value semantic risks.")
    if int(summary.get("non_ascii_records") or 0):
        steps.append(
            "Review non-English cases manually or with a domain judge; structural checks still work, "
            "but entity/refusal heuristics are English-oriented."
        )
    if int(summary["cases"]) and not summary["judgments"]:
        steps.append("After the first eval, mark expected or ignored changes to train the suite.")
    if int(summary["cases"]) == 0:
        steps.append("Generate or add at least one suite case before running eval.")
    return steps


def _suite_readiness(summary: dict[str, Any]) -> dict[str, Any]:
    cases = int(summary.get("cases") or 0)
    if cases == 0:
        return {
            "score": 0,
            "label": "empty",
            "reasons": ["no suite cases are available yet"],
        }

    score = 0.0
    score += 35.0 * float(summary.get("cluster_coverage") or 0.0)
    score += 20.0 * float(summary.get("case_coverage") or 0.0)
    score += 20.0 * float(summary.get("explicit_guard_coverage") or 0.0)
    owner_coverage = _ratio(int(summary.get("owned_cases") or 0), cases) or 0.0
    score += 10.0 * owner_coverage
    if int(summary.get("high_risk_clusters") or 0) == 0 or int(summary.get("requirements") or 0):
        score += 10.0
    if int(summary.get("non_ascii_records") or 0) == 0:
        score += 5.0

    rounded = int(round(min(100.0, max(0.0, score))))
    if rounded >= 80:
        label = "strong"
    elif rounded >= 55:
        label = "usable"
    else:
        label = "needs_work"

    return {
        "score": rounded,
        "label": label,
        "reasons": _readiness_reasons(summary, owner_coverage=owner_coverage),
    }


def _readiness_reasons(summary: dict[str, Any], *, owner_coverage: float) -> list[str]:
    reasons = []
    cluster_coverage = float(summary.get("cluster_coverage") or 0.0)
    case_coverage = float(summary.get("case_coverage") or 0.0)
    explicit_guard_coverage = float(summary.get("explicit_guard_coverage") or 0.0)

    if cluster_coverage >= 1.0:
        reasons.append("all detected behavior-signature groups have at least one selected case")
    else:
        reasons.append("some behavior-signature groups are not represented in the suite")

    if case_coverage >= 0.8:
        reasons.append("case budget covers most unique prompt-response pairs")
    else:
        reasons.append("case budget is sampling a small share of unique prompt-response pairs")

    if explicit_guard_coverage >= 0.5:
        reasons.append("many cases have requirements or recorded judgments")
    elif explicit_guard_coverage > 0:
        reasons.append("some cases have requirements or recorded judgments")
    else:
        reasons.append("no cases have explicit requirements or recorded judgments yet")

    if owner_coverage >= 1.0:
        reasons.append("all cases have owners")
    elif owner_coverage > 0:
        reasons.append("some cases still need owners")
    else:
        reasons.append("no cases have owners yet")

    if int(summary.get("high_risk_clusters") or 0) and int(summary.get("requirements") or 0) == 0:
        reasons.append("high-risk groups need explicit requirements or a judge before CI gating")
    if int(summary.get("non_ascii_records") or 0):
        reasons.append("non-ASCII records need extra review because entity/refusal heuristics are English-oriented")

    return reasons


def _format_readiness(value: object) -> str:
    if not isinstance(value, dict):
        return "<unknown>"
    score = int(value.get("score") or 0)
    label = str(value.get("label") or "unknown").replace("_", " ")
    return f"{score}/100 ({label})"


def _manifest_summary_status(summary: dict[str, Any]) -> str:
    if int(summary["invalid_suite_count"]):
        return "invalid"
    if int(summary["missing_suite_count"]):
        return "missing_suites"
    if int(summary["cases"]) == 0:
        return "empty"
    if int(summary["unowned_cases"]) or int(summary.get("explicit_guard_cases") or 0) == 0:
        return "needs_review"
    return "ready"


def _manifest_summary_next_steps(summary: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    first_missing = next(
        (item for item in summary.get("missing_suites", []) if isinstance(item, dict)),
        None,
    )
    if first_missing:
        steps.append(
            "Build missing suite: "
            f"redline suite path/to/baseline.jsonl --out {first_missing.get('suite')}"
        )
    first_invalid = next(
        (item for item in summary.get("invalid_suites", []) if isinstance(item, dict)),
        None,
    )
    if first_invalid:
        steps.append(f"Fix invalid suite: redline validate {first_invalid.get('suite')} --strict")
    if int(summary["cases"]) and int(summary["unowned_cases"]):
        steps.append("Assign owners to remaining unowned cases before team rollout.")
    if int(summary.get("unexplained_owner_cases") or 0):
        steps.append("Prefer redline.json owner rules so shared prompt manifests explain case routing.")
    if int(summary["cases"]) and int(summary.get("explicit_guard_cases") or 0) == 0:
        steps.append("Add requirements or recorded judgments to high-value cases so scale does not dilute trust.")
    if int(summary.get("non_ascii_records") or 0):
        steps.append(
            "Review non-English cases manually or with a domain judge; structural checks still work, "
            "but entity/refusal heuristics are English-oriented."
        )
    if int(summary["suite_count"]) == int(summary["prompt_count"]) and int(summary["cases"]):
        manifest = str(summary["manifest"])
        steps.append(f"Check eval budget: redline budget {manifest}")
        steps.append(f"Run manifest eval: redline eval {manifest}")
    if int(summary["prompt_count"]) == 0:
        steps.append("Add prompt files, then rerun redline prompts.")
    return steps


def _ratio(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return part / total


def _owner_rule_case_count(cases: list[Any]) -> int:
    return sum(
        1
        for case in cases
        if isinstance(case, dict)
        and str(case.get("owner") or "").strip()
        and isinstance(case.get("owner_rule"), dict)
    )


def _percent(value: Any) -> str:
    if isinstance(value, float):
        return f"{value * 100:.1f}%"
    return "n/a"
