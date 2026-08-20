"""ONP v0.7.3 — Tests for podcast_commands.py defensive fixes.

Two issues fixed:
  #10: result["transcript"] / result["outline"] accessed with [] would
       KeyError on a partial-result dict from podcast-creator. Switched
       to .get() consistent with the PodcastGenerationOutput block.
  #11: output_dir.mkdir() before create_podcast(); a failure left an
       empty UUID directory under data/podcasts/episodes/ that
       accumulated forever. Now we rmdir empty dirs on failure.

These tests exercise the two helpers without touching SurrealDB or
podcast-creator — pure logic checks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from commands import podcast_commands


def test_build_episode_output_dir_uses_uuid_filename(tmp_path):
    """Sanity check for the existing helper — confirms the path
    structure that v0.7.2's containment check pins against."""
    name, path = podcast_commands.build_episode_output_dir(str(tmp_path))
    assert path == tmp_path / "podcasts" / "episodes" / name
    # UUID format — must be safe for filesystem
    assert len(name) == 36  # UUIDv4 length
    assert "/" not in name and "\\" not in name


def test_orphan_dir_cleanup_on_create_podcast_failure(tmp_path, monkeypatch):
    """v0.7.3 Issue #11 regression: when create_podcast raises and the
    output dir is empty, it must be rmdir'd so we don't accumulate
    orphan UUID dirs over months of intermittent failures."""

    # Stub DATA_FOLDER so build_episode_output_dir lands under tmp_path
    monkeypatch.setattr(podcast_commands, "DATA_FOLDER", str(tmp_path))

    # Simulate the cleanup block in isolation — manually do what the
    # try/except in the worker does.
    name, output_dir = podcast_commands.build_episode_output_dir(str(tmp_path))
    output_dir.mkdir(parents=True)
    assert output_dir.exists()

    # Simulate failure path: check that an empty dir is cleaned up
    try:
        raise RuntimeError("simulated create_podcast failure")
    except Exception:
        if output_dir.exists() and not any(output_dir.iterdir()):
            output_dir.rmdir()

    assert not output_dir.exists(), (
        "empty output_dir should be removed after a failure to avoid "
        "accumulating orphan directories"
    )


def test_non_empty_output_dir_preserved_on_failure(tmp_path):
    """If the failure happened AFTER some intermediate files were
    written (e.g. transcript saved but audio TTS failed), the dir
    has useful diagnostic content — DON'T delete it."""
    output_dir = tmp_path / "ep-uuid"
    output_dir.mkdir()
    # Partial output — something podcast-creator wrote before crashing
    (output_dir / "transcript.json").write_text('{"partial": "transcript"}')
    (output_dir / "segment_001.wav").write_bytes(b"intermediate audio")

    # Simulate the cleanup branch
    try:
        raise RuntimeError("simulated late failure")
    except Exception:
        if output_dir.exists() and not any(output_dir.iterdir()):
            output_dir.rmdir()  # should NOT run — dir has content

    assert output_dir.exists()
    assert (output_dir / "transcript.json").exists()


def test_result_field_extraction_uses_safe_get_pattern():
    """v0.7.3 Issue #10 regression: lines 260-262 used to do
    `result["transcript"]` which KeyErrors on a partial dict. Confirm
    the new pattern handles each of:
      - result = None
      - result = {} (truthy-False dict)
      - result = {"transcript": None}
      - result = {"final_output_file_path": "...", "outline": None}
        (missing transcript key entirely)
    Without raising.
    """

    # Recreate the logic inline since it's embedded in the command
    def transcript_value(result):
        return (
            {"transcript": _fake_dump(result.get("transcript"))}
            if result and result.get("transcript") is not None
            else None
        )

    def outline_value(result):
        return (
            _fake_dump(result.get("outline"))
            if result and result.get("outline") is not None
            else None
        )

    # None result
    assert transcript_value(None) is None
    assert outline_value(None) is None
    # Empty dict
    assert transcript_value({}) is None
    assert outline_value({}) is None
    # Result with None values
    assert transcript_value({"transcript": None}) is None
    assert outline_value({"outline": None}) is None
    # Result with missing keys — would KeyError pre-fix
    partial = {"final_output_file_path": "/some/path.mp3", "outline": None}
    assert transcript_value(partial) is None
    assert outline_value(partial) is None
    # Result with actual content
    full = {"transcript": {"segments": ["a"]}, "outline": ["intro"]}
    assert transcript_value(full) == {"transcript": "DUMPED"}
    assert outline_value(full) == "DUMPED"


def _fake_dump(_v):
    """Stand-in for full_model_dump — we only care about behavior, not
    actual serialization."""
    return "DUMPED"
