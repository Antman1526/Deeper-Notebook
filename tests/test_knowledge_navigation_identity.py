from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from surrealdb import AsyncSurreal

from deeper_notebook.database.repository import ensure_record_id
from deeper_notebook.knowledge_engine.repository import KnowledgeRepository


@pytest.fixture
async def migrated_memory_connection():
    database = AsyncSurreal("mem://")
    await database.connect()
    await database.use("identity", "identity")
    root = Path(__file__).resolve().parents[1]
    await database.query(
        (root / "deeper_notebook/database/migrations/38.surrealql").read_text()
    )

    results: list[Any] = []

    class _Connection:
        async def query(self, statement: str, variables: dict[str, Any] | None = None):
            result = await database.query(statement, variables)
            results.append(result)
            return result

    @asynccontextmanager
    async def factory():
        yield _Connection()

    try:
        yield type(
            "MemoryConnection",
            (),
            {"factory": factory, "database": database, "results": results},
        )
    finally:
        await database.close()


async def _seed_page_identity(
    database: AsyncSurreal,
    *,
    space_id: str,
    document_id: str,
    revision_id: str,
    authority_kind: str,
    source_kind: str,
    relative_locator: str,
    source_native_id: str,
    source_ref: str,
) -> None:
    await database.query(
        """
        CREATE $space_id CONTENT {
            display_name: 'Identity fixture', authority_kind: $authority_kind,
            source_kind: $source_kind, source_ref: $source_ref,
            format_mode: 'markdown', availability_state: 'available',
            projection_state: 'ready', adapter_version: 'test',
            parser_version: 'test', policy_version: 1, capabilities: []
        };
        CREATE $document_id CONTENT {
            space_id: $space_text, source_native_id: $source_native_id,
            authority_kind: $authority_kind, relative_locator: $relative_locator,
            document_kind: 'note', title: 'Current page', normalized_body: 'secret body',
            properties: { secret: 'never-return' }, tags: [], content_hash: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            source_revision_id: $revision_id, provenance: 'test', availability: 'available',
            parse_state: 'ready', journal_date: NONE, capabilities: ['read'], observed_at: time::now()
        };
        CREATE knowledge_engine_block:current CONTENT {
            space_id: $space_text, document_id: $document_text, parent_block_id: NONE,
            position: 0, source_key: 'pages/plan.md/blocks/heading', block_kind: 'heading',
            markdown: '# Plan', plain_text: 'Plan', properties: {}, raw_task_state: NONE,
            normalized_task_state: NONE, heading_path: [], source_start: 0, source_end: 6,
            source_revision_id: $revision_id, capabilities: []
        };
        """,
        {
            "space_id": ensure_record_id(space_id),
            "space_text": space_id,
            "document_id": ensure_record_id(document_id),
            "document_text": document_id,
            "revision_id": revision_id,
            "authority_kind": authority_kind,
            "source_kind": source_kind,
            "relative_locator": relative_locator,
            "source_native_id": source_native_id,
            "source_ref": source_ref,
        },
    )


async def _claim(
    database: AsyncSurreal,
    *,
    legacy_kind: str,
    legacy_id: str,
    engine_kind: str,
    engine_id: str,
    revision_id: str,
    claim_hash: str,
) -> None:
    await database.query(
        "CREATE knowledge_engine_identity_map CONTENT $claim;",
        {
            "claim": {
                "legacy_kind": legacy_kind,
                "legacy_id": legacy_id,
                "engine_kind": engine_kind,
                "engine_id": engine_id,
                "source_revision_id": revision_id,
                "claim_hash": claim_hash,
            }
        },
    )


class _Connection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []

    @asynccontextmanager
    async def factory(self):
        yield self

    async def query(
        self, statement: str, variables: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        variables = variables or {}
        self.queries.append((statement, variables))
        if "block_claims" in statement:
            return [
                {
                    "document_claims": [
                        {
                            "engine_id": "knowledge_engine_document:current",
                            "source_revision_id": "knowledge_engine_revision:current",
                        }
                    ],
                    "documents": [
                        {
                            "id": "knowledge_engine_document:current",
                            "source_revision_id": "knowledge_engine_revision:current",
                        }
                    ],
                    "block_claims": [
                        {
                            "legacy_id": "heading-parser",
                            "engine_id": "knowledge_engine_block:heading",
                            "source_revision_id": "knowledge_engine_revision:current",
                        },
                        {
                            "legacy_id": "claim-1",
                            "engine_id": "knowledge_engine_block:claim",
                            "source_revision_id": "knowledge_engine_revision:current",
                        },
                    ],
                    "blocks": [
                        {
                            "id": "knowledge_engine_block:heading",
                            "document_id": "knowledge_engine_document:current",
                            "source_revision_id": "knowledge_engine_revision:current",
                        },
                        {
                            "id": "knowledge_engine_block:claim",
                            "document_id": "knowledge_engine_document:current",
                            "source_revision_id": "knowledge_engine_revision:current",
                        },
                    ],
                }
            ]
        if "container_claims" in statement:
            return [
                {
                    "document_id": "knowledge_engine_document:current",
                    "space_id": "knowledge_engine_space:fixture",
                    "authority_kind": "external_read_only",
                    "source_kind": "markdown",
                    "title": "Plan",
                    "relative_locator": "pages/plan.md",
                    "document_claims": [
                        {"legacy_kind": "note", "legacy_id": "note:plan"}
                    ],
                    "container_claims": [
                        {
                            "legacy_kind": "vault_mount",
                            "legacy_id": "vault_mount:fixture",
                        }
                    ],
                }
            ]
        return []


@pytest.fixture
def repository() -> KnowledgeRepository:
    connection = _Connection()
    return KnowledgeRepository(connection_factory=connection.factory)


@pytest.mark.asyncio
async def test_resolve_legacy_page_ignores_stale_identity_claims(repository):
    resolved = await repository.resolve_legacy_page(
        legacy_note_id="note:plan",
        block_keys=("heading-parser", "claim-1"),
    )

    assert resolved.document_id == "knowledge_engine_document:current"
    assert resolved.block_ids == {
        "heading-parser": "knowledge_engine_block:heading",
        "claim-1": "knowledge_engine_block:claim",
    }
    assert "knowledge_engine_document:stale" not in resolved.model_dump_json()


@pytest.mark.asyncio
async def test_open_descriptor_contains_safe_logical_hints_only(repository):
    descriptor = await repository.open_descriptor("knowledge_engine_document:current")

    assert descriptor is not None
    payload = descriptor.model_dump_json()
    assert descriptor.legacy_note_id == "note:plan"
    assert descriptor.legacy_container_id == "vault_mount:fixture"
    assert descriptor.relative_locator == "pages/plan.md"
    assert "/Users/" not in payload
    assert "normalized_body" not in payload


@pytest.mark.asyncio
async def test_resolve_legacy_page_executes_one_valid_migration_38_query_and_rejects_stale_claims(
    migrated_memory_connection,
):
    space_id = "knowledge_engine_space:vault"
    document_id = "knowledge_engine_document:current"
    revision_id = "knowledge_engine_revision:current"
    await _seed_page_identity(
        migrated_memory_connection.database,
        space_id=space_id,
        document_id=document_id,
        revision_id=revision_id,
        authority_kind="external_read_only",
        source_kind="markdown",
        relative_locator="pages/plan.md",
        source_native_id="unsafe-native",
        source_ref="/Users/unsafe/source-root",
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind="note",
        legacy_id="note:plan",
        engine_kind="document",
        engine_id=document_id,
        revision_id=revision_id,
        claim_hash="1" * 64,
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind="note",
        legacy_id="note:plan",
        engine_kind="document",
        engine_id=document_id,
        revision_id="knowledge_engine_revision:stale",
        claim_hash="2" * 64,
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind="source_native_block",
        legacy_id="heading",
        engine_kind="block",
        engine_id="knowledge_engine_block:current",
        revision_id=revision_id,
        claim_hash="3" * 64,
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind="source_native_block",
        legacy_id="heading",
        engine_kind="block",
        engine_id="knowledge_engine_block:stale",
        revision_id="knowledge_engine_revision:stale",
        claim_hash="4" * 64,
    )
    repository = KnowledgeRepository(
        connection_factory=migrated_memory_connection.factory
    )
    resolved = await repository.resolve_legacy_page(
        legacy_note_id="note:plan", block_keys=("heading",)
    )

    assert len(migrated_memory_connection.results) == 1
    assert isinstance(migrated_memory_connection.results[-1], dict)
    assert resolved.document_id == document_id
    assert resolved.block_ids == {"heading": "knowledge_engine_block:current"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "authority_kind,source_kind,note_kind,note_id,container_kind,container_id,document_id,space_id"
    ),
    [
        (
            "external_read_only",
            "markdown",
            "note",
            "note:plan",
            "vault_mount",
            "vault_mount:fixture",
            "knowledge_engine_document:vault",
            "knowledge_engine_space:vault",
        ),
        (
            "app_owned",
            "overlay",
            "overlay_note",
            "overlay_note:daily",
            "overlay_space",
            "overlay_space:default",
            "knowledge_engine_document:overlay",
            "knowledge_engine_space:overlay",
        ),
    ],
)
async def test_open_descriptor_uses_current_stable_identity_claims_only(
    migrated_memory_connection,
    authority_kind,
    source_kind,
    note_kind,
    note_id,
    container_kind,
    container_id,
    document_id,
    space_id,
):
    revision_id = "knowledge_engine_revision:current"
    await _seed_page_identity(
        migrated_memory_connection.database,
        space_id=space_id,
        document_id=document_id,
        revision_id=revision_id,
        authority_kind=authority_kind,
        source_kind=source_kind,
        relative_locator="pages/plan.md",
        source_native_id="/Users/unsafe/source-native",
        source_ref="/Users/unsafe/source-ref",
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind=note_kind,
        legacy_id=note_id,
        engine_kind="document",
        engine_id=document_id,
        revision_id=revision_id,
        claim_hash="5" * 64,
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind=container_kind,
        legacy_id=container_id,
        engine_kind="space",
        engine_id=space_id,
        revision_id=revision_id,
        claim_hash="6" * 64,
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind=note_kind,
        legacy_id=f"{note_kind}:stale",
        engine_kind="document",
        engine_id=document_id,
        revision_id="knowledge_engine_revision:stale",
        claim_hash="7" * 64,
    )
    await _claim(
        migrated_memory_connection.database,
        legacy_kind=container_kind,
        legacy_id=f"{container_kind}:stale",
        engine_kind="space",
        engine_id=space_id,
        revision_id="knowledge_engine_revision:stale",
        claim_hash="8" * 64,
    )

    descriptor = await KnowledgeRepository(
        connection_factory=migrated_memory_connection.factory
    ).open_descriptor(document_id)

    assert descriptor is not None
    assert descriptor.legacy_note_id == note_id
    assert descriptor.legacy_container_id == container_id
    payload = descriptor.model_dump_json()
    assert "/Users/" not in payload
    assert "source_ref" not in payload
    assert "normalized_body" not in payload


@pytest.mark.asyncio
async def test_current_block_lookup_is_bounded_to_document_and_revision(
    migrated_memory_connection,
):
    space_id = "knowledge_engine_space:blocks"
    document_id = "knowledge_engine_document:blocks"
    revision_id = "knowledge_engine_revision:current"
    await _seed_page_identity(
        migrated_memory_connection.database,
        space_id=space_id,
        document_id=document_id,
        revision_id=revision_id,
        authority_kind="external_read_only",
        source_kind="markdown",
        relative_locator="pages/blocks.md",
        source_native_id="unsafe-native",
        source_ref="/Users/unsafe/source-root",
    )
    repository = KnowledgeRepository(
        connection_factory=migrated_memory_connection.factory
    )

    current = await repository.get_current_block(
        document_id=document_id,
        block_id="knowledge_engine_block:current",
        source_revision_id=revision_id,
    )
    wrong_document = await repository.get_current_block(
        document_id="knowledge_engine_document:other",
        block_id="knowledge_engine_block:current",
        source_revision_id=revision_id,
    )
    wrong_revision = await repository.get_current_block(
        document_id=document_id,
        block_id="knowledge_engine_block:current",
        source_revision_id="knowledge_engine_revision:other",
    )

    assert current is not None
    assert current.document_id == document_id
    assert wrong_document is None
    assert wrong_revision is None
    assert all(
        "markdown" not in str(result) for result in migrated_memory_connection.results
    )


@pytest.mark.asyncio
async def test_current_block_content_projection_is_bounded_and_excludes_source_metadata(
    migrated_memory_connection,
):
    space_id = "knowledge_engine_space:block_content"
    document_id = "knowledge_engine_document:block_content"
    revision_id = "knowledge_engine_revision:current"
    await _seed_page_identity(
        migrated_memory_connection.database,
        space_id=space_id,
        document_id=document_id,
        revision_id=revision_id,
        authority_kind="external_read_only",
        source_kind="markdown",
        relative_locator="pages/block-content.md",
        source_native_id="unsafe-native",
        source_ref="/Users/unsafe/source-root",
    )
    repository = KnowledgeRepository(
        connection_factory=migrated_memory_connection.factory
    )

    block = await repository.get_current_block_content(
        document_id=document_id,
        block_id="knowledge_engine_block:current",
        source_revision_id=revision_id,
    )

    assert block is not None
    assert block.block_id == "knowledge_engine_block:current"
    assert block.plain_text == "Plan"
    payload = block.model_dump_json()
    assert "source_key" not in payload
    assert "markdown" not in payload
    assert "/Users/" not in payload
