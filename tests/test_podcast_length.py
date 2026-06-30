"""v0.8.86 — tests for per-episode podcast length → segment-count mapping."""

from commands.podcast_staged import segments_for_length


def test_segments_for_length_presets():
    assert segments_for_length("short") == 3
    assert segments_for_length("medium") == 5
    assert segments_for_length("long") == 8


def test_segments_for_length_normalizes_input():
    assert segments_for_length(" Long ") == 8
    assert segments_for_length("MEDIUM") == 5


def test_segments_for_length_none_or_unknown_returns_none():
    # None → caller falls back to the profile's num_segments.
    assert segments_for_length(None) is None
    assert segments_for_length("") is None
    assert segments_for_length("epic") is None
