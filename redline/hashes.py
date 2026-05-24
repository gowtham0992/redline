from __future__ import annotations

from hashlib import sha256
import json


def prompt_response_hash(prompt: str, response: str) -> str:
    payload = json.dumps(
        {"prompt": prompt, "response": response},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()
