from pathlib import Path

from deeper_notebook.podcasts.models import PodcastEpisode


def test_phase_two_episode_metadata_is_optional_and_redacted_by_contract():
    episode = PodcastEpisode(
        name="Legacy compatible",
        episode_profile={},
        speaker_profile={},
        briefing="Grounded",
        content="Existing episode content",
    )

    assert episode.selection_summary is None
    assert episode.selection_fingerprint is None
    assert episode.editorial_brief is None
    assert episode.model_plan_receipts == []
    assert episode.retry_submitted is None


def test_phase_two_migration_only_adds_and_removes_studio_metadata_fields():
    migration_root = Path("deeper_notebook/database/migrations")
    up = (migration_root / "40.surrealql").read_text(encoding="utf-8")
    down = (migration_root / "40_down.surrealql").read_text(encoding="utf-8")

    for field in (
        "selection_summary",
        "selection_fingerprint",
        "editorial_brief",
        "model_plan_receipts",
        "retry_submitted",
    ):
        assert f"DEFINE FIELD IF NOT EXISTS {field} ON TABLE episode" in up
        assert f"REMOVE FIELD IF EXISTS {field} ON TABLE episode" in down
    assert "content" not in up
    assert "audio_file" not in down
