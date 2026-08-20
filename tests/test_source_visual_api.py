from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from deeper_notebook.source_visuals.contracts import SourceVisualRecord
from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepositoryError,
)
from deeper_notebook.source_visuals.storage import SourceVisualStorageError

UTC = timezone.utc
NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)
SOURCE_SHA = "a" * 64
ASSET_SHA = "b" * 64


def _record() -> SourceVisualRecord:
    return SourceVisualRecord(
        source_id="source:one",
        source_updated_at=NOW,
        source_file_sha256="c" * 64,
        content_sha256=SOURCE_SHA,
        asset_sha256=ASSET_SHA,
        asset_relpath="aa/" + SOURCE_SHA + "/" + ASSET_SHA + ".webp",
        origin="embedded",
        source_locator={"page": 1},
        extractor_version="source-visual-v1",
        alt_text="Embedded image from Source one",
        width=640,
        height=360,
        mime_type="image/webp",
        created_at=NOW,
        updated_at=NOW,
    )


def _authority():
    return SimpleNamespace(
        source_id="source:one",
        source_updated_at=NOW,
        content_sha256=SOURCE_SHA,
        extractor_version="source-visual-v1",
    )


class _Repository:
    def __init__(self, record: SourceVisualRecord | None = None):
        self.record = record
        self.list_calls = []

    async def list_current(self, revisions):
        self.list_calls.append(revisions)
        return {"source:one": self.record} if self.record is not None else {}


class _Store:
    def __init__(self, body: bytes = b"webp-bytes", error: Exception | None = None):
        self.body = body
        self.error = error
        self.reads = []
        self.mutations = []

    def read_exact(self, record):
        self.reads.append(record)
        if self.error is not None:
            raise self.error
        return self.body

    def __getattr__(self, name):
        if name in {
            "stage",
            "publish",
            "tombstone",
            "remove_tombstone",
            "restore_tombstone",
        }:

            def unexpected(*_args, **_kwargs):
                self.mutations.append(name)
                raise AssertionError(f"GET must not mutate cache via {name}")

            return unexpected
        raise AttributeError(name)


@pytest.mark.asyncio
async def test_asset_get_recomputes_authority_reads_exact_bytes_and_emits_private_immutable_etag(
    monkeypatch,
):
    from api.routers import source_visuals

    record = _record()
    repository = _Repository(record)
    store = _Store()
    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals,
        "compute_source_visual_authority",
        AsyncMock(return_value=_authority()),
    )

    response = await source_visuals.get_source_visual_asset(
        "source:one", if_none_match=None, repository=repository, store=store
    )

    assert response.body == b"webp-bytes"
    assert response.media_type == "image/webp"
    assert response.headers["etag"] == f'"{ASSET_SHA}"'
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert repository.list_calls == [{"source:one": NOW}]
    assert store.reads == [record]
    assert store.mutations == []


@pytest.mark.asyncio
async def test_asset_get_returns_304_only_after_full_authority_and_exact_read(
    monkeypatch,
):
    from api.routers import source_visuals

    record = _record()
    store = _Store()
    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals,
        "compute_source_visual_authority",
        AsyncMock(return_value=_authority()),
    )

    response = await source_visuals.get_source_visual_asset(
        "source:one",
        if_none_match=f'"{ASSET_SHA}"',
        repository=_Repository(record),
        store=store,
    )

    assert response.status_code == 304
    assert response.headers["etag"] == f'"{ASSET_SHA}"'
    assert store.reads == [record]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record,authority,store_error",
    [
        (None, _authority(), None),
        (
            _record(),
            SimpleNamespace(**{**_authority().__dict__, "content_sha256": "d" * 64}),
            None,
        ),
        (_record(), _authority(), SourceVisualStorageError("ASSET_MISSING")),
        (_record(), _authority(), SourceVisualStorageError("ASSET_HASH_MISMATCH")),
        (_record(), _authority(), SourceVisualStorageError("ASSET_IO_FAILED")),
    ],
)
async def test_asset_get_maps_stale_and_controlled_cache_failures_to_safe_conflict(
    monkeypatch, record, authority, store_error
):
    from api.routers import source_visuals

    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals,
        "compute_source_visual_authority",
        AsyncMock(return_value=authority),
    )

    with pytest.raises(HTTPException) as exc:
        await source_visuals.get_source_visual_asset(
            "source:one",
            if_none_match=None,
            repository=_Repository(record),
            store=_Store(error=store_error),
        )

    assert exc.value.status_code == 409
    assert "/" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_asset_get_missing_source_is_404(monkeypatch):
    from api.routers import source_visuals

    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(source_visuals.Source, "get", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await source_visuals.get_source_visual_asset(
            "source:missing", if_none_match=None
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_refresh_missing_source_is_404_before_queue_submission(monkeypatch):
    from api.routers import source_visuals

    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(source_visuals.Source, "get", AsyncMock(return_value=None))
    submit = AsyncMock()
    monkeypatch.setattr(source_visuals, "submit_source_visual", submit)

    with pytest.raises(HTTPException) as exc:
        await source_visuals.submit_source_visual_refresh(
            "source:missing", {"request_id": "request:missing"}
        )

    assert exc.value.status_code == 404
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_feature_guard_runs_before_source_or_payload_parsing(monkeypatch):
    from api.routers import source_visuals

    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: False)
    source_get = AsyncMock()
    monkeypatch.setattr(source_visuals.Source, "get", source_get)

    with pytest.raises(HTTPException) as refresh:
        await source_visuals.submit_source_visual_refresh(
            "not a source id", {"request_id": []}
        )
    with pytest.raises(HTTPException) as delete:
        await source_visuals.delete_source_visual("not a source id", {"request_id": []})
    with pytest.raises(HTTPException) as asset:
        await source_visuals.get_source_visual_asset(
            "not a source id", if_none_match=None
        )

    assert {
        refresh.value.status_code,
        delete.value.status_code,
        asset.value.status_code,
    } == {404}
    assert refresh.value.detail == delete.value.detail == asset.value.detail
    source_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_returns_accepted_for_new_work_and_ok_for_replay(monkeypatch):
    from api.routers import source_visuals

    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    submit = AsyncMock(
        side_effect=[
            SimpleNamespace(
                source_id="source:one",
                command_id="command:new",
                content_sha256=SOURCE_SHA,
                outcome="queued",
                error_code=None,
            ),
            SimpleNamespace(
                source_id="source:one",
                command_id="command:new",
                content_sha256=SOURCE_SHA,
                outcome="replayed",
                error_code=None,
            ),
        ]
    )
    monkeypatch.setattr(source_visuals, "submit_source_visual", submit)

    created = await source_visuals.submit_source_visual_refresh(
        "source:one", {"request_id": "request:new"}
    )
    replay = await source_visuals.submit_source_visual_refresh(
        "source:one", {"request_id": "request:new"}
    )

    assert created.status_code == 202
    assert replay.status_code == 200
    assert submit.await_args_list[0].args == ("source:one", "request:new")
    assert submit.await_args_list[0].kwargs == {"explicit": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        SourceVisualConflictError("REQUEST_CONFLICT"),
        SourceVisualRepositoryError("MALFORMED_ROW"),
    ],
)
async def test_refresh_maps_typed_replay_conflict_to_409_without_raw_error(
    monkeypatch, error
):
    from api.routers import source_visuals

    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals, "submit_source_visual", AsyncMock(side_effect=error)
    )

    with pytest.raises(HTTPException) as exc:
        await source_visuals.submit_source_visual_refresh(
            "source:one", {"request_id": "request:conflict"}
        )

    assert exc.value.status_code == 409
    assert "/" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_delete_uses_durable_receipt_then_tombstone_cleanup_and_replays(
    monkeypatch,
):
    from api.routers import source_visuals

    record = _record()
    repository = SimpleNamespace(
        get_operation=AsyncMock(
            side_effect=[
                None,
                SimpleNamespace(
                    outcome="deleted",
                    source_id="source:one",
                    source_updated_at=NOW,
                    command_id=None,
                    content_sha256=SOURCE_SHA,
                    error_code=None,
                ),
            ]
        ),
        list_current=AsyncMock(return_value={"source:one": record}),
        record_operation=AsyncMock(return_value=SimpleNamespace(outcome="queued")),
        finalize_operation=AsyncMock(
            return_value=SimpleNamespace(
                outcome="deleted",
                source_id="source:one",
                command_id=None,
                content_sha256=SOURCE_SHA,
                error_code=None,
            )
        ),
    )
    cleanup = SimpleNamespace(delete_record=AsyncMock(return_value=True))
    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals,
        "compute_source_visual_authority",
        AsyncMock(return_value=_authority()),
    )

    deleted = await source_visuals.delete_source_visual(
        "source:one",
        {"request_id": "request:delete"},
        repository=repository,
        cleanup=cleanup,
    )
    replay = await source_visuals.delete_source_visual(
        "source:one",
        {"request_id": "request:delete"},
        repository=repository,
        cleanup=cleanup,
    )

    assert deleted.status_code == 200
    assert replay.status_code == 200
    cleanup.delete_record.assert_awaited_once_with(record)
    assert repository.record_operation.await_count == 1
    assert repository.finalize_operation.await_count == 1


@pytest.mark.asyncio
async def test_delete_replay_recovers_a_post_file_pre_receipt_crash_without_recreating(
    monkeypatch,
):
    from api.routers import source_visuals

    queued = SimpleNamespace(
        outcome="queued",
        source_id="source:one",
        source_updated_at=NOW,
        command_id=None,
        content_sha256=SOURCE_SHA,
        error_code=None,
    )
    completed = SimpleNamespace(
        outcome="deleted",
        source_id="source:one",
        source_updated_at=NOW,
        command_id=None,
        content_sha256=SOURCE_SHA,
        error_code=None,
    )
    repository = SimpleNamespace(
        get_operation=AsyncMock(return_value=queued),
        list_current=AsyncMock(return_value={}),
        record_operation=AsyncMock(),
        finalize_operation=AsyncMock(return_value=completed),
    )
    cleanup = SimpleNamespace(delete_record=AsyncMock())
    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals,
        "compute_source_visual_authority",
        AsyncMock(return_value=_authority()),
    )

    response = await source_visuals.delete_source_visual(
        "source:one",
        {"request_id": "request:delete"},
        repository=repository,
        cleanup=cleanup,
    )

    assert response.status_code == 200
    repository.record_operation.assert_not_awaited()
    cleanup.delete_record.assert_not_awaited()
    repository.finalize_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_conflict_and_crash_window_preserve_safe_receipt_and_never_recreate(
    monkeypatch,
):
    from api.routers import source_visuals

    record = _record()
    repository = SimpleNamespace(
        get_operation=AsyncMock(return_value=None),
        list_current=AsyncMock(return_value={"source:one": record}),
        record_operation=AsyncMock(return_value=SimpleNamespace(outcome="queued")),
        finalize_operation=AsyncMock(
            side_effect=SourceVisualConflictError("REQUEST_CONFLICT")
        ),
    )
    cleanup = SimpleNamespace(
        delete_record=AsyncMock(side_effect=SourceVisualStorageError("ASSET_IO_FAILED"))
    )
    monkeypatch.setattr(source_visuals, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(
        source_visuals.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    monkeypatch.setattr(
        source_visuals,
        "compute_source_visual_authority",
        AsyncMock(return_value=_authority()),
    )

    with pytest.raises(HTTPException) as exc:
        await source_visuals.delete_source_visual(
            "source:one",
            {"request_id": "request:delete"},
            repository=repository,
            cleanup=cleanup,
        )

    assert exc.value.status_code == 409
    assert cleanup.delete_record.await_count == 1


@pytest.mark.asyncio
async def test_completed_delete_suppresses_auto_ingest_but_a_new_explicit_refresh_recreates(
    monkeypatch,
):
    from deeper_notebook.source_visuals import queue

    authority = SimpleNamespace(
        source_id="source:one",
        source_updated_at=NOW,
        content_sha256=SOURCE_SHA,
        extractor_version="source-visual-v1",
    )
    deleted = SimpleNamespace(
        source_id="source:one",
        source_updated_at=NOW,
        content_sha256=SOURCE_SHA,
        operation="delete",
        outcome="deleted",
    )
    repository = SimpleNamespace(
        get_operation=AsyncMock(return_value=None),
        find_completed_delete=AsyncMock(return_value=deleted),
        record_operation=AsyncMock(return_value=SimpleNamespace(outcome="deleted")),
    )
    monkeypatch.setattr(queue, "SourceVisualRepository", lambda: repository)
    monkeypatch.setattr(
        queue, "_load_source", AsyncMock(return_value=SimpleNamespace(id="source:one"))
    )
    monkeypatch.setattr(
        queue, "compute_source_visual_authority", AsyncMock(return_value=authority)
    )

    automatic = await queue.submit_source_visual(
        "source:one", "ingest:" + SOURCE_SHA, explicit=False
    )
    assert automatic.outcome == "replayed"

    explicit = await queue._suppressed_auto_ingest_response(
        repository,
        authority=authority,
        request_id="request:new",
        explicit=True,
    )
    assert explicit is None


@pytest.mark.asyncio
async def test_queued_delete_intent_suppresses_auto_ingest_after_post_file_pre_receipt_crash(
    monkeypatch,
):
    """A durable accepted delete fence wins before its file cleanup is finalized."""

    from deeper_notebook.source_visuals import queue

    authority = SimpleNamespace(
        source_id="source:one",
        source_updated_at=NOW,
        content_sha256=SOURCE_SHA,
        extractor_version="source-visual-v1",
    )
    accepted = SimpleNamespace(
        source_id="source:one",
        source_updated_at=NOW,
        content_sha256=SOURCE_SHA,
        operation="delete",
        outcome="queued",
        command_id=None,
        error_code=None,
    )
    repository = SimpleNamespace(
        get_operation=AsyncMock(return_value=None),
        find_accepted_delete=AsyncMock(return_value=accepted),
        record_operation=AsyncMock(return_value=SimpleNamespace(outcome="deleted")),
    )
    monkeypatch.setattr(queue, "SourceVisualRepository", lambda: repository)
    monkeypatch.setattr(
        queue, "_load_source", AsyncMock(return_value=SimpleNamespace(id="source:one"))
    )
    monkeypatch.setattr(
        queue, "compute_source_visual_authority", AsyncMock(return_value=authority)
    )

    response = await queue.submit_source_visual(
        "source:one", "ingest:" + SOURCE_SHA, explicit=False
    )

    assert response.outcome == "replayed"
    repository.find_accepted_delete.assert_awaited_once_with(
        "source:one", NOW, SOURCE_SHA
    )
    repository.record_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_ready_atomically_rejects_a_running_worker_after_delete_intent(
    monkeypatch,
):
    """DELETE's queued receipt fences an already-running extraction before UPSERT."""

    from deeper_notebook.source_visuals.repository import SourceVisualRepository

    query = AsyncMock(return_value={"delete_requested": True})
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)

    with pytest.raises(SourceVisualConflictError) as error:
        await SourceVisualRepository().publish_ready(
            _record(),
            source_id="source:one",
            content_sha256=SOURCE_SHA,
            extractor_version="source-visual-v1",
            source_updated_at=NOW,
            owner_token="d" * 64,
            request_id="request:old-before-delete",
            now=NOW,
        )

    assert error.value.code == "DELETE_REQUESTED"
    query_text = query.await_args.args[0]
    assert "source_visual_operation" in query_text
    assert "delete_intent" in query_text
    assert "refresh_operation_record" in query_text
    assert "$refresh.created_at <= $delete_intent.created_at" in query_text
    assert "UPSERT $cache_record" in query_text


@pytest.mark.asyncio
async def test_publish_ready_allows_a_newer_explicit_refresh_to_supersede_delete_intent(
    monkeypatch,
):
    """A command-bound refresh created after DELETE may recreate the derivative."""

    from deeper_notebook.source_visuals.repository import SourceVisualRepository

    query = AsyncMock(
        return_value={
            "published": True,
            "owner_token": "d" * 64,
            "lease_until": NOW.replace(hour=13),
            "source_updated_at": NOW,
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)

    published = await SourceVisualRepository().publish_ready(
        _record(),
        source_id="source:one",
        content_sha256=SOURCE_SHA,
        extractor_version="source-visual-v1",
        source_updated_at=NOW,
        owner_token="d" * 64,
        request_id="request:explicit-after-delete",
        now=NOW,
    )

    assert published == _record()
    query_text, variables = query.await_args.args
    assert "refresh_operation_record" in query_text
    assert "$refresh.command_id != $claim.command_id" in query_text
    assert "$refresh.created_at <= $delete_intent.created_at" in query_text
    assert "ORDER BY created_at DESC, updated_at DESC" in query_text
    assert variables["request_id"] == "request:explicit-after-delete"


@pytest.mark.asyncio
async def test_disabled_sentinel_shape_and_state():
    """v0.8.86 — the capability sentinel list/detail projections stamp when the
    feature flag is off. The state is 'disabled' (not 'unavailable') so a
    client with baked-on build flags can hide mutation actions that would 404.
    """
    from api.schemas.source_visuals import disabled_visual_status

    sentinel = disabled_visual_status()
    assert sentinel.state == "disabled"
    assert sentinel.command_id is None
    assert sentinel.error_code is None
    assert sentinel.updated_at is not None
    # Serialises cleanly for the dict-shaped search results too.
    dumped = sentinel.model_dump(mode="json")
    assert dumped["state"] == "disabled"
