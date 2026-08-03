import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from deeper_notebook.overlay.contracts import OverlayNote
from deeper_notebook.overlay.paths import (
    OverlayLayout,
    OverlayPathError,
    daily_relative_path,
    overlay_frontmatter,
    unique_relative_path,
    validate_relative_path,
)


def test_layout_stays_under_explicit_data_root(tmp_path: Path):
    layout = OverlayLayout.from_data_root(tmp_path)
    assert layout.canonical_root == tmp_path / "overlay" / "v1"
    assert layout.daily_root == layout.canonical_root / "Daily"
    assert layout.unique_root == layout.canonical_root / "Notes"
    assert layout.state_root == tmp_path / "overlay-state"
    assert layout.revisions_root == layout.state_root / "revisions"
    assert layout.receipts_root == layout.state_root / "receipts"
    assert layout.recovery_root == layout.state_root / "recovery"


def test_daily_path_is_canonical():
    assert daily_relative_path("2026-07-29") == "Daily/2026-07-29.md"
    with pytest.raises(OverlayPathError):
        daily_relative_path("../2026-07-29")
    with pytest.raises(OverlayPathError):
        daily_relative_path("2026-02-30")


def test_unique_path_uses_timestamp_title_and_suffixes():
    when = datetime(2026, 7, 29, 15, 42)
    occupied = {"Notes/20260729-1542 Research Idea.md"}
    path = unique_relative_path(
        when,
        " Research / Idea ",
        exists=occupied.__contains__,
    )
    assert path == "Notes/20260729-1542 Research Idea-2.md"


def test_unique_path_limits_unicode_filename_bytes_and_utf16_code_units():
    for title in ("🧠" * 200, "漢字" * 200):
        path = unique_relative_path(
            datetime(2026, 7, 29, 15, 42),
            title,
            exists=lambda _path: False,
        )
        filename = path.rsplit("/", 1)[-1]

        assert len(filename.encode("utf-8")) <= 240
        assert len(filename.encode("utf-16-le")) // 2 <= 240


def test_unique_path_limits_collision_suffix_unicode_filename_budgets():
    when = datetime(2026, 7, 29, 15, 42)
    for title in ("🧠" * 200, "漢字" * 200):
        initial = unique_relative_path(when, title, exists=lambda _path: False)
        path = unique_relative_path(when, title, exists={initial}.__contains__)
        filename = path.rsplit("/", 1)[-1]

        assert path.endswith("-2.md")
        assert len(filename.encode("utf-8")) <= 240
        assert len(filename.encode("utf-16-le")) // 2 <= 240


def test_unique_path_rejects_bounded_collision_exhaustion():
    when = datetime(2026, 7, 29, 15, 42)

    with pytest.raises(OverlayPathError, match="Overlay path is invalid") as error:
        unique_relative_path(when, "Research", exists=lambda _path: True)

    assert error.value.code == "unique_name_exhausted"


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/note.md",
        r"C:\note.md",
        r"Daily\one.md",
        "../one.md",
        "Daily/../one.md",
        "Daily//one.md",
        "Daily/\x00one.md",
        " Daily/one.md",
        "Daily /one.md",
        "Daily/ one.md",
    ],
)
def test_relative_path_rejects_absolute_escaping_and_noncanonical_values(value: str):
    with pytest.raises(OverlayPathError) as error:
        validate_relative_path(value)

    assert error.value.code == "invalid_relative_path"


def test_overlay_frontmatter_has_reserved_identity_and_leaves_body_unchanged():
    created_at = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 7, 29, 21, 30, 15, tzinfo=timezone.utc)
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
        created_at=created_at,
        updated_at=updated_at,
    )
    body = "# Today\n\n- preserve this body exactly\n"

    rendered = overlay_frontmatter(note, body)
    frontmatter, rendered_body = rendered.split("---\n", 2)[1:]

    assert rendered_body == body
    assert yaml.safe_load(frontmatter) == {
        "title": "2026-07-29",
        "deeper_notebook": {
            "id": "overlay_note:one",
            "kind": "daily",
            "created_at": "2026-07-29T20:00:00+00:00",
            "updated_at": "2026-07-29T21:30:15+00:00",
            "date_key": "2026-07-29",
        },
    }


def test_overlay_frontmatter_omits_template_id_when_note_has_none():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    note = OverlayNote(
        id="overlay_note:two",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-two",
        stable_id="01JTESTOVERLAY000000000002",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Research.md",
        title="Research",
        content_hash="b" * 64,
        revision=1,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )

    rendered = overlay_frontmatter(note, "content")
    frontmatter = rendered.split("---\n", 2)[1]

    assert "template_id" not in yaml.safe_load(frontmatter)["deeper_notebook"]


def test_overlay_frontmatter_safely_round_trips_title_deterministically():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    note = OverlayNote(
        id="overlay_note:three",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-three",
        stable_id="01JTESTOVERLAY000000000003",
        kind="unique",
        date_key=None,
        relative_path='Notes/20260729-1542 Research_ "α" #1 [draft].md',
        title='Research: "α" #1 [draft]',
        content_hash="c" * 64,
        revision=1,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )
    body = "---\n# Body stays byte-for-byte\n"

    first = overlay_frontmatter(note, body)
    second = overlay_frontmatter(note, body)
    frontmatter, rendered_body = first.split("---\n", 2)[1:]

    assert first == second
    assert yaml.safe_load(frontmatter)["title"] == note.title
    assert rendered_body == body


def test_same_body_with_different_title_changes_canonical_sha256():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    note = OverlayNote(
        id="overlay_note:four",
        space_id="overlay_space:default",
        projected_note_id="note:overlay-four",
        stable_id="01JTESTOVERLAY000000000004",
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Research.md",
        title="Research",
        content_hash="d" * 64,
        revision=1,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )
    body = "# Identical body\n"

    first = overlay_frontmatter(note, body).encode("utf-8")
    second = overlay_frontmatter(
        note.model_copy(update={"title": "Renamed"}),
        body,
    ).encode("utf-8")

    assert hashlib.sha256(first).hexdigest() != hashlib.sha256(second).hexdigest()
