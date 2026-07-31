from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from deeper_notebook.knowledge_engine.repository import KnowledgeRepository


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
        if "resolved_block_ids" in statement:
            return [
                {
                    "document_id": "knowledge_engine_document:current",
                    "resolved_block_ids": [
                        {
                            "legacy_id": "heading-parser",
                            "engine_id": "knowledge_engine_block:heading",
                        },
                        {
                            "legacy_id": "claim-1",
                            "engine_id": "knowledge_engine_block:claim",
                        },
                    ],
                }
            ]
        if "legacy_container_id" in statement:
            return [
                {
                    "document_id": "knowledge_engine_document:current",
                    "space_id": "knowledge_engine_space:fixture",
                    "authority_kind": "external_read_only",
                    "source_kind": "markdown",
                    "title": "Plan",
                    "relative_locator": "pages/plan.md",
                    "legacy_note_id": "note:plan",
                    "legacy_container_id": "vault_mount:fixture",
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
