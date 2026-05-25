from __future__ import annotations


_INTENT_LABELS = {
    "classification": "classification prompt",
    "empty_input": "empty input",
    "general": "general prompt",
    "generation": "generation prompt",
    "question_answer": "question-answer prompt",
    "structured_json": "structured JSON prompt",
    "structured_table": "structured table prompt",
    "transformation": "transformation prompt",
}

_SHAPE_LABELS = {
    "bullet_list": "bullet-list response",
    "code": "code response",
    "empty": "empty response",
    "json": "JSON response",
    "numbered_list": "numbered-list response",
    "prose": "prose response",
    "refusal": "refusal response",
    "table": "table response",
}


def behavior_label(signature: str) -> str:
    """Return a user-facing label for an internal behavior signature."""
    parts = signature.split("|")
    if len(parts) < 3:
        return signature

    intent = _INTENT_LABELS.get(parts[0], parts[0].replace("_", " "))
    shape = _SHAPE_LABELS.get(parts[1], parts[1].replace("_", " "))
    length = parts[2].replace("_", " ")
    details = _signature_details(parts[3:])
    suffix = f"; {details}" if details else ""
    return f"{intent} -> {shape} ({length}{suffix})"


def _signature_details(parts: list[str]) -> str:
    details: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("json:"):
            details.append(_json_signature_detail(part))
        else:
            details.append(part.replace("_", " "))
    return "; ".join(detail for detail in details if detail)


def _json_signature_detail(part: str) -> str:
    _, _, remainder = part.partition(":")
    json_type, _, keys = remainder.partition(":")
    label = json_type or "value"
    if keys:
        return f"JSON {label} keys: {keys.replace(',', ', ')}"
    return f"JSON {label}"
