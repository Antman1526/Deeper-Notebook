"""v0.8.68 — episode table schema parity guard.

The `episode` table is SCHEMAFULL (migration 7), so SurrealDB silently
DROPS any saved field that lacks a DEFINE FIELD. The staged-generation
work added briefing_suffix / generation_stage / cancel_requested to the
PodcastEpisode model without a migration: saves looked successful while
the values vanished, leaving stage tracking, the Cancel button, and
retry-with-instructions dead against a real database. Unit tests mock
the DB, so only the live smoke test caught it.

This test statically pins every PodcastEpisode model field to a
DEFINE FIELD across the migration files, so the next model field added
without a migration fails CI with a pointed message.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_MIG_DIR = _REPO / "deeper_notebook" / "database" / "migrations"

# Maintained by ObjectModel/repository code, not by DEFINE FIELD parity.
_BASE_FIELDS = {"id", "created", "updated"}

_DEFINE_RE = re.compile(
    r"DEFINE\s+FIELD\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON(?:\s+TABLE)?\s+episode\b",
    re.IGNORECASE,
)


def _defined_episode_fields() -> set[str]:
    fields: set[str] = set()
    for path in _MIG_DIR.glob("*.surrealql"):
        if path.stem.endswith("_down"):
            continue
        fields.update(m.group(1) for m in _DEFINE_RE.finditer(path.read_text()))
    return fields


def test_every_episode_model_field_has_a_migration_define_field():
    from deeper_notebook.podcasts.models import PodcastEpisode

    model_fields = set(PodcastEpisode.model_fields) - _BASE_FIELDS
    defined = _defined_episode_fields()
    missing = sorted(model_fields - defined)
    assert not missing, (
        f"PodcastEpisode fields {missing} have no DEFINE FIELD on the "
        f"SCHEMAFULL `episode` table — SurrealDB will silently drop them "
        f"on save. Add a migration (see 22.surrealql for the pattern)."
    )


def test_v0_8_68_staged_fields_are_defined():
    defined = _defined_episode_fields()
    for field in ("briefing_suffix", "generation_stage", "cancel_requested"):
        assert field in defined, f"migration for episode.{field} missing"


def test_down_migration_removes_what_up_defines():
    up = (_MIG_DIR / "22.surrealql").read_text()
    down = (_MIG_DIR / "22_down.surrealql").read_text()
    up_fields = set(_DEFINE_RE.findall(up))
    down_fields = set(
        re.findall(
            r"REMOVE\s+FIELD\s+IF\s+EXISTS\s+(\w+)\s+ON\s+TABLE\s+episode",
            down,
            re.IGNORECASE,
        )
    )
    assert up_fields == down_fields


def test_generation_stage_none_survives_prepare_save_data():
    """ObjectModel._prepare_save_data drops None fields unless declared
    nullable — without this, clearing the stage on completion is a no-op
    and finished episodes stay stuck on 'combining_audio'."""
    from deeper_notebook.podcasts.models import PodcastEpisode

    episode = PodcastEpisode(
        name="t",
        episode_profile={},
        speaker_profile={},
        briefing="b",
        content="c",
        generation_stage=None,
    )
    assert "generation_stage" in episode._prepare_save_data()
