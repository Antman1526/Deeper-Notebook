"""v0.8.130 — text-on-fill contrast of the tokens the packaged app injects.

The injected `:root[data-theme="X"]` block outranks frontend globals.css, so a
pair fixed only in globals.css would not reach the desktop window. This checks
the same 4.5:1 rule as frontend/src/app/theme-contrast.contract.test.ts for the
pairs _theme_tokens() emits, and that it leaves the accent pairs to globals.css
(where that test measures them in every theme).
"""

from __future__ import annotations

import pytest

from desktop.window import _THEMES, _theme_tokens

# Same format and contents as KNOWN_EXCEPTIONS in the frontend test:
# (theme_id, fill token, measured ratio). Currently none.
KNOWN_EXCEPTIONS: set[tuple[str, str, float]] = set()

INJECTED_PAIRS = (
    ("--primary", "--primary-foreground"),
    ("--sidebar-primary", "--sidebar-primary-foreground"),
)
LEFT_TO_GLOBALS_CSS = {"--accent", "--accent-foreground", "--brand-accent", "--brand-accent-foreground"}


def _luminance(hex_color: str) -> float:
    assert len(hex_color) == 7 and hex_color.startswith("#"), f"not a #RRGGBB colour: {hex_color!r}"
    channels = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    low, high = sorted((_luminance(a), _luminance(b)))
    return (high + 0.05) / (low + 0.05)


def _check(theme_id: str, fill_name: str, fill: str, fg: str) -> None:
    ratio = _contrast(fill, fg)
    exception = next((e for e in KNOWN_EXCEPTIONS if e[:2] == (theme_id, fill_name)), None)
    if exception:
        assert ratio == pytest.approx(exception[2], abs=0.05)
        return
    assert ratio >= 4.5, f"{theme_id}: {fg} on {fill_name}={fill} is {ratio:.2f}:1, expected >= 4.5"


@pytest.mark.parametrize("theme_id", list(_THEMES))
@pytest.mark.parametrize(("fill", "fg"), INJECTED_PAIRS)
def test_injected_text_on_fill_pairs_meet_wcag_aa(theme_id, fill, fg):
    tokens = _theme_tokens(theme_id)
    _check(theme_id, fill, tokens[fill], tokens[fg])


@pytest.mark.parametrize("theme_id", list(_THEMES))
def test_accent_pairs_are_left_to_globals_css(theme_id):
    injected = LEFT_TO_GLOBALS_CSS & set(_theme_tokens(theme_id))
    assert not injected, f"{theme_id} injects {sorted(injected)}; globals.css owns and measures them"


@pytest.mark.parametrize("theme_id", list(_THEMES))
def test_table_accent_pair_stays_readable(theme_id):
    # The table's accent/accent_fg are not injected today; keep them passing so
    # re-enabling them cannot quietly ship an unreadable pair.
    palette = _THEMES[theme_id]
    _check(theme_id, "accent", palette["accent"], palette["accent_fg"])
