"""Tests for desktop/window.py theme-token derivation.

These were missing — the v0.5 theme contrast fix shipped without a permanent
test asserting the token set is complete or that WCAG contrast holds. (P1-LOW-12)
"""
from __future__ import annotations

import pytest

from desktop.window import _THEMES, _theme_injection_js, _theme_tokens


@pytest.mark.parametrize("theme_id", list(_THEMES.keys()))
def test_every_theme_produces_27_shadcn_tokens(theme_id):
    """All 9 themes must produce the full shadcn token set so no upstream
    component falls back to default colors (the source of the v0.4
    unreadable-labels bug)."""
    tokens = _theme_tokens(theme_id)
    required = {
        "--background", "--foreground",
        "--card", "--card-foreground",
        "--popover", "--popover-foreground",
        "--primary", "--primary-foreground",
        "--secondary", "--secondary-foreground",
        "--muted", "--muted-foreground",
        "--accent", "--accent-foreground",
        "--destructive", "--destructive-foreground",
        "--border", "--input", "--ring",
        "--sidebar", "--sidebar-foreground",
        "--sidebar-primary", "--sidebar-primary-foreground",
        "--sidebar-accent", "--sidebar-accent-foreground",
        "--sidebar-border", "--sidebar-ring",
    }
    missing = required - set(tokens.keys())
    assert not missing, f"{theme_id} missing tokens: {missing}"


def _relative_luminance(hex_color: str) -> float:
    """Compute WCAG relative luminance. Helper for contrast assertions."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return 0.5  # skip on unexpected shape
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(fg: str, bg: str) -> float:
    lf, lb = sorted((_relative_luminance(fg), _relative_luminance(bg)))
    return (lb + 0.05) / (lf + 0.05)


@pytest.mark.parametrize("theme_id", list(_THEMES.keys()))
def test_muted_foreground_meets_wcag_aa_against_background(theme_id):
    """The v0.4 'unreadable labels in dark mode' bug was --muted-foreground at
    too-low contrast. Lock in WCAG AA (4.5:1) so a future palette tweak can't
    silently regress."""
    tokens = _theme_tokens(theme_id)
    ratio = _contrast_ratio(tokens["--muted-foreground"], tokens["--background"])
    assert ratio >= 4.5, (
        f"{theme_id}: muted_fg={tokens['--muted-foreground']} "
        f"bg={tokens['--background']} contrast={ratio:.2f}, expected >= 4.5"
    )


@pytest.mark.parametrize("theme_id", list(_THEMES.keys()))
def test_foreground_meets_wcag_aaa_against_background(theme_id):
    """Body-text contrast should clear AAA (7:1) — these are the most-read
    pixels in the app."""
    tokens = _theme_tokens(theme_id)
    ratio = _contrast_ratio(tokens["--foreground"], tokens["--background"])
    assert ratio >= 7.0, (
        f"{theme_id}: fg={tokens['--foreground']} "
        f"bg={tokens['--background']} contrast={ratio:.2f}, expected >= 7.0"
    )


def test_dark_themes_set_dark_class_in_injection_js():
    """The shadcn dark-mode token block is keyed by the `.dark` class on
    <html>. v0.5.7 — applyTheme() uses classList.toggle('dark', is_dark)
    so a single code path covers both light and dark transitions."""
    js = _theme_injection_js("dark")
    # All 9 themes are present in the IS_DARK map
    for theme_id in _THEMES:
        assert f'"{theme_id}":' in js
    # And applyTheme toggles the class
    assert "classList.toggle('dark'" in js or 'classList.toggle("dark"' in js


def test_injection_contains_all_nine_themes_as_attribute_selectors():
    """v0.5.7 — injection emits all 9 themes as :root[data-theme="X"]
    blocks so the ThemeSwitcher can swap live by changing dataset.theme."""
    js = _theme_injection_js("dracula")
    # Every theme id should appear as an attribute selector
    for theme_id in _THEMES:
        assert f'data-theme="{theme_id}"' in js, (
            f"injection missing :root[data-theme=\"{theme_id}\"] block"
        )


def test_injection_exposes_setTheme_bridge():
    """v0.5.7 — window.ONP.setTheme is what ThemeSwitcher calls. Must be
    present in the generated JS or the dropdown won't work."""
    js = _theme_injection_js("dark")
    assert "window.ONP" in js
    assert "ONP.setTheme" in js
    # And it should POST to /api/onp/theme to persist
    assert "/api/onp/theme" in js


def test_injection_sets_initial_theme_via_dataset():
    """v0.5.7 — the initial active theme is set via dataset.theme on <html>."""
    js = _theme_injection_js("nord")
    assert 'INITIAL_THEME = "nord"' in js
    assert "applyTheme" in js
