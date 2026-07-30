"""Native SurrealDB proof for atomic unified knowledge projections."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from deeper_notebook.database.async_migrate import AsyncMigrationManager
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import SourceEnvelope
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
