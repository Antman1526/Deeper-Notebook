"""v0.8.97 — migration 47 ships the Cornell Notes default transformation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/47.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/47_down.surrealql"


def test_migration_47_exists_with_down() -> None:
    assert UP.exists()
    assert DOWN.exists()


def test_cornell_transformation_row_shape() -> None:
    text = UP.read_text(encoding="utf-8")
    assert "insert into transformation" in text
    # Every field the transformation table defines as required.
    for field in (
        'name: "Cornell Notes"',
        'title: "Cornell Notes"',
        "description:",
        "prompt:",
        "apply_default: False",
    ):
        assert field in text, f"migration 47 missing {field}"


def test_cornell_prompt_carries_the_method_not_just_the_name() -> None:
    """The prompt must actually implement the Cornell method — cue column,
    notes column, summary — not merely name-drop it."""
    text = UP.read_text(encoding="utf-8")
    for marker in ("CUE", "NOTES", "SUMMARY", "## Cues and Notes", "## Summary"):
        assert marker in text, f"Cornell prompt missing {marker}"
    # Grounding rule: transformations must not invent content.
    assert "Do not add outside knowledge" in text


def test_down_migration_deletes_only_the_cornell_row() -> None:
    text = DOWN.read_text(encoding="utf-8")
    assert 'name = "Cornell Notes"' in text
    assert 'title = "Cornell Notes"' in text
    # Guard against a broad DELETE that would nuke user transformations.
    assert "DELETE transformation WHERE" in text
