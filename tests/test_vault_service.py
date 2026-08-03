from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

try:
    import pwd
except ImportError:  # pragma: no cover - Windows skips POSIX vault tests
    pwd = None  # type: ignore[assignment]

from deeper_notebook.vault.repository import (
    FailureResult,
    ProjectionResult,
    VaultFile,
    VaultMount,
    VaultMountCreate,
)
from deeper_notebook.vault.security import VaultSecurityError, approve_vault_root
from deeper_notebook.vault.service import VaultService, _ObservationAdapter
from deeper_notebook.vault.watcher import (
    VaultFileObservation,
    VaultWatcher,
    VaultWorkItem,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)


@dataclass
class FakeRepository:
    mounts: list[VaultMount]
    projections: list[tuple[str, str, str]]
    missing_operations: list[tuple[str, str, str]]
    failures: list[tuple[str, str, str]] = field(default_factory=list)
    state_transitions: list[tuple[str, str, datetime]] = field(default_factory=list)
    files: dict[tuple[str, str], VaultFile] = field(default_factory=dict)

    async def create_mount(self, request: VaultMountCreate) -> VaultMount:
        mount = VaultMount(id=f"vault_mount:{request.name}", **request.model_dump())
        self.mounts.append(mount)
        return mount

    async def list_mounts(self) -> list[VaultMount]:
        return list(self.mounts)

    async def get_mount(self, vault_id: str) -> VaultMount:
        return next(mount for mount in self.mounts if mount.id == vault_id)

    async def get_file(self, vault_id: str, relative_path: str) -> VaultFile:
        return self.files[(vault_id, relative_path)]

    async def mark_scan_started(
        self, vault_id: str, *, started_at: datetime | None = None
    ) -> VaultMount:
        assert started_at is not None
        return self._replace_mount(
            vault_id,
            status="scanning",
            last_scan_started_at=started_at,
        )

    async def mark_scan_completed(
        self,
        vault_id: str,
        *,
        status: str,
        completed_at: datetime | None = None,
    ) -> VaultMount:
        assert completed_at is not None
        return self._replace_mount(
            vault_id,
            status=status,
            last_scan_completed_at=completed_at,
        )

    def _replace_mount(self, vault_id: str, **updates) -> VaultMount:
        index = next(
            index for index, mount in enumerate(self.mounts) if mount.id == vault_id
        )
        mount = self.mounts[index].model_copy(update=updates)
        self.mounts[index] = mount
        timestamp = updates.get("last_scan_started_at") or updates.get(
            "last_scan_completed_at"
        )
        self.state_transitions.append((vault_id, mount.status, timestamp))
        return mount

    async def list_files(self, vault_id: str, prefix: str, limit: int, offset: int):
        return []

    async def record_observation(self, observation: VaultFileObservation) -> None:
        return None

    async def mark_missing(
        self, vault_id: str, relative_path: str, operation_id: str
    ) -> None:
        self.missing_operations.append((vault_id, relative_path, operation_id))

    async def record_failure(
        self,
        vault_id: str,
        observation: VaultWorkItem,
        operation_id: str,
        error_code: str,
    ) -> FailureResult:
        self.failures.append((observation.relative_path, operation_id, error_code))
        return FailureResult(
            vault_file_id="vault_file:fixture",
            status="stale-invalid",
        )

    async def project_document(
        self, vault: VaultMount, work: VaultWorkItem, parsed, operation_id: str
    ):
        self.projections.append((work.relative_path, work.content_hash, operation_id))
        return ProjectionResult(
            vault_file_id="vault_file:fixture",
            note_id="note:fixture",
            status="projected",
            parse_state="parsed",
            embedding_state="pending",
        )


class FailingShadowProjector:
    def __init__(self) -> None:
        self.calls = []
        self.failure_reports = []

    async def project_external(self, **kwargs) -> None:
        self.calls.append(kwargs)
        raise RuntimeError("knowledge_engine_repository_unavailable")

    async def record_external_failure(self, **kwargs) -> None:
        self.failure_reports.append(kwargs)


def _mount(
    root: Path, *, name: str = "fixture", parent_vault_id: str | None = None
) -> VaultMount:
    return VaultMount(
        id=f"vault_mount:{name}",
        name=name,
        root_path=str(root),
        format_mode="markdown",
        status="disconnected",
        parent_vault_id=parent_vault_id,
        watch_enabled=True,
        parser_version="test",
    )


@pytest.fixture
def synthetic_root() -> Path:
    assert pwd is not None
    root = (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".cache"
        / "deeper-notebook-service-tests"
        / uuid.uuid4().hex
    )
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_scan_transitions_to_ready_read_only_and_projects_once(
    synthetic_root: Path,
):
    root = synthetic_root / "vault"
    root.mkdir()
    (root / "note.md").write_text("# Fixture\ntext\n")
    repository = FakeRepository([_mount(root)], [], [])
    moments = iter((1.0, 3.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    first = await service.scan("vault_mount:fixture")
    await asyncio.sleep(0)
    second = await service.scan("vault_mount:fixture")

    assert first.status == "ready-read-only"
    assert second.status == "ready-read-only"
    assert len(repository.projections) == 1
    assert repository.projections[0][2].startswith("vault-scan-")


@pytest.mark.asyncio
async def test_completed_scan_state_is_visible_to_repository_and_fresh_service(
    synthetic_root: Path,
):
    root = synthetic_root / "persisted"
    root.mkdir()
    repository = FakeRepository([_mount(root)], [], [])
    service = VaultService(repository, stable_after_seconds=0, clock=lambda: 1.0)

    result = await service.scan("vault_mount:fixture")

    persisted = (await repository.list_mounts())[0]
    fresh_service = VaultService(repository)
    await fresh_service._load_mounts()
    assert result.status == "ready-read-only"
    assert persisted.status == "ready-read-only"
    assert persisted.last_scan_started_at is not None
    assert persisted.last_scan_completed_at is not None
    assert fresh_service._states[persisted.id] == "ready-read-only"
    assert [state for _, state, _ in repository.state_transitions] == [
        "scanning",
        "ready-read-only",
    ]


@pytest.mark.asyncio
async def test_scan_marks_mount_unavailable_when_root_open_times_out(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = synthetic_root / "vault"
    root.mkdir()
    repository = FakeRepository([_mount(root)], [], [])
    service = VaultService(repository, stable_after_seconds=0)

    def stalled_root_open(_path: str, *, timeout_seconds: float):
        raise VaultSecurityError("root_open_timeout")

    monkeypatch.setattr(
        "deeper_notebook.vault.service.approve_vault_root_bounded", stalled_root_open
    )

    result = await service.scan("vault_mount:fixture")

    assert result.status == "unavailable"
    assert [state for _, state, _ in repository.state_transitions] == [
        "scanning",
        "unavailable",
    ]


@pytest.mark.asyncio
async def test_read_canvas_returns_only_a_hash_bound_document(
    synthetic_root: Path,
):
    root = synthetic_root / "canvas"
    root.mkdir()
    maps = root / "maps"
    maps.mkdir()
    content = (
        b'{"nodes":[{"id":"idea","type":"text","x":0,"y":0,"width":100,"height":80,"text":"Idea"}],"edges":[]}'
    )
    (maps / "plan.canvas").write_bytes(content)
    mount = _mount(root)
    file = VaultFile(
        id="vault_file:canvas",
        note_id="note:canvas",
        vault_id=mount.id,
        relative_path="maps/plan.canvas",
        file_kind="metadata",
        format="markdown",
        content_hash=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        modified_ns=1,
        parse_status="parsed",
        deleted_state="present",
    )
    repository = FakeRepository([mount], [], [], files={(mount.id, file.relative_path): file})

    result = await VaultService(repository).read_canvas(mount.id, file.relative_path)

    assert result.file.id == file.id
    assert result.source_hash == file.content_hash
    assert result.document.nodes[0].text == "Idea"


@pytest.mark.asyncio
async def test_scan_reports_unchanged_work_from_a_real_watcher(
    synthetic_root: Path,
):
    root = synthetic_root / "unchanged"
    root.mkdir()
    (root / "note.md").write_text("# Fixture\ntext\n")
    repository = FakeRepository([_mount(root)], [], [])
    repository.project_document = AsyncMock(
        return_value=ProjectionResult(
            vault_file_id="vault_file:fixture",
            note_id="note:fixture",
            status="unchanged",
            parse_state="parsed",
            embedding_state="pending",
        )
    )
    moments = iter((1.0, 3.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    await service.scan("vault_mount:fixture")
    result = await service.scan("vault_mount:fixture")

    assert result.projected == 0
    assert result.unchanged == 1
    assert result.failed == 0
    assert result.projected + result.unchanged + result.failed == 1


@pytest.mark.asyncio
async def test_pending_repository_file_is_not_seeded_as_already_projected(
    synthetic_root: Path,
):
    root = synthetic_root / "pending"
    root.mkdir()
    content = b"# Pending projection\n"
    (root / "note.md").write_bytes(content)
    repository = FakeRepository([_mount(root)], [], [])
    repository.list_files = AsyncMock(
        return_value=[
            SimpleNamespace(
                relative_path="note.md",
                content_hash=hashlib.sha256(content).hexdigest(),
                deleted_state="present",
                parse_status="pending",
            )
        ]
    )
    moments = iter((1.0, 3.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    await service.scan("vault_mount:fixture")
    result = await service.scan("vault_mount:fixture")

    assert result.projected == 1
    assert [path for path, _, _ in repository.projections] == ["note.md"]


@pytest.mark.asyncio
async def test_non_indexable_repository_row_is_not_used_as_watcher_seed(
    synthetic_root: Path,
):
    root = synthetic_root / "manifest-row"
    root.mkdir()
    repository = FakeRepository([_mount(root)], [], [])
    repository.list_files = AsyncMock(
        return_value=[
            SimpleNamespace(
                relative_path="brain-engine/trust.json",
                content_hash="a" * 64,
                deleted_state="present",
                parse_status="invalid",
            )
        ]
    )
    service = VaultService(repository, stable_after_seconds=0, clock=lambda: 1.0)

    result = await service.scan("vault_mount:fixture")

    assert result.status == "ready-read-only"
    assert result.failed == 0


@pytest.mark.asyncio
async def test_parse_failure_is_terminal_for_unchanged_hash(
    synthetic_root: Path,
):
    root = synthetic_root / "invalid"
    root.mkdir()
    (root / "broken.md").write_text("---\n[unterminated\n---\n")
    repository = FakeRepository([_mount(root)], [], [])
    moments = iter((1.0, 3.0, 5.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    await service.scan("vault_mount:fixture")
    failed = await asyncio.wait_for(
        service.scan("vault_mount:fixture"),
        timeout=1.0,
    )
    persisted_failure = (await repository.list_mounts())[0]
    settled = await asyncio.wait_for(
        service.scan("vault_mount:fixture"),
        timeout=1.0,
    )

    assert failed.failed == 1
    assert failed.status == "degraded"
    assert persisted_failure.status == "degraded"
    assert settled.failed == 0
    assert len(repository.failures) == 1


class _BlockingVaultWatcher(VaultWatcher):
    def __init__(self, *args, started: asyncio.Event, release: asyncio.Event, **kwargs):
        super().__init__(*args, **kwargs)
        self._started = started
        self._release = release

    async def scan(self, *, now_monotonic: float | None = None) -> list[VaultWorkItem]:
        self._started.set()
        await self._release.wait()
        return await super().scan(now_monotonic=now_monotonic)


@pytest.mark.asyncio
async def test_scan_returns_in_progress_only_while_a_real_watcher_scan_is_live(
    synthetic_root: Path,
):
    root = synthetic_root / "concurrent"
    root.mkdir()
    repository = FakeRepository([_mount(root)], [], [])
    service = VaultService(repository, stable_after_seconds=0, clock=lambda: 3.0)
    started = asyncio.Event()
    release = asyncio.Event()
    approved_root = approve_vault_root(str(root))
    watcher = _BlockingVaultWatcher(
        vault_id="vault_mount:fixture",
        approved_root=approved_root,
        repository=_ObservationAdapter(repository, service._operation_id),
        stable_after_seconds=2.0,
        started=started,
        release=release,
    )
    service._watchers["vault_mount:fixture"] = watcher

    first_scan = asyncio.create_task(service.scan("vault_mount:fixture"))
    await started.wait()
    concurrent = await asyncio.wait_for(
        service.scan("vault_mount:fixture"), timeout=0.1
    )
    release.set()
    completed = await first_scan
    subsequent = await service.scan("vault_mount:fixture")
    approved_root.close()

    assert concurrent.status == "scanning"
    assert completed.status == "ready-read-only"
    assert subsequent.status == "ready-read-only"


@pytest.mark.asyncio
async def test_cancelled_scan_persists_degraded_instead_of_stale_scanning(
    synthetic_root: Path,
):
    root = synthetic_root / "cancelled"
    root.mkdir()
    repository = FakeRepository([_mount(root)], [], [])
    service = VaultService(repository, stable_after_seconds=0, clock=lambda: 3.0)
    started = asyncio.Event()
    release = asyncio.Event()
    approved_root = approve_vault_root(str(root))
    watcher = _BlockingVaultWatcher(
        vault_id="vault_mount:fixture",
        approved_root=approved_root,
        repository=_ObservationAdapter(repository, service._operation_id),
        stable_after_seconds=2.0,
        started=started,
        release=release,
    )
    service._watchers["vault_mount:fixture"] = watcher

    scan = asyncio.create_task(service.scan("vault_mount:fixture"))
    await started.wait()
    scan.cancel()
    with pytest.raises(asyncio.CancelledError):
        await scan

    persisted = (await repository.list_mounts())[0]
    approved_root.close()
    assert persisted.status == "degraded"
    assert persisted.last_scan_completed_at is not None


@pytest.mark.asyncio
async def test_unavailable_root_is_reported_without_crashing(synthetic_root: Path):
    repository = FakeRepository([_mount(synthetic_root / "missing")], [], [])
    service = VaultService(repository, stable_after_seconds=0)

    result = await service.scan("vault_mount:fixture")

    assert result.status == "unavailable"
    persisted = (await repository.list_mounts())[0]
    assert persisted.status == "unavailable"
    assert persisted.last_scan_completed_at is not None


@pytest.mark.asyncio
async def test_parent_scan_excludes_files_owned_by_child_mount(synthetic_root: Path):
    root = synthetic_root / "parent"
    child = root / "child"
    child.mkdir(parents=True)
    (root / "parent.md").write_text("# Parent\n")
    (child / "child.md").write_text("# Child\n")
    parent = _mount(root, name="parent")
    child_mount = _mount(child, name="child", parent_vault_id=parent.id)
    repository = FakeRepository([parent, child_mount], [], [])
    moments = iter((1.0, 3.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    await service.scan(parent.id)
    await service.scan(parent.id)

    assert [path for path, _, _ in repository.projections] == ["parent.md"]


@pytest.mark.asyncio
async def test_one_scan_operation_id_is_reused_for_every_projected_file(
    synthetic_root: Path,
):
    root = synthetic_root / "multi"
    root.mkdir()
    (root / "one.md").write_text("# One\n")
    (root / "two.md").write_text("# Two\n")
    repository = FakeRepository([_mount(root)], [], [])
    moments = iter((1.0, 3.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    await service.scan("vault_mount:fixture")
    result = await service.scan("vault_mount:fixture")

    assert {operation for _, _, operation in repository.projections} == {
        result.operation_id
    }


@pytest.mark.asyncio
async def test_shadow_failure_does_not_undo_a_proven_vault_projection(
    synthetic_root: Path,
):
    root = synthetic_root / "shadow-contained"
    root.mkdir()
    source = b"# Research\n"
    (root / "Research.md").write_bytes(source)
    repository = FakeRepository([_mount(root)], [], [])
    shadow = FailingShadowProjector()
    moments = iter((1.0, 3.0))
    service = VaultService(
        repository,
        shadow_projector=shadow,
        stable_after_seconds=0,
        clock=lambda: next(moments),
    )

    await service.scan("vault_mount:fixture")
    result = await service.scan("vault_mount:fixture")

    assert result.projected == 1
    assert len(repository.projections) == 1
    assert shadow.calls[0]["observation"].content == source
    assert shadow.calls[0]["source_kind"] == "markdown"
    assert isinstance(shadow.failure_reports[0]["error"], RuntimeError)


@pytest.mark.asyncio
async def test_unavailable_shadow_reporter_uses_only_a_hashed_fallback(
    synthetic_root: Path,
    monkeypatch,
):
    class MissingReporter:
        async def project_external(self, **_kwargs) -> None:
            raise RuntimeError("private failure")

    root = synthetic_root / "shadow-fallback"
    root.mkdir()
    (root / "Research.md").write_text("# Research\n")
    messages = []
    monkeypatch.setattr(
        "deeper_notebook.vault.service.logger.warning",
        lambda message, *arguments: messages.append((message, arguments)),
    )
    moments = iter((1.0, 3.0))
    service = VaultService(
        FakeRepository([_mount(root)], [], []),
        shadow_projector=MissingReporter(),
        stable_after_seconds=0,
        clock=lambda: next(moments),
    )

    await service.scan("vault_mount:fixture")
    result = await service.scan("vault_mount:fixture")

    assert result.projected == 1
    assert messages == [
        (
            "Knowledge shadow failure receipt unavailable operation_id={} code={}",
            (messages[0][1][0], "knowledge_engine_failure_receipt_unavailable"),
        )
    ]
    assert messages[0][1][0].startswith("shadow-diagnostic-v1:")
    assert "vault-scan-" not in str(messages)
    assert "Research.md" not in str(messages)


@pytest.mark.asyncio
async def test_real_observer_event_debounces_burst_to_one_projection(
    synthetic_root: Path,
):
    root = synthetic_root / "observed"
    root.mkdir()
    repository = FakeRepository([_mount(root)], [], [])
    service = VaultService(repository)

    await service.start_watchers()
    note = root / "burst.md"
    note.write_text("# First\n")
    note.write_text("# Final\n")
    await asyncio.sleep(4.5)
    await service.stop_watchers()

    assert [path for path, _, _ in repository.projections] == ["burst.md"]


@pytest.mark.asyncio
async def test_conflict_is_not_acknowledged_then_stable_rescan_projects_authoritative_a(
    synthetic_root: Path,
):
    root = synthetic_root / "conflict"
    root.mkdir()
    (root / "note.md").write_text("# A\n")
    repository = FakeRepository([_mount(root)], [], [])
    conflict = ProjectionResult(
        vault_file_id="vault_file:fixture",
        note_id="note:fixture",
        status="conflict",
        parse_state="parsed",
        embedding_state="pending",
        reconciliation_required=True,
    )
    projected = ProjectionResult(
        vault_file_id="vault_file:fixture",
        note_id="note:fixture",
        status="projected",
        parse_state="parsed",
        embedding_state="pending",
    )
    repository.project_document = AsyncMock(side_effect=[conflict, projected])
    moments = iter((1.0, 3.0, 5.0, 7.0, 9.0))
    service = VaultService(
        repository, stable_after_seconds=0, clock=lambda: next(moments)
    )

    await service.scan("vault_mount:fixture")
    first = await service.scan("vault_mount:fixture")
    await service.scan("vault_mount:fixture")
    second = await service.scan("vault_mount:fixture")

    assert first.reconciliation_required is True
    assert second.status == "ready-read-only"
    assert repository.project_document.await_count == 2


@pytest.mark.asyncio
async def test_missing_receipts_always_get_fresh_ids_outside_scan_context(
    synthetic_root: Path,
):
    repository = FakeRepository([], [], [])
    adapter = _ObservationAdapter(repository, lambda: "vault-scan-shared")

    await adapter.mark_missing("vault_mount:fixture", "one.md")
    await adapter.mark_missing("vault_mount:fixture", "two.md")

    ids = [operation for _, _, operation in repository.missing_operations]
    assert len(set(ids)) == 2
    assert all(identifier.startswith("vault-missing-") for identifier in ids)
