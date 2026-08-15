"""Bounded two-phase cleanup for source-derived visual cache records."""

from __future__ import annotations

import asyncio
import inspect
import secrets
from collections.abc import Sequence
from typing import Protocol

from deeper_notebook.source_visuals.contracts import SourceVisualRecord
from deeper_notebook.source_visuals.storage import (
    DeleteFencedOrphan,
    SourceVisualStorageError,
    SourceVisualStore,
    TombstoneDeletionClaim,
    TombstonedVisualAsset,
)

_DELETION_CLAIM_HEARTBEAT_SECONDS = 60


async def _await_if_needed(value):
    if inspect.isawaitable(value):
        return await value
    return value


class _DeletionClaimHeartbeatLost(Exception):
    """A DB await lost its owner lease and must defer to durable recovery."""

    def __init__(self, error: SourceVisualStorageError) -> None:
        self.error = error
        super().__init__(error.code)


class _DeletionClaimDatabaseError(Exception):
    """Carry the latest lease when the awaited conditional delete fails."""

    def __init__(self, error: Exception, claim: TombstoneDeletionClaim) -> None:
        self.error = error
        self.claim = claim
        super().__init__(str(error))


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

    async def _renew_claim_until_stopped(
        self,
        claim_state: list[TombstoneDeletionClaim],
        stopped: asyncio.Event,
    ) -> SourceVisualStorageError | None:
        while True:
            try:
                await asyncio.wait_for(
                    stopped.wait(), timeout=_DELETION_CLAIM_HEARTBEAT_SECONDS
                )
                return None
            except TimeoutError:
                try:
                    claim_state[0] = self._store.renew_tombstone_deletion_claim(
                        claim_state[0]
                    )
                except SourceVisualStorageError as exc:
                    return exc

    async def _delete_with_claim_heartbeat(
        self,
        record: SourceVisualRecord,
        claim: TombstoneDeletionClaim,
    ) -> tuple[bool, TombstoneDeletionClaim]:
        claim_state = [claim]
        stopped = asyncio.Event()
        delete_task = asyncio.create_task(
            self._repository.delete_ready_if_current(record)
        )
        heartbeat_task = asyncio.create_task(
            self._renew_claim_until_stopped(claim_state, stopped)
        )
        try:
            done, _pending = await asyncio.wait(
                {delete_task, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat_task in done:
                heartbeat_error = heartbeat_task.result()
                if heartbeat_error is not None:
                    if not delete_task.done():
                        delete_task.cancel()
                        await asyncio.gather(delete_task, return_exceptions=True)
                    raise _DeletionClaimHeartbeatLost(heartbeat_error)
            if not delete_task.done():
                raise _DeletionClaimHeartbeatLost(
                    SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
                )
            stopped.set()
            heartbeat_error = await heartbeat_task
            if heartbeat_error is not None:
                raise _DeletionClaimHeartbeatLost(heartbeat_error)
            try:
                deleted = delete_task.result()
            except Exception as exc:
                raise _DeletionClaimDatabaseError(exc, claim_state[0]) from exc
            return deleted, claim_state[0]
        finally:
            stopped.set()
            if not delete_task.done():
                delete_task.cancel()
                await asyncio.gather(delete_task, return_exceptions=True)
            if not heartbeat_task.done():
                await heartbeat_task

    async def delete_record(self, record: SourceVisualRecord) -> bool:
        claimed_tombstone = self._store.tombstone_with_deletion_claim(record)
        if claimed_tombstone is None:
            return False
        tombstone, claim = claimed_tombstone
        try:
            deleted, claim = await self._delete_with_claim_heartbeat(record, claim)
        except _DeletionClaimHeartbeatLost as exc:
            # Retain the exact tombstone and expired/failed claim. A bounded
            # future reconciler rechecks the row before moving either byte set.
            raise exc.error
        except _DeletionClaimDatabaseError as exc:
            try:
                self._restore_after_failed_delete(tombstone)
                self._store.release_tombstone_deletion_claim(exc.claim)
            except (OSError, SourceVisualStorageError):
                # Preserve the original repository failure.  Any unfinished
                # byte/claim transition remains durable for reconciliation.
                pass
            raise exc.error
        except Exception:
            self._restore_after_failed_delete(tombstone)
            self._store.release_tombstone_deletion_claim(claim)
            raise
        if not deleted:
            self._restore_after_failed_delete(tombstone)
            self._store.release_tombstone_deletion_claim(claim)
            return False
        claim = self._store.mark_tombstone_deletion_claim_database_deleted(claim)
        try:
            self._store.remove_tombstone(tombstone)
        except (OSError, SourceVisualStorageError):
            # The row is gone, so a later bounded reconciliation owns cleanup.
            # Keep the lease until a reconciler removes this exact tombstone.
            return True
        self._store.release_tombstone_deletion_claim(claim)
        return True

    def _restore_after_failed_delete(self, tombstone: TombstonedVisualAsset) -> None:
        self._store.restore_tombstone(tombstone)

    async def reconcile_tombstones(self, *, limit: int = 100) -> int:
        self._store.reconcile_staged_files(limit=limit)
        tombstones = self._store.list_tombstones(limit=limit)
        claims = self._store.list_tombstone_deletion_claims(limit=limit)
        tombstone_set = set(tombstones)
        processed = 0
        for tombstone in tombstones:
            try:
                claim = self._store.acquire_tombstone_deletion_claim(tombstone)
            except (OSError, SourceVisualStorageError):
                continue
            if claim is None:
                # A live deletion owns this tombstone while it awaits its
                # conditional database mutation; never restore around it.
                continue
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
                        # canonical name. One storage method validates that
                        # replacement and removes the tombstone while its
                        # identity remains stable under the mutation guard.
                        self._store.remove_replaced_tombstone(tombstone)
                elif record is None:
                    self._store.remove_tombstone(tombstone)
                else:
                    self._store.release_tombstone_deletion_claim(claim)
                    continue
                self._store.release_tombstone_deletion_claim(claim)
            except (OSError, SourceVisualStorageError):
                continue
            processed += 1
        for claim in claims:
            if (
                claim.tombstone in tombstone_set
                or self._store.is_tombstone_deletion_claim_live(claim)
            ):
                continue
            try:
                record = await self._repository.find_ready_by_asset_relpath(
                    claim.tombstone.asset_relpath
                )
            except Exception:
                continue
            if record is None:
                try:
                    self._store.release_tombstone_deletion_claim(claim)
                except (OSError, SourceVisualStorageError):
                    continue
                processed += 1
                continue
            try:
                if not (
                    isinstance(record, SourceVisualRecord)
                    and record.asset_relpath == claim.tombstone.asset_relpath
                    and record.asset_sha256 == claim.tombstone.asset_sha256
                ):
                    continue
                # A pending claim is stale after a failed DB delete restored
                # canonical bytes. A db_deleted claim can likewise be stale
                # when a later exact ready record has republished those bytes.
                # In either phase, read_exact revalidates the full record/path,
                # descriptor identity, size, and hash under storage authority.
                if (
                    len(self._store.read_exact(record))
                    != claim.tombstone.byte_size
                ):
                    continue
                self._store.release_tombstone_deletion_claim(claim)
            except (OSError, SourceVisualStorageError):
                continue
            processed += 1
        return processed

    async def reconcile_delete_fenced_orphans(self, *, limit: int = 100) -> int:
        """Retire lost-owner publication markers only under a fresh exact claim."""

        lister = getattr(self._store, "list_delete_fenced_orphans", None)
        remover = getattr(self._store, "remove_delete_fenced_orphan", None)
        acquire = getattr(self._repository, "acquire_claim", None)
        release = getattr(self._repository, "release_claim", None)
        if not all(callable(value) for value in (lister, remover, acquire, release)):
            return 0
        processed = 0
        for orphan in await _await_if_needed(lister(limit=limit)):
            if not isinstance(orphan, DeleteFencedOrphan):
                raise SourceVisualStorageError("CACHE_RECOVERY_REQUIRED")
            record = orphan.record
            owner_token = secrets.token_hex(32)
            try:
                await _await_if_needed(
                    acquire(
                        source_id=record.source_id,
                        content_sha256=record.content_sha256,
                        extractor_version=record.extractor_version,
                        owner_token=owner_token,
                        lease_seconds=90,
                    )
                )
            except Exception:
                # A live extractor owns this exact identity, or the durable
                # authority is temporarily unavailable. Preserve the marker.
                continue
            try:
                current = await _await_if_needed(
                    self._repository.find_ready_by_asset_relpath(record.asset_relpath)
                )
                if current is None:
                    tombstone = self._store.tombstone(record)
                    if tombstone is not None:
                        self._store.remove_tombstone(tombstone)
                    await _await_if_needed(remover(orphan))
                    processed += 1
                elif current == record:
                    # The newer authoritative publisher retained this exact
                    # canonical; its row restores ownership, so only retire
                    # the stale marker.
                    if len(self._store.read_exact(record)) != orphan.byte_size:
                        continue
                    await _await_if_needed(remover(orphan))
                    processed += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                # Malformed/foreign marker state or a DB failure retains the
                # durable marker for a later bounded reconciliation.
                continue
            finally:
                try:
                    await _await_if_needed(
                        release(
                            source_id=record.source_id,
                            content_sha256=record.content_sha256,
                            extractor_version=record.extractor_version,
                            owner_token=owner_token,
                        )
                    )
                except Exception:
                    pass
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
        self._store.reconcile_staged_files(limit=page_size)
        # Delete-fenced publication leaves an exact durable tombstone even
        # when publication never created a ready row. Reconcile it before the
        # ready-row page, otherwise a zero-row repository cannot reclaim the
        # physical bytes at any budget.
        removed = await self.reconcile_tombstones(limit=page_size)
        removed += await self.reconcile_delete_fenced_orphans(limit=page_size)
        current_bytes = self._store.cache_size_bytes()
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
                    self._store.read_exact(record)
                    deleted = await self.delete_record(record)
                except SourceVisualStorageError:
                    continue
                if deleted:
                    removed += 1
                    measured_bytes = self._store.cache_size_bytes()
                    progressed = progressed or measured_bytes < current_bytes
                    current_bytes = measured_bytes
            if not progressed:
                break
        return removed


__all__ = ["SourceVisualCleanup", "SourceVisualCleanupRepository"]
