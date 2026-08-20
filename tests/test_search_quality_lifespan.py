"""Task 5 — clean-lifespan drain for source-search maintenance."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from api import main


@pytest.mark.asyncio
async def test_pool_close_waits_for_pending_source_index_maintenance(
    monkeypatch,
) -> None:
    """The real teardown sequence must drain before closing the database pool."""
    from deeper_notebook.database import repository
    from deeper_notebook.domain import notebook

    drain_started = asyncio.Event()
    release_drain = asyncio.Event()
    events: list[str] = []

    async def pending_drain() -> None:
        events.append("drain-start")
        drain_started.set()
        await release_drain.wait()
        events.append("drain-finish")

    async def close_pool() -> None:
        events.append("pool-close")

    monkeypatch.setattr(
        notebook, "drain_source_search_index_maintenance", pending_drain
    )
    monkeypatch.setattr(repository, "close_pool", close_pool)

    shutdown = asyncio.create_task(
        main._close_database_pool_after_source_search_index_maintenance()
    )
    await asyncio.wait_for(drain_started.wait(), timeout=0.05)
    assert events == ["drain-start"]
    assert not shutdown.done()

    release_drain.set()
    await shutdown

    assert events == ["drain-start", "drain-finish", "pool-close"]


@pytest.mark.asyncio
async def test_pool_close_stays_bounded_and_logs_degraded_search_on_drain_timeout(
    monkeypatch,
) -> None:
    """A bounded drain failure does not hang clean shutdown or hide degraded search."""
    from deeper_notebook.database import repository
    from deeper_notebook.domain import notebook

    warnings: list[str] = []
    events: list[str] = []
    worker = asyncio.create_task(asyncio.Event().wait())

    async def timed_out_drain() -> None:
        raise TimeoutError

    async def close_pool() -> None:
        assert worker.done() and worker.cancelled()
        events.append("pool-close")

    async def quiesce() -> None:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        events.append("worker-quiesced")

    monkeypatch.setattr(
        notebook, "drain_source_search_index_maintenance", timed_out_drain
    )
    monkeypatch.setattr(
        notebook,
        "cancel_source_search_index_maintenance",
        quiesce,
        raising=False,
    )
    monkeypatch.setattr(repository, "close_pool", close_pool)
    monkeypatch.setattr(
        main.logger,
        "warning",
        lambda message, *_args: warnings.append(str(message)),
    )

    await asyncio.wait_for(
        main._close_database_pool_after_source_search_index_maintenance(), timeout=0.05
    )

    assert events == ["worker-quiesced", "pool-close"]
    assert any(
        "source-search index maintenance" in warning.lower()
        and "degraded" in warning.lower()
        and "timed out" in warning.lower()
        for warning in warnings
    )


@pytest.mark.asyncio
async def test_pool_close_logs_and_reraises_lifespan_cancellation_without_closing_early(
    monkeypatch,
) -> None:
    """Cancellation does not silently discard the durable marker or close early."""
    from deeper_notebook.database import repository
    from deeper_notebook.domain import notebook

    warnings: list[str] = []
    closed = False
    worker = asyncio.create_task(asyncio.Event().wait())

    async def cancelled_drain() -> None:
        raise asyncio.CancelledError

    async def close_pool() -> None:
        nonlocal closed
        closed = True

    async def quiesce() -> None:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    monkeypatch.setattr(
        notebook, "drain_source_search_index_maintenance", cancelled_drain
    )
    monkeypatch.setattr(
        notebook,
        "cancel_source_search_index_maintenance",
        quiesce,
        raising=False,
    )
    monkeypatch.setattr(repository, "close_pool", close_pool)
    monkeypatch.setattr(
        main.logger,
        "warning",
        lambda message, *_args: warnings.append(str(message)),
    )

    with pytest.raises(asyncio.CancelledError):
        await main._close_database_pool_after_source_search_index_maintenance()

    assert not closed
    assert worker.done() and worker.cancelled()
    assert any(
        "source-search index maintenance" in warning.lower()
        and "degraded" in warning.lower()
        and "cancel" in warning.lower()
        for warning in warnings
    )


@pytest.mark.asyncio
async def test_api_startup_reconciles_pending_source_search_marker(monkeypatch) -> None:
    """The API startup seam awaits marker reconciliation before serving requests."""
    from deeper_notebook.domain import notebook

    calls: list[str] = []

    async def reconcile() -> bool:
        calls.append("reconciled")
        return True

    monkeypatch.setattr(
        notebook, "reconcile_source_search_index_maintenance", reconcile
    )

    await main._reconcile_source_search_index_maintenance_at_startup()

    assert calls == ["reconciled"]


def test_lifespan_uses_the_drain_before_pool_close_contract() -> None:
    """The production lifespan must not bypass its ordered teardown helper."""
    source = inspect.getsource(main.lifespan)
    assert (
        "await _close_database_pool_after_source_search_index_maintenance()" in source
    )
    assert "await _reconcile_source_search_index_maintenance_at_startup()" in source
    assert source.index(
        "await _reconcile_source_search_index_maintenance_at_startup()"
    ) < source.index("await _start_knowledge_engine(app)")
