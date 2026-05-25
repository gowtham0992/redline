from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from .redact import DEFAULT_PLACEHOLDER
from .watch import DEFAULT_WATCH_LOG, record


Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
Metadata = dict[str, Any] | Callable[[Scope, Any, Any], dict[str, Any]]
DEFAULT_MAX_BODY_BYTES = 1_000_000
DEFAULT_CAPTURE_CONTENT_TYPES = ("application/json", "application/*+json")


class RedlineMiddleware:
    """ASGI middleware that records JSON prompt-response pairs locally.

    Works with FastAPI and other ASGI apps without importing FastAPI. It buffers
    one JSON HTTP request and response body up to ``max_body_bytes``, extracts
    configured JSON fields, and appends a redline observation when both prompt
    and response are present.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        log: str = DEFAULT_WATCH_LOG,
        prompt_field: str = "prompt",
        response_field: str = "response",
        metadata: Metadata | None = None,
        dedupe: bool = True,
        redact: bool = True,
        placeholder: str = DEFAULT_PLACEHOLDER,
        max_body_bytes: int | None = DEFAULT_MAX_BODY_BYTES,
        capture_content_types: tuple[str, ...] = DEFAULT_CAPTURE_CONTENT_TYPES,
    ) -> None:
        if max_body_bytes is not None and max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be greater than 0")
        self.app = app
        self.log = log
        self.prompt_field = prompt_field
        self.response_field = response_field
        self.metadata = metadata
        self.dedupe = dedupe
        self.redact = redact
        self.placeholder = placeholder
        self.max_body_bytes = max_body_bytes
        self.capture_content_types = capture_content_types

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_chunks: list[bytes] = []
        response_chunks: list[bytes] = []
        request_capture = _scope_content_type_allowed(scope, self.capture_content_types)
        response_capture = False
        request_too_large = False
        response_too_large = False
        status_code: int | None = None

        async def capture_receive() -> Message:
            nonlocal request_too_large
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if request_capture and not request_too_large and isinstance(body, bytes) and body:
                    request_too_large = _append_limited(request_chunks, body, self.max_body_bytes)
            return message

        async def capture_send(message: Message) -> None:
            nonlocal response_capture, response_too_large, status_code
            if message.get("type") == "http.response.start":
                status = message.get("status")
                if isinstance(status, int):
                    status_code = status
                response_capture = _message_content_type_allowed(message, self.capture_content_types)
            elif message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if response_capture and not response_too_large and isinstance(body, bytes) and body:
                    response_too_large = _append_limited(response_chunks, body, self.max_body_bytes)
            await send(message)
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                if request_capture and response_capture and not request_too_large and not response_too_large:
                    self._record_observation(scope, request_chunks, response_chunks, status_code)

        await self.app(scope, capture_receive, capture_send)

    def _record_observation(
        self,
        scope: Scope,
        request_chunks: list[bytes],
        response_chunks: list[bytes],
        status_code: int | None,
    ) -> None:
        request_json = _decode_json(request_chunks)
        response_json = _decode_json(response_chunks)
        if request_json is None or response_json is None:
            return
        prompt = _path_value(request_json, self.prompt_field)
        response = _path_value(response_json, self.response_field)
        if prompt is _MISSING or response is _MISSING:
            return
        record(
            prompt,
            response,
            log=self.log,
            source=_scope_source(scope),
            metadata={
                **_scope_metadata(scope, status_code),
                **_metadata(self.metadata, scope, request_json, response_json),
            },
            dedupe=self.dedupe,
            redact=self.redact,
            placeholder=self.placeholder,
        )


_MISSING = object()


def _decode_json(chunks: list[bytes]) -> Any:
    if not chunks:
        return None
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _append_limited(chunks: list[bytes], body: bytes, max_body_bytes: int | None) -> bool:
    if max_body_bytes is None:
        chunks.append(body)
        return False
    current = sum(len(chunk) for chunk in chunks)
    if current + len(body) > max_body_bytes:
        chunks.clear()
        return True
    chunks.append(body)
    return False


def _scope_content_type_allowed(scope: Scope, allowed: tuple[str, ...]) -> bool:
    return _content_type_allowed(_headers_content_type(scope.get("headers")), allowed)


def _message_content_type_allowed(message: Message, allowed: tuple[str, ...]) -> bool:
    return _content_type_allowed(_headers_content_type(message.get("headers")), allowed)


def _headers_content_type(headers: Any) -> str | None:
    if not isinstance(headers, list):
        return None
    for key, value in headers:
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            continue
        if key.lower() == b"content-type":
            return value.decode("latin-1").split(";", 1)[0].strip().lower()
    return None


def _content_type_allowed(content_type: str | None, allowed: tuple[str, ...]) -> bool:
    if not content_type:
        return False
    for pattern in allowed:
        normalized = pattern.lower().strip()
        if normalized == content_type:
            return True
        if normalized.endswith("/*+json"):
            prefix = normalized.removesuffix("*+json")
            if content_type.startswith(prefix) and content_type.endswith("+json"):
                return True
    return False


def _path_value(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _scope_source(scope: Scope) -> str:
    method = str(scope.get("method") or "HTTP")
    path = str(scope.get("path") or "/")
    return f"asgi:{method} {path}"


def _scope_metadata(scope: Scope, status_code: int | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "method": str(scope.get("method") or "HTTP"),
        "path": str(scope.get("path") or "/"),
    }
    if status_code is not None:
        row["status_code"] = status_code
    return row


def _metadata(metadata: Metadata | None, scope: Scope, request_json: Any, response_json: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    row = metadata(scope, request_json, response_json) if callable(metadata) else metadata
    if not isinstance(row, dict):
        raise ValueError("middleware metadata must be a dict")
    return row
