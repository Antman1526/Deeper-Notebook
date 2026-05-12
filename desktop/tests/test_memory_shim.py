from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from desktop_shims.memory_shim import build_app


def _fake_memory_client():
    """Memory mock that returns canned search results."""
    client = MagicMock()
    client.search.return_value = [
        {"id": "fact:1", "text": "user likes coffee", "score": 0.95,
         "metadata": {"kind": "fact", "scope": "user"},
         "confidence": 0.9, "created_at": "2026-05-10T00:00:00Z"},
        {"id": "pref:1", "text": "bullet points", "score": 0.85,
         "metadata": {"kind": "preference", "scope": "user"},
         "confidence": 0.85, "created_at": "2026-05-09T00:00:00Z"},
    ]
    return client


def test_health_returns_200():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_relevant_returns_topk_records():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.get("/api/memory/relevant?topic=coffee&k=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["records"]) == 2
        assert body["records"][0]["text"] == "user likes coffee"


def test_relevant_empty_topic_returns_200():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.get("/api/memory/relevant?topic=&k=5")
        assert r.status_code == 200


def test_delete_translates_kind_to_table_prefix():
    """`/api/memory/fact/abc` must dispatch to `memory_id='memory_fact:abc'` —
    `fact:` would point at a non-existent SurrealDB table."""
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.delete("/api/memory/fact/abc-123")
        assert r.status_code == 200
        mem.delete.assert_called_once_with(memory_id="memory_fact:abc-123")


def test_delete_rejects_invalid_kind():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        r = c.delete("/api/memory/banana/abc")
        assert r.status_code == 400
        assert r.json()["detail"] == "invalid kind"


def test_delete_rejects_injection_in_id():
    """id is interpolated into SurrealQL downstream — reject anything outside
    the safe character whitelist. Some bad inputs (newlines, control chars) are
    rejected by httpx before they hit the server, which is even better
    (defense in depth)."""
    from httpx import InvalidURL
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    bad_ids = [
        "abc'; DROP TABLE memory_fact;",
        "abc def",
        "abc\nDELETE memory_fact",
        "abc:other_id",  # colon would smuggle a second record-id
        "",
    ]
    with TestClient(app) as c:
        for bad in bad_ids:
            try:
                r = c.delete(f"/api/memory/fact/{bad}")
            except InvalidURL:
                # httpx refused to send → input was rejected before reaching us.
                continue
            assert r.status_code in (400, 404, 405), (
                f"id={bad!r} returned {r.status_code}, expected 4xx"
            )
    mem.delete.assert_not_called()
