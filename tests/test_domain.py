"""
Unit tests for the deeper_notebook.domain module.

This test suite focuses on validation logic, business rules, and data structures
that can be tested without database mocking.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from deeper_notebook.ai.models import ModelManager
from deeper_notebook.domain.base import RecordModel
from deeper_notebook.domain.content_settings import ContentSettings
from deeper_notebook.domain.notebook import Asset, Note, Notebook, Source
from deeper_notebook.domain.transformation import Transformation
from deeper_notebook.exceptions import InvalidInputError
from deeper_notebook.podcasts.models import EpisodeProfile, SpeakerProfile

# ============================================================================
# TEST SUITE 1: RecordModel Singleton Pattern
# ============================================================================


class TestRecordModelSingleton:
    """Test suite for RecordModel singleton behavior."""

    def test_recordmodel_singleton_behavior(self):
        """Test that same instance is returned for same record_id."""

        class TestRecord(RecordModel):
            record_id = "test:singleton"
            value: int = 0

        # Clear any existing instance
        TestRecord.clear_instance()

        # Create first instance
        instance1 = TestRecord(value=42)
        assert instance1.value == 42

        # Create second instance - should return same object
        instance2 = TestRecord(value=99)
        assert instance1 is instance2
        assert instance2.value == 99  # Value was updated

        # Cleanup
        TestRecord.clear_instance()


# ============================================================================
# TEST SUITE 2: ModelManager Instance Isolation
# ============================================================================


class TestModelManager:
    """Test suite for ModelManager instance behavior."""

    def test_model_manager_instance_isolation(self):
        """Test that each ModelManager instance is independent (not a singleton)."""
        manager1 = ModelManager()
        manager2 = ModelManager()

        # Each instance should be independent (not a singleton)
        assert manager1 is not manager2
        assert id(manager1) != id(manager2)


# ============================================================================
# TEST SUITE 3: Notebook Domain Logic
# ============================================================================


class TestNotebookDomain:
    """Test suite for Notebook validation and business rules."""

    def test_notebook_name_validation(self):
        """Test empty/whitespace names are rejected."""
        # Empty name should raise error
        with pytest.raises(InvalidInputError, match="Notebook name cannot be empty"):
            Notebook(name="", description="Test")

        # Whitespace-only name should raise error
        with pytest.raises(InvalidInputError, match="Notebook name cannot be empty"):
            Notebook(name="   ", description="Test")

        # Valid name should work
        notebook = Notebook(name="Valid Name", description="Test")
        assert notebook.name == "Valid Name"

    def test_notebook_archived_flag(self):
        """Test archived flag defaults to False."""
        notebook = Notebook(name="Test", description="Test")
        assert notebook.archived is False

        notebook_archived = Notebook(name="Test", description="Test", archived=True)
        assert notebook_archived.archived is True


# ============================================================================
# TEST SUITE 4: Source Domain
# ============================================================================


class TestSourceDomain:
    """Test suite for Source domain model."""

    def test_source_command_field_parsing(self):
        """Test RecordID parsing for command field."""
        # Test with string command
        source = Source(title="Test", command="command:123")
        assert source.command is not None

        # Test with None command
        source2 = Source(title="Test", command=None)
        assert source2.command is None

        # Test command is included in save data prep
        source3 = Source(id="source:123", title="Test", command="command:456")
        save_data = source3._prepare_save_data()
        assert "command" in save_data

    @pytest.mark.asyncio
    async def test_source_delete_cleans_up_file(self, monkeypatch):
        """Test that deleting a source removes the associated file.

        v0.6.34 — must use a file INSIDE UPLOADS_FOLDER (the new
        containment check refuses to unlink outside-uploads paths).
        Monkeypatches UPLOADS_FOLDER to tempdir so the test stays
        hermetic.
        """
        # Create a "uploads" dir + a file inside it
        uploads_dir = Path(tempfile.mkdtemp()).resolve()
        monkeypatch.setattr(
            "deeper_notebook.config.UPLOADS_FOLDER",
            str(uploads_dir),
        )
        tmp_path = uploads_dir / "test.txt"
        tmp_path.write_bytes(b"Test content")

        try:
            # Create source with file asset
            source = Source(
                id="source:test_delete",
                title="Test Source",
                asset=Asset(file_path=str(tmp_path)),
            )

            # Verify file exists
            assert tmp_path.exists()

            # Mock the parent delete method to avoid database operations
            with patch.object(
                Source.__bases__[0], "delete", new_callable=AsyncMock
            ) as mock_delete:
                mock_delete.return_value = True

                # Delete the source
                result = await source.delete()

                # Verify parent delete was called
                mock_delete.assert_called_once()
                assert result is True

            # Verify file was deleted
            assert not tmp_path.exists()

        finally:
            # Cleanup in case test fails
            if tmp_path.exists():
                tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_source_delete_without_file(self):
        """Test that deleting a source without a file doesn't fail."""
        # Create source without file asset
        source = Source(id="source:test_no_file", title="Test Source", asset=None)

        # Mock the parent delete method
        with patch.object(
            Source.__bases__[0], "delete", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = True

            # Delete should complete without error
            result = await source.delete()
            assert result is True
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_source_delete_continues_on_file_error(self):
        """Test that source deletion continues even if file deletion fails."""
        # Create source with non-existent file
        source = Source(
            id="source:test_missing_file",
            title="Test Source",
            asset=Asset(file_path="/nonexistent/path/file.txt"),
        )

        # Mock the parent delete method
        with patch.object(
            Source.__bases__[0], "delete", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = True

            # Delete should complete even though file doesn't exist
            result = await source.delete()
            assert result is True
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_vectorize_raises_valueerror_when_no_text(self):
        """Test that vectorize() raises ValueError (not DatabaseOperationError) for empty text."""
        source = Source(id="source:test_empty", title="Test", full_text=None)
        with pytest.raises(ValueError, match="has no text to vectorize"):
            await source.vectorize()

    @pytest.mark.asyncio
    async def test_vectorize_raises_valueerror_when_empty_string(self):
        """Test that vectorize() raises ValueError for empty string."""
        source = Source(id="source:test_empty_str", title="Test", full_text="")
        with pytest.raises(ValueError, match="has no text to vectorize"):
            await source.vectorize()

    @pytest.mark.asyncio
    async def test_vectorize_raises_valueerror_when_whitespace_only(self):
        """Test that vectorize() raises ValueError for whitespace-only text."""
        source = Source(id="source:test_ws", title="Test", full_text="   \n\t  ")
        with pytest.raises(ValueError, match="has no text to vectorize"):
            await source.vectorize()

    @pytest.mark.asyncio
    async def test_vectorize_submits_command_with_valid_text(self):
        """Test that vectorize() submits embed_source command when text is valid."""
        source = Source(id="source:test_valid", title="Test", full_text="Real content")
        with patch(
            "deeper_notebook.domain.notebook.submit_command", return_value="command:123"
        ) as mock_submit:
            result = await source.vectorize()
            mock_submit.assert_called_once_with(
                "open_notebook",
                "embed_source",
                {"source_id": "source:test_valid"},
            )
            assert result == "command:123"


# ============================================================================
# TEST SUITE 5: Note Domain
# ============================================================================


class TestNoteDomain:
    """Test suite for Note validation."""

    def test_note_content_validation(self):
        """Test empty content is rejected."""
        # None content is allowed
        note = Note(title="Test", content=None)
        assert note.content is None

        # Non-empty content is valid
        note2 = Note(title="Test", content="Valid content")
        assert note2.content == "Valid content"

        # Empty string should raise error
        with pytest.raises(InvalidInputError, match="Note content cannot be empty"):
            Note(title="Test", content="")

        # Whitespace-only should raise error
        with pytest.raises(InvalidInputError, match="Note content cannot be empty"):
            Note(title="Test", content="   ")

    def test_note_content_for_embedding(self):
        """Test notes can hold content for embedding.

        Note: Embedding is now handled via command submission in Note.save(),
        not via needs_embedding() method. This test verifies basic content handling.
        """
        note = Note(title="Test", content="Test content")
        assert note.content == "Test content"

        # Test with None content - valid, no embedding will be submitted
        note2 = Note(title="Test", content=None)
        assert note2.content is None


# ============================================================================
# TEST SUITE 6: Podcast Domain Validation
# ============================================================================


class TestPodcastDomain:
    """Test suite for Podcast domain validation."""

    def test_speaker_profile_validation(self):
        """Test speaker profile validates count and required fields."""
        # Test invalid - no speakers
        with pytest.raises(ValidationError):
            SpeakerProfile(
                name="Test",
                tts_provider="openai",
                tts_model="tts-1",
                speakers=[],
            )

        # Test invalid - too many speakers (> 4)
        with pytest.raises(ValidationError):
            SpeakerProfile(
                name="Test",
                tts_provider="openai",
                tts_model="tts-1",
                speakers=[{"name": f"Speaker{i}"} for i in range(5)],
            )

        # Test invalid - missing required fields
        with pytest.raises(ValidationError):
            SpeakerProfile(
                name="Test",
                tts_provider="openai",
                tts_model="tts-1",
                speakers=[
                    {"name": "Speaker 1"}
                ],  # Missing voice_id, backstory, personality
            )

        # Test valid - single speaker with all fields
        profile = SpeakerProfile(
            name="Test",
            tts_provider="openai",
            tts_model="tts-1",
            speakers=[
                {
                    "name": "Host",
                    "voice_id": "voice123",
                    "backstory": "A friendly host",
                    "personality": "Enthusiastic and welcoming",
                }
            ],
        )
        assert len(profile.speakers) == 1
        assert profile.speakers[0]["name"] == "Host"


# ============================================================================
# TEST SUITE 7: Transformation Domain
# ============================================================================


class TestTransformationDomain:
    """Test suite for Transformation domain model."""

    def test_transformation_creation(self):
        """Test transformation model creation."""
        transform = Transformation(
            name="summarize",
            title="Summarize Content",
            description="Creates a summary",
            prompt="Summarize the following text: {content}",
            apply_default=True,
        )

        assert transform.name == "summarize"
        assert transform.apply_default is True


# ============================================================================
# TEST SUITE 8: Content Settings
# ============================================================================


class TestContentSettings:
    """Test suite for ContentSettings defaults."""

    def test_content_settings_defaults(self):
        """Test ContentSettings has proper defaults."""
        settings = ContentSettings()

        assert settings.record_id == "open_notebook:content_settings"
        assert settings.default_content_processing_engine_doc == "auto"
        assert settings.default_embedding_option == "ask"
        assert settings.auto_delete_files == "yes"
        assert len(settings.youtube_preferred_languages) > 0


# ============================================================================
# TEST SUITE 9: Episode Profile Validation
# ============================================================================


class TestEpisodeProfile:
    """Test suite for EpisodeProfile validation."""

    def test_episode_profile_segment_validation(self):
        """Test segment count validation (3-20)."""
        # Test invalid - too few segments
        with pytest.raises(
            ValidationError, match="Number of segments must be between 3 and 20"
        ):
            EpisodeProfile(
                name="Test",
                speaker_config="default",
                outline_provider="openai",
                outline_model="gpt-4",
                transcript_provider="openai",
                transcript_model="gpt-4",
                default_briefing="Test briefing",
                num_segments=2,
            )

        # Test invalid - too many segments
        with pytest.raises(
            ValidationError, match="Number of segments must be between 3 and 20"
        ):
            EpisodeProfile(
                name="Test",
                speaker_config="default",
                outline_provider="openai",
                outline_model="gpt-4",
                transcript_provider="openai",
                transcript_model="gpt-4",
                default_briefing="Test briefing",
                num_segments=21,
            )

        # Test valid segment count
        profile = EpisodeProfile(
            name="Test",
            speaker_config="default",
            outline_provider="openai",
            outline_model="gpt-4",
            transcript_provider="openai",
            transcript_model="gpt-4",
            default_briefing="Test briefing",
            num_segments=5,
        )
        assert profile.num_segments == 5


# ============================================================================
# TEST SUITE: Note.save() resilience to surreal-commands registry misses
# (v0.7.129 regression — found by the SurrealDB integration suite)
# ============================================================================


class TestNoteSaveResilience:
    """v0.7.129 — Note.save() previously raised
    `ValueError: Command not found: deeper_notebook.embed_note` whenever
    the surreal-commands worker hadn't registered the embed_note
    command (CI without a worker, fresh installs, restart windows).
    Embedding is fire-and-forget by design, so a missing worker
    must not fail the save itself.

    v0.7.133 — Updated to reflect the registry-introspection refactor.
    The behaviors these tests pin (save-survives-no-worker,
    save-survives-generic-failures, save-propagates-real-ValueErrors)
    are unchanged; only the implementation path is cleaner. Each test
    now patches `_is_command_registered` to control whether the
    pre-check skips or proceeds to submit_command.
    """

    @pytest.mark.asyncio
    async def test_save_survives_command_not_found(self):
        """When the registry doesn't have embed_note (worker not
        running), `_is_command_registered` returns False and we skip
        submit entirely. The note row is durable."""
        note = Note(title="N", content="some content", note_type="human")

        async def _fake_super_save(self):  # noqa: ARG001
            self.id = "note:fake123"

        with (
            patch("deeper_notebook.domain.notebook.ObjectModel.save", _fake_super_save),
            patch(
                "deeper_notebook.domain.notebook._is_command_registered",
                return_value=False,
            ),
            patch("deeper_notebook.domain.notebook.submit_command") as submit_mock,
        ):
            result = await note.save()
            assert result is None
            assert note.id == "note:fake123"
            # The whole point of the pre-check: submit_command never
            # got called, so no roundtrip and no exception to swallow.
            submit_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_survives_generic_submission_exception(self):
        """When the registry HAS embed_note but submit_command itself
        raises a non-ValueError (worker DB down, network blip), the
        save must still complete and return None."""
        note = Note(title="N", content="some content", note_type="human")

        async def _fake_super_save(self):  # noqa: ARG001
            self.id = "note:fake456"

        def _raise_runtime(*args, **kwargs):
            raise RuntimeError("worker DB unreachable")

        with (
            patch("deeper_notebook.domain.notebook.ObjectModel.save", _fake_super_save),
            patch(
                "deeper_notebook.domain.notebook._is_command_registered",
                return_value=True,
            ),
            patch("deeper_notebook.domain.notebook.submit_command", _raise_runtime),
        ):
            result = await note.save()
            assert result is None

    @pytest.mark.asyncio
    async def test_save_propagates_unrelated_value_errors(self):
        """v0.7.133 — Real ValueErrors (e.g. bad argument validation
        inside surreal_commands itself, future library changes) MUST
        propagate so they don't get silently masked. The pre-check
        already filtered the registry-miss case, so a ValueError at
        submit time is a real bug — surface it.

        Python except-clause matching: once the `except ValueError`
        branch matches and `raise`s, the exception leaves the try
        block. The broader `except Exception` below it does NOT get
        a second chance.
        """
        note = Note(title="N", content="some content", note_type="human")

        async def _fake_super_save(self):  # noqa: ARG001
            self.id = "note:fake789"

        def _raise_bad_args(*args, **kwargs):
            raise ValueError("Invalid note_id format")

        with (
            patch("deeper_notebook.domain.notebook.ObjectModel.save", _fake_super_save),
            patch(
                "deeper_notebook.domain.notebook._is_command_registered",
                return_value=True,
            ),
            patch("deeper_notebook.domain.notebook.submit_command", _raise_bad_args),
        ):
            with pytest.raises(ValueError, match="Invalid note_id format"):
                await note.save()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
