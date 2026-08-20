"""v0.8.67j — `_fit_window_size` scales the main window to the screen.

The main window opened at a fixed 1280x800, which felt cramped on large
displays. `_fit_window_size` now sizes it to a fraction of the usable
screen while guaranteeing it never opens smaller than the previous
default. These tests pin that pure math (the AppKit screen read in
`_preferred_window_size` is environment-specific and not unit-tested).
"""

from __future__ import annotations

import pytest

from desktop.window import _fit_window_size


def test_large_screen_scales_to_fraction():
    # 90% of 1920x1080
    assert _fit_window_size(1920, 1080, 1280, 800) == (1728, 972)


def test_16in_macbook_visible_frame():
    # ~16" MBP usable frame; comfortably larger than the old 1280x800
    w, h = _fit_window_size(1728, 1050, 1280, 800)
    assert (w, h) == (1555, 945)


def test_floor_wins_on_small_screen():
    # 90% of a small screen would be < the floor → never shrink below it
    assert _fit_window_size(1000, 600, 1280, 800) == (1280, 800)


def test_unmeasurable_screen_uses_fixed_fallback():
    # screen_w/h <= 0 → generous fixed fallback (still respecting the floor)
    assert _fit_window_size(0, 0, 1280, 800) == (1600, 1000)
    assert _fit_window_size(-1, -1, 1280, 800) == (1600, 1000)


def test_fallback_respects_a_higher_floor():
    # If the caller's floor exceeds the fixed fallback, the floor wins.
    assert _fit_window_size(0, 0, 2000, 1200) == (2000, 1200)


@pytest.mark.parametrize(
    "sw,sh",
    [
        (1280, 800),
        (1440, 900),
        (1680, 1050),
        (1920, 1200),
        (2560, 1440),
        (3008, 1692),
        (5120, 2880),
    ],
)
def test_never_smaller_than_floor(sw, sh):
    w, h = _fit_window_size(sw, sh, 1280, 800)
    assert w >= 1280 and h >= 800


def test_custom_fraction():
    assert _fit_window_size(2000, 1000, 1280, 800, frac=0.5) == (1280, 800)
    assert _fit_window_size(4000, 3000, 1280, 800, frac=0.5) == (2000, 1500)
