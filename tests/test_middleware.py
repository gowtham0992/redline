import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from redline import RedlineMiddleware as ExportedRedlineMiddleware
from redline.io import read_jsonl_records
from redline.middleware import RedlineMiddleware


class MiddlewareTests(unittest.TestCase):
    def test_asgi_middleware_records_json_prompt_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
                message = await receive()
                request = json.loads(message["body"].decode("utf-8"))
                response = {"answer": f"reply: {request['prompt']}"}
                await send({"type": "http.response.start", "status": 200, "headers": _json_headers()})
                await send({"type": "http.response.body", "body": json.dumps(response).encode("utf-8")})

            middleware = RedlineMiddleware(app, log=str(log), response_field="answer")

            messages = asyncio.run(_call_app(middleware, {"prompt": "refund policy"}))

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].prompt, "refund policy")
            self.assertEqual(records[0].response, "reply: refund policy")
            self.assertEqual(records[0].raw["source"], "asgi:POST /generate")
            self.assertEqual(records[0].raw["metadata"]["status_code"], 200)
            self.assertEqual(messages[0]["type"], "http.response.start")
            self.assertEqual(messages[1]["type"], "http.response.body")

    def test_asgi_middleware_supports_nested_fields_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
                await receive()
                response = {"choices": [{"message": {"content": "nested answer"}}]}
                await send({"type": "http.response.start", "status": 201, "headers": _json_headers()})
                await send({"type": "http.response.body", "body": json.dumps(response).encode("utf-8")})

            middleware = RedlineMiddleware(
                app,
                log=str(log),
                prompt_field="messages.0.content",
                response_field="choices.0.message.content",
                metadata=lambda scope, request, response: {"route_name": "chat"},
            )

            asyncio.run(_call_app(middleware, {"messages": [{"content": "nested prompt"}]}))

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].prompt, "nested prompt")
            self.assertEqual(records[0].response, "nested answer")
            self.assertEqual(records[0].raw["metadata"]["route_name"], "chat")

    def test_asgi_middleware_skips_non_json_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
                await receive()
                await send({"type": "http.response.start", "status": 200, "headers": _json_headers()})
                await send({"type": "http.response.body", "body": b"not json"})

            middleware = RedlineMiddleware(app, log=str(log))

            asyncio.run(_call_app(middleware, {"prompt": "hello"}))

            self.assertFalse(log.exists())

    def test_asgi_middleware_skips_non_json_content_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
                await receive()
                await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"plain response"})

            middleware = RedlineMiddleware(app, log=str(log))

            asyncio.run(_call_app(middleware, {"prompt": "hello"}, content_type=b"text/plain"))

            self.assertFalse(log.exists())

    def test_asgi_middleware_skips_oversized_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
                await receive()
                response = {"response": "x" * 256}
                await send({"type": "http.response.start", "status": 200, "headers": _json_headers()})
                await send({"type": "http.response.body", "body": json.dumps(response).encode("utf-8")})

            middleware = RedlineMiddleware(app, log=str(log), max_body_bytes=64)

            asyncio.run(_call_app(middleware, {"prompt": "hello"}))

            self.assertFalse(log.exists())

    def test_asgi_middleware_rejects_invalid_body_limit(self) -> None:
        async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            return None

        with self.assertRaisesRegex(ValueError, "max_body_bytes"):
            RedlineMiddleware(app, max_body_bytes=0)

    def test_asgi_middleware_accepts_json_suffix_content_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "observed.jsonl"

            async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
                await receive()
                response = {"response": "json suffix"}
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [(b"content-type", b"application/vnd.api+json")],
                    }
                )
                await send({"type": "http.response.body", "body": json.dumps(response).encode("utf-8")})

            middleware = RedlineMiddleware(app, log=str(log))

            asyncio.run(_call_app(middleware, {"prompt": "hello"}, content_type=b"application/vnd.api+json"))

            records = read_jsonl_records(log, "prompt", "response")
            self.assertEqual(records[0].response, "json suffix")

    def test_asgi_middleware_exports_from_package_root(self) -> None:
        self.assertIs(ExportedRedlineMiddleware, RedlineMiddleware)


async def _call_app(
    app: Any,
    body: dict[str, Any],
    *,
    content_type: bytes = b"application/json",
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {
            "type": "http.request",
            "body": json.dumps(body).encode("utf-8"),
            "more_body": False,
        }

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": "/generate",
            "headers": [(b"content-type", content_type)],
        },
        receive,
        send,
    )
    return sent


def _json_headers() -> list[tuple[bytes, bytes]]:
    return [(b"content-type", b"application/json")]


if __name__ == "__main__":
    unittest.main()
