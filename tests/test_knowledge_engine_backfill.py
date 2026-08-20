from __future__ import annotations

import asyncio
import os
import pwd
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from deeper_notebook.knowledge_engine.backfill import (
    CanonicalSource,
    CanonicalSourceCatalog,
    KnowledgeBackfillService,
)
from deeper_notebook.knowledge_engine.contracts import BackfillCheckpoint
from deeper_notebook.knowledge_engine.repository import KnowledgeRepositoryError
from deeper_notebook.overlay.contracts import OverlayNote
from deeper_notebook.overlay.paths import OverlayLayout
from deeper_notebook.overlay.storage import OverlayStorage
from deeper_notebook.vault.repository import VaultFile, VaultMount
from deeper_notebook.vault.security import VaultSecurityError

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def source(space: str, locator: str, raw: bytes = b"# Page\n") -> CanonicalSource:
    return CanonicalSource(
        space_id=space,
        space_display_name=space,
        source_ref=space.replace("knowledge_engine_space:", "source:"),
        authority_kind="external_read_only",
        source_kind="markdown",
        format_mode="markdown",
        relative_locator=locator,
        canonical_bytes=raw,
        byte_size=len(raw),
        declared_encoding="utf-8",
        declared_newline="lf",
        observed_content_hash=sha256(raw).hexdigest(),
        observed_modified_ns=1,
        observed_at=NOW,
        prior_revision=None,
        legacy_identities=(),
    )


class Catalog:
    def __init__(self, sources: list[CanonicalSource]) -> None:
        self.sources = sources
        self.failures: list[object] = []

    async def iter_sources(self):
        for item in self.sources:
            yield item


class Repository:
    def __init__(self) -> None:
        self.checkpoints: dict[str, BackfillCheckpoint] = {}
        self.projected_locators: list[tuple[str, str]] = []
        self.committed_snapshots: list[object] = []
        self.failure_codes: list[str] = []
        self.operations: dict[str, str] = {}
        self.cancel_on: str | None = None
        self.fail_receipts = False
        self.failure_status = "failed"

    async def get_checkpoint(self, space_id: str):
        return self.checkpoints.get(space_id)

    async def save_checkpoint(self, checkpoint: BackfillCheckpoint):
        self.checkpoints[checkpoint.space_id] = checkpoint
        return checkpoint

    async def commit_snapshot(self, snapshot, *, operation_id: str):
        locator = snapshot.document.relative_locator
        if self.cancel_on == locator:
            raise asyncio.CancelledError
        prior = self.operations.get(operation_id)
        if prior is not None:
            return SimpleNamespace(status="unchanged")
        self.projected_locators.append((snapshot.space.id, locator))
        self.committed_snapshots.append(snapshot)
        self.operations[operation_id] = snapshot.revision.content_hash
        return SimpleNamespace(status="projected")

    async def record_projection_failure(self, **kwargs):
        if self.fail_receipts:
            raise RuntimeError("receipt store unavailable")
        self.failure_codes.append(kwargs["error_code"])
        return SimpleNamespace(status=self.failure_status)


def service(catalog: Catalog, repository: Repository) -> KnowledgeBackfillService:
    return KnowledgeBackfillService(
        catalog=catalog, repository=repository, clock=lambda: NOW
    )


@pytest.mark.asyncio
async def test_backfill_orders_sources_and_resumes_after_checkpoint():
    repository = Repository()
    catalog = Catalog(
        [
            source("knowledge_engine_space:b", "Pages/Z.md"),
            source("knowledge_engine_space:a", "Pages/B.md", b"# B\n"),
            source("knowledge_engine_space:a", "Pages/A.md"),
        ]
    )
    repository.checkpoints["knowledge_engine_space:a"] = BackfillCheckpoint(
        space_id="knowledge_engine_space:a",
        last_relative_locator="Pages/A.md",
        last_source_hash=sha256(b"# Page\n").hexdigest(),
        status="running",
        projected=0,
        unchanged=0,
        failed=0,
        updated_at=NOW,
    )

    result = await service(catalog, repository).run()

    assert repository.projected_locators == [
        ("knowledge_engine_space:a", "Pages/B.md"),
        ("knowledge_engine_space:b", "Pages/Z.md"),
    ]
    assert result.projected == 2


@pytest.mark.asyncio
async def test_failed_item_keeps_prior_snapshot_and_requires_durable_failure_receipt():
    repository = Repository()
    catalog = Catalog([source("knowledge_engine_space:a", "Bad.md", b"\xff")])

    result = await service(catalog, repository).run()

    assert result.failed == 1
    assert repository.committed_snapshots == []
    assert repository.failure_codes == ["knowledge_adapter_invalid"]
    assert (
        repository.checkpoints["knowledge_engine_space:a"].last_relative_locator
        == "Bad.md"
    )


@pytest.mark.asyncio
async def test_failure_receipt_unavailability_stops_without_advancing_checkpoint():
    repository = Repository()
    repository.fail_receipts = True
    catalog = Catalog([source("knowledge_engine_space:a", "Bad.md", b"\xff")])

    with pytest.raises(RuntimeError, match="receipt store unavailable"):
        await service(catalog, repository).run()

    assert repository.checkpoints == {}


@pytest.mark.asyncio
async def test_checkpoint_corruption_fails_closed_without_restarting():
    class CorruptRepository(Repository):
        async def get_checkpoint(self, space_id: str):
            raise KnowledgeRepositoryError("knowledge_engine_checkpoint_invalid")

    repository = CorruptRepository()
    with pytest.raises(KnowledgeRepositoryError, match="checkpoint_invalid"):
        await service(
            Catalog([source("knowledge_engine_space:a", "Pages/A.md")]), repository
        ).run()
    assert repository.committed_snapshots == []


@pytest.mark.asyncio
async def test_cancellation_resumes_after_last_durable_item():
    repository = Repository()
    repository.cancel_on = "Pages/B.md"
    catalog = Catalog(
        [
            source("knowledge_engine_space:a", "Pages/A.md"),
            source("knowledge_engine_space:a", "Pages/B.md", b"# B\n"),
        ]
    )

    with pytest.raises(asyncio.CancelledError):
        await service(catalog, repository).run()

    assert (
        repository.checkpoints["knowledge_engine_space:a"].last_relative_locator
        == "Pages/A.md"
    )
    repository.cancel_on = None
    result = await service(catalog, repository).run()
    assert result.projected == 1
    assert repository.projected_locators[-1] == (
        "knowledge_engine_space:a",
        "Pages/B.md",
    )


@pytest.mark.asyncio
async def test_resume_reprojects_changed_checkpoint_locator_before_continuing():
    repository = Repository()
    repository.cancel_on = "Pages/B.md"
    catalog = Catalog(
        [
            source("knowledge_engine_space:a", "Pages/A.md", b"# Original\n"),
            source("knowledge_engine_space:a", "Pages/B.md", b"# B\n"),
        ]
    )

    with pytest.raises(asyncio.CancelledError):
        await service(catalog, repository).run()

    original_revision = repository.committed_snapshots[-1].revision.id
    catalog.sources[0] = replace(
        catalog.sources[0],
        canonical_bytes=b"# Changed\n",
        byte_size=len(b"# Changed\n"),
        observed_content_hash=sha256(b"# Changed\n").hexdigest(),
    )
    repository.cancel_on = None

    result = await service(catalog, repository).run()

    assert result.projected == 2
    assert repository.projected_locators == [
        ("knowledge_engine_space:a", "Pages/A.md"),
        ("knowledge_engine_space:a", "Pages/A.md"),
        ("knowledge_engine_space:a", "Pages/B.md"),
    ]
    assert repository.committed_snapshots[-2].revision.id != original_revision


@pytest.mark.asyncio
async def test_failure_receipt_with_nonfailed_status_stops_without_checkpointing():
    repository = Repository()
    repository.failure_status = "projected"
    catalog = Catalog([source("knowledge_engine_space:a", "Bad.md", b"\xff")])

    with pytest.raises(RuntimeError, match="knowledge_failure_receipt_invalid"):
        await service(catalog, repository).run()

    assert repository.checkpoints == {}


@pytest.mark.asyncio
async def test_completed_run_replays_idempotently_and_new_hash_creates_revision():
    repository = Repository()
    catalog = Catalog([source("knowledge_engine_space:a", "Pages/A.md")])
    first = await service(catalog, repository).run()
    first_revision = repository.committed_snapshots[-1].revision.id
    second = await service(catalog, repository).run()
    catalog.sources[0] = replace(
        catalog.sources[0],
        canonical_bytes=b"# Changed\n",
        byte_size=10,
        observed_content_hash=sha256(b"# Changed\n").hexdigest(),
    )
    third = await service(catalog, repository).run()

    assert (first.projected, second.unchanged, third.projected) == (1, 1, 1)
    assert repository.committed_snapshots[-1].revision.id != first_revision


@pytest.mark.asyncio
async def test_backfill_distinguishes_identical_bytes_at_different_locators():
    repository = Repository()
    catalog = Catalog(
        [
            source("knowledge_engine_space:a", "Pages/A.md", b"# Same\n"),
            source("knowledge_engine_space:a", "Pages/B.md", b"# Same\n"),
        ]
    )

    first = await service(catalog, repository).run()
    first_revisions = {
        snapshot.document.relative_locator: snapshot.revision.id
        for snapshot in repository.committed_snapshots
    }
    second = await service(catalog, repository).run()
    catalog.sources[1] = replace(
        catalog.sources[1],
        canonical_bytes=b"# Changed\n",
        byte_size=len(b"# Changed\n"),
        observed_content_hash=sha256(b"# Changed\n").hexdigest(),
    )
    third = await service(catalog, repository).run()

    assert first.projected == 2
    assert repository.projected_locators[:2] == [
        ("knowledge_engine_space:a", "Pages/A.md"),
        ("knowledge_engine_space:a", "Pages/B.md"),
    ]
    assert second.unchanged == 2
    assert (third.projected, third.unchanged) == (1, 1)
    assert repository.committed_snapshots[-1].document.relative_locator == "Pages/B.md"
    assert (
        repository.committed_snapshots[-1].revision.id != first_revisions["Pages/B.md"]
    )
    assert len(repository.operations) == 3


def test_operation_id_hashes_relative_locator_without_exposing_it():
    canonical = source(
        "knowledge_engine_space:a",
        "Private Pages/Exact Locator.md",
        b"# Page\n",
    )

    operation_id = KnowledgeBackfillService._operation_id(canonical)

    assert operation_id == (
        "backfill-v1:knowledge_engine_space:a:"
        f"{sha256(canonical.relative_locator.encode('utf-8')).hexdigest()}:"
        f"{canonical.observed_content_hash}"
    )
    assert canonical.relative_locator not in operation_id


class OverlayRepository:
    def __init__(self, note: OverlayNote) -> None:
        self.note = note
        self.write_calls: list[str] = []

    async def list_notes(self, limit: int, offset: int):
        return [self.note] if offset == 0 else []


class VaultRepository:
    def __init__(
        self, mounts: list[VaultMount], files: dict[str, list[VaultFile]]
    ) -> None:
        self.mounts = mounts
        self.files = files
        self.write_calls: list[str] = []

    async def list_mounts(self):
        return self.mounts

    async def list_files(self, vault_id: str, prefix: str, limit: int, offset: int):
        return self.files[vault_id][offset : offset + limit]


class EmptyOverlayRepository:
    async def list_notes(self, limit: int, offset: int):
        return []


@pytest.fixture
def approved_vault_root() -> Path:
    base = (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".cache"
        / "deeper-notebook-backfill-tests"
    )
    root = base / uuid4().hex / "vault"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)
        try:
            base.rmdir()
        except OSError:
            pass


@pytest.mark.asyncio
async def test_catalog_reads_overlay_body_only_without_source_writes(tmp_path: Path):
    storage = OverlayStorage(OverlayLayout.from_data_root(tmp_path))
    raw = b"---\ndeeper_notebook:\n  id: overlay_note:daily\n  kind: daily\n  date_key: '2026-07-30'\n---\n# Body\n"
    stored = storage.create("Daily/2026-07-30.md", raw.decode(), operation_id="seed")
    note = OverlayNote(
        id="overlay_note:daily",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-daily",
        stable_id="stable-overlay-daily-0001",
        kind="daily",
        date_key="2026-07-30",
        relative_path="Daily/2026-07-30.md",
        title="Daily",
        content_hash=stored.content_hash,
        revision=1,
        projection_state="current",
        created_at=NOW,
        updated_at=NOW,
    )
    overlay = OverlayRepository(note)
    vault = VaultRepository([], {})
    catalog = CanonicalSourceCatalog(
        overlay_repository=overlay, overlay_storage=storage, vault_repository=vault
    )

    sources = [item async for item in catalog.iter_sources()]

    assert sources[0].canonical_bytes == raw
    assert sources[0].source_kind == "overlay"
    snapshot = service(Catalog(sources), Repository())._project(sources[0])
    assert snapshot.document.normalized_body == "# Body\n"
    assert [claim.legacy_kind for claim in sources[0].legacy_identities] == [
        "note",
        "overlay_note",
        "overlay_space",
    ]
    assert overlay.write_calls == vault.write_calls == []


@pytest.mark.asyncio
async def test_catalog_reports_descriptor_failures_without_root_disclosure(
    approved_vault_root: Path,
):
    root = approved_vault_root
    (root / "Unsafe.md").symlink_to(root.parent / "outside.md")
    mount = VaultMount(
        id="vault_mount:one",
        name="One",
        root_path=str(root),
        format_mode="mixed",
        status="ready-read-only",
        parser_version="vault-parser-v1",
    )
    file = VaultFile(
        id="vault_file:unsafe",
        note_id="note:unsafe",
        vault_id=mount.id,
        relative_path="Unsafe.md",
        file_kind="markdown",
        format="markdown",
        content_hash="0" * 64,
        size_bytes=1,
        modified_ns=1,
        encoding="utf-8",
        newline="lf",
        parse_status="invalid",
        deleted_state="present",
    )
    catalog = CanonicalSourceCatalog(
        overlay_repository=EmptyOverlayRepository(),
        overlay_storage=SimpleNamespace(),
        vault_repository=VaultRepository([mount], {mount.id: [file]}),
    )

    assert [item async for item in catalog.iter_sources()] == []
    failure = catalog.failures[0]
    assert failure.error_code == "unsafe_symlink"
    assert str(root) not in str(failure)


@pytest.mark.asyncio
async def test_catalog_keeps_unavailable_root_path_out_of_failure():
    missing_root = (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".cache"
        / f"deeper-notebook-backfill-missing-{uuid4().hex}"
    )
    mount = VaultMount(
        id="vault_mount:missing",
        name="Missing",
        root_path=str(missing_root),
        format_mode="markdown",
        status="unavailable",
        parser_version="vault-parser-v1",
    )
    file = VaultFile(
        id="vault_file:missing",
        note_id="note:missing",
        vault_id=mount.id,
        relative_path="Lost.md",
        file_kind="markdown",
        format="markdown",
        content_hash="1" * 64,
        size_bytes=1,
        modified_ns=1,
        encoding="utf-8",
        newline="lf",
        parse_status="invalid",
        deleted_state="present",
    )
    catalog = CanonicalSourceCatalog(
        overlay_repository=EmptyOverlayRepository(),
        overlay_storage=SimpleNamespace(),
        vault_repository=VaultRepository([mount], {mount.id: [file]}),
    )

    assert [item async for item in catalog.iter_sources()] == []
    assert catalog.failures[0].error_code == "invalid_root"
    assert str(missing_root) not in str(catalog.failures[0])


@pytest.mark.asyncio
async def test_catalog_maps_root_drift_to_stable_failure_code(
    monkeypatch: pytest.MonkeyPatch,
):
    mount = VaultMount(
        id="vault_mount:drift",
        name="Drift",
        root_path="/safe/not-retained",
        format_mode="markdown",
        status="ready-read-only",
        parser_version="vault-parser-v1",
    )
    file = VaultFile(
        id="vault_file:drift",
        note_id="note:drift",
        vault_id=mount.id,
        relative_path="Drift.md",
        file_kind="markdown",
        format="markdown",
        content_hash="2" * 64,
        size_bytes=1,
        modified_ns=1,
        encoding="utf-8",
        newline="lf",
        parse_status="invalid",
        deleted_state="present",
    )

    class Root:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def drift(root, relative_path, *, max_bytes=None):
        raise VaultSecurityError("root_changed")

    monkeypatch.setattr(
        "deeper_notebook.knowledge_engine.backfill.approve_vault_root",
        lambda path: Root(),
    )
    monkeypatch.setattr("deeper_notebook.knowledge_engine.backfill.secure_read", drift)
    catalog = CanonicalSourceCatalog(
        overlay_repository=EmptyOverlayRepository(),
        overlay_storage=SimpleNamespace(),
        vault_repository=VaultRepository([mount], {mount.id: [file]}),
    )

    assert [item async for item in catalog.iter_sources()] == []
    assert catalog.failures[0].error_code == "root_changed"


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["markdown", "obsidian", "logseq"])
async def test_catalog_to_backfill_preserves_mixed_mount_format(
    approved_vault_root: Path, source_kind: str
):
    raw = b"# Mixed mount\n"
    relative_path = f"Pages/{source_kind}.md"
    path = approved_vault_root / relative_path
    path.parent.mkdir()
    path.write_bytes(raw)
    observed = path.stat()
    mount = VaultMount(
        id=f"vault_mount:{source_kind}",
        name="Mixed",
        root_path=str(approved_vault_root),
        format_mode="mixed",
        status="ready-read-only",
        parser_version="vault-parser-v1",
    )
    file = VaultFile(
        id=f"vault_file:{source_kind}",
        note_id=f"note:{source_kind}",
        vault_id=mount.id,
        relative_path=relative_path,
        file_kind="markdown",
        format=source_kind,
        content_hash=sha256(raw).hexdigest(),
        size_bytes=len(raw),
        modified_ns=observed.st_mtime_ns,
        encoding="utf-8",
        newline="lf",
        parse_status="parsed",
        deleted_state="present",
    )
    catalog = CanonicalSourceCatalog(
        overlay_repository=EmptyOverlayRepository(),
        overlay_storage=SimpleNamespace(),
        vault_repository=VaultRepository([mount], {mount.id: [file]}),
    )
    repository = Repository()

    result = await KnowledgeBackfillService(
        catalog=catalog, repository=repository, clock=lambda: NOW
    ).run()

    assert result.projected == 1
    assert repository.committed_snapshots[0].document.relative_locator == relative_path
