"""Safe runtime boundary for the optional unified knowledge engine."""

from __future__ import annotations

import asyncio

from deeper_notebook.environment import resolve_env
from deeper_notebook.knowledge_engine.backfill import (
    BackfillResult,
    CanonicalSourceCatalog,
    KnowledgeBackfillService,
)
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument
from deeper_notebook.knowledge_engine.repository import (
    EngineProjectionStatus,
    KnowledgeRepository,
)
from deeper_notebook.knowledge_engine.shadow import KnowledgeShadowCoordinator


def enabled_setting(canonical_name: str) -> bool:
    """Return one registered engine flag using a deliberately strict parser."""
    value = resolve_env(canonical_name, "false")
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("invalid knowledge engine boolean setting")


class KnowledgeEngineService:
    """Own engine dependencies while exposing only safe projections and results."""

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        coordinator: KnowledgeShadowCoordinator,
        catalog: CanonicalSourceCatalog,
        backfill: KnowledgeBackfillService,
    ) -> None:
        self._repository = repository
        self.coordinator = coordinator
        self._catalog = catalog
        self._backfill = backfill
        self._transition_lock = asyncio.Lock()

    async def status(self) -> EngineProjectionStatus:
        return await self._repository.projection_status()

    async def get_document(self, document_id: str) -> KnowledgeDocument:
        return await self._repository.get_document(document_id)

    async def list_documents(
        self,
        *,
        space_id: str | None,
        limit: int,
        offset: int,
    ) -> list[KnowledgeDocument]:
        return await self._repository.list_documents(
            space_id=space_id,
            limit=limit,
            offset=offset,
        )

    async def run_backfill(self) -> BackfillResult:
        async with self._transition_lock:
            return await self._backfill.run()


__all__ = ["KnowledgeEngineService", "enabled_setting"]
