"""Task 5 — source deletion refreshes only its own BM25 indexes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deeper_notebook.domain.base import ObjectModel
from deeper_notebook.domain.notebook import (
    Source,
    _schedule_source_search_index_maintenance,
    _source_search_index_maintenance_state,
    _wait_for_source_search_index_maintenance,
    drain_source_search_index_maintenance,
    reconcile_source_search_index_maintenance,
)
from deeper_notebook.exceptions import DatabaseOperationError

_SOURCE_REBUILDS = (
    "REBUILD INDEX idx_source_title ON TABLE source",
    "REBUILD INDEX idx_source_full_text ON TABLE source",
    "REBUILD INDEX idx_source_embed_chunk ON TABLE source_embedding",
    "REBUILD INDEX idx_source_insight ON TABLE source_insight",
)


def _source() -> Source:
    return Source(id="source:search-quality", title="Search quality", full_text="body")


@pytest.fixture(autouse=True)
def _stub_durable_marker_protocol_for_existing_delete_fixtures(monkeypatch, request):
    """Keep legacy delete fixtures focused on their own query behavior.

    Marker-specific regressions below exercise the real protocol directly. The
    pre-existing rebuild fixtures intentionally mock only rebuild queries, so
    they provide a complete in-memory marker protocol instead of leaking into
    the repository pool after their patches end.
    """
    marker_tests = {
        "test_marker_write_failure_aborts_before_any_source_delete_work",
        "test_cancellation_after_marker_write_leaves_marker_for_startup_reconciliation",
        "test_newer_marker_token_gets_a_trailing_pass_before_exact_cas_clear",
        "test_startup_reconciliation_rebuilds_a_persisted_marker_before_serving",
    }
    if request.node.name in marker_tests:
        return

    state: dict[str, str | int | None] = {"token": None, "generation": 0}

    async def mark() -> str:
        state["generation"] = int(state["generation"]) + 1
        state["token"] = f"fixture-marker-{state['generation']}"
        return str(state["token"])

    async def pending() -> str | None:
        return state["token"]

    async def clear(token: str) -> bool:
        if state["token"] != token:
            return False
        state["token"] = None
        return True

    monkeypatch.setattr(
        "deeper_notebook.domain.notebook._mark_source_search_rebuild_pending", mark
    )
    monkeypatch.setattr(
        "deeper_notebook.domain.notebook._pending_source_search_rebuild_token",
        pending,
    )
    monkeypatch.setattr(
        "deeper_notebook.domain.notebook._clear_source_search_rebuild_marker",
        clear,
    )


@pytest.mark.asyncio
async def test_shutdown_drain_waits_for_pending_maintenance() -> None:
    """Clean shutdown must hold the pool open until scheduled work finishes."""
    rebuild_started = asyncio.Event()
    release_rebuild = asyncio.Event()

    async def blocking_repo_query(query: str, params=None):
        if query.startswith("REBUILD INDEX"):
            rebuild_started.set()
            await release_rebuild.wait()
        return []

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=blocking_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
    ):
        try:
            assert await _source().delete() is True
            await asyncio.wait_for(rebuild_started.wait(), timeout=0.05)
            drain_task = asyncio.create_task(drain_source_search_index_maintenance())
            await asyncio.sleep(0)
            assert not drain_task.done()
        finally:
            release_rebuild.set()
        await drain_task


@pytest.mark.asyncio
async def test_marker_write_failure_aborts_before_any_source_delete_work() -> None:
    """The durable receipt is written before file or database deletion begins."""
    calls: list[str] = []
    super_delete = AsyncMock(return_value=True)

    async def unavailable_marker(query: str, params=None):
        calls.append(query)
        if query.startswith("UPSERT open_notebook:source_search_rebuild_pending"):
            raise RuntimeError("marker unavailable")
        return []

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=unavailable_marker),
        patch.object(ObjectModel, "delete", new=super_delete),
    ):
        with pytest.raises(
            DatabaseOperationError, match="source-search rebuild marker"
        ):
            await _source().delete()

    assert calls == [
        "UPSERT open_notebook:source_search_rebuild_pending SET "
        "source_search_rebuild_pending = true, "
        "source_search_rebuild_token = $rebuild_token RETURN AFTER;"
    ]
    super_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_after_marker_write_leaves_marker_for_startup_reconciliation() -> (
    None
):
    """A forced-stop window cannot erase the repair receipt before deletion work."""
    marker: dict[str, str | None] = {"token": None}
    super_delete = AsyncMock(return_value=True)

    async def crash_after_marker(query: str, params=None):
        if query.startswith("UPSERT open_notebook:source_search_rebuild_pending"):
            marker["token"] = params["rebuild_token"]
            return [{"source_search_rebuild_token": marker["token"]}]
        if query.startswith("DELETE source_embedding"):
            raise asyncio.CancelledError
        return []

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=crash_after_marker),
        patch.object(ObjectModel, "delete", new=super_delete),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _source().delete()

    assert marker["token"] is not None
    super_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_newer_marker_token_gets_a_trailing_pass_before_exact_cas_clear() -> None:
    """A delete arriving mid-pass cannot be cleared by the older pass."""
    first_rebuild_started = asyncio.Event()
    release_first_rebuild = asyncio.Event()
    marker: dict[str, str | None] = {"token": "first"}
    rebuilds: list[str] = []
    clears: list[str] = []

    async def marker_aware_repo_query(query: str, params=None):
        if query.startswith("SELECT source_search_rebuild_token"):
            return (
                []
                if marker["token"] is None
                else [{"source_search_rebuild_token": marker["token"]}]
            )
        if query.startswith("REBUILD INDEX"):
            rebuilds.append(query)
            if len(rebuilds) == 1:
                first_rebuild_started.set()
                await release_first_rebuild.wait()
            return []
        if query.startswith("UPDATE open_notebook:source_search_rebuild_pending"):
            expected = params["rebuild_token"]
            clears.append(expected)
            if marker["token"] == expected:
                marker["token"] = None
                return [{"source_search_rebuild_pending": False}]
            return []
        raise AssertionError(f"unexpected query: {query}")

    with patch(
        "deeper_notebook.domain.notebook.repo_query", new=marker_aware_repo_query
    ):
        _schedule_source_search_index_maintenance()
        await asyncio.wait_for(first_rebuild_started.wait(), timeout=0.05)
        marker["token"] = "second"
        release_first_rebuild.set()
        assert await drain_source_search_index_maintenance() is True

    assert marker["token"] is None
    assert clears == ["first", "second"]
    assert tuple(rebuilds) == _SOURCE_REBUILDS * 2


@pytest.mark.asyncio
async def test_startup_reconciliation_rebuilds_a_persisted_marker_before_serving() -> (
    None
):
    """A marker left by a forced kill is reconciled without a new delete."""
    marker: dict[str, str | None] = {"token": "crash-window"}
    rebuilds: list[str] = []

    async def marker_aware_repo_query(query: str, params=None):
        if query.startswith("SELECT source_search_rebuild_token"):
            return (
                []
                if marker["token"] is None
                else [{"source_search_rebuild_token": marker["token"]}]
            )
        if query.startswith("REBUILD INDEX"):
            rebuilds.append(query)
            return []
        if query.startswith("UPDATE open_notebook:source_search_rebuild_pending"):
            if marker["token"] == params["rebuild_token"]:
                marker["token"] = None
                return [{"source_search_rebuild_pending": False}]
            return []
        raise AssertionError(f"unexpected query: {query}")

    with patch(
        "deeper_notebook.domain.notebook.repo_query", new=marker_aware_repo_query
    ):
        assert await reconcile_source_search_index_maintenance() is True

    assert marker["token"] is None
    assert tuple(rebuilds) == _SOURCE_REBUILDS


@pytest.mark.asyncio
async def test_successful_source_delete_returns_without_awaiting_index_rebuild() -> (
    None
):
    """Irreversible deletion must not be held hostage by index maintenance."""
    rebuild_started = asyncio.Event()
    allow_rebuild = asyncio.Event()

    async def blocking_repo_query(query: str, params=None):
        if query.startswith("REBUILD INDEX"):
            rebuild_started.set()
            await allow_rebuild.wait()
        return []

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=blocking_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
    ):
        try:
            assert await asyncio.wait_for(_source().delete(), timeout=0.05) is True
            await asyncio.wait_for(rebuild_started.wait(), timeout=0.05)
        finally:
            allow_rebuild.set()
        await _wait_for_source_search_index_maintenance()


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
        await _wait_for_source_search_index_maintenance()

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
        await _wait_for_source_search_index_maintenance()

    assert tuple(calls[-len(_SOURCE_REBUILDS) :]) == _SOURCE_REBUILDS
    logged = " ".join(
        str(value) for call in warning.call_args_list for value in call.args
    )
    assert "idx_source_full_text" in logged
    assert "source" in logged
    assert "degraded" in logged.lower()


@pytest.mark.asyncio
async def test_cancelling_a_request_after_delete_keeps_maintenance_independent() -> (
    None
):
    """Caller cancellation after the irreversible delete cannot own the rebuild."""
    post_sweep_started = asyncio.Event()
    release_post_sweep = asyncio.Event()
    rebuild_started = asyncio.Event()
    embedding_deletes = 0
    rebuilds: list[str] = []

    async def fake_repo_query(query: str, params=None):
        nonlocal embedding_deletes
        if query == "DELETE source_embedding WHERE source = $source_id":
            embedding_deletes += 1
            if embedding_deletes == 2:
                post_sweep_started.set()
                await release_post_sweep.wait()
        if query.startswith("REBUILD INDEX"):
            rebuilds.append(query)
            rebuild_started.set()
        return []

    delete_task = None
    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
    ):
        try:
            delete_task = asyncio.create_task(_source().delete())
            await asyncio.wait_for(post_sweep_started.wait(), timeout=0.05)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(rebuild_started.wait(), timeout=0.01)
            delete_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await delete_task
            await asyncio.wait_for(rebuild_started.wait(), timeout=0.05)
            await _wait_for_source_search_index_maintenance()
        finally:
            release_post_sweep.set()

    assert tuple(rebuilds) == _SOURCE_REBUILDS


@pytest.mark.asyncio
async def test_deletes_during_a_pass_coalesce_to_one_serial_trailing_pass() -> None:
    """Four successful deletes do not overlap or multiply the fixed rebuilds."""
    first_rebuild_started = asyncio.Event()
    release_first_rebuild = asyncio.Event()
    rebuilds: list[str] = []
    active_rebuilds = 0
    max_active_rebuilds = 0

    async def fake_repo_query(query: str, params=None):
        nonlocal active_rebuilds, max_active_rebuilds
        if query.startswith("REBUILD INDEX"):
            rebuilds.append(query)
            active_rebuilds += 1
            max_active_rebuilds = max(max_active_rebuilds, active_rebuilds)
            try:
                if len(rebuilds) == 1:
                    first_rebuild_started.set()
                    await release_first_rebuild.wait()
            finally:
                active_rebuilds -= 1
        return []

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
    ):
        assert await _source().delete() is True
        await asyncio.wait_for(first_rebuild_started.wait(), timeout=0.05)
        assert await asyncio.gather(*(_source().delete() for _ in range(3))) == [
            True,
            True,
            True,
        ]
        release_first_rebuild.set()
        await _wait_for_source_search_index_maintenance()

    assert max_active_rebuilds == 1
    assert tuple(rebuilds) == _SOURCE_REBUILDS * 2


@pytest.mark.asyncio
async def test_rebuild_timeouts_log_exact_context_without_unhandled_task_failure() -> (
    None
):
    """Each index gets its own bounded wait; the detached task still resolves."""
    started: list[str] = []

    async def timing_out_repo_query(query: str, params=None):
        if query.startswith("REBUILD INDEX"):
            started.append(query)
            await asyncio.Event().wait()
        return []

    warning = MagicMock()
    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=timing_out_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
        patch("deeper_notebook.domain.notebook._SOURCE_SEARCH_REBUILD_TIMEOUT_S", 0.01),
        patch("deeper_notebook.domain.notebook.logger.warning", warning),
    ):
        assert await _source().delete() is True
        await asyncio.wait_for(_wait_for_source_search_index_maintenance(), timeout=0.2)

    assert tuple(started) == _SOURCE_REBUILDS
    logged = " ".join(
        str(value) for call in warning.call_args_list for value in call.args
    )
    assert "timed out" in logged.lower()
    for table, index in (
        ("source", "idx_source_title"),
        ("source", "idx_source_full_text"),
        ("source_embedding", "idx_source_embed_chunk"),
        ("source_insight", "idx_source_insight"),
    ):
        assert table in logged
        assert index in logged


@pytest.mark.asyncio
async def test_completed_maintenance_releases_its_strong_task_reference() -> None:
    """Loop-owned state keeps a task only while it can still do work."""

    async def fake_repo_query(query: str, params=None):
        return []

    with (
        patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query),
        patch.object(ObjectModel, "delete", new=AsyncMock(return_value=True)),
    ):
        assert await _source().delete() is True
        await _wait_for_source_search_index_maintenance()

    assert _source_search_index_maintenance_state().task is None
