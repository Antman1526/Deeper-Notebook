from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayLink,
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


def test_overlay_link_requires_explicit_nullable_overlay_identities():
    link = {
        "id": "note_link:one",
        "source_note_id": "note:source",
        "source_note_title": "Source",
        "target_note_id": "note:target",
        "target_note_title": "Target",
        "target_relative_path": "Notes/20260729-1542 Target.md",
        "target_text": "Target",
        "link_kind": "wikilink",
        "resolved": True,
        "source_start": 0,
        "source_end": 10,
        "source_overlay_note_id": "overlay_note:source",
        "target_overlay_note_id": "overlay_note:target",
        "schema_version": 1,
        "target_title_key": "target",
    }

    parsed = OverlayLink.model_validate(link)
    assert parsed.source_note_id == "note:source"
    assert parsed.target_note_id == "note:target"
    assert parsed.source_overlay_note_id == "overlay_note:source"
    assert parsed.target_overlay_note_id == "overlay_note:target"
    assert parsed.model_dump()["target_overlay_note_id"] == "overlay_note:target"
    assert "schema_version" not in parsed.model_dump()
    assert "target_title_key" not in parsed.model_dump()

    for missing_field in (
        "source_overlay_note_id",
        "target_overlay_note_id",
    ):
        with pytest.raises(ValidationError):
            OverlayLink.model_validate({
                key: value
                for key, value in link.items()
                if key != missing_field
            })

    external = OverlayLink.model_validate({
        **link,
        "target_overlay_note_id": None,
    })
    assert external.target_note_id == "note:target"
    assert external.target_overlay_note_id is None


def test_overlay_page_builds_a_deduplicated_overlay_only_local_graph():
    now = datetime.now(timezone.utc)
    overlay = OverlayNote(
        id="overlay_note:center",
        space_id="overlay_space:default",
        projected_note_id="note:center",
        stable_id="01JTESTOVERLAY000000CENTER",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Center.md",
        title="Center",
        content_hash="a" * 64,
        revision=1,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )
    outgoing = {
        "id": "note_link:outgoing",
        "source_note_id": "note:center",
        "source_note_title": "Center",
        "source_overlay_note_id": "overlay_note:center",
        "target_note_id": "note:target",
        "target_note_title": "Target",
        "target_overlay_note_id": "overlay_note:target",
        "target_relative_path": "Notes/20260729-1543 Target.md",
        "target_text": "Target",
        "link_kind": "wikilink",
        "resolved": True,
        "source_start": 0,
        "source_end": 10,
    }
    incoming = {
        **outgoing,
        "id": "note_link:incoming",
        "source_note_id": "note:source",
        "source_note_title": "Source",
        "source_overlay_note_id": "overlay_note:source",
        "target_note_id": "note:center",
        "target_note_title": "Center",
        "target_overlay_note_id": "overlay_note:center",
        "target_relative_path": "Notes/20260729-1542 Center.md",
    }
    page = OverlayPage(
        overlay=overlay,
        note={"id": "note:center", "title": "Center"},
        outgoing_links=[
            outgoing,
            {**outgoing, "id": "note_link:duplicate"},
            {
                **outgoing,
                "id": "note_link:external-target",
                "target_note_id": "note:external",
                "target_note_title": "External",
                "target_overlay_note_id": None,
            },
        ],
        backlinks=[
            incoming,
            {**incoming, "id": "note_link:duplicate-incoming"},
            {
                **incoming,
                "id": "note_link:external-source",
                "source_note_id": "note:external",
                "source_note_title": "External",
                "source_overlay_note_id": None,
            },
        ],
    )

    assert page.graph is not None
    assert {node["id"] for node in page.graph.nodes} == {
        "note:center",
        "note:source",
        "note:target",
    }
    assert {
        (edge["source"], edge["target"])
        for edge in page.graph.edges
    } == {
        ("note:center", "note:target"),
        ("note:source", "note:center"),
    }


def test_overlay_page_local_graph_is_bounded():
    now = datetime.now(timezone.utc)
    overlay = OverlayNote(
        id="overlay_note:center",
        space_id="overlay_space:default",
        projected_note_id="note:center",
        stable_id="01JTESTOVERLAY000000CENTER",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Center.md",
        title="Center",
        content_hash="a" * 64,
        revision=1,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )
    outgoing = [
        {
            "id": f"note_link:{index}",
            "source_note_id": "note:center",
            "source_overlay_note_id": "overlay_note:center",
            "target_note_id": f"note:target-{index}",
            "target_note_title": f"Target {index}",
            "target_overlay_note_id": f"overlay_note:target-{index}",
            "target_relative_path": (
                f"Notes/20260729-{1600 + index:04d} Target {index}.md"
            ),
            "target_text": f"Target {index}",
            "link_kind": "wikilink",
            "resolved": True,
            "source_start": index,
            "source_end": index + 1,
        }
        for index in range(200)
    ]

    page = OverlayPage(
        overlay=overlay,
        note={"id": "note:center", "title": "Center"},
        outgoing_links=outgoing,
    )

    assert page.graph is not None
    assert len(page.graph.nodes) <= 129
    assert len(page.graph.edges) <= 128


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
