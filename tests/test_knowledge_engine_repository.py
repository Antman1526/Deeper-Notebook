from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

import pytest

from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import SourceEnvelope
from deeper_notebook.knowledge_engine.repository import (
    KnowledgeRepository,
    KnowledgeRepositoryError,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.receipts: dict[str, dict[str, Any]] = {}

    @asynccontextmanager
    async def factory(self):
        yield self

    async def query(
        self, statement: str, variables: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        variables = variables or {}
        self.queries.append((statement, variables))
        if "BEGIN TRANSACTION;" in statement:
            if "success_receipt" not in variables:
                existing = self.receipts.get(variables["receipt"]["operation_id"])
                if existing is not None:
                    return [{"receipt": existing}]
                receipt = dict(variables["receipt"])
                self.receipts[receipt["operation_id"]] = receipt
                return [{"receipt": receipt}]
            existing = self.receipts.get(variables["operation_id"])
            if existing is not None:
                if (
                    existing["status"] == "failed"
                    and existing["input_hash"] == variables["input_hash"]
                ):
                    receipt = dict(variables["success_receipt"])
                    self.receipts[receipt["operation_id"]] = receipt
                    return [
                        {
                            "outcome": "projected",
                            "prior_input_hash": existing["input_hash"],
                            "existing_status": "failed",
                            "receipt": receipt,
                        }
                    ]
                outcome = (
                    "unchanged"
                    if existing["input_hash"] == variables["input_hash"]
                    else "operation_conflict"
                )
                return [
                    {
                        "outcome": outcome,
                        "prior_input_hash": existing["input_hash"],
                        "existing_status": existing["status"],
                        "receipt": existing,
                    }
                ]
            receipt = dict(variables["success_receipt"])
            self.receipts[receipt["operation_id"]] = receipt
            return [
                {
                    "outcome": "projected",
                    "prior_input_hash": None,
                    "existing_status": "missing",
                    "receipt": receipt,
                }
            ]
        return []


@pytest.fixture
def fake_connection() -> FakeConnection:
    return FakeConnection()


@pytest.fixture
def snapshot():
    raw = b"# Portable Page\n\n- [ ] Ship atomic snapshots\n"
    envelope = SourceEnvelope(
        space_id="knowledge_engine_space:repository",
        space_display_name="Repository Test Space",
        source_ref="fixture:repository",
        authority_kind="external_read_only",
        source_kind="markdown",
        format_mode="markdown",
        relative_locator="Pages/Repository.md",
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


@pytest.mark.asyncio
async def test_commit_snapshot_uses_one_transaction(snapshot, fake_connection):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)

    receipt = await repository.commit_snapshot(snapshot, operation_id="shadow-project-one")

    assert len(fake_connection.queries) == 1
    statement, variables = fake_connection.queries[-1]
    assert "BEGIN TRANSACTION;" in statement
    assert "COMMIT TRANSACTION;" in statement
    assert "knowledge_engine_document" in statement
    assert "knowledge_engine_projection_receipt" in statement
    assert receipt.status == "projected"
    assert "canonical_bytes" not in variables
    assert "/Users/" not in str(variables)


@pytest.mark.asyncio
async def test_commit_snapshot_rejects_operation_replay_with_other_hash(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    await repository.commit_snapshot(snapshot, operation_id="same-operation")
    changed = snapshot.model_copy(
        update={
            "revision": snapshot.revision.model_copy(
                update={"content_hash": "b" * 64}
            )
        }
    )

    with pytest.raises(KnowledgeRepositoryError, match="operation_conflict"):
        await repository.commit_snapshot(changed, operation_id="same-operation")


@pytest.mark.asyncio
async def test_commit_snapshot_rejects_untrusted_child_record_references(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    invalid_block = snapshot.blocks[0].model_copy(
        update={"parent_block_id": "note:untrusted"}
    )
    invalid = snapshot.model_copy(update={"blocks": [invalid_block]})

    with pytest.raises(ValueError, match="invalid_knowledge_engine_block_id"):
        await repository.commit_snapshot(invalid, operation_id="unsafe-child-reference")

    assert fake_connection.queries == []


@pytest.mark.asyncio
async def test_checkpoint_rejects_a_non_engine_space_id(fake_connection):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)

    with pytest.raises(ValueError, match="invalid_knowledge_engine_space_id"):
        await repository.get_checkpoint("space:untrusted")

    assert fake_connection.queries == []


@pytest.mark.asyncio
async def test_commit_snapshot_keeps_schema_string_foreign_keys_as_strings(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)

    await repository.commit_snapshot(snapshot, operation_id="schema-string-foreign-keys")

    _, variables = fake_connection.queries[0]
    assert variables["document_id"] == snapshot.document.id
    assert variables["space_id"] == snapshot.space.id
    assert str(variables["document_record_id"]) == snapshot.document.id
    assert str(variables["space_record_id"]) == snapshot.space.id


@pytest.mark.asyncio
async def test_commit_snapshot_rejects_unknown_identity_engine_kinds(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    invalid_claim = snapshot.identity_claims[0].model_copy(
        update={"engine_kind": "untrusted"}
    )
    invalid = snapshot.model_copy(update={"identity_claims": [invalid_claim]})

    with pytest.raises(ValueError, match="invalid_knowledge_engine_engine_id"):
        await repository.commit_snapshot(invalid, operation_id="unsafe-identity-kind")

    assert fake_connection.queries == []


@pytest.mark.asyncio
async def test_failed_receipt_retries_the_same_snapshot_to_success(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    await repository.record_projection_failure(
        operation_id="retry-failed-snapshot",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    receipt = await repository.commit_snapshot(
        snapshot, operation_id="retry-failed-snapshot"
    )

    assert receipt.status == "projected"
    assert fake_connection.receipts["retry-failed-snapshot"]["status"] == "projected"


@pytest.mark.asyncio
async def test_failure_receipt_replay_is_exactly_idempotent(snapshot, fake_connection):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    first = await repository.record_projection_failure(
        operation_id="exact-failure-replay",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )
    replay = await repository.record_projection_failure(
        operation_id="exact-failure-replay",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    assert replay == first


@pytest.mark.asyncio
async def test_failure_receipt_rejects_a_different_input_hash(snapshot, fake_connection):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    await repository.record_projection_failure(
        operation_id="failure-hash-conflict",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    with pytest.raises(KnowledgeRepositoryError, match="operation_conflict"):
        await repository.record_projection_failure(
            operation_id="failure-hash-conflict",
            space_id=snapshot.space.id,
            relative_locator=snapshot.document.relative_locator,
            input_hash="b" * 64,
            error_code="parser_failed",
        )


@pytest.mark.asyncio
async def test_failure_recording_never_downgrades_a_successful_receipt(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    projected = await repository.commit_snapshot(
        snapshot, operation_id="preserve-success-receipt"
    )

    receipt = await repository.record_projection_failure(
        operation_id="preserve-success-receipt",
        space_id=snapshot.space.id,
        relative_locator=snapshot.document.relative_locator,
        input_hash=snapshot.revision.content_hash,
        error_code="parser_failed",
    )

    assert receipt == projected
    assert fake_connection.receipts["preserve-success-receipt"]["status"] == "projected"


@pytest.mark.asyncio
async def test_commit_snapshot_rejects_an_absolute_space_source_ref_before_query(
    snapshot, fake_connection
):
    repository = KnowledgeRepository(connection_factory=fake_connection.factory)
    unsafe = snapshot.model_copy(
        update={
            "space": snapshot.space.model_copy(update={"source_ref": "/Users/Antman"})
        }
    )

    with pytest.raises(ValueError, match="invalid_knowledge_engine_source_ref"):
        await repository.commit_snapshot(unsafe, operation_id="unsafe-source-ref")

    assert fake_connection.queries == []
