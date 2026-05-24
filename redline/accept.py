from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .features import behavior_signature, extract_features
from .hashes import prompt_response_hash
from .io import LogRecord


def accept_candidate_baseline(
    suite: dict[str, Any],
    candidate_records: list[LogRecord],
    case_id: str,
    *,
    note: str = "",
) -> dict[str, Any]:
    case = _find_case(suite, case_id)
    candidate = _find_candidate(candidate_records, case)
    if candidate is None:
        raise ValueError(f"candidate output not found for case: {case_id}")

    previous_response = str(case.get("baseline_response", ""))
    prompt = str(case.get("prompt", ""))
    case["baseline_response"] = candidate.response
    case["features"] = extract_features(candidate.response).to_dict()
    case["cluster"] = behavior_signature(prompt, candidate.response)
    case["content_hash"] = prompt_response_hash(prompt, candidate.response)

    judgments = suite.get("judgments")
    if isinstance(judgments, dict):
        judgments.pop(case_id, None)

    history = suite.setdefault("accepted_baselines", [])
    if isinstance(history, list):
        history.append(
            {
                "case_id": case_id,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
                "candidate_line": candidate.line_number,
                "note": note,
                "previous_response": previous_response,
            }
        )

    return {
        "case_id": case_id,
        "candidate_line": candidate.line_number,
        "previous_response": previous_response,
        "accepted_response": candidate.response,
    }


def expected_case_ids(suite: dict[str, Any]) -> list[str]:
    judgments = suite.get("judgments", {})
    if not isinstance(judgments, dict):
        return []
    return sorted(
        case_id
        for case_id, judgment in judgments.items()
        if isinstance(judgment, dict) and judgment.get("status") == "expected"
    )


def _find_case(suite: dict[str, Any], case_id: str) -> dict[str, Any]:
    for case in suite.get("cases", []):
        if isinstance(case, dict) and str(case.get("id")) == case_id:
            return case
    raise ValueError(f"case not found in suite: {case_id}")


def _find_candidate(candidate_records: list[LogRecord], case: dict[str, Any]) -> LogRecord | None:
    case_id = str(case.get("id"))
    prompt = str(case.get("prompt", ""))

    for record in candidate_records:
        if record.raw.get("case_id") == case_id:
            return record
    for record in candidate_records:
        if record.prompt == prompt:
            return record
    return None
