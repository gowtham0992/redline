from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


_REFUSAL_RE = re.compile(
    r"\b("
    r"as an ai|i can(?:not|'t)|i'?m unable|unable to|sorry|"
    r"i do not have|i don't have|cannot provide|can't provide"
    r")\b",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"(?m)^\s*[-*+]\s+")
_NUMBERED_RE = re.compile(r"(?m)^\s*\d+[.)]\s+")
_URL_RE = re.compile(r"https?://\S+")
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?%?")


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
    numbers: tuple[str, ...]
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
            "numbers": list(self.numbers),
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
    refusal = bool(_REFUSAL_RE.search(text))
    numbers = tuple(_NUMBER_RE.findall(text))
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
        url_count=len(_URL_RE.findall(text)),
        numbers=numbers,
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
