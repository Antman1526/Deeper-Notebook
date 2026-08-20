"""Task 5 — source deletion refreshes only its own BM25 indexes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deeper_notebook.domain.base import ObjectModel
from deeper_notebook.domain.notebook import Source

_SOURCE_REBUILDS = (
    "REBUILD INDEX idx_source_title ON TABLE source",
    "REBUILD INDEX idx_source_full_text ON TABLE source",
    "REBUILD INDEX idx_source_embed_chunk ON TABLE source_embedding",
    "REBUILD INDEX idx_source_insight ON TABLE source_insight",
)


def _source() -> Source:
    return Source(id="source:search-quality", title="Search quality", full_text="body")


@pytest.mark.asyncio
async def test_successful_source_delete_rebuilds_only_the_affected_search_indexes() -> (
    None
):
    """The real Source.delete path refreshes a fixed, non-user-derived whitelist."""
    calls: list[str] = []

    async def fake_repo_query(query: str, params=None):
        calls.append(query)
        return []

    async def successful_super_delete(self) -> bool:
        calls.append("__SUPER_DELETE__")
        return True

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query),
        patch.object(ObjectModel, "delete", new=successful_super_delete),
    ):
        assert await _source().delete() is True

    assert tuple(calls[-len(_SOURCE_REBUILDS) :]) == _SOURCE_REBUILDS
    assert not any("note" in query.lower() for query in _SOURCE_REBUILDS)
    assert all("search-quality" not in query for query in _SOURCE_REBUILDS)


@pytest.mark.asyncio
async def test_failed_source_delete_does_not_rebuild_any_search_index() -> None:
    """A failed primary deletion is never followed by an index rebuild."""
    calls: list[str] = []

    async def fake_repo_query(query: str, params=None):
        calls.append(query)
        return []

    async def failed_super_delete(self) -> bool:
        calls.append("__SUPER_DELETE__")
        return False

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query),
        patch.object(ObjectModel, "delete", new=failed_super_delete),
    ):
        assert await _source().delete() is False

    assert not any(query.startswith("REBUILD INDEX") for query in calls)


@pytest.mark.asyncio
async def test_rebuild_failure_keeps_successful_source_delete_and_logs_context() -> (
    None
):
    """Search may be degraded, but a completed delete must remain successful."""
    calls: list[str] = []

    async def flaky_repo_query(query: str, params=None):
        calls.append(query)
        if query == "REBUILD INDEX idx_source_full_text ON TABLE source":
            raise RuntimeError("simulated rebuild outage")
        return []

    warning = MagicMock()
    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=flaky_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
        patch("deeper_notebook.domain.notebook.logger.warning", warning),
    ):
        assert await _source().delete() is True

    assert tuple(calls[-len(_SOURCE_REBUILDS) :]) == _SOURCE_REBUILDS
    logged = " ".join(
        str(value) for call in warning.call_args_list for value in call.args
    )
    assert "idx_source_full_text" in logged
    assert "source" in logged
    assert "degraded" in logged.lower()
