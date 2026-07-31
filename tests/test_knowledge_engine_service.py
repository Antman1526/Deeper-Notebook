from __future__ import annotations

import pytest

from deeper_notebook.knowledge_engine.backfill import BackfillResult
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


class _Backfill:
    async def run(self):
        return BackfillResult(projected=1)


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
    assert await service.run_backfill() == BackfillResult(projected=1)
    assert service.coordinator is coordinator


@pytest.mark.parametrize(
    ("value", "expected"),
    (("1", True), (" TRUE ", True), ("yes", True), ("on", True), ("0", False), (" false ", False), ("NO", False), ("off", False)),
)
def test_enabled_setting_uses_a_strict_boolean_parser(monkeypatch, value, expected):
    monkeypatch.setattr(
        "deeper_notebook.knowledge_engine.service.resolve_env",
        lambda *_args, **_kwargs: value,
    )

    assert enabled_setting("DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED") is expected


def test_enabled_setting_rejects_an_unknown_boolean(monkeypatch):
    monkeypatch.setattr(
        "deeper_notebook.knowledge_engine.service.resolve_env",
        lambda *_args, **_kwargs: "maybe",
    )

    with pytest.raises(ValueError, match="invalid knowledge engine boolean setting"):
        enabled_setting("DEEPER_NOTEBOOK_KNOWLEDGE_ENGINE_SHADOW_ENABLED")
