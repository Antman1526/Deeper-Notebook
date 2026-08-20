"""v0.8.66 (audit H1) — regression tests for SelectiveGZipMiddleware.

The global GZipMiddleware buffered the token stream (it only exempts
`text/event-stream`, but our streams are `application/x-ndjson` / `text/plain`),
defeating real-time per-token delivery. SelectiveGZipMiddleware bypasses GZip
for the streaming endpoints while keeping it for large JSON responses.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from api.main import SelectiveGZipMiddleware, _is_streaming_path


def _build_app() -> FastAPI:
    app = FastAPI()
    # minimum_size tiny so the big-JSON route definitely crosses the threshold.
    app.add_middleware(SelectiveGZipMiddleware, minimum_size=10)

    @app.post("/api/chat/stream")
    async def chat_stream():
        async def gen():
            for i in range(8):
                yield f'{{"token": "{i}"}}\n'

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.post("/api/sources/s1/chat/sessions/x/messages")
    async def source_messages():
        async def gen():
            yield "x" * 4000  # big enough that GZip WOULD compress if applied

        return StreamingResponse(gen(), media_type="text/plain")

    @app.get("/api/notebooks")
    async def big_json():
        return JSONResponse({"data": "x" * 5000})

    return app


def test_chat_stream_not_gzipped():
    client = TestClient(_build_app())
    r = client.post("/api/chat/stream", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") != "gzip", (
        "/api/chat/stream must NOT be gzip-encoded — GZip buffers the token "
        "stream and defeats real-time delivery."
    )


def test_source_chat_messages_post_not_gzipped():
    client = TestClient(_build_app())
    r = client.post(
        "/api/sources/s1/chat/sessions/x/messages",
        headers={"accept-encoding": "gzip"},
    )
    assert r.status_code == 200
    assert r.headers.get("content-encoding") != "gzip"


def test_large_json_still_gzipped():
    """The CRUD path GZip was added for must still compress."""
    client = TestClient(_build_app())
    r = client.get("/api/notebooks", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip", (
        "Large non-streaming JSON must still be gzip-compressed."
    )


def test_is_streaming_path_matrix():
    def scope(path, method="POST"):
        return {"type": "http", "path": path, "method": method}

    assert _is_streaming_path(scope("/api/chat/stream"))
    assert _is_streaming_path(scope("/api/search/ask"))
    assert _is_streaming_path(scope("/api/search/ask/simple"))
    assert _is_streaming_path(
        scope("/api/sources/abc/chat/sessions/xyz/messages", "POST")
    )
    # A GET to a /messages listing is still gzipped (not a stream).
    assert not _is_streaming_path(
        scope("/api/sources/abc/chat/sessions/xyz/messages", "GET")
    )
    assert not _is_streaming_path(scope("/api/notebooks", "GET"))
    assert not _is_streaming_path(scope("/api/chat/execute", "POST"))
