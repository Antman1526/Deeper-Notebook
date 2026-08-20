"""v0.7.137 — pagination on POST /notebooks/{id}/vectorize_sources.

Hermetic — no SurrealDB, no surreal-commands worker. Notebook +
model_manager + commands import are patched so the test exercises
only the pagination semantics.

What this pins:
  * offset/limit defaults preserve pre-v0.7.137 behavior
  * offset+limit correctly slice the source list
  * has_more flag toggles based on remaining items
  * limit > DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES is clamped with warning
  * negative offset / limit < 1 / limit > 2000 are rejected (422)
  * X-Total-Count / X-Offset / X-Limit response headers match
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeSource:
    def __init__(self, idx: int):
        # Use a unique ID per fake source so the dedup-by-id logic
        # inside the handler doesn't collapse them.
        self.id = f"source:fake{idx:04d}"
        self.title = f"Source {idx}"
        self.full_text = f"text {idx}"


class _FakeNotebook:
    """Minimum surface needed by the handler: id + name + async
    get_sources() returning a list of source-like objects."""

    def __init__(self, source_count: int):
        self.id = "notebook:fake"
        self.name = "Test Notebook"
        self._sources = [_FakeSource(i) for i in range(source_count)]

    async def get_sources(self):
        return list(self._sources)


def _make_client(notebook: _FakeNotebook | None):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routers.embedding import router

    app = FastAPI()
    app.include_router(router)

    # Stack of patchers we'll start in each test fixture (the
    # `with patch(...)` form is awkward when we need ~4 patches per
    # test, so we manage them manually).
    patchers = [
        patch(
            "deeper_notebook.domain.notebook.Notebook.get",
            AsyncMock(return_value=notebook),
        ),
        patch(
            "deeper_notebook.ai.models.model_manager.get_embedding_model",
            AsyncMock(return_value=MagicMock()),  # truthy = configured
        ),
        # The handler imports commands.embedding_commands inside a
        # try block; that import itself can succeed in tests so we
        # don't need to mock it. But submit_command would talk to
        # SurrealDB — patch that.
        patch(
            "commands.embedding_commands.submit_command",
            return_value="command:fake_id",
            create=True,
        ),
        # The handler calls Source.vectorize() in the loop — short-
        # circuit that.
        patch(
            "deeper_notebook.domain.notebook.Source.vectorize",
            AsyncMock(return_value="command:fake_id"),
        ),
        # has_embeddings() is checked when only_missing=True. Force
        # False so every source gets queued (simpler test math).
        patch(
            "deeper_notebook.domain.notebook.Source.has_embeddings",
            AsyncMock(return_value=False),
            create=True,
        ),
    ]
    for p in patchers:
        p.start()
    return TestClient(app), patchers


def _stop(patchers):
    for p in patchers:
        p.stop()


# ---------------------------------------------------------------------- #
# Pagination defaults
# ---------------------------------------------------------------------- #


class TestVectorizePaginationDefaults:
    """v0.7.137 — when offset/limit aren't passed, the endpoint
    behaves like pre-pagination v0.7.106 (first 500 sources, or
    however many exist)."""

    def test_small_notebook_one_page(self):
        nb = _FakeNotebook(source_count=12)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources",
                json={"only_missing": False},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total_sources"] == 12
            assert body["offset"] == 0
            assert body["limit"] == 500  # default
            assert body["has_more"] is False
            assert r.headers["X-Total-Count"] == "12"
            assert r.headers["X-Offset"] == "0"
            assert r.headers["X-Limit"] == "500"
        finally:
            _stop(patchers)

    def test_large_notebook_default_first_500(self):
        """A 750-source notebook without offset/limit should process
        the first 500 and report has_more=True so the caller can page."""
        nb = _FakeNotebook(source_count=750)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources",
                json={"only_missing": False},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total_sources"] == 750
            assert body["offset"] == 0
            assert body["limit"] == 500
            assert body["has_more"] is True
        finally:
            _stop(patchers)


# ---------------------------------------------------------------------- #
# offset semantics
# ---------------------------------------------------------------------- #


class TestVectorizePaginationOffsetSlicing:
    def test_offset_pages_to_remaining_sources(self):
        nb = _FakeNotebook(source_count=750)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?offset=500&limit=500",
                json={"only_missing": False},
            )
            body = r.json()
            # We requested offset=500, limit=500. Only 250 sources remain
            # in that slice (750 - 500 = 250).
            assert body["total_sources"] == 750
            assert body["offset"] == 500
            assert body["limit"] == 500
            assert body["has_more"] is False  # 500 + 250 = 750 = total
            assert body["queued"] + body["skipped"] + body["failed"] == 250
        finally:
            _stop(patchers)

    def test_offset_beyond_total_returns_empty_no_error(self):
        nb = _FakeNotebook(source_count=10)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?offset=100&limit=50",
                json={"only_missing": False},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["queued"] == 0
            assert body["has_more"] is False
            assert r.headers["X-Total-Count"] == "10"
        finally:
            _stop(patchers)


# ---------------------------------------------------------------------- #
# limit ceiling
# ---------------------------------------------------------------------- #


class TestVectorizeLimitClamping:
    def test_limit_above_env_cap_is_clamped_with_warning(self, monkeypatch):
        """limit=2000 with default cap=500 → clamp to 500 + warning."""
        monkeypatch.setenv("DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES", "500")
        nb = _FakeNotebook(source_count=1500)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?limit=2000",
                json={"only_missing": False},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["limit"] == 500  # clamped down to the env cap
            assert any("clamped" in w or "exceeds" in w for w in body["warnings"]), (
                f"Expected clamp warning, got {body['warnings']}"
            )
        finally:
            _stop(patchers)

    def test_env_cap_can_be_raised(self, monkeypatch):
        """Operators with bigger notebooks can raise DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES."""
        monkeypatch.setenv("DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES", "1500")
        nb = _FakeNotebook(source_count=1500)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?limit=1500",
                json={"only_missing": False},
            )
            body = r.json()
            assert body["limit"] == 1500  # not clamped
            assert body["has_more"] is False  # all 1500 in one call
            # No clamp warning
            assert not any("clamped" in w for w in body["warnings"])
        finally:
            _stop(patchers)


# ---------------------------------------------------------------------- #
# Query validation
# ---------------------------------------------------------------------- #


class TestVectorizeQueryValidation:
    """FastAPI's Query validation should reject malformed values
    BEFORE any backend work happens. Returns 422 from the
    framework, not 500 from a downstream catch."""

    def test_negative_offset_rejected(self):
        nb = _FakeNotebook(source_count=10)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?offset=-1",
                json={"only_missing": False},
            )
            assert r.status_code == 422
        finally:
            _stop(patchers)

    def test_zero_limit_rejected(self):
        nb = _FakeNotebook(source_count=10)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?limit=0",
                json={"only_missing": False},
            )
            assert r.status_code == 422
        finally:
            _stop(patchers)

    def test_huge_limit_rejected(self):
        """The framework-level cap (2000) defends against pathological
        callers requesting limit=1_000_000."""
        nb = _FakeNotebook(source_count=10)
        client, patchers = _make_client(nb)
        try:
            r = client.post(
                "/notebooks/notebook:fake/vectorize_sources?limit=999999",
                json={"only_missing": False},
            )
            assert r.status_code == 422
        finally:
            _stop(patchers)
