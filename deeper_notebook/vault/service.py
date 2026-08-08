"""Read-only orchestration for durable external-vault projections."""

from __future__ import annotations

import asyncio
import contextvars
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from deeper_notebook.knowledge_engine.shadow import KnowledgeShadowProjector
from deeper_notebook.vault.canvas import CanvasDocument, parse_canvas_document
from deeper_notebook.vault.contracts import VaultState
from deeper_notebook.vault.parsers import VaultParseError, parse_document
from deeper_notebook.vault.repository import VaultFile, VaultMount, VaultMountCreate
from deeper_notebook.vault.security import (
    VaultSecurityError,
    approve_vault_root,
    approve_vault_root_bounded,
    classify_vault_path,
    secure_read,
)
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


@dataclass(frozen=True, slots=True)
class VaultCanvasDocument:
    file: VaultFile
    source_hash: str
    document: CanvasDocument


def _shadow_diagnostic_operation_id(
    legacy_operation_id: str, relative_locator: str
) -> str:
    return (
        "shadow-diagnostic-v1:"
        f"{sha256(legacy_operation_id.encode()).hexdigest()}:"
        f"{sha256(relative_locator.encode()).hexdigest()}"
    )


class _Repository(Protocol):
    async def create_mount(self, request: VaultMountCreate) -> VaultMount: ...
    async def enable_watch(self, vault_id: str) -> VaultMount: ...
    async def list_mounts(self) -> list[VaultMount]: ...
    async def get_mount(self, vault_id: str) -> VaultMount: ...
    async def get_file(self, vault_id: str, relative_path: str) -> VaultFile: ...
    async def mark_scan_started(
        self, vault_id: str, *, started_at: datetime | None = None
    ) -> None: ...
    async def mark_scan_completed(
        self,
        vault_id: str,
        *,
        status: VaultState,
        completed_at: datetime | None = None,
    ) -> None: ...
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
            vault_id, relative_path, f"vault-missing-{uuid.uuid4().hex}"
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
        shadow_projector: KnowledgeShadowProjector | None = None,
        stable_after_seconds: float = 2.0,
        filesystem_timeout_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repository = repository
        self._shadow_projector = shadow_projector
        self._stable_after_seconds = max(2.0, stable_after_seconds)
        if filesystem_timeout_seconds <= 0:
            raise ValueError("filesystem timeout must be positive")
        self._filesystem_timeout_seconds = filesystem_timeout_seconds
        self._clock = clock
        self._watchers: dict[str, VaultWatcher] = {}
        self._scheduled_watchers: set[str] = set()
        self._mounts: dict[str, VaultMount] = {}
        self._states: dict[str, str] = {}
        self._scan_locks: dict[str, asyncio.Lock] = {}
        self._dirty: set[str] = set()
        self._rescan_after_stability: set[str] = set()
        self._scan_operation_id: contextvars.ContextVar[str | None] = (
            contextvars.ContextVar("vault_scan_operation_id", default=None)
        )
        self._worker: asyncio.Task[None] | None = None
        self._observer: Observer | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    def _operation_id(self) -> str:
        return self._scan_operation_id.get() or f"vault-scan-{uuid.uuid4().hex}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _cache_mount_state(
        self,
        mount: VaultMount,
        status: VaultState,
        **updates: datetime,
    ) -> VaultMount:
        current = mount.model_copy(update={"status": status, **updates})
        self._mounts[current.id] = current
        self._states[current.id] = current.status
        return current

    async def _complete_scan(self, vault_id: str, status: VaultState) -> None:
        completed_at = self._now()
        await self._repository.mark_scan_completed(
            vault_id,
            status=status,
            completed_at=completed_at,
        )
        mount = self._mounts[vault_id]
        self._cache_mount_state(
            mount,
            status,
            last_scan_completed_at=completed_at,
        )

    async def register_mount(self, request: VaultMountCreate) -> VaultMount:
        mount = await self._repository.create_mount(request)
        self._mounts[mount.id] = mount
        self._states[mount.id] = mount.status
        return mount

    async def enable_watch(self, vault_id: str) -> VaultMount:
        """Enable observer-driven scans without changing vault write policy."""
        mount = await self._repository.enable_watch(vault_id)
        if mount.write_policy != "read-only":
            raise VaultSecurityError("unsafe_root")
        self._mounts[mount.id] = mount
        self._states[mount.id] = mount.status
        if self._closed or self._observer is None:
            return mount
        await self._watcher_for(mount)
        if mount.id not in self._scheduled_watchers:
            self._observer.schedule(
                _VaultEventHandler(self, mount), mount.root_path, recursive=True
            )
            self._scheduled_watchers.add(mount.id)
        self.notify_change(mount.id)
        return mount

    async def read_canvas(
        self, vault_id: str, relative_path: str
    ) -> VaultCanvasDocument:
        """Read one current external Canvas only when it matches its projection."""

        file = await self._repository.get_file(vault_id, relative_path)
        if (
            file.vault_id != vault_id
            or file.relative_path != relative_path
            or file.deleted_state != "present"
            or file.parse_status not in {"parsed", "invalid"}
            or not file.content_hash
            or classify_vault_path(relative_path).kind != "metadata"
            or not relative_path.casefold().endswith(".canvas")
        ):
            raise LookupError("canvas_not_found")
        mount = self._mounts.get(vault_id) or await self._repository.get_mount(vault_id)
        with approve_vault_root(mount.root_path) as root:
            source = secure_read(root, relative_path)
        if source.sha256 != file.content_hash:
            raise VaultSecurityError("changed_during_read")
        return VaultCanvasDocument(
            file=file,
            source_hash=source.sha256,
            document=parse_canvas_document(source.content, relative_path=relative_path),
        )

    async def _load_mounts(self) -> None:
        for mount in await self._repository.list_mounts():
            self._mounts[mount.id] = mount
            self._states.setdefault(mount.id, mount.status)

    async def _watcher_for(self, mount: VaultMount) -> VaultWatcher | None:
        watcher = self._watchers.get(mount.id)
        if watcher is not None:
            return watcher
        try:
            root = approve_vault_root_bounded(
                mount.root_path,
                timeout_seconds=self._filesystem_timeout_seconds,
            )
        except VaultSecurityError as exc:
            self._states[mount.id] = "unavailable"
            logger.warning("Vault mount {} is unavailable ({})", mount.id, exc.code)
            return None
        known = await self._repository.list_files(mount.id, "", 10_000, 0)
        indexable = [
            item for item in known if classify_vault_path(item.relative_path).indexable
        ]
        hashes = {
            item.relative_path: item.content_hash
            for item in indexable
            if item.deleted_state == "present"
            and item.parse_status in {"parsed", "invalid"}
            and item.content_hash
        }
        paths = {item.relative_path for item in indexable}
        child_prefixes = self._child_prefixes(mount)
        watcher = VaultWatcher(
            vault_id=mount.id,
            approved_root=root,
            repository=_ObservationAdapter(self._repository, self._operation_id),
            stable_after_seconds=self._stable_after_seconds,
            known_paths=paths,
            known_projected_hashes=hashes,
            excluded_relative_prefixes=child_prefixes,
            filesystem_timeout_seconds=self._filesystem_timeout_seconds,
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
        operation_id = self._operation_id()
        scan_lock = self._scan_locks.setdefault(vault_id, asyncio.Lock())
        if scan_lock.locked():
            return VaultScanResult(vault_id, "scanning", operation_id)
        async with scan_lock:
            token = self._scan_operation_id.set(operation_id)
            try:
                return await self._scan_with_operation(vault_id, operation_id)
            finally:
                self._scan_operation_id.reset(token)

    async def _scan_with_operation(
        self, vault_id: str, operation_id: str
    ) -> VaultScanResult:
        await self._load_mounts()
        mount = self._mounts.get(vault_id)
        if mount is None:
            raise LookupError("vault_mount_not_found")
        started_at = self._now()
        await self._repository.mark_scan_started(vault_id, started_at=started_at)
        mount = self._cache_mount_state(
            mount,
            "scanning",
            last_scan_started_at=started_at,
        )
        try:
            watcher = await self._watcher_for(mount)
            if watcher is None:
                result = VaultScanResult(vault_id, "unavailable", operation_id)
                await self._complete_scan(vault_id, "unavailable")
                return result
            work = await watcher.scan(now_monotonic=self._clock())
            if not work:
                result = VaultScanResult(
                    vault_id,
                    "ready-read-only",
                    operation_id,
                )
                await self._complete_scan(vault_id, "ready-read-only")
                return result
            projected = unchanged = failed = 0
            reconciliation_required = False
            for item in work:
                outcome = await self._project(mount, watcher, item, operation_id)
                projected += outcome.projected
                unchanged += outcome.unchanged
                failed += outcome.failed
                reconciliation_required = (
                    reconciliation_required or outcome.reconciliation_required
                )
            terminal_status: VaultState
            if reconciliation_required:
                terminal_status = "conflict"
            elif failed:
                terminal_status = "degraded"
            else:
                terminal_status = "ready-read-only"
            result = VaultScanResult(
                vault_id,
                terminal_status,
                operation_id,
                projected,
                unchanged=unchanged,
                failed=failed,
                reconciliation_required=reconciliation_required,
            )
            await self._complete_scan(vault_id, terminal_status)
            return result
        except BaseException:
            try:
                await self._complete_scan(vault_id, "degraded")
            except Exception:
                logger.exception(
                    "Failed to persist degraded state for vault {}", vault_id
                )
            raise

    async def _project(
        self,
        mount: VaultMount,
        watcher: VaultWatcher,
        item: VaultWorkItem,
        operation_id: str,
    ) -> VaultScanResult:
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
            handoff = await watcher.acknowledge_projected(
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
        if result.reconciliation_required:
            await watcher.release_queued(item.relative_path, item.content_hash)
            self._watchers.pop(mount.id, None)
            watcher._root.close()
            self._dirty.add(mount.id)
            return VaultScanResult(
                mount.id, "conflict", operation_id, reconciliation_required=True
            )
        if (
            self._shadow_projector is not None
            and result.status in {"projected", "unchanged"}
            and parsed.source_format in {"obsidian", "logseq", "markdown"}
        ):
            try:
                await self._shadow_projector.project_external(
                    legacy_operation_id=operation_id,
                    mount=mount,
                    observation=item,
                    source_kind=parsed.source_format,
                    vault_file_id=result.vault_file_id,
                    projected_note_id=result.note_id,
                )
            except Exception as error:
                try:
                    await self._shadow_projector.record_external_failure(
                        legacy_operation_id=operation_id,
                        mount=mount,
                        observation=item,
                        error=error,
                    )
                except Exception:
                    logger.warning(
                        "Knowledge shadow failure receipt unavailable operation_id={} code={}",
                        _shadow_diagnostic_operation_id(
                            operation_id, item.relative_path
                        ),
                        "knowledge_engine_failure_receipt_unavailable",
                    )
                else:
                    logger.warning(
                        "Knowledge shadow failed operation_id={} code={}",
                        _shadow_diagnostic_operation_id(
                            operation_id, item.relative_path
                        ),
                        "knowledge_engine_shadow_failed",
                    )
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
            await self._project(mount, watcher, item, self._operation_id())

    def notify_change(self, vault_id: str, relative_path: str = "") -> None:
        if not self._closed:
            self._dirty.add(vault_id)
            self._rescan_after_stability.add(vault_id)

    async def scan_dirty_mounts(self) -> list[VaultScanResult]:
        vault_ids = sorted(self._dirty)
        self._dirty.clear()
        return [await self.scan(vault_id) for vault_id in vault_ids]

    async def _run_worker(self) -> None:
        while not self._closed:
            await asyncio.sleep(2)
            if self._dirty:
                results = await self.scan_dirty_mounts()
                for result in results:
                    if (
                        result.status == "scanning"
                        or result.vault_id in self._rescan_after_stability
                    ):
                        self._dirty.add(result.vault_id)
                    self._rescan_after_stability.discard(result.vault_id)

    async def start_watchers(self) -> None:
        self._closed = False
        self._event_loop = asyncio.get_running_loop()
        await self._load_mounts()
        for mount in self._mounts.values():
            if mount.watch_enabled:
                await self._watcher_for(mount)
                self.notify_change(mount.id)
        if self._worker is None:
            self._worker = asyncio.create_task(
                self._run_worker(), name="vault-index-worker"
            )
        if self._observer is None:
            observer = Observer()
            for mount in self._mounts.values():
                if mount.watch_enabled and mount.id in self._watchers:
                    observer.schedule(
                        _VaultEventHandler(self, mount), mount.root_path, recursive=True
                    )
                    self._scheduled_watchers.add(mount.id)
            observer.start()
            self._observer = observer

    async def stop_watchers(self) -> None:
        self._closed = True
        if self._observer is not None:
            self._observer.stop()
            await asyncio.to_thread(self._observer.join)
            self._observer = None
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        for watcher in self._watchers.values():
            watcher._root.close()  # descriptor cleanup; watcher owns the approved root.
        self._watchers.clear()
        self._scheduled_watchers.clear()


class _VaultEventHandler(FileSystemEventHandler):
    """Thread-only event bridge; filesystem parsing stays on the async worker."""

    def __init__(self, service: VaultService, mount: VaultMount) -> None:
        self._service = service
        self._mount = mount
        self._root = Path(mount.root_path)

    def on_any_event(self, event: FileSystemEvent) -> None:
        paths = [event.src_path]
        destination = getattr(event, "dest_path", None)
        if destination:
            paths.append(destination)
        for raw_path in paths:
            try:
                relative = Path(raw_path).relative_to(self._root).as_posix()
            except ValueError:
                continue
            watcher = self._service._watchers.get(self._mount.id)
            if watcher is not None and watcher._is_excluded(relative):
                continue
            loop = self._service._event_loop
            if loop is not None and not self._service._closed:
                loop.call_soon_threadsafe(
                    self._service.notify_change, self._mount.id, relative
                )
            return


__all__ = ["VaultScanResult", "VaultService"]
