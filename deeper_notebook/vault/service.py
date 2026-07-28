"""Read-only orchestration for durable external-vault projections."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from deeper_notebook.vault.parsers import VaultParseError, parse_document
from deeper_notebook.vault.repository import VaultMount, VaultMountCreate
from deeper_notebook.vault.security import VaultSecurityError, approve_vault_root
from deeper_notebook.vault.watcher import (
    VaultFileObservation,
    VaultWatcher,
    VaultWorkItem,
)


@dataclass(frozen=True, slots=True)
class VaultScanResult:
    vault_id: str
    status: str
    operation_id: str
    projected: int = 0
    unchanged: int = 0
    failed: int = 0
    reconciliation_required: bool = False


class _Repository(Protocol):
    async def create_mount(self, request: VaultMountCreate) -> VaultMount: ...
    async def list_mounts(self) -> list[VaultMount]: ...
    async def list_files(
        self, vault_id: str, prefix: str, limit: int, offset: int
    ) -> list[Any]: ...
    async def project_document(
        self,
        vault: VaultMount,
        observation: VaultWorkItem,
        parsed: Any,
        operation_id: str,
    ) -> Any: ...
    async def record_failure(
        self,
        vault_id: str,
        observation: VaultWorkItem,
        operation_id: str,
        error_code: str,
    ) -> Any: ...
    async def mark_missing(
        self, vault_id: str, relative_path: str, operation_id: str
    ) -> None: ...
    async def record_observation(self, observation: VaultFileObservation) -> None: ...


class _ObservationAdapter:
    """Bridge the watcher callback to operation-bound repository receipts."""

    def __init__(
        self, repository: _Repository, operation_id: Callable[[], str]
    ) -> None:
        self._repository = repository
        self._operation_id = operation_id

    async def record_observation(self, observation: VaultFileObservation) -> None:
        await self._repository.record_observation(observation)

    async def mark_missing(self, vault_id: str, relative_path: str) -> None:
        await self._repository.mark_missing(
            vault_id, relative_path, self._operation_id()
        )


class VaultService:
    """Coordinates stable reads, projection, and immediate corrective handoffs.

    The service deliberately has no file mutation capability. Its worker is a
    debounced scheduler: a filesystem integration can call ``notify_change``
    without deciding which competing observation wins.
    """

    def __init__(
        self,
        repository: _Repository,
        *,
        stable_after_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repository = repository
        self._stable_after_seconds = max(2.0, stable_after_seconds)
        self._clock = clock
        self._watchers: dict[str, VaultWatcher] = {}
        self._mounts: dict[str, VaultMount] = {}
        self._states: dict[str, str] = {}
        self._dirty: set[str] = set()
        self._worker: asyncio.Task[None] | None = None
        self._observer: asyncio.Task[None] | None = None
        self._closed = False

    def _operation_id(self) -> str:
        return f"vault-scan-{uuid.uuid4().hex}"

    async def register_mount(self, request: VaultMountCreate) -> VaultMount:
        mount = await self._repository.create_mount(request)
        self._mounts[mount.id] = mount
        self._states[mount.id] = mount.status
        return mount

    async def _load_mounts(self) -> None:
        for mount in await self._repository.list_mounts():
            self._mounts[mount.id] = mount
            self._states.setdefault(mount.id, mount.status)

    async def _watcher_for(self, mount: VaultMount) -> VaultWatcher | None:
        watcher = self._watchers.get(mount.id)
        if watcher is not None:
            return watcher
        try:
            root = approve_vault_root(mount.root_path)
        except VaultSecurityError as exc:
            self._states[mount.id] = "unavailable"
            logger.warning("Vault mount {} is unavailable ({})", mount.id, exc.code)
            return None
        known = await self._repository.list_files(mount.id, "", 10_000, 0)
        hashes = {
            item.relative_path: item.content_hash
            for item in known
            if item.deleted_state == "present"
        }
        paths = {item.relative_path for item in known}
        child_prefixes = self._child_prefixes(mount)
        watcher = VaultWatcher(
            vault_id=mount.id,
            approved_root=root,
            repository=_ObservationAdapter(self._repository, self._operation_id),
            stable_after_seconds=self._stable_after_seconds,
            known_paths=paths,
            known_projected_hashes=hashes,
            excluded_relative_prefixes=child_prefixes,
        )
        self._watchers[mount.id] = watcher
        return watcher

    def _child_prefixes(self, mount: VaultMount) -> tuple[str, ...]:
        parent_root = Path(mount.root_path)
        prefixes: list[str] = []
        for candidate in self._mounts.values():
            if candidate.parent_vault_id != mount.id:
                continue
            try:
                relative = Path(candidate.root_path).relative_to(parent_root).as_posix()
            except ValueError:
                continue
            if relative not in {"", "."}:
                prefixes.append(relative)
        return tuple(sorted(set(prefixes)))

    async def scan(self, vault_id: str) -> VaultScanResult:
        await self._load_mounts()
        mount = self._mounts.get(vault_id)
        operation_id = self._operation_id()
        if mount is None:
            raise LookupError("vault_mount_not_found")
        watcher = await self._watcher_for(mount)
        if watcher is None:
            return VaultScanResult(vault_id, "unavailable", operation_id)
        self._states[vault_id] = "scanning"
        work = await watcher.scan(now_monotonic=self._clock())
        if not work:
            return VaultScanResult(vault_id, self._states[vault_id], operation_id)
        projected = failed = 0
        reconciliation_required = False
        for item in work:
            outcome = await self._project(mount, watcher, item)
            projected += outcome.projected
            failed += outcome.failed
            reconciliation_required = (
                reconciliation_required or outcome.reconciliation_required
            )
        self._states[vault_id] = (
            "conflict" if reconciliation_required else "ready-read-only"
        )
        return VaultScanResult(
            vault_id,
            self._states[vault_id],
            operation_id,
            projected,
            failed=failed,
            reconciliation_required=reconciliation_required,
        )

    async def _project(
        self, mount: VaultMount, watcher: VaultWatcher, item: VaultWorkItem
    ) -> VaultScanResult:
        operation_id = self._operation_id()
        try:
            parsed = parse_document(
                item.relative_path, item.content, format_mode=mount.format_mode
            )
            result = await self._repository.project_document(
                mount, item, parsed, operation_id
            )
        except VaultParseError as exc:
            await self._repository.record_failure(
                mount.id, item, operation_id, exc.code
            )
            handoff = await watcher.release_queued(
                item.relative_path, item.content_hash
            )
            await self._process_corrective(mount, watcher, handoff.corrective_work)
            return VaultScanResult(mount.id, "degraded", operation_id, failed=1)
        except Exception:
            handoff = await watcher.release_queued(
                item.relative_path, item.content_hash
            )
            await self._process_corrective(mount, watcher, handoff.corrective_work)
            raise
        handoff = await watcher.acknowledge_projected(
            item.relative_path, item.content_hash
        )
        await self._process_corrective(mount, watcher, handoff.corrective_work)
        return VaultScanResult(
            mount.id,
            "conflict" if result.reconciliation_required else "ready-read-only",
            operation_id,
            projected=int(result.status == "projected"),
            unchanged=int(result.status == "unchanged"),
            reconciliation_required=result.reconciliation_required,
        )

    async def _process_corrective(
        self, mount: VaultMount, watcher: VaultWatcher, work: tuple[VaultWorkItem, ...]
    ) -> None:
        for item in work:
            await self._project(mount, watcher, item)

    def notify_change(self, vault_id: str, relative_path: str = "") -> None:
        if not self._closed:
            self._dirty.add(vault_id)

    async def scan_dirty_mounts(self) -> list[VaultScanResult]:
        vault_ids = sorted(self._dirty)
        self._dirty.clear()
        return [await self.scan(vault_id) for vault_id in vault_ids]

    async def _run_worker(self) -> None:
        while not self._closed:
            await asyncio.sleep(2)
            if self._dirty:
                await self.scan_dirty_mounts()

    async def start_watchers(self) -> None:
        await self._load_mounts()
        for mount in self._mounts.values():
            if mount.watch_enabled:
                await self._watcher_for(mount)
                self._dirty.add(mount.id)
        if self._worker is None:
            self._worker = asyncio.create_task(
                self._run_worker(), name="vault-index-worker"
            )
        if self._observer is None:
            self._observer = asyncio.create_task(
                asyncio.sleep(float("inf")), name="vault-observer"
            )

    async def stop_watchers(self) -> None:
        self._closed = True
        for task in (self._observer, self._worker):
            if task is not None:
                task.cancel()
        for task in (self._observer, self._worker):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._observer = self._worker = None
        for watcher in self._watchers.values():
            watcher._root.close()  # descriptor cleanup; watcher owns the approved root.
        self._watchers.clear()


__all__ = ["VaultScanResult", "VaultService"]
