"""Bounded two-phase cleanup for source-derived visual cache records."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from deeper_notebook.source_visuals.contracts import SourceVisualRecord
from deeper_notebook.source_visuals.storage import (
    SourceVisualStorageError,
    SourceVisualStore,
    TombstonedVisualAsset,
)


class SourceVisualCleanupRepository(Protocol):
    async def find_ready_by_asset_relpath(
        self, relpath: str
    ) -> SourceVisualRecord | None: ...

    async def delete_ready_if_current(self, record: SourceVisualRecord) -> bool: ...

    async def list_ready_for_eviction(
        self, *, limit: int
    ) -> Sequence[SourceVisualRecord]: ...

    async def is_claim_active(self, record: SourceVisualRecord) -> bool: ...


class SourceVisualCleanup:
    """Coordinate exact file tombstones with conditional repository deletion."""

    def __init__(
        self, store: SourceVisualStore, repository: SourceVisualCleanupRepository
    ) -> None:
        self._store = store
        self._repository = repository

    async def delete_record(self, record: SourceVisualRecord) -> bool:
        tombstone = self._store.tombstone(record)
        if tombstone is None:
            return False
        try:
            deleted = await self._repository.delete_ready_if_current(record)
        except Exception:
            self._restore_after_failed_delete(tombstone)
            raise
        if not deleted:
            self._restore_after_failed_delete(tombstone)
            return False
        try:
            self._store.remove_tombstone(tombstone)
        except (OSError, SourceVisualStorageError):
            # The row is gone, so a later bounded reconciliation owns cleanup.
            pass
        return True

    def _restore_after_failed_delete(self, tombstone: TombstonedVisualAsset) -> None:
        self._store.restore_tombstone(tombstone)

    async def reconcile_tombstones(self, *, limit: int = 100) -> int:
        tombstones = self._store.list_tombstones(limit=limit)
        processed = 0
        for tombstone in tombstones:
            try:
                record = await self._repository.find_ready_by_asset_relpath(
                    tombstone.asset_relpath
                )
            except Exception:
                continue
            try:
                if (
                    isinstance(record, SourceVisualRecord)
                    and record.asset_relpath == tombstone.asset_relpath
                    and record.asset_sha256 == tombstone.asset_sha256
                ):
                    try:
                        self._store.restore_tombstone(tombstone)
                    except SourceVisualStorageError as exc:
                        if exc.code != "TOMBSTONE_INVALID":
                            raise
                        # A crash-safe replacement may already occupy the
                        # canonical name. Validate it before removing the old
                        # duplicate tombstone.
                        self._store.read_exact(record)
                        self._store.remove_tombstone(tombstone)
                elif record is None:
                    self._store.remove_tombstone(tombstone)
                else:
                    continue
            except (OSError, SourceVisualStorageError):
                continue
            processed += 1
        return processed

    async def evict_to_budget(
        self,
        *,
        max_bytes: int = 2 * 1024**3,
        page_size: int = 100,
    ) -> int:
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes < 0
            or isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 100
        ):
            raise SourceVisualStorageError("INVALID_INPUT")
        current_bytes = self._store.cache_size_bytes()
        removed = 0
        while current_bytes > max_bytes:
            page = list(await self._repository.list_ready_for_eviction(limit=page_size))
            if len(page) > page_size:
                raise SourceVisualStorageError("INVALID_INPUT")
            records = sorted(
                (record for record in page if isinstance(record, SourceVisualRecord)),
                key=lambda record: (record.updated_at, record.asset_relpath),
            )
            progressed = False
            for record in records:
                if current_bytes <= max_bytes:
                    break
                if self._store.is_read_active(record):
                    continue
                try:
                    if await self._repository.is_claim_active(record):
                        continue
                    asset_size = len(self._store.read_exact(record))
                    deleted = await self.delete_record(record)
                except SourceVisualStorageError:
                    continue
                if deleted:
                    current_bytes = max(0, current_bytes - asset_size)
                    removed += 1
                    progressed = True
            if not progressed:
                break
        return removed


__all__ = ["SourceVisualCleanup", "SourceVisualCleanupRepository"]
