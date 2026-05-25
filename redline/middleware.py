from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from .io import append_jsonl
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

    Works with FastAPI and other ASGI apps without importing FastAPI. It
    captures JSON-only HTTP request and response bodies up to
    ``max_body_bytes``, skips streaming responses by default, extracts
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
        capture_streaming_responses: bool = False,
        skip_log: str | None = None,
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
        self.capture_streaming_responses = capture_streaming_responses
        self.skip_log = skip_log

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_body = _CaptureBuffer(self.max_body_bytes)
        response_body = _CaptureBuffer(self.max_body_bytes)
        request_skip_reason = _scope_skip_reason(scope, self.capture_content_types, self.max_body_bytes)
        request_capture = request_skip_reason is None
        response_capture = False
        response_streaming = False
        response_skip_reason: str | None = None
        response_headers: Any = None
        status_code: int | None = None

        async def capture_receive() -> Message:
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if request_capture and isinstance(body, bytes) and body:
                    request_body.append(body)
            return message

        async def capture_send(message: Message) -> None:
            nonlocal response_capture, response_headers, response_skip_reason, response_streaming, status_code
            if message.get("type") == "http.response.start":
                status = message.get("status")
                if isinstance(status, int):
                    status_code = status
                response_headers = message.get("headers")
                response_skip_reason = _message_skip_reason(message, self.capture_content_types, self.max_body_bytes)
                response_capture = response_skip_reason is None
            elif message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if response_capture and message.get("more_body", False) and not self.capture_streaming_responses:
                    response_streaming = True
                    response_capture = False
                    response_skip_reason = "response_streaming"
                    response_body.clear()
                elif response_capture and isinstance(body, bytes) and body:
                    response_body.append(body)
            await send(message)
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                if request_skip_reason is not None:
                    self._record_skip(
                        scope,
                        request_skip_reason,
                        status_code=status_code,
                        request_body=request_body,
                        response_body=response_body,
                        response_headers=response_headers,
                    )
                    return
                if request_body.too_large:
                    self._record_skip(
                        scope,
                        "request_body_too_large",
                        status_code=status_code,
                        request_body=request_body,
                        response_body=response_body,
                        response_headers=response_headers,
                    )
                    return
                if response_skip_reason is not None:
                    self._record_skip(
                        scope,
                        response_skip_reason,
                        status_code=status_code,
                        request_body=request_body,
                        response_body=response_body,
                        response_headers=response_headers,
                    )
                    return
                if response_body.too_large:
                    self._record_skip(
                        scope,
                        "response_body_too_large",
                        status_code=status_code,
                        request_body=request_body,
                        response_body=response_body,
                        response_headers=response_headers,
                    )
                    return
                if request_capture and response_capture and not response_streaming:
                    reason = self._record_observation(scope, request_body.chunks, response_body.chunks, status_code)
                    if reason is not None:
                        self._record_skip(
                            scope,
                            reason,
                            status_code=status_code,
                            request_body=request_body,
                            response_body=response_body,
                            response_headers=response_headers,
                        )

        await self.app(scope, capture_receive, capture_send)

    def _record_observation(
        self,
        scope: Scope,
        request_chunks: list[bytes],
        response_chunks: list[bytes],
        status_code: int | None,
    ) -> str | None:
        request_json = _decode_json(request_chunks)
        response_json = _decode_json(response_chunks)
        if request_json is None:
            return "request_json_decode"
        if response_json is None:
            return "response_json_decode"
        prompt = _path_value(request_json, self.prompt_field)
        response = _path_value(response_json, self.response_field)
        if prompt is _MISSING:
            return "prompt_field_missing"
        if response is _MISSING:
            return "response_field_missing"
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
        return None

    def _record_skip(
        self,
        scope: Scope,
        reason: str,
        *,
        status_code: int | None,
        request_body: _CaptureBuffer,
        response_body: _CaptureBuffer,
        response_headers: Any,
    ) -> None:
        if not self.skip_log:
            return
        row = {
            "event": "middleware_capture_skipped",
            "reason": reason,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": _scope_source(scope),
            "metadata": {
                **_scope_metadata(scope, status_code),
                "max_body_bytes": self.max_body_bytes,
                "prompt_field": self.prompt_field,
                "response_field": self.response_field,
                "request": _capture_summary(scope.get("headers"), request_body),
                "response": _capture_summary(response_headers, response_body),
            },
        }
        try:
            append_jsonl(self.skip_log, [row])
        except OSError:
            return


_MISSING = object()


class _CaptureBuffer:
    def __init__(self, max_body_bytes: int | None) -> None:
        self.max_body_bytes = max_body_bytes
        self.bytes_seen = 0
        self.too_large = False
        self.chunks: list[bytes] = []

    def append(self, body: bytes) -> None:
        if self.too_large:
            return
        self.bytes_seen += len(body)
        if self.max_body_bytes is not None and self.bytes_seen > self.max_body_bytes:
            self.clear()
            self.too_large = True
            return
        self.chunks.append(body)

    def clear(self) -> None:
        self.chunks.clear()


def _decode_json(chunks: list[bytes]) -> Any:
    if not chunks:
        return None
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _scope_skip_reason(scope: Scope, allowed: tuple[str, ...], max_body_bytes: int | None) -> str | None:
    headers = scope.get("headers")
    return _headers_skip_reason(headers, allowed, max_body_bytes, prefix="request")


def _message_skip_reason(message: Message, allowed: tuple[str, ...], max_body_bytes: int | None) -> str | None:
    headers = message.get("headers")
    return _headers_skip_reason(headers, allowed, max_body_bytes, prefix="response")


def _headers_skip_reason(
    headers: Any,
    allowed: tuple[str, ...],
    max_body_bytes: int | None,
    *,
    prefix: str,
) -> str | None:
    if not _content_type_allowed(_headers_content_type(headers), allowed):
        return f"{prefix}_content_type"
    if not _content_length_allowed(headers, max_body_bytes):
        return f"{prefix}_content_length"
    return None


def _headers_content_type(headers: Any) -> str | None:
    if not isinstance(headers, list):
        return None
    for key, value in headers:
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            continue
        if key.lower() == b"content-type":
            return value.decode("latin-1").split(";", 1)[0].strip().lower()
    return None


def _headers_content_length(headers: Any) -> int | None:
    if not isinstance(headers, list):
        return None
    for key, value in headers:
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            continue
        if key.lower() != b"content-length":
            continue
        try:
            length = int(value.decode("latin-1").strip())
        except ValueError:
            return None
        return length if length >= 0 else None
    return None


def _content_length_allowed(headers: Any, max_body_bytes: int | None) -> bool:
    if max_body_bytes is None:
        return True
    content_length = _headers_content_length(headers)
    return content_length is None or content_length <= max_body_bytes


def _capture_summary(headers: Any, body: _CaptureBuffer) -> dict[str, Any]:
    return {
        "content_type": _headers_content_type(headers),
        "content_length": _headers_content_length(headers),
        "bytes_seen": body.bytes_seen,
        "too_large": body.too_large,
    }


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
