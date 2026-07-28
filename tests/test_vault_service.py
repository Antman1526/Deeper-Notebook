from __future__ import annotations

import asyncio
import os
import pwd
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.vault.repository import (
    ProjectionResult,
    VaultMount,
    VaultMountCreate,
)
from deeper_notebook.vault.service import VaultService, _ObservationAdapter
from deeper_notebook.vault.watcher import VaultFileObservation, VaultWorkItem


@dataclass
class FakeRepository:
    mounts: list[VaultMount]
    projections: list[tuple[str, str, str]]
    missing_operations: list[tuple[str, str, str]]

    async def create_mount(self, request: VaultMountCreate) -> VaultMount:
        mount = VaultMount(id=f"vault_mount:{request.name}", **request.model_dump())
        self.mounts.append(mount)
        return mount

    async def list_mounts(self) -> list[VaultMount]:
        return list(self.mounts)

    async def list_files(self, vault_id: str, prefix: str, limit: int, offset: int):
        return []

    async def record_observation(self, observation: VaultFileObservation) -> None:
        return None

    async def mark_missing(
        self, vault_id: str, relative_path: str, operation_id: str
    ) -> None:
        self.missing_operations.append((vault_id, relative_path, operation_id))

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

    assert first.status == "scanning"
    assert second.status == "ready-read-only"
    assert len(repository.projections) == 1
    assert repository.projections[0][2].startswith("vault-scan-")


@pytest.mark.asyncio
async def test_unavailable_root_is_reported_without_crashing(synthetic_root: Path):
    repository = FakeRepository([_mount(synthetic_root / "missing")], [], [])
    service = VaultService(repository, stable_after_seconds=0)

    result = await service.scan("vault_mount:fixture")

    assert result.status == "unavailable"


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
async def test_one_scan_operation_id_is_reused_for_every_projected_file(synthetic_root: Path):
    root = synthetic_root / "multi"
    root.mkdir()
    (root / "one.md").write_text("# One\n")
    (root / "two.md").write_text("# Two\n")
    repository = FakeRepository([_mount(root)], [], [])
    moments = iter((1.0, 3.0))
    service = VaultService(repository, stable_after_seconds=0, clock=lambda: next(moments))

    await service.scan("vault_mount:fixture")
    result = await service.scan("vault_mount:fixture")

    assert {operation for _, _, operation in repository.projections} == {result.operation_id}


@pytest.mark.asyncio
async def test_real_observer_event_debounces_burst_to_one_projection(synthetic_root: Path):
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
async def test_conflict_is_not_acknowledged_then_stable_rescan_projects_authoritative_a(synthetic_root: Path):
    root = synthetic_root / "conflict"
    root.mkdir()
    (root / "note.md").write_text("# A\n")
    repository = FakeRepository([_mount(root)], [], [])
    conflict = ProjectionResult(vault_file_id="vault_file:fixture", note_id="note:fixture", status="conflict", parse_state="parsed", embedding_state="pending", reconciliation_required=True)
    projected = ProjectionResult(vault_file_id="vault_file:fixture", note_id="note:fixture", status="projected", parse_state="parsed", embedding_state="pending")
    repository.project_document = AsyncMock(side_effect=[conflict, projected])
    moments = iter((1.0, 3.0, 5.0, 7.0, 9.0))
    service = VaultService(repository, stable_after_seconds=0, clock=lambda: next(moments))

    await service.scan("vault_mount:fixture")
    first = await service.scan("vault_mount:fixture")
    await service.scan("vault_mount:fixture")
    second = await service.scan("vault_mount:fixture")

    assert first.reconciliation_required is True
    assert second.status == "ready-read-only"
    assert repository.project_document.await_count == 2


@pytest.mark.asyncio
async def test_missing_receipts_always_get_fresh_ids_outside_scan_context(synthetic_root: Path):
    repository = FakeRepository([], [], [])
    adapter = _ObservationAdapter(repository, lambda: "vault-scan-shared")

    await adapter.mark_missing("vault_mount:fixture", "one.md")
    await adapter.mark_missing("vault_mount:fixture", "two.md")

    ids = [operation for _, _, operation in repository.missing_operations]
    assert len(set(ids)) == 2
    assert all(identifier.startswith("vault-missing-") for identifier in ids)
