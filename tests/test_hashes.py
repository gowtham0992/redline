from __future__ import annotations

from redline.hashes import prompt_response_hash


def test_prompt_response_hash_is_stable_and_field_order_independent() -> None:
    digest = prompt_response_hash("prompt", "response")

    assert digest == prompt_response_hash("prompt", "response")
    assert digest == "b9f10d0ded5a34b3748102422a78c4633a8a4b3bbc84d5d153acaa5a7a6572e3"


def test_prompt_response_hash_distinguishes_prompt_and_response() -> None:
    digest = prompt_response_hash("prompt", "response")

    assert digest != prompt_response_hash("response", "prompt")
    assert digest != prompt_response_hash("prompt", "changed response")


def test_prompt_response_hash_preserves_unicode() -> None:
    assert prompt_response_hash("¿Listo?", "Sí") == prompt_response_hash("¿Listo?", "Sí")
