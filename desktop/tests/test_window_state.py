"""v0.8.67m — tests for persisted window size (clamp + load/save)."""

from __future__ import annotations

from desktop import window_state

# --- clamp --------------------------------------------------------------------


def test_clamp_applies_floor():
    assert window_state.clamp(800, 500, 0, 0, min_w=1280, min_h=800) == (1280, 800)


def test_clamp_caps_to_screen():
    # Saved on a big monitor (3000x2000), now on a 1440x900 screen.
    assert window_state.clamp(3000, 2000, 1440, 900, min_w=1280, min_h=800) == (
        1440,
        900,
    )


def test_clamp_keeps_value_in_range():
    assert window_state.clamp(1600, 1000, 1920, 1200, min_w=1280, min_h=800) == (
        1600,
        1000,
    )


def test_clamp_unknown_screen_only_floors():
    assert window_state.clamp(1600, 1000, 0, 0, min_w=1280, min_h=800) == (1600, 1000)


def test_clamp_bad_input_returns_floor():
    assert window_state.clamp("x", None, 1920, 1200, min_w=1280, min_h=800) == (
        1280,
        800,
    )


# --- load / save roundtrip ----------------------------------------------------


def test_save_then_load_roundtrips(tmp_path):
    window_state.save_size(tmp_path, 1700, 1050)
    assert window_state.load_size(tmp_path) == (1700, 1050)


def test_load_missing_returns_none(tmp_path):
    assert window_state.load_size(tmp_path) is None


def test_load_corrupt_returns_none(tmp_path):
    window_state.state_path(tmp_path).write_text("{not json")
    assert window_state.load_size(tmp_path) is None


def test_load_rejects_nonpositive(tmp_path):
    window_state.state_path(tmp_path).write_text('{"width": 0, "height": 800}')
    assert window_state.load_size(tmp_path) is None


def test_save_ignores_bad_input(tmp_path):
    window_state.save_size(tmp_path, None, "nope")
    assert window_state.load_size(tmp_path) is None
    window_state.save_size(tmp_path, -5, -5)
    assert window_state.load_size(tmp_path) is None
