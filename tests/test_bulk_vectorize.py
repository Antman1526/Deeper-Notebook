"""v0.7.106 — tests for POST /api/notebooks/{id}/vectorize_sources.

Exercises the bulk re-embed endpoint with stubbed domain objects so
no SurrealDB or embedding-model dependency is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import embedding as embedding_router


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    a = FastAPI()
    a.include_router(embedding_router.router, prefix="/api")
    return TestClient(a)


@pytest.fixture()
def patched_domain(monkeypatch):
    """Stub Notebook.get + model_manager + import path so the endpoint
    runs without a database or embedding model."""
    state = {"notebook": None, "has_embedding_model": True}

    async def _nb_get(_id):
        return state["notebook"]

    async def _has_embedding():
        return state["has_embedding_model"]

    monkeypatch.setattr(
        embedding_router.Notebook,
        "get",
        staticmethod(_nb_get),
    )
    monkeypatch.setattr(
        embedding_router.model_manager,
        "get_embedding_model",
        _has_embedding,
    )

    return state


def _make_source(
    sid: str,
    title: str,
    *,
    full_text: Optional[str] = None,
    embedded_chunks: int = 0,
    vectorize_returns: Optional[str] = None,
    vectorize_raises: Optional[BaseException] = None,
):
    """Build a stub Source. vectorize() returns or raises per kwargs."""
    src = SimpleNamespace(id=sid, title=title, full_text=full_text)
    src.embedded_chunks = embedded_chunks

    async def _vec():
        if vectorize_raises:
            raise vectorize_raises
        return vectorize_returns

    src.vectorize = _vec
    return src


def _make_notebook(sources, name: str = "Test"):
    nb = SimpleNamespace(id="notebook:test", name=name)

    async def _get_sources():
        return sources

    nb.get_sources = _get_sources
    return nb


def test_bulk_vectorize_404_when_notebook_missing(client, patched_domain):
    patched_domain["notebook"] = None
    r = client.post(
        "/api/notebooks/notebook:nope/vectorize_sources",
        json={"only_missing": True},
    )
    assert r.status_code == 404


def test_bulk_vectorize_400_when_no_embedding_model(client, patched_domain):
    patched_domain["notebook"] = _make_notebook([])
    patched_domain["has_embedding_model"] = False
    r = client.post(
        "/api/notebooks/notebook:test/vectorize_sources",
        json={"only_missing": True},
    )
    assert r.status_code == 400
    assert "embedding model" in r.json()["detail"].lower()


def test_bulk_vectorize_queues_all_when_only_missing_false(client, patched_domain):
    """only_missing=false must queue every source, even ones with
    existing embeddings (useful after switching embedding models)."""
    sources = [
        _make_source(
            "source:1",
            "First",
            full_text="hello",
            embedded_chunks=5,  # already embedded
            vectorize_returns="cmd:1",
        ),
        _make_source(
            "source:2",
            "Second",
            full_text="world",
            embedded_chunks=0,  # never embedded
            vectorize_returns="cmd:2",
        ),
    ]
    patched_domain["notebook"] = _make_notebook(sources)

    r = client.post(
        "/api/notebooks/notebook:test/vectorize_sources",
        json={"only_missing": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queued"] == 2
    assert body["skipped"] == 0
    assert body["failed"] == 0
    assert all(s["queued"] for s in body["sources"])


def test_bulk_vectorize_skips_already_embedded_when_only_missing_true(
    client,
    patched_domain,
):
    sources = [
        _make_source(
            "source:1",
            "Already done",
            full_text="hello",
            embedded_chunks=5,
            vectorize_returns="should-not-be-called",
        ),
        _make_source(
            "source:2",
            "Pending",
            full_text="world",
            embedded_chunks=0,
            vectorize_returns="cmd:2",
        ),
    ]
    patched_domain["notebook"] = _make_notebook(sources)

    r = client.post(
        "/api/notebooks/notebook:test/vectorize_sources",
        json={"only_missing": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queued"] == 1
    assert body["skipped"] == 1
    # The already-embedded one was skipped with the right reason
    skipped_entries = [s for s in body["sources"] if not s["queued"]]
    assert skipped_entries[0]["skip_reason"] == "already_embedded"


def test_bulk_vectorize_skips_sources_with_no_text_and_warns(
    client,
    patched_domain,
):
    """v0.7.106 — A source without full_text would no-op or error in the
    embed worker. Skip it client-side with a warning that tells the user
    to re-extract the source first."""
    sources = [
        _make_source("source:1", "Empty source", full_text=None),
        _make_source("source:2", "Empty string", full_text="   "),
        _make_source(
            "source:3",
            "Has text",
            full_text="real content",
            vectorize_returns="cmd:ok",
        ),
    ]
    patched_domain["notebook"] = _make_notebook(sources)

    r = client.post(
        "/api/notebooks/notebook:test/vectorize_sources",
        json={"only_missing": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queued"] == 1
    assert body["skipped"] == 2
    # Both no-text sources got a warning
    assert sum(1 for w in body["warnings"] if "no extracted text" in w) == 2


def test_bulk_vectorize_continues_after_submit_failure(
    client,
    patched_domain,
):
    """One source failing to queue must not abort the rest — partial
    success is the whole point of a bulk endpoint."""
    sources = [
        _make_source(
            "source:1",
            "First",
            full_text="hello",
            vectorize_raises=RuntimeError("worker queue down"),
        ),
        _make_source(
            "source:2",
            "Second",
            full_text="world",
            vectorize_returns="cmd:2",
        ),
    ]
    patched_domain["notebook"] = _make_notebook(sources)

    r = client.post(
        "/api/notebooks/notebook:test/vectorize_sources",
        json={"only_missing": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queued"] == 1
    assert body["failed"] == 1
    # Warning surfaces the actual failure cause
    assert any("worker queue down" in w for w in body["warnings"])


# ============================================================================
# v0.7.110 — Per-request cap on source count
# ============================================================================


def test_bulk_vectorize_caps_at_max_sources_with_truncation_warning(
    client,
    patched_domain,
    monkeypatch,
):
    """v0.7.110 — Notebooks larger than DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES
    get clamped to the cap with a warning. v0.7.137 reframed this as
    a `limit` clamp: the default request `limit=500` is clamped down
    to the env cap, sources beyond `offset + effective_limit` aren't
    processed in this call, and `has_more=True` signals the caller
    can paginate.

    Without the cap a 10k-source notebook would pin the request
    submitting 10k commands."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES", "3")
    sources = [
        _make_source(
            f"source:{i}",
            f"Source {i}",
            full_text="x",
            vectorize_returns=f"cmd:{i}",
        )
        for i in range(10)
    ]
    patched_domain["notebook"] = _make_notebook(sources)

    r = client.post(
        "/api/notebooks/notebook:test/vectorize_sources",
        json={"only_missing": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Only the first 3 sources got queued (env cap)
    assert body["queued"] == 3
    # v0.7.137 — Clamp warning surfaced with actionable hint.
    # The wording changed from "Notebook has X sources; processed
    # only first Y" to "Requested limit N exceeds the per-call cap
    # (M); clamped". Both mention how to escape: raise the env var
    # or paginate.
    assert any(
        "clamped" in w and "DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES" in w
        for w in body["warnings"]
    ), body["warnings"]
    # Per-source entries reflect only the processed subset
    assert len(body["sources"]) == 3
    # v0.7.137 — has_more must be True since 10 > 3 and we processed
    # only the first 3. Caller can call again with offset=3.
    assert body["has_more"] is True
    assert body["total_sources"] == 10
    assert body["offset"] == 0
    assert body["limit"] == 3  # clamped down from default 500
