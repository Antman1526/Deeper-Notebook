"""v0.8.74 — tests for the notebook suggested-starter-questions endpoint
(improvement roadmap, Batch 1).

The endpoint generates corpus-grounded starter questions via one bounded LLM
call and MUST degrade to an empty list on any failure (no sources, no model,
LLM error) so it can never block opening a notebook.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.routers.notebooks import get_suggested_questions


class _FakeSource:
    def __init__(self, title, topics=None):
        self.title = title
        self.topics = topics or []


class _FakeNotebook:
    name = "ML Reading List"
    description = "Papers on deep learning"

    def __init__(self, sources):
        self._sources = sources

    async def get_sources(self):
        return self._sources


class _FakeResp:
    def __init__(self, content):
        self.content = content


def _patch_model(content):
    chain = AsyncMock()
    chain.ainvoke = AsyncMock(return_value=_FakeResp(content))
    return patch(
        "deeper_notebook.ai.provision.provision_langchain_model",
        new=AsyncMock(return_value=chain),
    )


@pytest.mark.asyncio
async def test_parses_and_cleans_questions():
    nb = _FakeNotebook(
        [_FakeSource("Deep Learning", ["ml", "ai"]), _FakeSource("RAG systems")]
    )
    llm_out = (
        "What is deep learning?\n"
        "- How does RAG improve answers?\n"
        "1. What are embeddings used for?\n"
        "This line is not a question\n"
        '"Why do transformers scale well?"'
    )
    with (
        patch("api.routers.notebooks.Notebook.get", new=AsyncMock(return_value=nb)),
        _patch_model(llm_out),
    ):
        out = await get_suggested_questions("notebook:x", limit=4)

    qs = out["questions"]
    assert qs[0] == "What is deep learning?"
    assert "How does RAG improve answers?" in qs  # bullet stripped
    assert "What are embeddings used for?" in qs  # numbering stripped
    assert "Why do transformers scale well?" in qs  # quotes stripped
    assert "This line is not a question" not in qs  # no '?' → dropped
    assert all("?" in q for q in qs)
    assert len(qs) <= 4


@pytest.mark.asyncio
async def test_respects_limit():
    nb = _FakeNotebook([_FakeSource("S1")])
    llm_out = "\n".join(f"Question number {i}?" for i in range(10))
    with (
        patch("api.routers.notebooks.Notebook.get", new=AsyncMock(return_value=nb)),
        _patch_model(llm_out),
    ):
        out = await get_suggested_questions("notebook:x", limit=3)
    assert len(out["questions"]) == 3


@pytest.mark.asyncio
async def test_empty_when_no_sources():
    nb = _FakeNotebook([])
    with patch("api.routers.notebooks.Notebook.get", new=AsyncMock(return_value=nb)):
        out = await get_suggested_questions("notebook:x", limit=4)
    assert out == {"questions": []}


@pytest.mark.asyncio
async def test_degrades_to_empty_on_llm_error():
    nb = _FakeNotebook([_FakeSource("S1", ["t"])])
    with (
        patch("api.routers.notebooks.Notebook.get", new=AsyncMock(return_value=nb)),
        patch(
            "deeper_notebook.ai.provision.provision_langchain_model",
            new=AsyncMock(side_effect=RuntimeError("no model configured")),
        ),
    ):
        out = await get_suggested_questions("notebook:x", limit=4)
    assert out == {"questions": []}
