from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayMutationReceipt,
    OverlayNote,
    OverlayPage,
    OverlayRevision,
    UpdateOverlayNote,
)


def test_daily_and_unique_requests_are_strict_and_bounded():
    daily = CreateDailyNote(date_key="2026-07-29")
    unique = CreateUniqueNote(
        title="Research Idea",
        idempotency_key="req-123",
    )
    assert daily.date_key == "2026-07-29"
    assert unique.title == "Research Idea"
    with pytest.raises(ValidationError):
        CreateDailyNote(date_key="07/29/2026")
    with pytest.raises(ValidationError):
        CreateDailyNote(date_key="2026-02-30")
    with pytest.raises(ValidationError):
        CreateUniqueNote(
            title="x" * 513,
            idempotency_key="req-123",
        )
    with pytest.raises(ValidationError):
        CreateUniqueNote(
            title="Research",
            idempotency_key="req-123",
            external_vault_id="vault_mount:forbidden",
        )


def test_overlay_note_forbids_paths_and_invalid_hashes():
    now = datetime.now(timezone.utc)
    note = OverlayNote(
        id="overlay_note:one",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-one",
        stable_id="01JTESTOVERLAY000000000001",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        content_hash="a" * 64,
        revision=1,
        projection_state="current",
        encoding="utf-8",
        newline="lf",
        created_at=now,
        updated_at=now,
    )
    assert note.source_authority == "overlay"
    with pytest.raises(ValidationError):
        OverlayNote.model_validate({
            **note.model_dump(),
            "relative_path": "/Users/owner/private.md",
        })
    with pytest.raises(ValidationError):
        OverlayNote.model_validate({
            **note.model_dump(),
            "content_hash": "not-a-hash",
        })
    with pytest.raises(ValidationError):
        OverlayNote.model_validate({
            **note.model_dump(),
            "date_key": "2026-02-30",
        })


def test_overlay_note_paths_match_their_persisted_kind_contract():
    now = datetime.now(timezone.utc)
    daily_data = {
        "id": "overlay_note:one",
        "space_id": "overlay_space:default",
        "projected_note_id": "note:overlay-one",
        "stable_id": "01JTESTOVERLAY000000000001",
        "kind": "daily",
        "date_key": "2026-07-29",
        "relative_path": "Daily/2026-07-29.md",
        "title": "2026-07-29",
        "content_hash": "a" * 64,
        "revision": 1,
        "projection_state": "current",
        "created_at": now,
        "updated_at": now,
    }
    daily = OverlayNote.model_validate(daily_data)
    unique = OverlayNote.model_validate({
        **daily_data,
        "kind": "unique",
        "date_key": None,
        "relative_path": "Notes/20260729-1542 Research Idea-2.md",
    })
    unique_third = OverlayNote.model_validate({
        **daily_data,
        "kind": "unique",
        "date_key": None,
        "relative_path": "Notes/20260729-1542 Research Idea-3.md",
    })
    assert daily.relative_path == "Daily/2026-07-29.md"
    assert unique.relative_path == "Notes/20260729-1542 Research Idea-2.md"
    assert unique_third.relative_path == "Notes/20260729-1542 Research Idea-3.md"
    for invalid in (
        {**daily_data, "relative_path": "Daily/2026-07-28.md"},
        {**daily_data, "relative_path": "Notes/20260729-1542 Research.md"},
        {
            **daily_data,
            "kind": "unique",
            "date_key": None,
            "relative_path": "Daily/20260729-1542 Research.md",
        },
        {
            **daily_data,
            "kind": "unique",
            "date_key": None,
            "relative_path": "Notes/Research.md",
        },
    ):
        with pytest.raises(ValidationError):
            OverlayNote.model_validate(invalid)


def test_update_requires_expected_revision_and_idempotency():
    update = UpdateOverlayNote(
        title=" Today ",
        markdown="# Today\n",
        expected_revision=3,
        idempotency_key="save-3",
    )
    assert update.expected_revision == 3
    assert update.title == "Today"
    with pytest.raises(ValidationError):
        UpdateOverlayNote(
            title="Today",
            markdown="# Today\n",
            expected_revision=0,
            idempotency_key="save-3",
        )
    with pytest.raises(ValidationError):
        UpdateOverlayNote(
            title="To\tday",
            markdown="# Today\n",
            expected_revision=3,
            idempotency_key="save-3",
        )


def test_overlay_page_rejects_a_note_from_another_projection():
    now = datetime.now(timezone.utc)
    overlay = OverlayNote(
        id="overlay_note:one",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-one",
        stable_id="01JTESTOVERLAY000000000001",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        content_hash="a" * 64,
        revision=1,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )
    page = OverlayPage(overlay=overlay, note={"id": "note:overlay-one"})
    assert page.note["id"] == overlay.projected_note_id
    with pytest.raises(ValidationError):
        OverlayPage(overlay=overlay, note={"id": "note:external"})


def test_receipt_has_no_content_or_absolute_path_fields():
    fields = set(OverlayMutationReceipt.model_fields)
    assert "markdown" not in fields
    assert "absolute_path" not in fields
    assert "root_path" not in fields


def test_revision_snapshot_must_be_canonical_and_relative():
    with pytest.raises(ValidationError):
        OverlayRevision(
            id="overlay_revision:one",
            overlay_note_id="overlay_note:one",
            revision=1,
            relative_snapshot="/Users/owner/private.md",
            content_hash="a" * 64,
            byte_size=1,
            created_at=datetime.now(timezone.utc),
        )
