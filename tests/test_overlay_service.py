from __future__ import annotations

import hashlib
from dataclasses import replace
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
from deeper_notebook.overlay.paths import OverlayLayout, overlay_frontmatter
from deeper_notebook.overlay.repository import (
    OverlayConflictError,
    OverlayRepositoryError,
    OverlayReservation,
)
from deeper_notebook.overlay.service import OverlayService
from deeper_notebook.overlay.storage import OverlayStorage, OverlayStorageError

NOW = datetime(2026, 7, 29, 15, 42, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self, durable: MemoryRepository | None = None) -> None:
        self.notes = durable.notes if durable else {}
        self.pages = durable.pages if durable else {}
        self.reservations = durable.reservations if durable else {}
        self.receipts = durable.receipts if durable else {}
        self.paths = durable.paths if durable else {}
        self.revisions = durable.revisions if durable else []
        self.commit_calls = 0
        self.failure_codes: list[str] = []
        self.fail_commit_once = False
        self.fail_record_failure = False
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

    async def prepare_revision(
        self,
        *,
        reservation: OverlayReservation,
        content_hash: str,
    ) -> None:
        receipt = self.receipts[reservation.operation_id]
        if receipt.after_hash not in {None, content_hash}:
            raise OverlayConflictError("overlay_hash_conflict")
        self.receipts[reservation.operation_id] = receipt.model_copy(
            update={"after_hash": content_hash}
        )

    async def reassign_unique_path(
        self,
        *,
        reservation: OverlayReservation,
        relative_path: str,
    ) -> OverlayReservation:
        note = self.notes[reservation.overlay_note_id]
        self.paths.pop(note.relative_path)
        reassigned = note.model_copy(
            update={
                "relative_path": relative_path,
                "projection_state": "pending",
            }
        )
        self.notes[note.id] = reassigned
        self.paths[relative_path] = note.id
        updated_reservation = replace(reservation, relative_path=relative_path)
        self.reservations[("create-unique", reservation.idempotency_key)] = (
            updated_reservation
        )
        receipt = self.receipts[reservation.operation_id]
        self.receipts[reservation.operation_id] = receipt.model_copy(
            update={
                "after_hash": None,
                "status": "started",
                "error_code": None,
                "completed_at": None,
            }
        )
        return updated_reservation

    async def commit_revision(
        self,
        *,
        reservation: OverlayReservation,
        content_hash: str,
        byte_size: int,
        relative_snapshot: str | None,
        parsed,
    ) -> OverlayNote:
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
        self.revisions.append(
            {
                "overlay_note_id": note.id,
                "revision": revision,
                "relative_snapshot": relative_snapshot,
                "content_hash": content_hash,
                "byte_size": byte_size,
            }
        )
        return note

    async def record_failure(
        self,
        *,
        reservation: OverlayReservation,
        error_code: str,
    ) -> None:
        if self.fail_record_failure:
            raise OverlayRepositoryError("overlay_repository_unavailable")
        self.failure_codes.append(error_code)
        prior = self.receipts[reservation.operation_id]
        self.receipts[reservation.operation_id] = prior.model_copy(
            update={
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
        self.snapshot_calls = []
        self.fail_create = False
        self.inject_create_collision_once = False

    def create(self, *args, **kwargs):
        self.create_calls += 1
        if self.fail_create:
            raise OverlayStorageError("overlay_storage_unavailable")
        if self.inject_create_collision_once:
            self.inject_create_collision_once = False
            OverlayStorage.create(
                self,
                args[0],
                "# Raced manual note\n",
                operation_id="manual-race",
            )
        return super().create(*args, **kwargs)

    def replace(self, *args, **kwargs):
        self.replace_calls += 1
        return super().replace(*args, **kwargs)

    def snapshot(self, *args, **kwargs):
        result = super().snapshot(*args, **kwargs)
        self.snapshot_calls.append(result)
        return result


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
async def test_manual_unique_collision_advances_without_adopting_orphan_bytes(fixture):
    orphan = fixture.storage.create(
        "Notes/20260729-1542 Research.md",
        "# Manual note\n",
        operation_id="manual",
    )

    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )

    assert page.overlay.relative_path == "Notes/20260729-1542 Research-2.md"
    assert fixture.storage.read(orphan.relative_path) == orphan
    assert page.note["content"] != orphan.markdown


@pytest.mark.asyncio
async def test_racing_manual_unique_collision_reassigns_reserved_path(fixture):
    fixture.storage.inject_create_collision_once = True

    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )

    assert page.overlay.relative_path == "Notes/20260729-1542 Research-2.md"
    assert (
        fixture.storage.read("Notes/20260729-1542 Research.md").markdown
        == "# Raced manual note\n"
    )


@pytest.mark.asyncio
async def test_daily_collision_with_different_reserved_identity_fails_closed(fixture):
    foreign = OverlayNote(
        id="overlay_note:foreign",
        space_id="overlay_space:default",
        projected_note_id="note:foreign",
        stable_id="01JTESTOVERLAY000000FOREIGN",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        content_hash="0" * 64,
        revision=1,
        projection_state="pending",
        created_at=NOW,
        updated_at=NOW,
    )
    foreign_bytes = fixture.storage.create(
        foreign.relative_path,
        overlay_frontmatter(foreign, "# Foreign daily\n"),
        operation_id="foreign",
    )

    with pytest.raises(OverlayConflictError, match="overlay_identity_conflict"):
        await fixture.service().create_daily(CreateDailyNote(date_key="2026-07-29"))

    assert fixture.repository.commit_calls == 0
    assert fixture.storage.read(foreign.relative_path) == foreign_bytes


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


def _assert_revision_snapshot(
    fixture: Fixture,
    revision: dict,
) -> None:
    relative_snapshot = revision["relative_snapshot"]
    assert relative_snapshot.startswith("revisions/")
    payload = (fixture.layout.state_root / relative_snapshot).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == revision["content_hash"]
    assert len(payload) == revision["byte_size"]


@pytest.mark.asyncio
async def test_create_and_update_revisions_reference_exact_resulting_snapshots(fixture):
    created = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )

    assert len(fixture.repository.revisions) == 1
    create_revision = fixture.repository.revisions[0]
    assert create_revision["revision"] == 1
    assert create_revision["content_hash"] == created.overlay.content_hash
    _assert_revision_snapshot(fixture, create_revision)

    updated = await fixture.service().update(
        created.overlay.id,
        UpdateOverlayNote(
            title="Changed",
            markdown="# Changed\n",
            expected_revision=1,
            idempotency_key="save",
        ),
    )

    assert len(fixture.repository.revisions) == 2
    update_revision = fixture.repository.revisions[1]
    assert update_revision["revision"] == 2
    assert update_revision["content_hash"] == updated.overlay.content_hash
    _assert_revision_snapshot(fixture, update_revision)
    assert len(fixture.storage.snapshot_calls) == 3
    assert (
        fixture.storage.snapshot_calls[-2].content_hash == created.overlay.content_hash
    )
    assert (
        fixture.storage.snapshot_calls[-1].content_hash == updated.overlay.content_hash
    )


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
    assert receipt.after_hash is not None


@pytest.mark.asyncio
async def test_started_create_recovers_in_fresh_instance_after_both_db_calls_fail(
    fixture,
):
    fixture.repository.fail_commit_once = True
    fixture.repository.fail_record_failure = True
    request = CreateUniqueNote(title="Research", idempotency_key="one")

    with pytest.raises(OverlayRepositoryError, match="overlay_projection_pending"):
        await fixture.service().create_unique(request)

    reservation = fixture.repository.reservations[("create-unique", "one")]
    canonical = fixture.storage.read(reservation.relative_path)
    started = fixture.repository.receipts[reservation.operation_id]
    assert started.status == "started"
    assert started.after_hash == canonical.content_hash

    fresh_repository = MemoryRepository(fixture.repository)
    fresh_service = OverlayService(
        fresh_repository,
        fixture.storage,
        clock=fixture.clock,
    )
    recovered = await fresh_service.create_unique(request)

    assert recovered.overlay.content_hash == canonical.content_hash
    assert fixture.storage.create_calls == 2
    assert fixture.storage.replace_calls == 0
    assert len(fresh_repository.revisions) == 1
    _assert_revision_snapshot(fixture, fresh_repository.revisions[0])


@pytest.mark.asyncio
async def test_started_receipt_hash_mismatch_fails_closed(fixture):
    reservation = await fixture.repository.reserve_create(
        operation="create-unique",
        idempotency_key="one",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Research.md",
        title="Research",
    )
    note = await fixture.repository.get_note(reservation.overlay_note_id)
    canonical = fixture.storage.create(
        reservation.relative_path,
        overlay_frontmatter(note, "# Reserved note\n"),
        operation_id=reservation.operation_id,
    )
    receipt = fixture.repository.receipts[reservation.operation_id]
    fixture.repository.receipts[reservation.operation_id] = receipt.model_copy(
        update={"after_hash": "b" * 64}
    )

    with pytest.raises(OverlayConflictError, match="overlay_hash_conflict"):
        await fixture.service().create_unique(
            CreateUniqueNote(title="Research", idempotency_key="one")
        )

    assert fixture.storage.read(reservation.relative_path) == canonical
    assert fixture.repository.commit_calls == 0


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
async def test_started_update_recovers_in_fresh_instance_after_both_db_calls_fail(
    fixture,
):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    fixture.repository.fail_commit_once = True
    fixture.repository.fail_record_failure = True
    request = UpdateOverlayNote(
        title="Changed",
        markdown="# Changed\n",
        expected_revision=1,
        idempotency_key="save-started",
    )

    with pytest.raises(OverlayRepositoryError, match="overlay_projection_pending"):
        await fixture.service().update(page.overlay.id, request)

    reservation = fixture.repository.reservations[("update", "save-started")]
    canonical = fixture.storage.read(page.overlay.relative_path)
    started = fixture.repository.receipts[reservation.operation_id]
    assert started.status == "started"
    assert started.after_hash == canonical.content_hash

    fresh_repository = MemoryRepository(fixture.repository)
    recovered = await OverlayService(
        fresh_repository,
        fixture.storage,
        clock=fixture.clock,
    ).update(page.overlay.id, request)

    assert recovered.overlay.revision == 2
    assert recovered.overlay.content_hash == canonical.content_hash
    assert fixture.storage.replace_calls == 1
    assert len(fresh_repository.revisions) == 2
    _assert_revision_snapshot(fixture, fresh_repository.revisions[-1])


@pytest.mark.asyncio
async def test_started_update_rejects_changed_request_for_same_idempotency_key(
    fixture,
):
    page = await fixture.service().create_unique(
        CreateUniqueNote(title="Research", idempotency_key="one")
    )
    fixture.repository.fail_commit_once = True
    fixture.repository.fail_record_failure = True
    first_request = UpdateOverlayNote(
        title="Changed",
        markdown="# Changed\n",
        expected_revision=1,
        idempotency_key="save-started",
    )
    with pytest.raises(OverlayRepositoryError, match="overlay_projection_pending"):
        await fixture.service().update(page.overlay.id, first_request)
    canonical = fixture.storage.read(page.overlay.relative_path)

    fresh_repository = MemoryRepository(fixture.repository)
    changed_request = first_request.model_copy(
        update={"title": "Different", "markdown": "# Different\n"}
    )
    with pytest.raises(OverlayConflictError, match="overlay_hash_conflict"):
        await OverlayService(
            fresh_repository,
            fixture.storage,
            clock=fixture.clock,
        ).update(page.overlay.id, changed_request)

    assert fixture.storage.read(page.overlay.relative_path) == canonical
    assert fixture.storage.replace_calls == 1
    assert len(fresh_repository.revisions) == 1


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
