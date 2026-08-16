from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_shims.memory_shim import build_app
from fastapi.testclient import TestClient


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


def test_models_use_canonical_owner_identity():
    app = build_app(mem_client=_fake_memory_client())
    with TestClient(app) as c:
        body = c.get("/models").json()

    assert {model["owned_by"] for model in body["data"]} == {
        "deeper-notebook"
    }


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
    # starlette's TestClient prefers httpx2 when it is installed and raises
    # httpx2.InvalidURL, an unrelated class from httpx.InvalidURL. The build
    # venv already has httpx2; the test venv does not yet. Catch both so the
    # refusal is recognized under either client.
    try:
        from httpx2 import InvalidURL as InvalidURL2
    except ImportError:  # pragma: no cover - depends on the installed client
        InvalidURL2 = InvalidURL
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
            except (InvalidURL, InvalidURL2):
                # the client refused to send → input was rejected before reaching us.
                continue
            assert r.status_code in (400, 404, 405), (
                f"id={bad!r} returned {r.status_code}, expected 4xx"
            )
    mem.delete.assert_not_called()


# ---------------------------------------------------------- ONP v0.5 Capture Inbox

def test_capture_approve_calls_mem_client_add_with_source_metadata():
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.post("/api/memory/capture/approve", json={
            "text": "User read the Self-RAG paper",
            "source_app": "Safari",
            "event_id": "evt-abc",
            "ts": "2026-05-12T14:30:00Z",
            "kind": "fact",
        })
        assert r.status_code == 200
        mem.add.assert_called_once()
        call = mem.add.call_args
        # mem0 add scoped to single user (single-user desktop)
        assert call.kwargs["user_id"] == "local"
        assert call.kwargs["messages"] == "User read the Self-RAG paper"
        # source attribution baked into metadata so we can trace facts back
        md = call.kwargs["metadata"]
        assert md["kind"] == "fact"
        assert md["source"] == "openchronicle"
        assert md["source_app"] == "Safari"
        assert md["source_event_id"] == "evt-abc"


def test_capture_approve_rejects_empty_text():
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.post("/api/memory/capture/approve", json={"text": "", "kind": "fact"})
        assert r.status_code == 400
        mem.add.assert_not_called()


def test_capture_approve_rejects_invalid_kind():
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.post("/api/memory/capture/approve",
                   json={"text": "hi", "kind": "banana"})
        assert r.status_code == 400
        mem.add.assert_not_called()


# ---------------------------------------------------------- v0.5.8 Memory edit

def test_memory_update_calls_mem_client_update():
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.post("/api/memory/update", json={
            "kind": "fact", "id": "abc-123", "text": "user prefers tabs"
        })
        assert r.status_code == 200
        mem.update.assert_called_once()
        # Full record id is reconstructed from kind + id
        call = mem.update.call_args
        assert call.kwargs["memory_id"] == "memory_fact:abc-123"
        assert call.kwargs["data"] == "user prefers tabs"


def test_memory_update_accepts_full_record_id():
    """If the caller passes a full id like 'memory_fact:abc', we pass it
    through unchanged — useful for the dashboard's search results where the
    full id is already known."""
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        r = c.post("/api/memory/update", json={
            "kind": "fact", "id": "memory_fact:xyz", "text": "y"
        })
        assert r.status_code == 200
        call = mem.update.call_args
        assert call.kwargs["memory_id"] == "memory_fact:xyz"


def test_memory_update_rejects_missing_fields():
    mem = _fake_memory_client()
    app = build_app(mem_client=mem)
    with TestClient(app) as c:
        for bad in [
            {"kind": "fact", "id": "abc"},               # no text
            {"kind": "fact", "text": "x"},                # no id
            {"id": "abc", "text": "x"},                   # no kind
            {"kind": "banana", "id": "abc", "text": "x"}, # invalid kind
        ]:
            r = c.post("/api/memory/update", json=bad)
            assert r.status_code == 400
        mem.update.assert_not_called()
