"""Native SurrealDB proof for atomic unified knowledge projections."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from surrealdb import AsyncSurreal

from deeper_notebook.database.async_migrate import AsyncMigrationManager
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import (
    BackfillCheckpoint,
    SourceEnvelope,
)
from deeper_notebook.knowledge_engine.repository import (
    KnowledgeRepository,
    KnowledgeRepositoryError,
)

pytestmark = pytest.mark.integration_surreal

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_38_DOWN = ROOT / "deeper_notebook/database/migrations/38_down.surrealql"
NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def _snapshot(raw: bytes):
    envelope = SourceEnvelope(
        space_id="knowledge_engine_space:native",
        space_display_name="Native Repository Test Space",
        source_ref="fixture:native",
        authority_kind="external_read_only",
        source_kind="markdown",
        format_mode="markdown",
        relative_locator="Pages/Native.md",
        canonical_bytes=raw,
        byte_size=len(raw),
        declared_encoding=None,
        declared_newline=None,
        observed_content_hash=sha256(raw).hexdigest(),
        observed_modified_ns=1,
        observed_at=NOW,
        prior_revision=None,
    )
    return adapter_for("markdown").project(envelope)


class _BarrierConnection:
    def __init__(self, connection: AsyncSurreal, barrier: asyncio.Barrier) -> None:
        self._connection = connection
        self._barrier = barrier

    async def query(
        self, statement: str, variables: dict[str, Any] | None = None
    ) -> Any:
        if "BEGIN TRANSACTION;" in statement:
            await self._barrier.wait()
        return await self._connection.query(statement, variables)


def _barrier_factory(meta: dict[str, Any], barrier: asyncio.Barrier):
    @asynccontextmanager
    async def factory():
        connection = AsyncSurreal(meta["url"])
        await connection.signin({"username": meta["user"], "password": meta["password"]})
        await connection.use(meta["namespace"], meta["database"])
        try:
            yield _BarrierConnection(connection, barrier)
        finally:
            await connection.close()

    return factory


async def test_snapshot_commit_replays_without_rewriting_and_creates_children(
    clean_namespace,
):
    snapshot = _snapshot(b"# Native\n\n- [ ] Persist atomically\n")
    repository = KnowledgeRepository()

    first = await repository.commit_snapshot(snapshot, operation_id="native-project")
    replay = await repository.commit_snapshot(snapshot, operation_id="native-project")

    assert first.status == "projected"
    assert replay.status == "unchanged"
    counts = await repo_query(
        """
        RETURN {
            documents: count((SELECT * FROM knowledge_engine_document)),
            blocks: count((SELECT * FROM knowledge_engine_block)),
            tasks: count((SELECT * FROM knowledge_engine_task)),
            receipts: count((SELECT * FROM knowledge_engine_projection_receipt))
        };
        """
    )
    assert counts == {
        "documents": 1,
        "blocks": len(snapshot.blocks),
        "tasks": len(snapshot.tasks),
        "receipts": 1,
    }


async def test_conflicting_operation_replay_is_rejected(clean_namespace):
    repository = KnowledgeRepository()
    await repository.commit_snapshot(
        _snapshot(b"# Native\n\nFirst snapshot\n"), operation_id="native-conflict"
    )

    with pytest.raises(KnowledgeRepositoryError, match="operation_conflict"):
        await repository.commit_snapshot(
            _snapshot(b"# Native\n\nReplacement snapshot\n"),
            operation_id="native-conflict",
        )


async def test_failed_child_insert_keeps_the_previous_valid_snapshot(clean_namespace):
    repository = KnowledgeRepository()
    original = _snapshot(b"# Native\n\nPrevious valid snapshot\n")
    await repository.commit_snapshot(original, operation_id="native-original")
    replacement = _snapshot(b"# Native\n\nReplacement must roll back\n")
    duplicate = replacement.blocks[0].model_copy(
        update={"id": "knowledge_engine_block:duplicate", "position": 1}
    )
    invalid = replacement.model_copy(update={"blocks": [replacement.blocks[0], duplicate]})

    with pytest.raises(KnowledgeRepositoryError, match="repository_unavailable"):
        await repository.commit_snapshot(invalid, operation_id="native-failed-replacement")

    persisted = await repository.get_document(original.document.id)
    children = await repo_query(
        "SELECT * FROM knowledge_engine_block WHERE document_id = $document_id;",
        {"document_id": original.document.id},
    )
    assert persisted.content_hash == original.document.content_hash
    assert persisted.normalized_body == original.document.normalized_body
    assert len(children) == len(original.blocks)


async def test_receipts_exclude_canonical_bytes_and_absolute_roots(clean_namespace):
    source = b"# Native\n\ncanonical-only-secret\n"
    snapshot = _snapshot(source)
    receipt = await KnowledgeRepository().commit_snapshot(
        snapshot, operation_id="native-sanitized-receipt"
    )

    assert source.decode() not in str(receipt)
    assert "/Users/Antman" not in str(receipt)
    rows = await repo_query(
        "SELECT * FROM knowledge_engine_projection_receipt WHERE operation_id = $operation_id;",
        {"operation_id": "native-sanitized-receipt"},
    )
    assert source.decode() not in str(rows)
    assert "/Users/Antman" not in str(rows)


async def test_migration_38_down_up_preserves_engine_records(clean_namespace):
    snapshot = _snapshot(b"# Native\n\nSticky migration proof\n")
    await KnowledgeRepository().commit_snapshot(snapshot, operation_id="native-migration")

    await repo_query(MIGRATION_38_DOWN.read_text(encoding="utf-8"))
    await repo_query("DELETE type::thing('_sbl_migrations', 38);")
    await AsyncMigrationManager().run_migration_up()

    rows = await repo_query(
        "SELECT * FROM $document_id;",
        {"document_id": ensure_record_id(snapshot.document.id)},
    )
    assert rows[0]["content_hash"] == snapshot.document.content_hash


async def test_failed_receipt_retries_same_hash_to_a_complete_snapshot(clean_namespace):
    snapshot = _snapshot(b"# Native\n\nRetry failed receipt\n")
    repository = KnowledgeRepository()
    await repository.record_projection_failure(
        operation_id="native-retry-failed",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    receipt = await repository.commit_snapshot(
        snapshot, operation_id="native-retry-failed"
    )

    assert receipt.status == "projected"
    document = await repository.get_document(snapshot.document.id)
    children = await repo_query(
        "SELECT * FROM knowledge_engine_block WHERE document_id = $document_id;",
        {"document_id": snapshot.document.id},
    )
    assert document.content_hash == snapshot.document.content_hash
    assert len(children) == len(snapshot.blocks)
    rows = await repo_query(
        "SELECT status FROM knowledge_engine_projection_receipt WHERE operation_id = $operation_id;",
        {"operation_id": "native-retry-failed"},
    )
    assert rows == [{"status": "projected"}]


async def test_failure_receipt_replay_and_hash_conflict_are_bounded(clean_namespace):
    snapshot = _snapshot(b"# Native\n\nFailure receipt replay\n")
    repository = KnowledgeRepository()
    first = await repository.record_projection_failure(
        operation_id="native-failure-replay",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )
    replay = await repository.record_projection_failure(
        operation_id="native-failure-replay",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    assert replay == first
    with pytest.raises(KnowledgeRepositoryError, match="operation_conflict"):
        await repository.record_projection_failure(
            operation_id="native-failure-replay",
            space_id=snapshot.space.id,
            relative_locator=snapshot.document.relative_locator,
            input_hash="b" * 64,
            error_code="parser_failed",
        )


async def test_failure_recording_cannot_downgrade_a_success_receipt(clean_namespace):
    snapshot = _snapshot(b"# Native\n\nSuccessful receipt is durable\n")
    repository = KnowledgeRepository()
    projected = await repository.commit_snapshot(
        snapshot, operation_id="native-preserve-success"
    )

    receipt = await repository.record_projection_failure(
        operation_id="native-preserve-success",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    assert receipt == projected
    rows = await repo_query(
        "SELECT status FROM knowledge_engine_projection_receipt WHERE operation_id = $operation_id;",
        {"operation_id": "native-preserve-success"},
    )
    assert rows == [{"status": "projected"}]


async def test_absolute_space_source_ref_is_rejected_before_persistence(clean_namespace):
    snapshot = _snapshot(b"# Native\n\nSource ref boundary\n")
    unsafe = snapshot.model_copy(
        update={"space": snapshot.space.model_copy(update={"source_ref": "/Users/Antman"})}
    )

    with pytest.raises(ValueError, match="invalid_knowledge_engine_source_ref"):
        await KnowledgeRepository().commit_snapshot(
            unsafe, operation_id="native-unsafe-source-ref"
        )

    assert await repo_query("SELECT * FROM knowledge_engine_space;") == []


async def test_concurrent_identical_snapshot_commits_resolve_to_unchanged(
    clean_namespace,
):
    snapshot = _snapshot(b"# Native\n\nConcurrent transaction\n")
    barrier = asyncio.Barrier(2)
    first = KnowledgeRepository(connection_factory=_barrier_factory(clean_namespace, barrier))
    second = KnowledgeRepository(connection_factory=_barrier_factory(clean_namespace, barrier))

    receipts = await asyncio.gather(
        first.commit_snapshot(snapshot, operation_id="native-concurrent"),
        second.commit_snapshot(snapshot, operation_id="native-concurrent"),
    )

    assert sorted(receipt.status for receipt in receipts) == ["projected", "unchanged"]
    rows = await repo_query(
        "SELECT * FROM knowledge_engine_projection_receipt WHERE operation_id = $operation_id;",
        {"operation_id": "native-concurrent"},
    )
    assert len(rows) == 1


async def test_rich_snapshot_persists_every_record_class_with_engine_values(
    clean_namespace,
):
    snapshot = _snapshot(
        b"# Native Rich\n\n[[Target Note#Heading|Target Alias]]\n\n"
        b"![Diagram](assets/diagram.png)\n\n- [ ] Persist all records\n"
    )

    receipt = await KnowledgeRepository().commit_snapshot(
        snapshot, operation_id="native-rich-projection"
    )

    assert receipt.status == "projected"
    counts = await repo_query(
        """
        RETURN {
            spaces: count((SELECT * FROM knowledge_engine_space)),
            documents: count((SELECT * FROM knowledge_engine_document)),
            revisions: count((SELECT * FROM knowledge_engine_source_revision)),
            blocks: count((SELECT * FROM knowledge_engine_block)),
            relations: count((SELECT * FROM knowledge_engine_relation)),
            tasks: count((SELECT * FROM knowledge_engine_task)),
            assets: count((SELECT * FROM knowledge_engine_asset)),
            identities: count((SELECT * FROM knowledge_engine_identity_map)),
            receipts: count((SELECT * FROM knowledge_engine_projection_receipt))
        };
        """
    )
    assert counts == {
        "spaces": 1,
        "documents": 1,
        "revisions": 1,
        "blocks": len(snapshot.blocks),
        "relations": len(snapshot.relations),
        "tasks": len(snapshot.tasks),
        "assets": len(snapshot.assets),
        "identities": len(snapshot.identity_claims),
        "receipts": 1,
    }
    relation = await repo_query(
        "SELECT * FROM knowledge_engine_relation WHERE id = $relation_id;",
        {"relation_id": ensure_record_id(snapshot.relations[0].id)},
    )
    asset = await repo_query(
        "SELECT * FROM knowledge_engine_asset WHERE id = $asset_id;",
        {"asset_id": ensure_record_id(snapshot.assets[0].id)},
    )
    identity = await repo_query(
        """
        SELECT * FROM knowledge_engine_identity_map
        WHERE legacy_kind = $legacy_kind
        AND legacy_id = $legacy_id
        AND source_revision_id = $source_revision_id;
        """,
        snapshot.identity_claims[0].model_dump(),
    )
    assert len(relation) == 1
    assert relation[0]["source_document_id"] == snapshot.document.id
    assert relation[0]["source_block_id"] == snapshot.relations[0].source_block_id
    assert relation[0]["target_text"] == "Target Note"
    assert relation[0]["target_heading"] == "Heading"
    assert relation[0]["alias"] == "Target Alias"
    assert relation[0]["relation_kind"] == "wikilink"
    assert len(asset) == 1
    assert asset[0]["source_document_id"] == snapshot.document.id
    assert asset[0]["relative_locator"] == "assets/diagram.png"
    assert asset[0]["media_kind"] == "image"
    assert len(identity) == 1
    assert identity[0]["legacy_kind"] == snapshot.identity_claims[0].legacy_kind
    assert identity[0]["legacy_id"] == snapshot.identity_claims[0].legacy_id
    assert identity[0]["engine_kind"] == "document"
    assert identity[0]["engine_id"] == snapshot.document.id
    assert identity[0]["source_revision_id"] == snapshot.revision.id
    assert identity[0]["claim_hash"] == snapshot.identity_claims[0].claim_hash


async def test_identity_mapping_conflict_rolls_back_new_snapshot(clean_namespace):
    repository = KnowledgeRepository()
    original = _snapshot(b"# Native\n\nOriginal document\n")
    replacement = _snapshot(b"# Native\n\nReplacement document\n")
    await repository.commit_snapshot(original, operation_id="native-identity-original")
    claim = replacement.identity_claims[0]
    conflicting_mapping = {
        **claim.model_dump(),
        "engine_id": "knowledge_engine_document:legacy_conflict",
        "claim_hash": "0" * 64,
    }
    await repo_query(
        "CREATE knowledge_engine_identity_map CONTENT $mapping;",
        {"mapping": conflicting_mapping},
    )

    with pytest.raises(KnowledgeRepositoryError, match="repository_unavailable"):
        await repository.commit_snapshot(
            replacement, operation_id="native-identity-conflict"
        )

    persisted = await repository.get_document(original.document.id)
    mapping = await repo_query(
        """
        SELECT * FROM knowledge_engine_identity_map
        WHERE legacy_kind = $legacy_kind
        AND legacy_id = $legacy_id
        AND source_revision_id = $source_revision_id;
        """,
        claim.model_dump(),
    )
    assert persisted.content_hash == original.document.content_hash
    assert persisted.normalized_body == original.document.normalized_body
    assert len(mapping) == 1
    assert mapping[0]["engine_id"] == "knowledge_engine_document:legacy_conflict"
    assert mapping[0]["claim_hash"] == "0" * 64
    assert await repo_query(
        "SELECT * FROM knowledge_engine_source_revision WHERE content_hash = $content_hash;",
        {"content_hash": replacement.revision.content_hash},
    ) == []


async def test_checkpoint_and_document_reads_round_trip_with_pagination(clean_namespace):
    snapshot = _snapshot(b"# Native\n\nRead round trip\n")
    repository = KnowledgeRepository()
    await repository.commit_snapshot(snapshot, operation_id="native-read-round-trip")
    checkpoint = BackfillCheckpoint(
        space_id=snapshot.space.id,
        last_relative_locator=snapshot.document.relative_locator,
        last_source_hash=snapshot.revision.content_hash,
        status="completed",
        projected=1,
        unchanged=0,
        failed=0,
        updated_at=NOW,
    )

    saved = await repository.save_checkpoint(checkpoint)
    restored = await repository.get_checkpoint(snapshot.space.id)
    listed = await repository.list_documents(
        space_id=snapshot.space.id, limit=1, offset=0
    )
    after_first_page = await repository.list_documents(
        space_id=snapshot.space.id, limit=1, offset=1
    )
    document = await repository.get_document(snapshot.document.id)

    assert restored == saved
    assert saved.space_id == checkpoint.space_id
    assert saved.last_relative_locator == checkpoint.last_relative_locator
    assert saved.last_source_hash == checkpoint.last_source_hash
    assert saved.status == checkpoint.status
    assert (saved.projected, saved.unchanged, saved.failed) == (1, 0, 0)
    assert listed == [document]
    assert document.id == snapshot.document.id
    assert document.space_id == snapshot.document.space_id
    assert document.relative_locator == snapshot.document.relative_locator
    assert document.content_hash == snapshot.document.content_hash
    assert document.source_revision_id == snapshot.document.source_revision_id
    assert document.normalized_body == snapshot.document.normalized_body
    assert after_first_page == []
