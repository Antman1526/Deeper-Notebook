from __future__ import annotations

from pathlib import Path

from api.routers.study_anki import (
    _persisted_card_kind,
    export_anki_package,
    inspect_export,
)

PLAN_EXPORT = {
    "plan_id": "study_plan:export",
    "state": "approved",
    "approved_syllabus_version": 3,
    "cards": [
        {
            "card_id": "study_card:basic",
            "front": "What is inertia?",
            "back": "Resistance to a change in motion.",
            "tags": ["mechanics"],
            "kind": "basic",
        },
        {
            "card_id": "study_card:reverse",
            "front": "Velocity",
            "back": "Speed with direction.",
            "tags": ["mechanics"],
            "kind": "reverse",
        },
        {
            "card_id": "study_card:cloze",
            "front": "Newton's {{c1::first law}}",
            "back": "An object remains at rest or in uniform motion unless acted on.",
            "tags": ["laws"],
            "kind": "cloze",
        },
    ],
}


def test_export_uses_stable_ids_and_round_trips_basic_reverse_and_cloze(
    tmp_path: Path,
) -> None:
    first = export_anki_package(PLAN_EXPORT, tmp_path / "first.apkg")
    second = export_anki_package(PLAN_EXPORT, tmp_path / "second.apkg")

    assert first.receipt.card_count == second.receipt.card_count == 4
    assert first.receipt.card_count == inspect_export(first.path).card_count
    assert inspect_export(first.path).stable_note_guids == inspect_export(second.path).stable_note_guids
    assert inspect_export(first.path).stable_model_ids == inspect_export(second.path).stable_model_ids
    assert inspect_export(first.path).stable_deck_ids == inspect_export(second.path).stable_deck_ids


def test_export_rejects_unapproved_or_unbound_plan(tmp_path: Path) -> None:
    invalid = {**PLAN_EXPORT, "state": "editing"}
    try:
        export_anki_package(invalid, tmp_path / "invalid.apkg")
    except ValueError as exc:
        assert "approved" in str(exc).lower()
    else:  # pragma: no cover - assertion gives a useful failure
        raise AssertionError("unapproved plan must not export")


def test_imported_kind_marker_round_trips_as_export_kind() -> None:
    assert _persisted_card_kind("anki_card:reverse:note-1") == "reverse"
    assert _persisted_card_kind("anki_card:cloze:note-2") == "cloze"
    assert _persisted_card_kind("anki_card:legacy-note") == "basic"
