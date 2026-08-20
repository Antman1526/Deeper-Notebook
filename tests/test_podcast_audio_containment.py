"""ONP v0.7.2 — Regression tests for podcast audio path-traversal hardening.

`_resolve_audio_path` is invoked by 5 sites in api/routers/podcasts.py:
  - list_podcast_episodes (audio_url visibility)
  - get_podcast_episode (audio_url visibility)
  - stream_podcast_episode_audio (FileResponse — file-exfil if unchecked)
  - retry_podcast_episode (audio_path.unlink — arbitrary file delete)
  - delete_podcast_episode (audio_path.unlink — arbitrary file delete)

Before v0.7.2 it returned `Path(audio_file)` with no containment check.
A tampered episode.audio_file pointing to e.g. /etc/passwd would have
turned those into arbitrary-file-read + arbitrary-file-delete vectors.

These tests verify the new `is_relative_to(_AUDIO_ROOT)` containment
gate at the helper layer. The callsite-level fix (None-handling) is
covered implicitly by the existing API tests.
"""

from __future__ import annotations

import nturl2path
from pathlib import Path

import pytest

import deeper_notebook.podcasts as podcast_paths
from api.routers import podcasts as podcasts_mod


@pytest.fixture
def patched_root(monkeypatch, tmp_path):
    """Pin _AUDIO_ROOT to a tmp dir so we can construct paths inside +
    outside it. Sets up an episodes/ subdir to match production layout."""
    root = tmp_path / "podcasts" / "episodes"
    root.mkdir(parents=True)
    monkeypatch.setattr(podcasts_mod, "_AUDIO_ROOT", root.resolve())
    return root


def test_resolve_audio_path_accepts_file_inside_root(patched_root):
    """Happy path — a legitimate path under _AUDIO_ROOT resolves OK."""
    ep_dir = patched_root / "abc-uuid"
    ep_dir.mkdir()
    audio = ep_dir / "episode.mp3"
    audio.write_bytes(b"id3v2")

    result = podcasts_mod._resolve_audio_path(str(audio))
    assert result is not None
    assert result.resolve() == audio.resolve()


def test_resolve_audio_path_accepts_file_uri_inside_root(patched_root):
    """file:// URLs are also accepted as long as they resolve under root."""
    ep_dir = patched_root / "abc-uuid"
    ep_dir.mkdir()
    audio = ep_dir / "episode.mp3"
    audio.write_bytes(b"id3v2")

    result = podcasts_mod._resolve_audio_path(audio.resolve().as_uri())
    assert result is not None
    assert result.resolve() == audio.resolve()


def test_file_uri_to_local_path_converts_windows_drive_uri():
    """A standard Windows file URI must become a native drive path first."""
    convert = getattr(podcast_paths, "file_uri_to_local_path", None)
    assert convert is not None, "podcast paths must expose file URI conversion"
    assert (
        convert(
            "file:///C:/Podcast%20Audio/episode.mp3",
            pathname_converter=nturl2path.url2pathname,
        )
        == r"C:\Podcast Audio\episode.mp3"
    )


def test_resolve_audio_path_rejects_outside_root(patched_root, tmp_path):
    """The actual v0.7.2 regression. A tampered DB record pointing
    outside the audio root must return None, NOT a Path that downstream
    callers would try to serve or unlink."""
    # Victim file: a sibling of the audio root (DB tamper would target
    # something useful like /etc/passwd; we simulate with tmp_path).
    victim = tmp_path / "victim.txt"
    victim.write_text("private")

    result = podcasts_mod._resolve_audio_path(str(victim))
    assert result is None, (
        f"_resolve_audio_path should refuse {victim}, returned {result}"
    )


def test_resolve_audio_path_rejects_dotdot_traversal(patched_root, tmp_path):
    """A path with `..` segments must still be caught — resolve()
    canonicalizes; is_relative_to does the structural check."""
    victim = tmp_path / "secret.key"
    victim.write_text("api-key")
    # Craft a path that LOOKS inside the audio root but escapes via ..
    tampered = str(patched_root / "ep-uuid" / ".." / ".." / ".." / "secret.key")
    # Sanity: this DOES resolve to victim.
    assert Path(tampered).resolve() == victim.resolve()

    result = podcasts_mod._resolve_audio_path(tampered)
    assert result is None


def test_resolve_audio_path_rejects_sibling_prefix(patched_root, tmp_path):
    """Defense against the str.startswith bug we fixed in v0.6.31 — a
    path like `.../episodes_evil/x.mp3` would have passed a naive
    string-prefix check but is correctly rejected by is_relative_to."""
    # _AUDIO_ROOT is `.../podcasts/episodes`; the trap path is
    # `.../podcasts/episodes_evil/x.mp3`. Both have `.../podcasts/episodes`
    # as a STRING prefix but only the first is structurally under root.
    evil_dir = patched_root.parent / "episodes_evil"
    evil_dir.mkdir()
    evil_file = evil_dir / "x.mp3"
    evil_file.write_bytes(b"id3")

    result = podcasts_mod._resolve_audio_path(str(evil_file))
    assert result is None, (
        "is_relative_to should reject sibling-prefix paths even though "
        "they share a string prefix with _AUDIO_ROOT"
    )


def test_resolve_audio_path_handles_invalid_input_safely(patched_root):
    """Malformed input (e.g. unresolvable path) returns None rather
    than raising. Critical because callers expect Optional[Path] and
    don't wrap in try/except."""
    # A path that os.realpath can't resolve due to permission/structure
    # issues should return None gracefully. Test with a clearly invalid
    # path containing null bytes — Path(...).resolve() may raise ValueError.
    result = podcasts_mod._resolve_audio_path("\x00\x00\x00")
    assert result is None
