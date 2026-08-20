"""v0.8.67w — unit tests for HNSW / KNN query operators in memory recall.

This verifies that the memory recall layer queries utilize the proper
SurrealDB KNN operator format `<|limit|>` based on the maximum limits configured:
- _MAX_FACTS = 15
- _MAX_PREFERENCES = 10
- _MAX_EPISODES = 2
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.utils import memory_recall
from deeper_notebook.utils.memory_recall import (
    recall_memory,
    recall_relevant_memory,
)


@pytest.mark.asyncio
async def test_recall_relevant_memory_hnsw_operator(monkeypatch):
    """Assert that recall_relevant_memory builds queries using the f-string
    interpolated <|K|> operators for facts, preferences, and episodes.
    """
    captured_queries = []

    async def _mock_safe_select(query, vars):
        captured_queries.append((query, vars))
        return []

    # Mock the embedding model so it returns a dummy embedding vector
    class FakeEmbedModel:
        async def aembed(self, texts):
            return [[0.1] * 768]

    # Monkeypatch model_manager to return our FakeEmbedModel
    class FakeModelManager:
        async def get_embedding_model(self):
            return FakeEmbedModel()

    monkeypatch.setattr(
        "deeper_notebook.ai.models.model_manager",
        FakeModelManager(),
    )
    monkeypatch.setattr(memory_recall, "_safe_select", _mock_safe_select)

    # Trigger semantic/relevant recall
    await recall_relevant_memory("test query")

    # Since _safe_select returned [], we expect all three tables to be queried
    assert len(captured_queries) == 3

    # Check fact query
    fact_q, fact_vars = captured_queries[0]
    assert "FROM memory_fact" in fact_q
    assert "embedding <|15|> $q" in fact_q
    assert fact_vars["limit"] == 15

    # Check preference query
    pref_q, pref_vars = captured_queries[1]
    assert "FROM memory_preference" in pref_q
    assert "embedding <|10|> $q" in pref_q
    assert pref_vars["limit"] == 10

    # Check episode query
    ep_q, ep_vars = captured_queries[2]
    assert "FROM memory_episode" in ep_q
    assert "embedding <|2|> $q" in ep_q
    assert ep_vars["limit"] == 2
