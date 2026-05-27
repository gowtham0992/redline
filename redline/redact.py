from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .io import iter_jsonl, write_jsonl


DEFAULT_PLACEHOLDER = "[REDACTED]"

SENSITIVE_FIELD_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "password",
    "private_key",
    "secret",
    "token",
)


@dataclass(frozen=True)
class RedactionPattern:
    label: str
    regex: re.Pattern[str]


DEFAULT_PATTERNS = (
    RedactionPattern("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    RedactionPattern("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    RedactionPattern("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    RedactionPattern("pypi_token", re.compile(r"\bpypi-[A-Za-z0-9_-]{20,}\b")),
    RedactionPattern("aws_access_key", re.compile(r"\bA[KS]IA[0-9A-Z]{16}\b")),
    RedactionPattern("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
)


def redact_jsonl(
    source: str,
    output: str,
    *,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    records = 0
    for _, row in iter_jsonl(source):
        records += 1
        redacted = redact_object(row, placeholder=placeholder, counts=counts)
        rows.append(redacted)
    write_jsonl(output, rows)
    redactions = sum(counts.values())
    return {
        "source": source,
        "output": output,
        "records": records,
        "redactions": redactions,
        "patterns": dict(sorted(counts.items())),
    }


def scan_jsonl_redactions(
    source: str,
    *,
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    records = 0
    for _, row in iter_jsonl(source):
        records += 1
        redact_object(row, placeholder=placeholder, counts=counts)
    redactions = sum(counts.values())
    return {
        "source": source,
        "output": None,
        "records": records,
        "redactions": redactions,
        "patterns": dict(sorted(counts.items())),
        "check": True,
    }


def redact_object(
    value: Any,
    *,
    placeholder: str = DEFAULT_PLACEHOLDER,
    counts: dict[str, int] | None = None,
    key: str = "",
) -> Any:
    counts = counts if counts is not None else {}
    if isinstance(value, dict):
        return {
            item_key: redact_object(item_value, placeholder=placeholder, counts=counts, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_object(item, placeholder=placeholder, counts=counts, key=key) for item in value]
    if isinstance(value, str):
        if _is_sensitive_field(key) and value:
            counts["sensitive_field"] = counts.get("sensitive_field", 0) + 1
            return placeholder
        return redact_text(value, placeholder=placeholder, counts=counts)
    return value


def redact_text(
    text: str,
    *,
    placeholder: str = DEFAULT_PLACEHOLDER,
    counts: dict[str, int] | None = None,
) -> str:
    output = text
    counts = counts if counts is not None else {}
    for pattern in DEFAULT_PATTERNS:
        output, count = pattern.regex.subn(placeholder, output)
        if count:
            counts[pattern.label] = counts.get(pattern.label, 0) + count
    return output


def format_redaction_report(report: dict[str, Any]) -> str:
    lines = [
        "redline redact",
        "",
        f"Read:       {report['source']}",
    ]
    if report.get("check"):
        lines.append("Mode:       check only")
    else:
        lines.append(f"Wrote:      {report['output']}")
    lines.extend(
        [
            f"Records:    {report['records']}",
            f"Redactions: {report['redactions']}",
            "Boundary:   best-effort common secret/PII patterns; review sensitive logs before sharing",
        ]
    )
    patterns = report.get("patterns")
    if isinstance(patterns, dict) and patterns:
        lines.append("Patterns:")
        for key, value in patterns.items():
            lines.append(f"  {key}: {value}")
    lines.extend(
        [
            "",
            "Next:",
        ]
    )
    if report.get("check"):
        lines.append(f"- Write a sanitized copy: redline redact {report['source']} --out redacted.jsonl")
        lines.append(f"- Or generate a suite if clean: redline suite {report['source']} --out redline-suite.json")
    else:
        lines.append(f"- Generate a suite: redline suite {report['output']} --out redline-suite.json")
        lines.append(f"- Inspect clusters: redline cluster {report['output']}")
    return "\n".join(lines).rstrip() + "\n"


def _is_sensitive_field(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in SENSITIVE_FIELD_FRAGMENTS)
