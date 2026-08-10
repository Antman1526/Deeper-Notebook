"""v0.7.186 — Frontend HIGH-severity audit fixes.

Two bugs that would degrade the everyday UX of the desktop app:

1.  Sources page hijacked ALL keyboard navigation globally.
    `src/app/(dashboard)/sources/page.tsx`'s window-level
    `keydown` listener called `e.preventDefault()` on
    ArrowDown/Up/Home/End/Enter regardless of `e.target`. With
    any input focused (the app search bar, a dialog input, the
    command palette, any text field anywhere) arrow-key caret
    movement was BROKEN as long as Sources was the active route.
    Fixed by adding the standard input-focus guard the
    CommandPalette already uses.

2.  EpisodeCard leaked object-URLs + setState-after-unmount.
    `src/components/podcasts/EpisodeCard.tsx`'s audio-fetch
    useEffect had three subtle bugs:
      (a) `revokeUrl` closure was undefined when cleanup ran on
          fast unmount (the URL is created LATER in the async path)
          — every quick unmount leaked a blob URL.
      (b) setAudioSrc/setAudioError ran after unmount → React
          warnings + memory pinning.
      (c) No AbortController on the fetch — slow first fetch
          could resolve AFTER a fast second fetch and stomp the
          correct `audioSrc` with the stale blob (user clicking
          between episodes).
    Rewritten with: `cancelled` flag + `currentObjectUrl` set
    BEFORE the setState (so cleanup always sees it) + an
    AbortController wired to the fetch's `signal`.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Sources page keyboard guard
# ---------------------------------------------------------------------------


def test_sources_page_keyboard_handler_skips_inputs():
    """v0.7.186: the global keydown listener on the Sources page
    MUST early-return when the event target is an input element.
    Otherwise it hijacks arrow keys / Enter / Home / End from
    every input on every dialog/modal that overlays the page."""
    src = _read_source("frontend/src/app/(dashboard)/sources/page.tsx")
    # The guard pattern is present.
    assert "target.isContentEditable" in src, (
        "v0.7.186 regression: Sources keydown handler no longer "
        "checks isContentEditable. Caret movement in contenteditable "
        "elements is broken whenever Sources is the active route."
    )
    assert "['INPUT', 'TEXTAREA', 'SELECT']" in src, (
        "v0.7.186 regression: Sources keydown handler no longer "
        "guards against INPUT/TEXTAREA/SELECT focus. Typing in any "
        "input is broken whenever Sources is the active route."
    )


# ---------------------------------------------------------------------------
# EpisodeCard memory leak fix
# ---------------------------------------------------------------------------


def test_episode_card_uses_cancelled_flag_pattern():
    """v0.7.186: EpisodeCard's audio-load useEffect MUST use the
    cancelled-flag + AbortController pattern to prevent (a)
    object-URL leak on fast unmount, (b) setState-after-unmount,
    (c) stale-blob-wins races on rapid episode switching."""
    src = _read_source("frontend/src/components/podcasts/EpisodeCard.tsx")
    # The cancelled flag is declared and used as a guard before
    # every setState in the async path.
    assert "let cancelled = false" in src, (
        "v0.7.186 regression: EpisodeCard audio-load lost its "
        "cancelled flag — setState-after-unmount is back."
    )
    # AbortController is wired to the fetch call.
    assert "const controller = new AbortController()" in src, (
        "v0.7.186 regression: EpisodeCard audio fetch is missing "
        "AbortController. Rapid episode-switch will race + stomp "
        "audioSrc with stale blobs."
    )
    assert "signal: controller.signal" in src
    # currentObjectUrl is assigned BEFORE setAudioSrc (so cleanup
    # always sees it even on fast unmount mid-async).
    assert "currentObjectUrl = url" in src
    # Cleanup revokes the URL.
    assert "URL.revokeObjectURL(currentObjectUrl)" in src


def test_episode_card_does_not_surface_abort_as_user_error():
    """v0.7.186: AbortError is the expected outcome of switching
    episodes mid-fetch. Showing 'Audio unavailable' on every
    rapid click would be UX confetti."""
    src = _read_source("frontend/src/components/podcasts/EpisodeCard.tsx")
    assert "AbortError" in src, (
        "v0.7.186 regression: EpisodeCard audio error handler no "
        "longer distinguishes AbortError from real failures. Rapid "
        "episode switching will spam 'audio unavailable' toasts."
    )
