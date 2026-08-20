"""Real-SurrealDB authority and recovery contracts for Source Visual Gallery."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from deeper_notebook.database.repository import ensure_record_id
from deeper_notebook.source_visuals.cleanup import SourceVisualCleanup
from deeper_notebook.source_visuals.contracts import (
    PreparedVisualAsset,
    SourceVisualRecord,
)
from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepository,
    claim_identity,
)
from deeper_notebook.source_visuals.storage import SourceVisualStore

pytestmark = pytest.mark.integration_surreal

UTC = timezone.utc
NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)
CONTENT = "a" * 64
ASSET = "b" * 64
OWNER_A = "c" * 64
OWNER_B = "d" * 64
VERSION = "source-visual-v1"


async def _source(source_id: str) -> datetime:
    """Create the smallest real source and return its persisted revision."""

    from deeper_notebook.database.repository import repo_query

    source_name = source_id.removeprefix("source:")
    assert source_id == f"source:{source_name}"
    assert source_name.replace("_", "").isalnum()
    await repo_query(
        f"CREATE source:{source_name} CONTENT {{ title: $title, source_type: 'text', "
        "full_text: 'source visual integration fixture' };",
        {"title": f"Source {source_id}"},
    )
    rows = await repo_query(f"SELECT * FROM source:{source_name};")
    assert len(rows) == 1
    updated = rows[0]["updated"]
    assert isinstance(updated, datetime)
    return updated


def _record(
    source_id: str, updated: datetime, *, asset: str = ASSET
) -> SourceVisualRecord:
    return SourceVisualRecord(
        source_id=source_id,
        source_updated_at=updated,
        source_file_sha256=None,
        content_sha256=CONTENT,
        asset_sha256=asset,
        asset_relpath=f"aa/{CONTENT}/{asset}.webp",
        origin="embedded",
        source_locator={"page": 1},
        extractor_version=VERSION,
        alt_text="A bounded source-derived visual",
        width=640,
        height=360,
        created_at=NOW,
        updated_at=NOW,
    )


def _prepared(payload: bytes) -> PreparedVisualAsset:
    return PreparedVisualAsset(
        encoded_bytes=payload,
        asset_sha256=hashlib.sha256(payload).hexdigest(),
        width=640,
        height=360,
    )


def _stored_record(
    store: SourceVisualStore,
    source_id: str,
    updated: datetime,
    content: str,
    payload: bytes,
    *,
    receipt_time: datetime = NOW,
) -> SourceVisualRecord:
    staged = store.stage(source_id, content, _prepared(payload))
    stored = store.publish(staged)
    return SourceVisualRecord(
        source_id=source_id,
        source_updated_at=updated,
        source_file_sha256=None,
        content_sha256=content,
        asset_sha256=stored.asset_sha256,
        asset_relpath=stored.asset_relpath,
        origin="embedded",
        source_locator={"page": 1},
        extractor_version=VERSION,
        alt_text="A bounded source-derived visual",
        width=stored.width,
        height=stored.height,
        created_at=receipt_time,
        updated_at=receipt_time,
    )


async def _insert_ready(record: SourceVisualRecord) -> None:
    """Seed one exact cache record using its canonical deterministic identity."""

    from deeper_notebook.database.repository import repo_query

    identity = hashlib.sha256(
        f"{record.source_id}\0{record.content_sha256}".encode()
    ).hexdigest()
    row = record.model_dump()
    row["source_id"] = ensure_record_id(record.source_id)
    await repo_query(
        f"CREATE source_visual_cache:{identity} CONTENT $row;", {"row": row}
    )


def _tables(info: object) -> dict[str, object]:
    """Surreal 2 driver returns INFO FOR DB as a dict, not a one-row list."""

    if isinstance(info, dict):
        tables = info.get("tables")
    elif isinstance(info, list) and info and isinstance(info[0], dict):
        tables = info[0].get("tables")
    else:
        tables = None
    assert isinstance(tables, dict)
    return tables


@pytest.mark.asyncio
async def test_migration_46_up_down_up_is_schemafull_and_preserves_sources(
    clean_namespace: dict[str, object],
) -> None:
    """The derived-only migration round-trips without changing source bytes."""

    from deeper_notebook.database.repository import repo_query

    source_id = "source:visual_migration"
    updated = await _source(source_id)
    before = await repo_query("SELECT * FROM source:visual_migration;")
    assert len(before) == 1
    seeded = _record(source_id, updated)
    await _insert_ready(seeded)
    seeded_identity = hashlib.sha256(f"{source_id}\0{CONTENT}".encode()).hexdigest()
    assert await repo_query(f"SELECT * FROM source_visual_cache:{seeded_identity};")

    root = Path(__file__).resolve().parents[2]
    down = (root / "deeper_notebook/database/migrations/46_down.surrealql").read_text()
    up = (root / "deeper_notebook/database/migrations/46.surrealql").read_text()
    await repo_query(down)
    tables_after_down = await repo_query("INFO FOR DB;")
    assert "source_visual_cache" not in _tables(tables_after_down)
    await repo_query(up)
    tables_after_up = _tables(await repo_query("INFO FOR DB;"))
    assert "SCHEMAFULL" in str(tables_after_up["source_visual_cache"])
    assert (
        await repo_query(f"SELECT * FROM source_visual_cache:{seeded_identity};") == []
    )

    # SurrealDB v2 rejects an undeclared value from durable SCHEMAFULL state by
    # filtering it; keep the fixture to fields that are durably representable.
    invalid = _record(source_id, updated).model_dump(exclude_none=True)
    invalid["source_id"] = ensure_record_id(source_id)
    invalid["unexpected"] = "blocked"
    created = await repo_query(
        "CREATE source_visual_cache:extra CONTENT $row RETURN AFTER;", {"row": invalid}
    )
    assert len(created) == 1
    assert "unexpected" not in created[0]
    expected = dict(invalid)
    expected.pop("unexpected")
    expected["source_id"] = source_id
    assert created[0] == {"id": "source_visual_cache:extra", **expected}
    persisted = await repo_query("SELECT * FROM source_visual_cache:extra;")
    assert persisted == created

    after = await repo_query("SELECT * FROM source:visual_migration;")
    assert after == before
    assert after[0]["updated"] == updated


@pytest.mark.asyncio
async def test_publish_after_delete_intent_requires_a_new_bound_refresh_receipt(
    clean_namespace: dict[str, object],
) -> None:
    """A queued delete fences publishing until a later bound refresh receipt."""

    from deeper_notebook.database.repository import repo_query

    source_id = "source:visual_delete_fence"
    updated = await _source(source_id)
    repository = SourceVisualRepository()
    delete_time = NOW
    lease_until = NOW + timedelta(minutes=10)
    await repository.record_operation(
        source_id=source_id,
        request_id="delete-before-publish",
        source_updated_at=updated,
        content_sha256=CONTENT,
        operation="delete",
        outcome="queued",
        command_id=None,
        error_code=None,
        now=delete_time,
    )
    claim = await repository.acquire_claim(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        now=delete_time + timedelta(seconds=1),
        lease_until=lease_until,
    )
    assert claim.command_id is None

    record = _record(source_id, updated)
    with pytest.raises(SourceVisualConflictError) as fenced:
        await repository.publish_ready(
            record,
            source_id=source_id,
            content_sha256=CONTENT,
            extractor_version=VERSION,
            owner_token=OWNER_A,
            source_updated_at=updated,
            now=delete_time + timedelta(seconds=2),
        )
    assert fenced.value.code == "DELETE_REQUESTED"
    cache_id = hashlib.sha256(f"{source_id}\0{CONTENT}".encode()).hexdigest()
    assert await repo_query(f"SELECT * FROM source_visual_cache:{cache_id};") == []

    request_id = "refresh-after-delete"
    await repository.record_operation(
        source_id=source_id,
        request_id=request_id,
        source_updated_at=updated,
        content_sha256=CONTENT,
        operation="refresh",
        outcome="queued",
        command_id=None,
        error_code=None,
        now=delete_time + timedelta(seconds=3),
    )
    bound = await repository.bind_command_and_finalize_operation(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        "command:visual_delete_fence",
        request_id=request_id,
        source_updated_at=updated,
        now=delete_time + timedelta(seconds=4),
    )
    assert bound.command_id == "command:visual_delete_fence"
    assert bound.created_at > delete_time

    published = await repository.publish_ready(
        record,
        source_id=source_id,
        content_sha256=CONTENT,
        extractor_version=VERSION,
        owner_token=OWNER_A,
        request_id=request_id,
        source_updated_at=updated,
        now=delete_time + timedelta(seconds=5),
    )
    assert published == record


@pytest.mark.asyncio
async def test_post_delete_refresh_reacquires_until_a_new_claim_command_is_bound(
    clean_namespace: dict[str, object],
) -> None:
    """Only a post-delete receipt bound to the current claim clears reacquire."""

    source_id = "source:visual_post_delete_reacquire"
    updated = await _source(source_id)
    repository = SourceVisualRepository()
    delete_time = NOW
    request_id = "refresh-after-delete-reacquire"
    await repository.record_operation(
        source_id=source_id,
        request_id="delete-before-reacquire",
        source_updated_at=updated,
        content_sha256=CONTENT,
        operation="delete",
        outcome="queued",
        command_id=None,
        error_code=None,
        now=delete_time,
    )
    claim = await repository.acquire_claim(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        now=delete_time + timedelta(seconds=1),
        lease_until=delete_time + timedelta(minutes=10),
    )
    assert claim.command_id is None
    await repository.record_operation(
        source_id=source_id,
        request_id=request_id,
        source_updated_at=updated,
        content_sha256=CONTENT,
        operation="refresh",
        outcome="queued",
        command_id=None,
        error_code=None,
        now=delete_time + timedelta(seconds=2),
    )

    assert await repository.post_delete_refresh_needs_reacquire(
        source_id=source_id,
        content_sha256=CONTENT,
        extractor_version=VERSION,
        request_id=request_id,
        source_updated_at=updated,
        now=delete_time + timedelta(seconds=3),
    )

    bound = await repository.bind_command_and_finalize_operation(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        "command:visual_post_delete_reacquire",
        request_id=request_id,
        source_updated_at=updated,
        now=delete_time + timedelta(seconds=4),
    )
    assert bound.command_id == "command:visual_post_delete_reacquire"
    assert (
        await repository.post_delete_refresh_needs_reacquire(
            source_id=source_id,
            content_sha256=CONTENT,
            extractor_version=VERSION,
            request_id=request_id,
            source_updated_at=updated,
            now=delete_time + timedelta(seconds=5),
        )
        is False
    )


@pytest.mark.asyncio
async def test_two_clients_enforce_live_owner_fencing_expiry_and_command_binding(
    clean_namespace: dict[str, object],
) -> None:
    """A live 90-second owner wins; only expiry permits one fenced takeover."""

    source_id = "source:visual_claim"
    await _source(source_id)
    first = SourceVisualRepository()
    second = SourceVisualRepository()
    lease = NOW + timedelta(seconds=90)

    acquired = await first.acquire_claim(
        source_id, CONTENT, VERSION, OWNER_A, now=NOW, lease_until=lease
    )
    assert acquired.owner_token == OWNER_A
    assert acquired.lease_until == lease
    assert acquired.claim_id == claim_identity(source_id, CONTENT, VERSION)
    from deeper_notebook.database.repository import repo_query

    persisted = await repo_query("SELECT * FROM source_visual_claim;")
    assert len(persisted) == 1
    assert str(persisted[0]["owner_token"]) == OWNER_A
    assert persisted[0]["lease_until"] == lease
    predicate = await repo_query(
        "SELECT owner_token = $owner AS same_owner, lease_until <= $now AS expired "
        "FROM source_visual_claim;",
        {"owner": OWNER_B, "now": NOW},
    )
    assert predicate == [{"same_owner": False, "expired": False}]

    with pytest.raises(SourceVisualConflictError) as held:
        await second.acquire_claim(
            source_id, CONTENT, VERSION, OWNER_B, now=NOW, lease_until=lease
        )
    assert held.value.code == "CLAIM_HELD"

    taken = await second.acquire_claim(
        source_id,
        CONTENT,
        VERSION,
        OWNER_B,
        now=lease,
        lease_until=lease + timedelta(seconds=90),
    )
    assert taken.owner_token == OWNER_B
    with pytest.raises(SourceVisualConflictError) as fenced:
        await first.renew_claim(
            source_id,
            CONTENT,
            VERSION,
            OWNER_A,
            now=lease,
            lease_until=lease + timedelta(seconds=90),
        )
    assert fenced.value.code == "OWNER_MISMATCH"

    bound = await second.bind_command(
        source_id, CONTENT, VERSION, OWNER_B, "command:source_visual_claim", now=lease
    )
    assert bound.command_id == "command:source_visual_claim"


@pytest.mark.asyncio
async def test_operation_replay_conflict_and_stale_projection_are_exact(
    clean_namespace: dict[str, object],
) -> None:
    """Operation idempotency is payload-bound and stale source revisions are omitted."""

    source_id = "source:visual_operation"
    updated = await _source(source_id)
    repository = SourceVisualRepository()
    payload = {
        "source_id": source_id,
        "request_id": "refresh-visual-operation",
        "source_updated_at": updated,
        "content_sha256": CONTENT,
        "operation": "refresh",
        "outcome": "queued",
        "command_id": None,
        "error_code": None,
        "now": NOW,
    }
    created = await repository.record_operation(**payload)
    replay = await SourceVisualRepository().record_operation(**payload)
    assert replay == created
    with pytest.raises(SourceVisualConflictError) as conflict:
        await repository.record_operation(**{**payload, "outcome": "failed"})
    assert conflict.value.code == "REQUEST_CONFLICT"

    claim = await repository.acquire_claim(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        now=NOW,
        lease_until=NOW + timedelta(seconds=90),
    )
    assert claim.owner_token == OWNER_A
    ready = await repository.publish_ready(
        _record(source_id, updated),
        source_id=source_id,
        content_sha256=CONTENT,
        extractor_version=VERSION,
        owner_token=OWNER_A,
        source_updated_at=updated,
        now=NOW,
    )
    assert ready.source_id == source_id
    assert (await repository.list_current({source_id: updated}))[source_id] == ready
    assert (
        await repository.list_current({source_id: updated + timedelta(seconds=1)}) == {}
    )


@pytest.mark.asyncio
async def test_concurrent_ready_publication_has_one_cache_identity(
    clean_namespace: dict[str, object],
) -> None:
    """The unique cache identity keeps two different record IDs from coexisting."""

    from deeper_notebook.database.repository import repo_query

    source_id = "source:visual_unique"
    updated = await _source(source_id)
    row = _record(source_id, updated).model_dump()
    row["source_id"] = ensure_record_id(source_id)
    await repo_query(
        "CREATE source_visual_cache:unique_one CONTENT $row;", {"row": row}
    )
    with pytest.raises(RuntimeError, match="idx_source_visual_identity"):
        await repo_query(
            "CREATE source_visual_cache:unique_two CONTENT $row;", {"row": row}
        )
    rows = await repo_query(
        "SELECT id, source_id, content_sha256 FROM source_visual_cache "
        "WHERE source_id = $source AND content_sha256 = $content;",
        {"source": ensure_record_id(source_id), "content": CONTENT},
    )
    assert rows == [
        {
            "id": "source_visual_cache:unique_one",
            "source_id": source_id,
            "content_sha256": CONTENT,
        }
    ]


@pytest.mark.asyncio
async def test_database_failure_restores_exact_tombstoned_file(
    clean_namespace: dict[str, object], tmp_path: Path
) -> None:
    """A DB-before-cleanup failure restores the byte-identical canonical asset."""

    source_id = "source:visual_delete_restore"
    updated = await _source(source_id)
    store = SourceVisualStore(data_folder=tmp_path)
    record = _stored_record(
        store, source_id, updated, "3" * 64, b"restore-after-db-error"
    )

    class DatabaseFailure:
        async def delete_ready_if_current(self, current: SourceVisualRecord) -> bool:
            assert current == record
            raise RuntimeError("simulated database failure")

    with pytest.raises(RuntimeError, match="simulated database failure"):
        await SourceVisualCleanup(store, DatabaseFailure()).delete_record(record)
    assert (
        SourceVisualStore(data_folder=tmp_path).read_exact(record)
        == b"restore-after-db-error"
    )
    assert store.list_tombstones(limit=100) == ()


@pytest.mark.asyncio
async def test_command_finalization_and_concurrent_publication_are_owner_fenced(
    clean_namespace: dict[str, object],
) -> None:
    """A single bound command/ready row wins two simultaneous publishers."""

    source_id = "source:visual_publish"
    updated = await _source(source_id)
    repository = SourceVisualRepository()
    await repository.record_operation(
        source_id=source_id,
        request_id="publish-command",
        source_updated_at=updated,
        content_sha256=CONTENT,
        operation="refresh",
        outcome="queued",
        command_id=None,
        error_code=None,
        now=NOW,
    )
    await repository.acquire_claim(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        now=NOW,
        lease_until=NOW + timedelta(seconds=90),
    )
    finalized = await repository.bind_command_and_finalize_operation(
        source_id,
        CONTENT,
        VERSION,
        OWNER_A,
        "command:visual_publish",
        request_id="publish-command",
        source_updated_at=updated,
        now=NOW,
    )
    assert finalized.command_id == "command:visual_publish"
    assert finalized.outcome == "queued"

    record = _record(source_id, updated)
    outcomes = await asyncio.gather(
        repository.publish_ready(
            record,
            source_id=source_id,
            content_sha256=CONTENT,
            extractor_version=VERSION,
            owner_token=OWNER_A,
            request_id="publish-command",
            source_updated_at=updated,
            now=NOW,
        ),
        SourceVisualRepository().publish_ready(
            record,
            source_id=source_id,
            content_sha256=CONTENT,
            extractor_version=VERSION,
            owner_token=OWNER_A,
            request_id="publish-command",
            source_updated_at=updated,
            now=NOW,
        ),
        return_exceptions=True,
    )
    assert outcomes == [record, record]
    current = await SourceVisualRepository().list_current({source_id: updated})
    assert current == {source_id: record}


@pytest.mark.asyncio
async def test_file_before_db_db_before_cleanup_restart_and_bounded_eviction(
    clean_namespace: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crash-order recovery remains exact across fresh store/repository instances."""

    source_one = "source:visual_recovery_one"
    source_two = "source:visual_recovery_two"
    updated_one = await _source(source_one)
    updated_two = await _source(source_two)
    store = SourceVisualStore(data_folder=tmp_path)
    first = _stored_record(store, source_one, updated_one, "1" * 64, b"first-derived")
    second = _stored_record(
        store,
        source_two,
        updated_two,
        "2" * 64,
        b"second-derived-larger",
        receipt_time=NOW + timedelta(seconds=1),
    )
    # File-before-DB: the unreferenced first asset survives only until its exact
    # cache row is durably created; a fresh store hydrates the known ready file.
    assert SourceVisualStore(data_folder=tmp_path).read_exact(first) == b"first-derived"
    await _insert_ready(first)
    await _insert_ready(second)
    repository = SourceVisualRepository()
    hydrated = await SourceVisualRepository().list_current(
        {source_one: updated_one, source_two: updated_two}
    )
    assert hydrated == {source_one: first, source_two: second}

    cleanup = SourceVisualCleanup(store, repository)
    original_remove = store.remove_tombstone

    def interrupt_after_database_delete(_tombstone: object) -> None:
        raise OSError("simulated cleanup interruption")

    monkeypatch.setattr(store, "remove_tombstone", interrupt_after_database_delete)
    assert await cleanup.delete_record(first) is True
    assert await repository.list_current({source_one: updated_one}) == {}
    assert len(store.list_tombstones(limit=100)) == 1

    monkeypatch.setattr(store, "remove_tombstone", original_remove)
    restarted = SourceVisualCleanup(
        SourceVisualStore(data_folder=tmp_path), SourceVisualRepository()
    )
    assert await restarted.reconcile_tombstones(limit=100) == 1
    assert SourceVisualStore(data_folder=tmp_path).list_tombstones(limit=100) == ()

    evicted = await SourceVisualCleanup(
        SourceVisualStore(data_folder=tmp_path), SourceVisualRepository()
    ).evict_to_budget(max_bytes=0, page_size=1)
    assert evicted == 1
    assert SourceVisualStore(data_folder=tmp_path).cache_size_bytes() == 0
    assert await SourceVisualRepository().list_current({source_two: updated_two}) == {}
