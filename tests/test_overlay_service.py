from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayMutationReceipt,
    OverlayNote,
    OverlayPage,
    UpdateOverlayNote,
)
from deeper_notebook.overlay.paths import OverlayLayout
from deeper_notebook.overlay.repository import (
    OverlayConflictError,
    OverlayRepositoryError,
    OverlayReservation,
)
from deeper_notebook.overlay.service import OverlayService
from deeper_notebook.overlay.storage import OverlayStorage, OverlayStorageError

NOW = datetime(2026, 7, 29, 15, 42, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self) -> None:
        self.notes: dict[str, OverlayNote] = {}
        self.pages: dict[str, OverlayPage] = {}
        self.reservations: dict[tuple[str, str], OverlayReservation] = {}
        self.receipts: dict[str, OverlayMutationReceipt] = {}
        self.paths: dict[str, str] = {}
        self.commit_calls = 0
        self.failure_codes: list[str] = []
        self.fail_commit_once = False
        self.staged_hashes: dict[str, str] = {}

    async def reserve_create(
        self,
        *,
        operation: str,
        idempotency_key: str,
        kind: str,
        date_key: str | None,
        relative_path: str,
        title: str,
    ) -> OverlayReservation:
        key = (operation, idempotency_key)
        if key in self.reservations:
            return self.reservations[key]
        if relative_path in self.paths:
            raise OverlayConflictError("overlay_path_conflict")
        note_id = f"overlay_note:{len(self.notes) + 1}"
        projected_id = f"note:overlay-{len(self.notes) + 1}"
        reservation = OverlayReservation(
            operation_id=f"operation-{len(self.reservations) + 1}",
            idempotency_key=idempotency_key,
            overlay_note_id=note_id,
            projected_note_id=projected_id,
            relative_path=relative_path,
            title=title,
            kind=kind,
            date_key=date_key,
            expected_revision=None,
        )
        note = OverlayNote(
            id=note_id,
            space_id="overlay_space:default",
            projected_note_id=projected_id,
            stable_id=f"01JTESTOVERLAY{len(self.notes) + 1:012d}",
            kind=kind,
            date_key=date_key,
            relative_path=relative_path,
            title=title,
            content_hash="0" * 64,
            revision=1,
            projection_state="pending",
            created_at=NOW,
            updated_at=NOW,
        )
        self.notes[note_id] = note
        self.paths[relative_path] = note_id
        self.reservations[key] = reservation
        self.receipts[reservation.operation_id] = OverlayMutationReceipt(
            id=f"overlay_mutation_receipt:{reservation.operation_id}",
            operation_id=reservation.operation_id,
            idempotency_key=idempotency_key,
            overlay_note_id=note_id,
            operation=operation,
            status="started",
            started_at=NOW,
        )
        return reservation

    async def reserve_update(
        self,
        *,
        note_id: str,
        expected_revision: int,
        idempotency_key: str,
    ) -> OverlayReservation:
        key = ("update", idempotency_key)
        if key in self.reservations:
            return self.reservations[key]
        note = self.notes[note_id]
        if note.revision != expected_revision:
            raise OverlayConflictError("overlay_revision_conflict")
        reservation = OverlayReservation(
            operation_id=f"operation-{len(self.reservations) + 1}",
            idempotency_key=idempotency_key,
            overlay_note_id=note.id,
            projected_note_id=note.projected_note_id,
            relative_path=note.relative_path,
            title=note.title,
            kind=note.kind,
            date_key=note.date_key,
            expected_revision=expected_revision,
        )
        self.reservations[key] = reservation
        self.receipts[reservation.operation_id] = OverlayMutationReceipt(
            id=f"overlay_mutation_receipt:{reservation.operation_id}",
            operation_id=reservation.operation_id,
            idempotency_key=idempotency_key,
            overlay_note_id=note_id,
            operation="update",
            expected_revision=expected_revision,
            before_hash=note.content_hash,
            status="started",
            started_at=NOW,
        )
        return reservation

    async def get_replay(
        self,
        reservation: OverlayReservation,
    ) -> OverlayPage | None:
        receipt = self.receipts[reservation.operation_id]
        if receipt.status != "success":
            return None
        return self.pages[reservation.overlay_note_id]

    async def get_note(self, note_id: str) -> OverlayNote:
        return self.notes[note_id]

    async def get_page(self, note_id: str) -> OverlayPage:
        return self.pages[note_id]

    async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]:
        return list(self.notes.values())[offset : offset + limit]

    async def get_receipt(
        self,
        reservation: OverlayReservation,
    ) -> OverlayMutationReceipt:
        return self.receipts[reservation.operation_id]

    def stage_failure_hash(
        self,
        reservation: OverlayReservation,
        content_hash: str,
    ) -> None:
        self.staged_hashes[reservation.operation_id] = content_hash

    async def commit_revision(
        self,
        *,
        reservation: OverlayReservation,
        content_hash: str,
        byte_size: int,
        relative_snapshot: str | None,
        parsed,
    ) -> OverlayNote:
        del byte_size, relative_snapshot
        self.commit_calls += 1
        self.stage_failure_hash(reservation, content_hash)
        if self.fail_commit_once:
            self.fail_commit_once = False
            raise OverlayRepositoryError("overlay_repository_unavailable")
        prior = self.notes[reservation.overlay_note_id]
        revision = (
            1
            if reservation.expected_revision is None
            else reservation.expected_revision + 1
        )
        note = prior.model_copy(
            update={
                "title": reservation.title,
                "content_hash": content_hash,
                "revision": revision,
                "projection_state": "current",
                "updated_at": NOW,
            }
        )
        self.notes[note.id] = note
        self.pages[note.id] = OverlayPage(
            overlay=note,
            note={
                "id": note.projected_note_id,
                "title": parsed.title,
                "content": parsed.markdown,
                "source_hash": parsed.content_hash,
                "source_authority": "overlay",
            },
            blocks=[block.model_dump() for block in parsed.blocks],
            tasks=[task.model_dump() for task in parsed.tasks],
        )
        receipt = self.receipts[reservation.operation_id]
        self.receipts[reservation.operation_id] = receipt.model_copy(
            update={
                "resulting_revision": revision,
                "after_hash": content_hash,
                "status": "success",
                "error_code": None,
                "completed_at": NOW,
            }
        )
        return note

    async def record_failure(
        self,
        *,
        reservation: OverlayReservation,
        error_code: str,
    ) -> None:
        self.failure_codes.append(error_code)
        prior = self.receipts[reservation.operation_id]
        after_hash = self.staged_hashes.get(reservation.operation_id)
        self.receipts[reservation.operation_id] = prior.model_copy(
            update={
                "after_hash": after_hash,
                "status": "failed",
                "error_code": error_code,
                "completed_at": NOW,
            }
        )


class CountingStorage(OverlayStorage):
    def __init__(self, layout: OverlayLayout) -> None:
        super().__init__(layout)
        self.create_calls = 0
        self.replace_calls = 0
        self.fail_create = False

    def create(self, *args, **kwargs):
        self.create_calls += 1
        if self.fail_create:
            raise OverlayStorageError("overlay_storage_unavailable")
        return super().create(*args, **kwargs)

    def replace(self, *args, **kwargs):
        self.replace_calls += 1
        return super().replace(*args, **kwargs)


class Fixture:
    def __init__(self, tmp_path: Path) -> None:
        data_root = tmp_path / "data"
        data_root.mkdir(mode=0o700)
        self.layout = OverlayLayout.from_data_root(data_root)
        self.storage = CountingStorage(self.layout)
        self.repository = MemoryRepository()
        self.clock = lambda: NOW

    def service(self) -> OverlayService:
        return OverlayService(
            self.repository,
            self.storage,
            clock=self.clock,
        )


@pytest.fixture
def fixture(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


@pytest.mark.asyncio
async def test_daily_creation_is_idempotent_across_service_instances(fixture):
    first = await fixture.service().create_daily(CreateDailyNote(date_key="2026-07-29"))
    second = await fixture.service().create_daily(
        CreateDailyNote(date_key="2026-07-29")
    )

    assert first.overlay.id == second.overlay.id
    assert first.overlay.content_hash == second.overlay.content_hash
    assert fixture.storage.create_calls == 1
    assert list(fixture.layout.daily_root.glob("*.md")) == [
        fixture.layout.daily_root / "2026-07-29.md"
    ]


@pytest.mark.asyncio
async def test_unique_collisions_receive_deterministic_suffixes(fixture):
    first = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    second = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="two")
    )

    assert first.overlay.relative_path.endswith("Research.md")
    assert second.overlay.relative_path.endswith("Research-2.md")


@pytest.mark.asyncio
async def test_update_conflict_never_replaces_canonical_file(fixture):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )

    with pytest.raises(OverlayConflictError, match="overlay_revision_conflict"):
        await fixture.service().update(
            page.overlay.id,
            UpdateOverlayNote(
                title="Changed",
                markdown="# Changed\n",
                expected_revision=99,
                idempotency_key="save",
            ),
        )

    stored = fixture.storage.read(page.overlay.relative_path)
    assert stored.content_hash == page.overlay.content_hash
    assert fixture.storage.replace_calls == 0


@pytest.mark.asyncio
async def test_update_hash_drift_is_detected_before_snapshot_or_replace(fixture):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    fixture.storage.replace(
        page.overlay.relative_path,
        "# Changed outside the projection\n",
        expected_hash=page.overlay.content_hash,
        revision=2,
        operation_id="external-drift",
    )
    fixture.storage.replace_calls = 0
    drifted = fixture.storage.read(page.overlay.relative_path)
    snapshots_before = set(fixture.layout.revisions_root.glob("*.md"))

    with pytest.raises(OverlayConflictError, match="overlay_revision_conflict"):
        await fixture.service().update(
            page.overlay.id,
            UpdateOverlayNote(
                title="Changed",
                markdown="# Changed\n",
                expected_revision=1,
                idempotency_key="save-drift",
            ),
        )

    assert fixture.storage.replace_calls == 0
    assert fixture.storage.read(page.overlay.relative_path) == drifted
    assert set(fixture.layout.revisions_root.glob("*.md")) == snapshots_before


@pytest.mark.asyncio
async def test_storage_failure_leaves_no_successful_revision(fixture):
    fixture.storage.fail_create = True

    with pytest.raises(OverlayStorageError, match="overlay_storage_unavailable"):
        await fixture.service().create_unique(
            CreateUniqueNote(title="Research", idempotency_key="one")
        )

    assert fixture.repository.commit_calls == 0
    assert fixture.repository.failure_codes == ["overlay_storage_unavailable"]
    receipt = next(iter(fixture.repository.receipts.values()))
    assert receipt.status == "failed"
    assert receipt.after_hash is None


@pytest.mark.asyncio
async def test_db_failure_after_replace_is_retryable_without_second_write(fixture):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    fixture.repository.fail_commit_once = True
    request = UpdateOverlayNote(
        title="Changed",
        markdown="# Changed\n",
        expected_revision=1,
        idempotency_key="save-one",
    )

    with pytest.raises(
        OverlayRepositoryError,
        match="overlay_projection_pending",
    ):
        await fixture.service().update(page.overlay.id, request)

    replaced = fixture.storage.read(page.overlay.relative_path)
    assert replaced.content_hash != page.overlay.content_hash
    assert fixture.repository.failure_codes[-1] == "overlay_projection_pending"
    failed_receipt = fixture.repository.receipts[
        fixture.repository.reservations[("update", "save-one")].operation_id
    ]
    assert failed_receipt.status == "failed"
    assert failed_receipt.after_hash == replaced.content_hash

    reconciled = await fixture.service().update(page.overlay.id, request)

    assert reconciled.overlay.revision == 2
    assert reconciled.overlay.content_hash == replaced.content_hash
    assert fixture.storage.replace_calls == 1


@pytest.mark.asyncio
async def test_parser_failure_preserves_prior_projection(fixture, monkeypatch):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    prior_projection = fixture.repository.pages[page.overlay.id]

    def fail_parse(*_args, **_kwargs):
        raise ValueError("synthetic parser details")

    monkeypatch.setattr(
        "deeper_notebook.overlay.service.parse_document",
        fail_parse,
    )

    with pytest.raises(
        OverlayRepositoryError,
        match="overlay_projection_pending",
    ):
        await fixture.service().update(
            page.overlay.id,
            UpdateOverlayNote(
                title="Changed",
                markdown="# Changed\n",
                expected_revision=1,
                idempotency_key="save-parser",
            ),
        )

    assert fixture.repository.pages[page.overlay.id] == prior_projection
    assert fixture.repository.notes[page.overlay.id].revision == 1
    assert fixture.repository.failure_codes[-1] == "overlay_parser_failed"


@pytest.mark.asyncio
async def test_pages_and_receipts_never_expose_absolute_overlay_roots(fixture):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    receipt = next(iter(fixture.repository.receipts.values()))

    serialized = f"{page.model_dump_json()} {receipt.model_dump_json()}"
    assert str(fixture.layout.canonical_root) not in serialized
    assert "/Users/" not in serialized
    assert "synthetic parser details" not in serialized
