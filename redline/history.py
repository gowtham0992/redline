from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import iter_jsonl
from .labels import behavior_label


SUMMARY_KEYS = (
    "cases",
    "regression",
    "changed",
    "improved",
    "accepted",
    "ignored",
    "missing",
    "neutral",
    "worse",
    "better",
    "resolved",
    "new",
    "removed",
    "unchanged",
)

TREND_VERSION = "0.1"
HISTORY_DIRECTIONS = (
    "worse",
    "better",
    "flat",
    "baseline",
    "no_history",
    "more_changed",
    "less_changed",
)


def history_entry(
    report: dict[str, Any],
    *,
    report_path: str = "",
    label: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("report missing summary object")
    return {
        "version": "0.1",
        "timestamp": timestamp or _utc_now(),
        "label": label,
        "report": report_path,
        "summary": _summary_counts(summary),
        "clusters": _cluster_counts(report.get("diffs")),
    }


def read_history(path: str | Path) -> list[dict[str, Any]]:
    entries = []
    for line_number, row in iter_jsonl(path):
        summary = row.get("summary")
        if not isinstance(summary, dict):
            raise ValueError(f"{path}:{line_number} missing summary object")
        entries.append(row)
    return entries


def history_trend(entries: list[dict[str, Any]]) -> dict[str, Any]:
    comparable = [entry for entry in entries if isinstance(entry.get("summary"), dict)]
    if not comparable:
        return {
            "version": TREND_VERSION,
            "direction": "no_history",
            "summary": "no history entries recorded yet",
            "recommendation": "record a redline report to start tracking prompt quality",
            "latest": {},
            "previous": {},
            "delta": {},
        }

    latest = _entry_metrics(comparable[-1])
    if len(comparable) == 1:
        return {
            "version": TREND_VERSION,
            "direction": "baseline",
            "summary": f"baseline recorded with {_blocking_text(latest)}",
            "recommendation": "record another run to see whether prompt quality is improving or regressing",
            "latest": latest,
            "previous": {},
            "delta": {},
            "clusters": [],
        }

    previous = _entry_metrics(comparable[-2])
    delta = {
        "blocking": latest["blocking"] - previous["blocking"],
        "regression": latest["regression"] - previous["regression"],
        "missing": latest["missing"] - previous["missing"],
        "changed": latest["changed"] - previous["changed"],
        "blocking_rate": _rate_delta(latest.get("blocking_rate"), previous.get("blocking_rate")),
    }
    direction = _trend_direction(latest, previous, delta)
    clusters = _cluster_deltas(comparable[-1], comparable[-2])
    return {
        "version": TREND_VERSION,
        "direction": direction,
        "summary": _trend_summary(direction, latest, previous, delta),
        "recommendation": _trend_recommendation(direction, latest),
        "latest": latest,
        "previous": previous,
        "delta": delta,
        "clusters": clusters,
    }


def format_history(entries: list[dict[str, Any]], *, limit: int | None = None) -> str:
    rows = entries[-limit:] if limit is not None and limit > 0 else entries
    lines = ["redline history", ""]
    if not rows:
        lines.append("No history entries.")
        return "\n".join(lines).rstrip() + "\n"

    lines.append(format_history_trend(history_trend(entries)))
    lines.append("")
    for entry in rows:
        timestamp = str(entry.get("timestamp") or "-")
        label = str(entry.get("label") or "-")
        report = str(entry.get("report") or "-")
        raw_summary = entry.get("summary")
        summary = raw_summary if isinstance(raw_summary, dict) else {}
        lines.append(f"{timestamp}  {label}  {report}  {_summary_text(summary)}")
    return "\n".join(lines).rstrip() + "\n"


def format_markdown_history(entries: list[dict[str, Any]], *, limit: int | None = None) -> str:
    rows = entries[-limit:] if limit is not None and limit > 0 else entries
    lines = ["# redline history", ""]
    if not rows:
        lines.append("No history entries.")
        return "\n".join(lines).rstrip() + "\n"

    trend = history_trend(entries)
    lines.extend(
        [
            "## Trend",
            "",
            f"**{str(trend.get('direction') or 'unknown').replace('_', ' ').title()}**: {trend.get('summary') or '-'}",
            "",
            f"Recommendation: {trend.get('recommendation') or '-'}",
            "",
        ]
    )
    cluster_rows = _cluster_trend_rows(trend.get("clusters"))
    if cluster_rows:
        lines.extend(
            [
                "## Behavior Group Diagnosis",
                "",
                "| Behavior Group | Blocking Delta | Latest Blocking | Changed Delta |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for row in cluster_rows:
            latest = row.get("latest")
            latest_counts = latest if isinstance(latest, dict) else {}
            lines.append(
                f"| {_markdown_cell(row.get('label') or row.get('cluster') or 'unclustered')} | "
                f"{_signed(int(row.get('blocking_delta') or 0))} | "
                f"{_metric(latest_counts, 'blocking')} | "
                f"{_signed(int(row.get('changed_delta') or 0))} |"
            )
        lines.append("")
    lines.extend(["## Runs", ""])
    lines.extend(
        [
            "| Timestamp | Label | Report | Summary |",
            "| --- | --- | --- | --- |",
        ]
    )
    for entry in rows:
        raw_summary = entry.get("summary")
        summary = raw_summary if isinstance(raw_summary, dict) else {}
        cells = [
            _markdown_cell(entry.get("timestamp") or "-"),
            _markdown_cell(entry.get("label") or "-"),
            _markdown_cell(entry.get("report") or "-"),
            _markdown_cell(_summary_text(summary) or "-"),
        ]
        lines.append(f"| {' | '.join(cells)} |")
    return "\n".join(lines).rstrip() + "\n"


def format_history_trend(trend: dict[str, Any]) -> str:
    direction = str(trend.get("direction") or "unknown").replace("_", " ").upper()
    summary = str(trend.get("summary") or "-")
    recommendation = str(trend.get("recommendation") or "-")
    cluster_text = _cluster_trend_text(trend.get("clusters"))
    return f"Trend: {direction} - {summary}.{cluster_text} {recommendation}."


def parse_history_fail_on(value: str | None) -> set[str]:
    if value is None or value == "":
        return set()
    if value.strip().lower() == "none":
        return set()
    directions = {item.strip().lower() for item in value.split(",") if item.strip()}
    unknown = sorted(directions - set(HISTORY_DIRECTIONS))
    if unknown:
        allowed = ", ".join(sorted(set(HISTORY_DIRECTIONS) | {"none"}))
        raise ValueError(f"history --fail-on must use: {allowed}")
    return directions


def should_fail_history(trend: dict[str, Any], fail_on: set[str]) -> bool:
    return str(trend.get("direction") or "") in fail_on


def _summary_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {}
    for key in SUMMARY_KEYS:
        if key in summary:
            counts[key] = _int_count(summary[key], key)
    for key, value in summary.items():
        if key not in counts:
            counts[str(key)] = _int_count(value, str(key))
    return counts


def _cluster_counts(diffs: Any) -> dict[str, dict[str, int]]:
    if not isinstance(diffs, list):
        return {}
    clusters: dict[str, dict[str, int]] = {}
    for item in diffs:
        if not isinstance(item, dict):
            continue
        cluster = str(item.get("cluster") or "unclustered")
        status = str(item.get("status") or "")
        row = clusters.setdefault(
            cluster,
            {
                "cases": 0,
                "regression": 0,
                "missing": 0,
                "changed": 0,
                "blocking": 0,
            },
        )
        row["cases"] += 1
        if status == "regression":
            row["regression"] += 1
            row["blocking"] += 1
        elif status == "missing":
            row["missing"] += 1
            row["blocking"] += 1
        elif status == "changed":
            row["changed"] += 1
    return clusters


def _summary_text(summary: dict[str, Any]) -> str:
    parts = []
    for key in SUMMARY_KEYS:
        if key in summary:
            parts.append(f"{key}={int(summary.get(key) or 0)}")
    for key in sorted(str(item) for item in summary if str(item) not in SUMMARY_KEYS):
        parts.append(f"{key}={int(summary.get(key) or 0)}")
    return " ".join(parts)


def _int_count(value: Any, key: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"summary.{key} must be an integer") from exc


def _markdown_cell(value: Any) -> str:
    text = str(value).replace("\n", " ").strip()
    if not text:
        return "-"
    return text.replace("|", r"\|")


def _entry_metrics(entry: dict[str, Any]) -> dict[str, Any]:
    raw_summary = entry.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    cases = _int_count(summary.get("cases", 0), "cases")
    regression = _int_count(summary.get("regression", 0), "regression")
    missing = _int_count(summary.get("missing", 0), "missing")
    changed = _int_count(summary.get("changed", 0), "changed")
    blocking = regression + missing
    return {
        "timestamp": str(entry.get("timestamp") or ""),
        "label": str(entry.get("label") or ""),
        "report": str(entry.get("report") or ""),
        "cases": cases,
        "regression": regression,
        "missing": missing,
        "changed": changed,
        "blocking": blocking,
        "blocking_rate": (blocking / cases) if cases > 0 else None,
    }


def _cluster_deltas(latest_entry: dict[str, Any], previous_entry: dict[str, Any]) -> list[dict[str, Any]]:
    latest = _entry_clusters(latest_entry)
    previous = _entry_clusters(previous_entry)
    rows = []
    for cluster in sorted(set(latest) | set(previous)):
        latest_counts = latest.get(cluster, {})
        previous_counts = previous.get(cluster, {})
        row = {
            "cluster": cluster,
            "label": behavior_label(cluster),
            "latest": latest_counts,
            "previous": previous_counts,
            "blocking_delta": _metric(latest_counts, "blocking") - _metric(previous_counts, "blocking"),
            "changed_delta": _metric(latest_counts, "changed") - _metric(previous_counts, "changed"),
        }
        if (
            row["blocking_delta"]
            or row["changed_delta"]
            or _metric(latest_counts, "blocking")
            or _metric(latest_counts, "changed")
        ):
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            -int(row["blocking_delta"]),
            -_metric(row["latest"], "blocking"),
            -int(row["changed_delta"]),
            str(row["label"]).lower(),
        ),
    )


def _entry_clusters(entry: dict[str, Any]) -> dict[str, dict[str, int]]:
    raw = entry.get("clusters")
    if not isinstance(raw, dict):
        return {}
    clusters: dict[str, dict[str, int]] = {}
    for name, counts in raw.items():
        if not isinstance(counts, dict):
            continue
        clusters[str(name)] = {
            "cases": _safe_int(counts.get("cases")),
            "regression": _safe_int(counts.get("regression")),
            "missing": _safe_int(counts.get("missing")),
            "changed": _safe_int(counts.get("changed")),
            "blocking": _safe_int(counts.get("blocking")),
        }
    return clusters


def _cluster_trend_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = [row for row in value if isinstance(row, dict)]
    return rows[:5]


def _cluster_trend_text(value: Any) -> str:
    rows = _cluster_trend_rows(value)
    if not rows:
        return ""
    top = rows[0]
    latest = top.get("latest")
    latest_counts = latest if isinstance(latest, dict) else {}
    label = str(top.get("label") or top.get("cluster") or "unclustered")
    blocking_delta = int(top.get("blocking_delta") or 0)
    changed_delta = int(top.get("changed_delta") or 0)
    latest_blocking = _metric(latest_counts, "blocking")
    return (
        f" Cluster: {label} blocking {_signed(blocking_delta)} "
        f"(latest {latest_blocking}), changed {_signed(changed_delta)}."
    )


def _metric(counts: Any, key: str) -> int:
    if not isinstance(counts, dict):
        return 0
    return _safe_int(counts.get(key))


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _trend_direction(latest: dict[str, Any], previous: dict[str, Any], delta: dict[str, Any]) -> str:
    latest_rate = latest.get("blocking_rate")
    previous_rate = previous.get("blocking_rate")
    if isinstance(latest_rate, float) and isinstance(previous_rate, float):
        rate_delta = latest_rate - previous_rate
        if rate_delta < -0.0001:
            return "better"
        if rate_delta > 0.0001:
            return "worse"
    if delta["blocking"] < 0:
        return "better"
    if delta["blocking"] > 0:
        return "worse"
    if delta["changed"] > 0:
        return "more_changed"
    if delta["changed"] < 0:
        return "less_changed"
    return "flat"


def _trend_summary(direction: str, latest: dict[str, Any], previous: dict[str, Any], delta: dict[str, Any]) -> str:
    delta_text = _signed(int(delta.get("blocking") or 0))
    changed_delta = int(delta.get("changed") or 0)
    if direction in {"better", "worse", "flat"}:
        return (
            f"{_blocking_text(latest)} was {_blocking_text(previous)} "
            f"(blocking {delta_text}, changed {_signed(changed_delta)})"
        )
    return (
        f"blocking stayed at {_blocking_text(latest)} "
        f"while changed cases moved {_signed(changed_delta)}"
    )


def _trend_recommendation(direction: str, latest: dict[str, Any]) -> str:
    blocking = int(latest.get("blocking") or 0)
    changed = int(latest.get("changed") or 0)
    if direction == "worse":
        return "investigate before accepting this run as the new baseline"
    if direction == "better":
        if blocking:
            return "quality is improving, but blocking cases remain"
        return "latest run has no blocking cases; review changed cases before accepting"
    if direction == "more_changed":
        return "review newly changed cases so expected behavior is marked deliberately"
    if direction == "less_changed":
        return "changed-case noise is down; keep tracking until blocking cases stay at zero"
    if blocking:
        return "blocking cases are unchanged; fix or mark expected before accepting"
    if changed:
        return "no blocking cases, but changed cases still need review"
    return "no blocking cases in the latest trend window"


def _blocking_text(metrics: dict[str, Any]) -> str:
    cases = int(metrics.get("cases") or 0)
    blocking = int(metrics.get("blocking") or 0)
    regression = int(metrics.get("regression") or 0)
    missing = int(metrics.get("missing") or 0)
    rate = metrics.get("blocking_rate")
    rate_text = f" ({float(rate) * 100:.1f}%)" if isinstance(rate, float) else ""
    return f"blocking={blocking}/{cases}{rate_text} regression={regression} missing={missing}"


def _rate_delta(latest: Any, previous: Any) -> float | None:
    if isinstance(latest, float) and isinstance(previous, float):
        return latest - previous
    return None


def _signed(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
