from __future__ import annotations

from datetime import datetime, timezone

import pytest

from deeper_notebook.knowledge_engine.backfill import BackfillResult
from deeper_notebook.knowledge_engine.contracts import (
    BackfillCheckpoint,
    ProjectionDigest,
)
from deeper_notebook.knowledge_engine.service import (
    KnowledgeEngineService,
    enabled_setting,
)


class _Repository:
    async def projection_status(self):
        return "status"

    async def get_document(self, document_id: str):
        return {"document_id": document_id}

    async def list_documents(self, *, space_id: str | None, limit: int, offset: int):
        return [{"space_id": space_id, "limit": limit, "offset": offset}]

    async def resolve_legacy_page(
        self, *, legacy_note_id: str, block_keys: tuple[str, ...]
    ):
        return {
            "document_id": "knowledge_engine_document:fixture",
            "block_ids": {key: f"knowledge_engine_block:{key}" for key in block_keys},
        }

    async def open_descriptor(self, document_id: str):
        return {"document_id": document_id}

    async def get_current_block(self, **kwargs):
        return kwargs

    async def get_current_block_content(self, **kwargs):
        return {"content": kwargs}

    async def get_checkpoint(self, space_id: str):
        if space_id.endswith(":missing"):
            return None
        return BackfillCheckpoint(
            space_id=space_id,
            last_relative_locator="Pages/Plan.md",
            last_source_hash="a" * 64,
            status="completed",
            projected=1,
            unchanged=0,
            failed=0,
            updated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )


class _Backfill:
    async def run(self):
        return BackfillResult(projected=1)


def _digest() -> ProjectionDigest:
    return ProjectionDigest(
        space_id="knowledge_engine_space:fixture",
        document_count=0,
        block_count=0,
        relation_count=0,
        task_count=0,
        asset_count=0,
    )


@pytest.mark.asyncio
async def test_service_owns_and_delegates_the_safe_engine_boundary():
    repository = _Repository()
    coordinator = object()
    catalog = object()
    service = KnowledgeEngineService(
        repository=repository,
        coordinator=coordinator,
        catalog=catalog,
        backfill=_Backfill(),
    )

    assert await service.status() == "status"
    assert await service.get_document("knowledge_engine_document:fixture") == {
        "document_id": "knowledge_engine_document:fixture"
    }
    assert await service.list_documents(space_id=None, limit=3, offset=2) == [
        {"space_id": None, "limit": 3, "offset": 2}
    ]
    assert [
        checkpoint.space_id
        for checkpoint in await service.backfill_checkpoints(
            (
                "knowledge_engine_space:fixture",
                "knowledge_engine_space:missing",
            )
        )
    ] == ["knowledge_engine_space:fixture"]
    assert await service.run_backfill() == BackfillResult(projected=1)
    assert await service.resolve_legacy_page(
        legacy_note_id="note:fixture", block_keys=("first", "second")
    ) == {
        "document_id": "knowledge_engine_document:fixture",
        "block_ids": {
            "first": "knowledge_engine_block:first",
            "second": "knowledge_engine_block:second",
        },
    }
    assert await service.open_descriptor("knowledge_engine_document:fixture") == {
        "document_id": "knowledge_engine_document:fixture"
    }
    assert await service.get_current_block(
        document_id="knowledge_engine_document:fixture",
        block_id="knowledge_engine_block:fixture",
        source_revision_id="knowledge_engine_revision:fixture",
    ) == {
        "document_id": "knowledge_engine_document:fixture",
        "block_id": "knowledge_engine_block:fixture",
        "source_revision_id": "knowledge_engine_revision:fixture",
    }
    assert await service.get_current_block_content(
        document_id="knowledge_engine_document:fixture",
        block_id="knowledge_engine_block:fixture",
        source_revision_id="knowledge_engine_revision:fixture",
    ) == {
        "content": {
            "document_id": "knowledge_engine_document:fixture",
            "block_id": "knowledge_engine_block:fixture",
            "source_revision_id": "knowledge_engine_revision:fixture",
        }
    }
    assert service.coordinator is coordinator


@pytest.mark.asyncio
async def test_service_builds_both_digests_and_rejects_unbounded_queries():
    calls: list[tuple[str, tuple[str, ...]]] = []

    async def legacy(space_id: str, queries: tuple[str, ...]) -> ProjectionDigest:
        calls.append((space_id, queries))
        return _digest()

    async def unified(space_id: str, queries: tuple[str, ...]) -> ProjectionDigest:
        calls.append((space_id, queries))
        return _digest()

    service = KnowledgeEngineService(
        repository=_Repository(),
        coordinator=object(),
        catalog=object(),
        backfill=_Backfill(),
        legacy_digest_builder=legacy,
        unified_digest_builder=unified,
    )

    report = await service.equivalence_report(
        space_id="knowledge_engine_space:fixture",
        exact_queries=("research",),
    )

    assert report.passed is True
    assert calls == [
        ("knowledge_engine_space:fixture", ("research",)),
        ("knowledge_engine_space:fixture", ("research",)),
    ]
    with pytest.raises(ValueError, match="invalid_equivalence_queries"):
        await service.equivalence_report(
            space_id="knowledge_engine_space:fixture",
            exact_queries=(),
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("1", True),
        (" TRUE ", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        (" false ", False),
        ("NO", False),
        ("off", False),
    ),
)
def test_enabled_setting_uses_a_strict_boolean_parser(monkeypatch, value, expected):
    monkeypatch.setattr(
        "deeper_notebook.knowledge_engine.service.resolve_env",
        lambda *_args, **_kwargs: value,
    )

    assert (
        enabled_setting("DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED") is expected
    )


def test_enabled_setting_rejects_an_unknown_boolean(monkeypatch):
    monkeypatch.setattr(
        "deeper_notebook.knowledge_engine.service.resolve_env",
        lambda *_args, **_kwargs: "maybe",
    )

    with pytest.raises(ValueError, match="invalid knowledge engine boolean setting"):
        enabled_setting("DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED")
