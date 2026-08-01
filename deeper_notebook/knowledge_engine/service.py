"""Safe runtime boundary for the optional unified knowledge engine."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

from deeper_notebook.environment import resolve_env
from deeper_notebook.knowledge_engine.backfill import (
    BackfillResult,
    CanonicalSourceCatalog,
    KnowledgeBackfillService,
)
from deeper_notebook.knowledge_engine.contracts import (
    BackfillCheckpoint,
    EquivalenceReport,
    KnowledgeDocument,
    ProjectionDigest,
)
from deeper_notebook.knowledge_engine.equivalence import compare_projection_digests
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
        legacy_digest_builder: Callable[
            [str, tuple[str, ...]], Awaitable[ProjectionDigest]
        ]
        | None = None,
        unified_digest_builder: Callable[
            [str, tuple[str, ...]], Awaitable[ProjectionDigest]
        ]
        | None = None,
    ) -> None:
        self._repository = repository
        self.coordinator = coordinator
        self._catalog = catalog
        self._backfill = backfill
        self._legacy_digest_builder = legacy_digest_builder
        self._unified_digest_builder = unified_digest_builder
        self._transition_lock = asyncio.Lock()

    async def status(self) -> EngineProjectionStatus:
        return await self._repository.projection_status()

    async def get_document(self, document_id: str) -> KnowledgeDocument:
        return await self._repository.get_document(document_id)

    async def open_descriptor(self, document_id: str):
        return await self._repository.open_descriptor(document_id)

    async def get_current_block(
        self,
        *,
        document_id: str,
        block_id: str,
        source_revision_id: str,
    ):
        return await self._repository.get_current_block(
            document_id=document_id,
            block_id=block_id,
            source_revision_id=source_revision_id,
        )

    async def get_current_block_content(
        self,
        *,
        document_id: str,
        block_id: str,
        source_revision_id: str,
    ):
        return await self._repository.get_current_block_content(
            document_id=document_id,
            block_id=block_id,
            source_revision_id=source_revision_id,
        )

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

    async def resolve_legacy_page(
        self, *, legacy_note_id: str, block_keys: tuple[str, ...]
    ):
        return await self._repository.resolve_legacy_page(
            legacy_note_id=legacy_note_id,
            block_keys=block_keys,
        )

    async def backfill_checkpoints(
        self, space_ids: tuple[str, ...]
    ) -> list[BackfillCheckpoint]:
        if (
            not isinstance(space_ids, tuple)
            or not 1 <= len(space_ids) <= 32
            or len(set(space_ids)) != len(space_ids)
            or any(
                not isinstance(space_id, str)
                or re.fullmatch(r"knowledge_engine_space:[A-Za-z0-9_-]+", space_id)
                is None
                for space_id in space_ids
            )
        ):
            raise ValueError("invalid_backfill_checkpoint_inventory")
        checkpoints: list[BackfillCheckpoint] = []
        for space_id in sorted(space_ids):
            checkpoint = await self._repository.get_checkpoint(space_id)
            if checkpoint is not None:
                checkpoints.append(checkpoint)
        return checkpoints

    async def run_backfill(self) -> BackfillResult:
        async with self._transition_lock:
            return await self._backfill.run()

    async def equivalence_report(
        self, *, space_id: str, exact_queries: tuple[str, ...]
    ) -> EquivalenceReport:
        if (
            not isinstance(space_id, str)
            or re.fullmatch(r"knowledge_engine_space:[A-Za-z0-9_-]+", space_id) is None
            or not isinstance(exact_queries, tuple)
            or not 1 <= len(exact_queries) <= 32
            or any(
                not isinstance(query, str) or not query.strip() or len(query) > 256
                for query in exact_queries
            )
        ):
            raise ValueError("invalid_equivalence_queries")
        if self._legacy_digest_builder is None or self._unified_digest_builder is None:
            raise RuntimeError("knowledge_engine_equivalence_unavailable")
        legacy = await self._legacy_digest_builder(space_id, exact_queries)
        unified = await self._unified_digest_builder(space_id, exact_queries)
        return compare_projection_digests(legacy, unified)


__all__ = ["KnowledgeEngineService", "enabled_setting"]
