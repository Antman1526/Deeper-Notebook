from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from deeper_notebook.knowledge_engine.repository import KnowledgeRepositoryError
from deeper_notebook.knowledge_engine.shadow import KnowledgeShadowCoordinator
from deeper_notebook.overlay.contracts import OverlayNote
from deeper_notebook.vault.repository import VaultMount
from deeper_notebook.vault.watcher import VaultWorkItem

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


class CapturingKnowledgeRepository:
    def __init__(self) -> None:
        self.snapshots = []
        self.operation_ids: list[str] = []
        self.failure_receipts: list[dict[str, str]] = []
        self.fail_commit = False
        self.commit_error_code: str | None = None
        self.fail_failure_receipt = False

    async def commit_snapshot(self, snapshot, *, operation_id: str):
        self.snapshots.append(snapshot)
        self.operation_ids.append(operation_id)
        if self.fail_commit:
            raise RuntimeError("private repository detail")
        if self.commit_error_code is not None:
            raise KnowledgeRepositoryError(self.commit_error_code)
        return SimpleNamespace(status="projected")

    async def record_projection_failure(self, **kwargs):
        if self.fail_failure_receipt:
            raise RuntimeError("receipt repository unavailable")
        self.failure_receipts.append(kwargs)
        return SimpleNamespace(status="failed")


def _mount() -> VaultMount:
    return VaultMount(
        id="vault_mount:fixture",
        name="Fixture vault",
        root_path="/safe/fixture",
        format_mode="markdown",
        status="ready-read-only",
        watch_enabled=True,
        parser_version="test",
    )


def _work() -> VaultWorkItem:
    content = b"# Exact source\r\n\r\n- [ ] preserve bytes\r\n"
    return VaultWorkItem(
        vault_id="vault_mount:fixture",
        relative_path="Research/Exact.md",
        file_kind="markdown",
        protected=False,
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        modified_ns=123,
    )


@pytest.mark.asyncio
async def test_external_shadow_projects_exact_work_item_bytes_and_proven_claims():
    repository = CapturingKnowledgeRepository()
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    work = _work()

    result = await coordinator.project_external(
        legacy_operation_id="vault-scan-fixture",
        mount=_mount(),
        observation=work,
        source_kind="markdown",
        vault_file_id="vault_file:fixture",
        projected_note_id="note:fixture",
    )

    snapshot = repository.snapshots[0]
    assert result is None
    assert snapshot.revision.content_hash == work.content_hash
    assert snapshot.revision.byte_size == len(work.content)
    assert snapshot.document.normalized_body == "# Exact source\r\n\r\n- [ ] preserve bytes\r\n"
    assert {
        (claim.legacy_kind, claim.legacy_id)
        for claim in snapshot.identity_claims
    } >= {
        ("vault_mount", "vault_mount:fixture"),
        ("vault_file", "vault_file:fixture"),
        ("note", "note:fixture"),
    }


@pytest.mark.asyncio
async def test_shadow_operation_is_deterministic_for_a_legacy_operation_and_hash():
    repository = CapturingKnowledgeRepository()
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    work = _work()
    arguments = {
        "legacy_operation_id": "vault-scan-fixture",
        "mount": _mount(),
        "observation": work,
        "source_kind": "markdown",
        "vault_file_id": "vault_file:fixture",
        "projected_note_id": "note:fixture",
    }

    await coordinator.project_external(**arguments)
    await coordinator.project_external(**arguments)

    assert repository.operation_ids == [
        repository.operation_ids[0],
        repository.operation_ids[0],
    ]
    assert work.content_hash in repository.operation_ids[0]


@pytest.mark.asyncio
async def test_shadow_operation_separates_same_bytes_at_different_locators():
    repository = CapturingKnowledgeRepository()
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    first = _work()
    second = VaultWorkItem(
        vault_id=first.vault_id,
        relative_path="Research/Copy.md",
        file_kind=first.file_kind,
        protected=first.protected,
        content=first.content,
        content_hash=first.content_hash,
        byte_size=first.byte_size,
        modified_ns=first.modified_ns,
    )

    for work in (first, second):
        await coordinator.project_external(
            legacy_operation_id="vault-scan-fixture",
            mount=_mount(),
            observation=work,
            source_kind="markdown",
            vault_file_id=f"vault_file:{work.relative_path}",
            projected_note_id=f"note:{work.relative_path}",
        )

    assert repository.operation_ids[0] != repository.operation_ids[1]


@pytest.mark.asyncio
async def test_shadow_records_sanitized_failure_without_returning_content():
    repository = CapturingKnowledgeRepository()
    repository.fail_commit = True
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    work = _work()

    result = await coordinator.project_external(
        legacy_operation_id="vault-scan-fixture",
        mount=_mount(),
        observation=work,
        source_kind="markdown",
        vault_file_id="vault_file:fixture",
        projected_note_id="note:fixture",
    )

    assert result is None
    assert repository.failure_receipts == [
        {
            "operation_id": repository.operation_ids[0],
            "space_id": repository.snapshots[0].space.id,
            "relative_locator": "Research/Exact.md",
            "input_hash": work.content_hash,
            "error_code": "knowledge_engine_projection_failed",
        }
    ]


@pytest.mark.asyncio
async def test_shadow_preserves_a_stable_repository_failure_code_in_its_receipt():
    repository = CapturingKnowledgeRepository()
    repository.commit_error_code = "knowledge_engine_repository_unavailable"
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    work = _work()

    await coordinator.project_external(
        legacy_operation_id="vault-scan-fixture",
        mount=_mount(),
        observation=work,
        source_kind="markdown",
        vault_file_id="vault_file:fixture",
        projected_note_id="note:fixture",
    )

    assert repository.failure_receipts[0]["error_code"] == (
        "knowledge_engine_repository_unavailable"
    )


@pytest.mark.asyncio
async def test_overlay_shadow_uses_exact_canonical_markdown_bytes():
    repository = CapturingKnowledgeRepository()
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    markdown = (
        "---\n"
        "deeper_notebook:\n"
        "  id: overlay_note:fixture\n"
        "  kind: unique\n"
        "  date_key: null\n"
        "---\n"
        "# Overlay\n"
    )
    note = OverlayNote(
        id="overlay_note:fixture",
        space_id="overlay_space:default",
        projected_note_id="note:fixture",
        stable_id="01JTESTOVERLAY000000000001",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260731-1200 Overlay.md",
        title="Overlay",
        content_hash=hashlib.sha256(markdown.encode()).hexdigest(),
        revision=1,
        projection_state="current",
        created_at=NOW,
        updated_at=NOW,
    )

    result = await coordinator.project_overlay(
        legacy_operation_id="overlay-fixture",
        overlay_note=note,
        canonical_markdown=markdown,
        observed_modified_ns=456,
    )

    snapshot = repository.snapshots[0]
    assert result is None
    assert snapshot.revision.content_hash == hashlib.sha256(markdown.encode()).hexdigest()
    assert snapshot.revision.byte_size == len(markdown.encode())
    assert {
        (claim.legacy_kind, claim.legacy_id)
        for claim in snapshot.identity_claims
    } >= {
        ("overlay_space", "overlay_space:default"),
        ("overlay_note", "overlay_note:fixture"),
        ("note", "note:fixture"),
    }


@pytest.mark.asyncio
async def test_shadow_does_not_attempt_external_source_mutation():
    class MutationTripwire(CapturingKnowledgeRepository):
        def write(self, *_args, **_kwargs):
            raise AssertionError("external write must not be available")

        replace = write
        delete = write
        rename = write
        move = write
        scan = write

    repository = MutationTripwire()
    coordinator = KnowledgeShadowCoordinator(repository=repository, clock=lambda: NOW)
    work = _work()

    await coordinator.project_external(
        legacy_operation_id="vault-scan-fixture",
        mount=_mount(),
        observation=work,
        source_kind="markdown",
        vault_file_id="vault_file:fixture",
        projected_note_id="note:fixture",
    )

    assert len(repository.snapshots) == 1
