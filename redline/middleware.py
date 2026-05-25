from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from .watch import DEFAULT_WATCH_LOG, record


Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
Metadata = dict[str, Any] | Callable[[Scope, Any, Any], dict[str, Any]]


class RedlineMiddleware:
    """ASGI middleware that records JSON prompt-response pairs locally.

    Works with FastAPI and other ASGI apps without importing FastAPI. It buffers
    one HTTP request and response body, extracts configured JSON fields, and
    appends a redline observation when both prompt and response are present.
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
    ) -> None:
        self.app = app
        self.log = log
        self.prompt_field = prompt_field
        self.response_field = response_field
        self.metadata = metadata
        self.dedupe = dedupe

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_chunks: list[bytes] = []
        response_chunks: list[bytes] = []
        status_code: int | None = None

        async def capture_receive() -> Message:
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if isinstance(body, bytes) and body:
                    request_chunks.append(body)
            return message

        async def capture_send(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status = message.get("status")
                if isinstance(status, int):
                    status_code = status
            elif message.get("type") == "http.response.body":
                body = message.get("body", b"")
                if isinstance(body, bytes) and body:
                    response_chunks.append(body)
            await send(message)
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
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
        )


_MISSING = object()


def _decode_json(chunks: list[bytes]) -> Any:
    if not chunks:
        return None
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


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
