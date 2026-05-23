from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def add_case_requirement(
    suite: dict[str, Any],
    case_id: str,
    *,
    include: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    _find_case(suite, case_id)
    requirements = suite.setdefault("requirements", {})
    if not isinstance(requirements, dict):
        raise ValueError("suite requirements must be a JSON object")

    existing = requirements.setdefault(case_id, {})
    if not isinstance(existing, dict):
        existing = {}
        requirements[case_id] = existing

    includes = list(existing.get("include") or [])
    for item in include or []:
        value = item.strip()
        if value and value not in includes:
            includes.append(value)

    existing["include"] = includes
    existing["note"] = note
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    return existing


def clear_case_requirements(suite: dict[str, Any], case_id: str) -> bool:
    requirements = suite.get("requirements")
    if not isinstance(requirements, dict):
        return False
    return requirements.pop(case_id, None) is not None


def case_requirements(suite: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    requirements = suite.get("requirements")
    if not isinstance(requirements, dict):
        return None
    value = requirements.get(case_id)
    return value if isinstance(value, dict) else None


def requirement_reasons(requirement: dict[str, Any] | None, candidate_response: str) -> list[str]:
    if not requirement:
        return []
    reasons = []
    for value in requirement.get("include") or []:
        required = str(value)
        if required and required not in candidate_response:
            reasons.append(f"candidate missing required text: {required}")
    return reasons


def _find_case(suite: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in suite.get("cases", []):
        if isinstance(case, dict) and str(case.get("id")) == case_id:
            return case
    raise ValueError(f"case not found in suite: {case_id}")
