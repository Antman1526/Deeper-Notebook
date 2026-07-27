"""Tests for desktop/window.py theme-token derivation.

These were missing — the v0.5 theme contrast fix shipped without a permanent
test asserting the token set is complete or that WCAG contrast holds. (P1-LOW-12)
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import desktop.window as window_module
from desktop.window import _THEMES, _theme_injection_js, _theme_tokens


@pytest.mark.parametrize("theme_id", list(_THEMES.keys()))
def test_every_theme_produces_27_shadcn_tokens(theme_id):
    """Every theme must produce the full shadcn token set so no upstream
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
    # Every theme is present in the IS_DARK map
    for theme_id in _THEMES:
        assert f'"{theme_id}":' in js
    # And applyTheme toggles the class
    assert "classList.toggle('dark'" in js or 'classList.toggle("dark"' in js


def test_injection_contains_every_theme_as_attribute_selector():
    """v0.5.7 — injection emits every theme as a :root[data-theme="X"] block
    so the ThemeSwitcher can swap live by changing dataset.theme."""
    js = _theme_injection_js("dracula")
    # Every theme id should appear as an attribute selector
    for theme_id in _THEMES:
        assert f'data-theme="{theme_id}"' in js, (
            f"injection missing :root[data-theme=\"{theme_id}\"] block"
        )


def test_theme_ids_are_in_lockstep_with_api_allowlist():
    """v0.8.72 — the theme palette lives in desktop/window.py:_THEMES, but the
    API theme router independently allowlists which theme strings the
    canonical endpoint will accept and persist. If they drift, a theme
    shown in the picker would be rejected on save (or vice-versa). Pin them
    together. (The frontend ThemeSwitcher:ONP_THEMES is the third copy — kept in
    sync by code review, since it can't be imported here.)"""
    from api.routers.deeper_notebook import _VALID_THEMES

    assert set(_THEMES) == set(_VALID_THEMES), (
        "desktop _THEMES and api _VALID_THEMES are out of sync: "
        f"{set(_THEMES) ^ set(_VALID_THEMES)}"
    )


def test_injection_exposes_setTheme_bridge():
    """v0.5.7 — window.ONP.setTheme is what ThemeSwitcher calls. Must be
    present in the generated JS or the dropdown won't work."""
    js = _theme_injection_js("dark")
    assert "window.ONP" in js
    assert "ONP.setTheme" in js
    # And it should POST to the canonical endpoint to persist.
    assert "/api/deeper-notebook/theme" in js


def test_injection_sets_initial_theme_via_dataset():
    """v0.5.7 — the initial active theme is set via dataset.theme on <html>."""
    js = _theme_injection_js("nord")
    assert 'INITIAL_THEME = "nord"' in js
    assert "applyTheme" in js


# ---------------------------------------------------------------------------
# v0.7.152 — STT + TTS URL injection (window.ONP_STT_URL / ONP_TTS_URL)
# ---------------------------------------------------------------------------


def test_injection_sets_onp_stt_url_when_provided():
    """v0.7.152 regression.

    `voice_injection.js` reads `window.ONP_STT_URL` to know where to POST
    recorded audio. When the launcher supplies the whisper-shim port,
    we MUST inject the absolute URL so the mic FAB calls the shim
    directly instead of POSTing to the non-existent `/api/transcribe`
    on the main API (the cause of the recurring "STT failed: HTTP 404"
    toast).
    """
    js = _theme_injection_js(
        "dark",
        stt_url="http://127.0.0.1:51234/v1/audio/transcriptions",
    )
    # Look for the EXPLICIT assignment (the bare `window.ONP_STT_URL`
    # token already appears in voice_injection.js as a fallback lookup).
    assert "window.ONP_STT_URL = " in js
    assert "127.0.0.1:51234" in js
    assert "/v1/audio/transcriptions" in js


def test_injection_sets_onp_tts_url_when_provided():
    """v0.7.152 — same wiring for the TTS speaker button.

    voice_injection.js posts to `window.ONP_TTS_URL` (defaults to
    `/api/audio/speech` which 404s). The piper shim exposes the OpenAI-
    compatible `/v1/audio/speech` endpoint, so we wire the FAB to it.
    """
    js = _theme_injection_js(
        "dark",
        tts_url="http://127.0.0.1:51235/v1/audio/speech",
    )
    assert "window.ONP_TTS_URL = " in js
    assert "127.0.0.1:51235" in js
    assert "/v1/audio/speech" in js


def test_injection_omits_onp_stt_url_when_none():
    """v0.7.152 — When the whisper shim failed to start (`stt_url=None`),
    we MUST NOT inject `window.ONP_STT_URL = "...";`, so that
    voice_injection.js falls back to its built-in `/api/transcribe`
    default. Still broken in that scenario but no worse than today;
    doesn't actively misroute to a stale port that may belong to a
    completely different process by next launch.

    NB: the literal string `window.ONP_STT_URL` appears in the
    bundled voice_injection.js source itself (as `window.ONP_STT_URL
    || '/api/transcribe'`), so we have to look for the explicit
    ASSIGNMENT pattern, not the bare name.
    """
    js = _theme_injection_js("dark", stt_url=None, tts_url=None)
    assert "window.ONP_STT_URL =" not in js, (
        "must not emit an assignment to window.ONP_STT_URL when stt_url is None"
    )
    assert "window.ONP_TTS_URL =" not in js, (
        "must not emit an assignment to window.ONP_TTS_URL when tts_url is None"
    )


def test_injection_supports_both_stt_and_tts_simultaneously():
    """Both URLs in the same injection should both land. Regression guard
    against a future copy-paste bug where one accidentally overrides
    or shadows the other."""
    js = _theme_injection_js(
        "dark",
        stt_url="http://127.0.0.1:51111/v1/audio/transcriptions",
        tts_url="http://127.0.0.1:51222/v1/audio/speech",
    )
    assert "window.ONP_STT_URL = " in js
    assert "window.ONP_TTS_URL = " in js
    assert "51111" in js
    assert "51222" in js


def test_recovery_card_renders_explanation_confirmation_and_explicit_actions():
    renderer = getattr(window_module, "_app_recovery_injection_js", None)
    assert renderer is not None, "the packaged window has no recovery-card renderer"

    js = renderer(
        {
            "show_recovery_card": True,
            "title": "Two Deeper Notebook apps are installed",
            "message": (
                "Open Notebook Plus.app and Deeper Notebook.app both exist."
            ),
            "replace_label": "Replace Old App",
            "keep_label": "Keep Both",
        }
    )

    assert "Two Deeper Notebook apps are installed" in js
    assert "Open Notebook Plus.app" in js
    assert "Deeper Notebook.app" in js
    assert "Replace Old App" in js
    assert "Keep Both" in js
    assert "confirm(" in js
    assert "replace_old_app" in js
    assert "keep_both" in js


def test_native_app_termination_runs_window_cleanup_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """Cocoa app termination must use the same cleanup path as window close.

    ``NSRunningApplication.terminate()`` emits the application-termination
    notification without necessarily emitting pywebview's ``closed`` event.
    The packaged compatibility smoke exercises that native path.
    """

    callbacks: dict[str, object] = {}

    class FakeNotificationCenter:
        def addObserverForName_object_queue_usingBlock_(
            self, name, obj, queue, block
        ):
            callbacks["notification"] = block
            return "observer-token"

        def removeObserver_(self, token):
            callbacks["removed"] = token

    center = FakeNotificationCenter()
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        SimpleNamespace(
            NSNotificationCenter=SimpleNamespace(
                defaultCenter=lambda: center
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(
            NSApplicationWillTerminateNotification="will-terminate"
        ),
    )

    class Event:
        def __init__(self):
            self.callback = None

        def __iadd__(self, callback):
            self.callback = callback
            return self

    fake_window = SimpleNamespace(
        events=SimpleNamespace(
            resized=Event(),
            closed=Event(),
            loaded=Event(),
        ),
        width=1280,
        height=800,
    )

    def start(**_kwargs):
        callbacks["notification"](None)
        fake_window.events.closed.callback()

    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(
            create_window=lambda *_args, **_kwargs: fake_window,
            start=start,
        ),
    )
    monkeypatch.setattr(window_module, "_preferred_window_size", lambda *_: (1280, 800))
    monkeypatch.setattr(window_module, "_start_handoff_controller", lambda *_: None)
    monkeypatch.setattr(
        "desktop.data_root.active_data_root", lambda: tmp_path
    )
    monkeypatch.setattr("desktop.window_state.load_size", lambda *_: None)
    monkeypatch.setattr("desktop.window_state.save_size", lambda *_: None)

    cleaned: list[bool] = []
    window_module.open_window("http://127.0.0.1:62001", lambda: cleaned.append(True))

    assert cleaned == [True]
    assert callbacks["removed"] == "observer-token"
