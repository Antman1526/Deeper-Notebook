"""v0.8.98 — artifact source loading is concurrent, order-stable, and keeps
its 404 contract.

`artifact_sources` fetched every selected source with a sequential `await`
inside a `for` loop — an N+1 on the path of EVERY Evidence Studio generation.
The same loop was duplicated in `api/routers/studio/common.py`.

These tests pin the externally-visible contract so the concurrency change
cannot alter behaviour:

1. returned sources match the requested ids **in order**;
2. a missing source still raises 404 naming the FIRST missing id in
   `source_ids` order (not whichever request happened to fail first);
3. the no-selection path still falls back to the notebook's sources;
4. the fetches actually overlap rather than running one after another.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from deeper_notebook.exceptions import NotFoundError
from deeper_notebook.studio.generation import context as context_module


class _FakeSource:
    def __init__(self, source_id: str) -> None:
        self.id = source_id


class _Artifact:
    def __init__(self, source_ids: list[str], notebook_id: str = "notebook:n1") -> None:
        self.source_ids = source_ids
        self.notebook_id = notebook_id


@pytest.mark.asyncio
async def test_sources_are_returned_in_requested_order(monkeypatch):
    async def fake_get(source_id: str):
        # Reverse-ordered delays: a sequential implementation returns in call
        # order anyway, but a naive "collect as they finish" concurrent one
        # would scramble. This pins order explicitly.
        await asyncio.sleep(0.01 if source_id.endswith("1") else 0.001)
        return _FakeSource(source_id)

    monkeypatch.setattr(context_module.Source, "get", staticmethod(fake_get))
    artifact = _Artifact(["source:1", "source:2", "source:3"])
    result = await context_module.artifact_sources(artifact)
    assert [s.id for s in result] == ["source:1", "source:2", "source:3"]


@pytest.mark.asyncio
async def test_missing_source_raises_404_naming_the_first_missing_id(monkeypatch):
    async def fake_get(source_id: str):
        if source_id in {"source:2", "source:3"}:
            raise NotFoundError(f"missing {source_id}")
        return _FakeSource(source_id)

    monkeypatch.setattr(context_module.Source, "get", staticmethod(fake_get))
    artifact = _Artifact(["source:1", "source:2", "source:3"])
    with pytest.raises(HTTPException) as excinfo:
        await context_module.artifact_sources(artifact)
    assert excinfo.value.status_code == 404
    # First missing in source_ids order wins, not whichever failed first.
    assert "source:2" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_fetches_actually_overlap(monkeypatch):
    """Sequential loading of 6 sources at 20ms each takes >=120ms;
    concurrent loading takes roughly one delay."""
    async def fake_get(source_id: str):
        await asyncio.sleep(0.02)
        return _FakeSource(source_id)

    monkeypatch.setattr(context_module.Source, "get", staticmethod(fake_get))
    artifact = _Artifact([f"source:{i}" for i in range(6)])
    started = asyncio.get_running_loop().time()
    await context_module.artifact_sources(artifact)
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.08, f"expected overlapping fetches, took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_no_selection_falls_back_to_notebook_sources(monkeypatch):
    notebook_sources = [_FakeSource("source:a"), _FakeSource("source:b")]

    class _Notebook:
        async def get_sources(self):
            return notebook_sources

    async def fake_notebook_get(notebook_id: str):
        return _Notebook()

    monkeypatch.setattr(context_module.Notebook, "get", staticmethod(fake_notebook_get))
    artifact = _Artifact([])
    assert await context_module.artifact_sources(artifact) == notebook_sources


@pytest.mark.asyncio
async def test_router_copy_is_also_concurrent(monkeypatch):
    """`api/routers/studio/common._artifact_sources` deliberately mirrors the
    shared helper rather than calling it: the Evidence Studio API suite patches
    `Source` on THAT module, so delegating would escape the patch seam and hit
    the live database. Because the copy is intentional, its concurrency must be
    pinned separately or the two will drift.
    """
    from api.routers.studio import common as common_module

    class _SourceStub:
        @staticmethod
        async def get(source_id: str):
            await asyncio.sleep(0.02)
            return _FakeSource(source_id)

    monkeypatch.setattr(common_module, "Source", _SourceStub)
    artifact = _Artifact([f"source:{i}" for i in range(6)])
    started = asyncio.get_running_loop().time()
    result = await common_module._artifact_sources(artifact)
    elapsed = asyncio.get_running_loop().time() - started
    assert [s.id for s in result] == [f"source:{i}" for i in range(6)]
    assert elapsed < 0.08, f"router copy still sequential, took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_router_copy_keeps_the_404_contract(monkeypatch):
    from api.routers.studio import common as common_module

    class _SourceStub:
        @staticmethod
        async def get(source_id: str):
            if source_id in {"source:2", "source:3"}:
                raise NotFoundError(f"missing {source_id}")
            return _FakeSource(source_id)

    monkeypatch.setattr(common_module, "Source", _SourceStub)
    artifact = _Artifact(["source:1", "source:2", "source:3"])
    with pytest.raises(HTTPException) as excinfo:
        await common_module._artifact_sources(artifact)
    assert excinfo.value.status_code == 404
    assert "source:2" in str(excinfo.value.detail)
