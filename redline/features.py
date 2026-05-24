from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


_REFUSAL_RE = re.compile(
    r"\b(?:"
    r"as an ai(?: language model)?|"
    r"(?:i\s+)?(?:can(?:not|'t)|cannot|can't)\s+"
    r"(?:help|assist|answer|provide|comply|fulfill|complete|do|share|generate|create|write|access)|"
    r"i'?m unable to\s+"
    r"(?:help|assist|answer|provide|comply|fulfill|complete|do|share|generate|create|write|access)|"
    r"unable to\s+"
    r"(?:help|assist|answer|provide|comply|fulfill|complete|do|share|generate|create|write|access)|"
    r"i do not have\s+(?:access|permission|the ability)|"
    r"i don't have\s+(?:access|permission|the ability)|"
    r"sorry,?\s+(?:but\s+)?(?:i\s+)?(?:can(?:not|'t)|cannot|can't|am unable)"
    r")\b",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"(?m)^\s*[-*+]\s+")
_NUMBERED_RE = re.compile(r"(?m)^\s*\d+[.)]\s+")
_URL_RE = re.compile(r"https?://\S+")
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:(?:,\d{3})+|:\d{2})?(?:\.\d+)?%?")
_ENTITY_RE = re.compile(r"\b(?:[A-Z]{2,}(?:-[A-Z0-9]+)*|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
_ENTITY_STOPWORDS = {
    "A",
    "An",
    "The",
    "This",
    "That",
    "These",
    "Those",
    "Customer",
    "Customers",
    "Added",
    "Changed",
    "Fixed",
    "Improved",
    "Impact",
    "Mitigated",
    "Next",
    "Owner",
    "Removed",
    "Return",
    "Route",
    "Updated",
    "User",
    "Users",
}
_COMMON_TITLE_WORDS = {
    "Account",
    "Answer",
    "Billing",
    "Case",
    "Classify",
    "Details",
    "Docs",
    "Example",
    "Issue",
    "Login",
    "Note",
    "Policy",
    "Prompt",
    "Question",
    "Read",
    "Refund",
    "Release",
    "Response",
    "Result",
    "Security",
    "Status",
    "Support",
    "Ticket",
}
_SENTENCE_START_ENTITY_VERBS = {
    "asked",
    "filed",
    "handles",
    "has",
    "is",
    "joined",
    "left",
    "needs",
    "owns",
    "reported",
    "requested",
    "requires",
    "said",
    "uses",
    "works",
    "wrote",
}


@dataclass(frozen=True)
class TextFeatures:
    chars: int
    words: int
    lines: int
    empty: bool
    valid_json: bool
    json_type: str | None
    json_keys: tuple[str, ...]
    has_code_block: bool
    has_bullets: bool
    has_numbered_list: bool
    has_markdown_table: bool
    refusal: bool
    url_count: int
    urls: tuple[str, ...]
    numbers: tuple[str, ...]
    entities: tuple[str, ...]
    shape: str
    length_bucket: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chars": self.chars,
            "words": self.words,
            "lines": self.lines,
            "empty": self.empty,
            "valid_json": self.valid_json,
            "json_type": self.json_type,
            "json_keys": list(self.json_keys),
            "has_code_block": self.has_code_block,
            "has_bullets": self.has_bullets,
            "has_numbered_list": self.has_numbered_list,
            "has_markdown_table": self.has_markdown_table,
            "refusal": self.refusal,
            "url_count": self.url_count,
            "urls": list(self.urls),
            "numbers": list(self.numbers),
            "entities": list(self.entities),
            "shape": self.shape,
            "length_bucket": self.length_bucket,
        }


def extract_features(text: str) -> TextFeatures:
    stripped = text.strip()
    words = re.findall(r"\S+", stripped)
    valid_json = False
    json_type: str | None = None
    json_keys: tuple[str, ...] = ()

    if stripped:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        else:
            valid_json = True
            json_type = type(parsed).__name__
            if isinstance(parsed, dict):
                json_keys = tuple(sorted(str(key) for key in parsed.keys()))

    has_code = "```" in text
    has_bullets = bool(_BULLET_RE.search(text))
    has_numbered = bool(_NUMBERED_RE.search(text))
    has_table = _looks_like_markdown_table(text)
    refusal = _has_refusal(text)
    urls = tuple(_URL_RE.findall(text))
    numbers = tuple(_NUMBER_RE.findall(text))
    entities = _entities(text)
    length_bucket = _length_bucket(len(words))
    shape = _shape(
        empty=not stripped,
        valid_json=valid_json,
        has_code=has_code,
        has_table=has_table,
        has_bullets=has_bullets,
        has_numbered=has_numbered,
        refusal=refusal,
    )

    return TextFeatures(
        chars=len(text),
        words=len(words),
        lines=0 if not stripped else stripped.count("\n") + 1,
        empty=not stripped,
        valid_json=valid_json,
        json_type=json_type,
        json_keys=json_keys,
        has_code_block=has_code,
        has_bullets=has_bullets,
        has_numbered_list=has_numbered,
        has_markdown_table=has_table,
        refusal=refusal,
        url_count=len(urls),
        urls=urls,
        numbers=numbers,
        entities=entities,
        shape=shape,
        length_bucket=length_bucket,
    )


def input_intent(text: str) -> str:
    lowered = text.strip().lower()
    if not lowered:
        return "empty_input"
    if "json" in lowered or "schema" in lowered:
        return "structured_json"
    if "table" in lowered or "csv" in lowered:
        return "structured_table"
    if any(lowered.startswith(prefix) for prefix in ("classify", "label", "categorize")):
        return "classification"
    if any(lowered.startswith(prefix) for prefix in ("summarize", "rewrite", "extract")):
        return "transformation"
    if any(lowered.startswith(prefix) for prefix in ("write", "draft", "compose")):
        return "generation"
    if lowered.endswith("?") or any(
        lowered.startswith(prefix)
        for prefix in ("what", "why", "how", "when", "where", "who", "is ", "are ")
    ):
        return "question_answer"
    return "general"


def behavior_signature(prompt: str, response: str) -> str:
    features = extract_features(response)
    parts = [
        input_intent(prompt),
        features.shape,
        features.length_bucket,
    ]
    if features.valid_json and features.json_type:
        parts.append(f"json:{features.json_type}:{','.join(features.json_keys[:8])}")
    return "|".join(parts)


def _length_bucket(words: int) -> str:
    if words == 0:
        return "empty"
    if words <= 30:
        return "short"
    if words <= 120:
        return "medium"
    return "long"


def _shape(
    *,
    empty: bool,
    valid_json: bool,
    has_code: bool,
    has_table: bool,
    has_bullets: bool,
    has_numbered: bool,
    refusal: bool,
) -> str:
    if empty:
        return "empty"
    if refusal:
        return "refusal"
    if valid_json:
        return "json"
    if has_code:
        return "code"
    if has_table:
        return "table"
    if has_numbered:
        return "numbered_list"
    if has_bullets:
        return "bullet_list"
    return "prose"


def _looks_like_markdown_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        next_line = lines[index + 1]
        if "|" in line and re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", next_line):
            return True
    return False


def _has_refusal(text: str) -> bool:
    checked = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        checked += 1
        normalized = re.sub(r"^(?:>\s*)?(?:[-*+]\s+|\d+[.)]\s+)?", "", line)
        if _REFUSAL_RE.match(normalized):
            return True
        if checked >= 3:
            return False
    return False


def _entities(text: str) -> tuple[str, ...]:
    entities = set()
    for match in _ENTITY_RE.finditer(text):
        words = match.group(0).split()
        while len(words) > 1 and words[0] in _ENTITY_STOPWORDS:
            words = words[1:]
        entity = " ".join(words)
        if _keep_entity(entity, text, match.start(), match.end()):
            entities.add(entity)
    return tuple(sorted(entities))


def _keep_entity(entity: str, text: str, start: int, end: int) -> bool:
    if not entity or entity in _ENTITY_STOPWORDS:
        return False
    if _is_acronym(entity):
        return True

    words = entity.split()
    if len(words) > 1:
        return any(
            word not in _ENTITY_STOPWORDS and word not in _COMMON_TITLE_WORDS
            for word in words
        )

    if entity in _COMMON_TITLE_WORDS:
        return False
    if not _is_sentence_start(text, start):
        return True
    return _next_word(text, end).lower() in _SENTENCE_START_ENTITY_VERBS


def _is_acronym(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2,}(?:-[A-Z0-9]+)*", value))


def _is_sentence_start(text: str, start: int) -> bool:
    prefix = text[:start].rstrip()
    return not prefix or prefix[-1] in ".!?\n"


def _next_word(text: str, end: int) -> str:
    match = re.search(r"\b([A-Za-z]+)\b", text[end:])
    return match.group(1) if match else ""
