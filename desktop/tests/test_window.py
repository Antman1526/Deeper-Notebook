"""Tests for desktop/window.py theme-token derivation.

These were missing — the v0.5 theme contrast fix shipped without a permanent
test asserting the token set is complete or that WCAG contrast holds. (P1-LOW-12)
"""
from __future__ import annotations

import sys
from pathlib import Path
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
    together. (The frontend ThemeSwitcher:DEEPER_NOTEBOOK_THEMES is the third copy — kept in
    sync by code review, since it can't be imported here.)"""
    from api.routers.deeper_notebook import _VALID_THEMES

    assert set(_THEMES) == set(_VALID_THEMES), (
        "desktop _THEMES and api _VALID_THEMES are out of sync: "
        f"{set(_THEMES) ^ set(_VALID_THEMES)}"
    )


def test_injection_exposes_canonical_theme_bridge_and_legacy_alias():
    """The canonical bridge wins while an existing legacy bridge migrates."""
    js = _theme_injection_js("dark")
    assert "window.DN = window.DN || window.ONP || {}" in js
    assert "window.ONP = window.DN" in js
    assert "window.DN.setTheme" in js
    assert "window.DN.themes" in js
    assert "window.DN.relaunch" in js
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


def test_injection_sets_canonical_stt_url_and_deterministic_legacy_mirror():
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
    assert "window.DEEPER_NOTEBOOK_STT_URL = " in js
    assert (
        "window.ONP_STT_URL = window.DEEPER_NOTEBOOK_STT_URL;"
        in js
    )
    assert "127.0.0.1:51234" in js
    assert "/v1/audio/transcriptions" in js


def test_injection_sets_canonical_tts_url_and_deterministic_legacy_mirror():
    """v0.7.152 — same wiring for the TTS speaker button.

    voice_injection.js posts to `window.ONP_TTS_URL` (defaults to
    `/api/audio/speech` which 404s). The piper shim exposes the OpenAI-
    compatible `/v1/audio/speech` endpoint, so we wire the FAB to it.
    """
    js = _theme_injection_js(
        "dark",
        tts_url="http://127.0.0.1:51235/v1/audio/speech",
    )
    assert "window.DEEPER_NOTEBOOK_TTS_URL = " in js
    assert (
        "window.ONP_TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;"
        in js
    )
    assert "127.0.0.1:51235" in js
    assert "/v1/audio/speech" in js


def test_injection_omits_canonical_and_legacy_voice_urls_when_none():
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
    assert "window.DEEPER_NOTEBOOK_STT_URL =" not in js
    assert "window.DEEPER_NOTEBOOK_TTS_URL =" not in js
    assert "window.ONP_STT_URL =" not in js, (
        "must not emit an assignment to window.ONP_STT_URL when stt_url is None"
    )
    assert "window.ONP_TTS_URL =" not in js, (
        "must not emit an assignment to window.ONP_TTS_URL when tts_url is None"
    )


def test_injection_supports_both_canonical_voice_urls_and_legacy_mirrors():
    """Both URLs in the same injection should both land. Regression guard
    against a future copy-paste bug where one accidentally overrides
    or shadows the other."""
    js = _theme_injection_js(
        "dark",
        stt_url="http://127.0.0.1:51111/v1/audio/transcriptions",
        tts_url="http://127.0.0.1:51222/v1/audio/speech",
    )
    assert "window.DEEPER_NOTEBOOK_STT_URL = " in js
    assert "window.DEEPER_NOTEBOOK_TTS_URL = " in js
    assert "window.ONP_STT_URL = window.DEEPER_NOTEBOOK_STT_URL;" in js
    assert "window.ONP_TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;" in js
    assert "51111" in js
    assert "51222" in js


def test_injection_sets_canonical_memory_globals_and_legacy_mirrors():
    js = _theme_injection_js(
        "dark",
        memory_url="http://127.0.0.1:51236/memory",
        remind_openchronicle=True,
    )

    assert "window.DEEPER_NOTEBOOK_MEMORY_URL = " in js
    assert "window.ONP_MEMORY_URL = window.DEEPER_NOTEBOOK_MEMORY_URL;" in js
    assert "window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE = true;" in js
    assert (
        "window.ONP_REMIND_OPENCHRONICLE = "
        "window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE;"
        in js
    )


def test_desktop_bridge_producer_consumer_contract_is_canonical_first():
    root = Path(__file__).resolve().parents[2]
    producer = _theme_injection_js(
        "dark",
        stt_url="http://127.0.0.1:51111/v1/audio/transcriptions",
        tts_url="http://127.0.0.1:51222/v1/audio/speech",
        memory_url="http://127.0.0.1:51236/memory",
        remind_openchronicle=True,
    )
    voice = (
        root / "desktop/first_run/static/voice_injection.js"
    ).read_text(encoding="utf-8")
    memory = (
        root / "desktop/first_run/static/memory_injection.js"
    ).read_text(encoding="utf-8")

    producer_pairs = [
        ("window.DEEPER_NOTEBOOK_STT_URL =", "window.ONP_STT_URL ="),
        ("window.DEEPER_NOTEBOOK_TTS_URL =", "window.ONP_TTS_URL ="),
        ("window.DEEPER_NOTEBOOK_MEMORY_URL =", "window.ONP_MEMORY_URL ="),
        (
            "window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE =",
            "window.ONP_REMIND_OPENCHRONICLE =",
        ),
        ("window.DEEPER_NOTEBOOK_VERSION =", "window.ONP_VERSION ="),
    ]
    for canonical, legacy in producer_pairs:
        assert producer.index(canonical) < producer.index(legacy)

    consumer_chains = [
        (
            voice,
            "window.DEEPER_NOTEBOOK_STT_URL",
            "window.ONP_STT_URL",
            "'/api/transcribe'",
        ),
        (
            voice,
            "window.DEEPER_NOTEBOOK_TTS_URL",
            "window.ONP_TTS_URL",
            "'/api/audio/speech'",
        ),
        (
            memory,
            "window.DEEPER_NOTEBOOK_MEMORY_URL",
            "window.ONP_MEMORY_URL",
            "'#'",
        ),
        (
            memory,
            "window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE",
            "window.ONP_REMIND_OPENCHRONICLE",
            "false",
        ),
    ]
    for source, canonical, legacy, fallback in consumer_chains:
        canonical_position = source.index(canonical)
        legacy_position = source.index(legacy, canonical_position)
        fallback_position = source.index(fallback, legacy_position)
        assert canonical_position < legacy_position < fallback_position


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
            closing=Event(),
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


def test_native_close_waits_for_frontend_workspace_flush(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    callbacks: dict[str, object] = {}

    class Event:
        def __init__(self):
            self.callback = None

        def __iadd__(self, callback):
            self.callback = callback
            return self

    closing = Event()
    closed = Event()
    loaded = Event()
    fake_window = SimpleNamespace(
        events=SimpleNamespace(
            resized=Event(),
            closing=closing,
            closed=closed,
            loaded=loaded,
        ),
        width=1280,
        height=800,
    )

    def evaluate_js(source, callback=None):
        if callback is None:
            return True
        callbacks["flush_source"] = source
        callbacks["flush_callback"] = callback
        return None

    def destroy():
        callbacks["second_close_result"] = closing.callback()
        if callbacks["second_close_result"] is not False:
            closed.callback()

    fake_window.evaluate_js = evaluate_js
    fake_window.destroy = destroy
    cleaned: list[bool] = []

    def start(**_kwargs):
        loaded.callback()
        if closing.callback is None:
            callbacks["first_close_result"] = "missing"
            callbacks["cleaned_before_flush"] = bool(cleaned)
            closed.callback()
            return
        callbacks["first_close_result"] = closing.callback()
        callbacks["cleaned_before_flush"] = bool(cleaned)
        flush_callback = callbacks.get("flush_callback")
        if callable(flush_callback):
            flush_callback({"ok": True})

    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(
            create_window=lambda *_args, **_kwargs: fake_window,
            start=start,
        ),
    )
    monkeypatch.setattr(
        window_module,
        "_install_native_termination_observer",
        lambda _callback: lambda: None,
    )
    monkeypatch.setattr(
        window_module,
        "_preferred_window_size",
        lambda *_: (1280, 800),
    )
    monkeypatch.setattr(
        window_module,
        "_start_handoff_controller",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "desktop.data_root.active_data_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr("desktop.window_state.load_size", lambda *_: None)
    monkeypatch.setattr("desktop.window_state.save_size", lambda *_: None)

    window_module.open_window(
        "http://127.0.0.1:62001",
        lambda: cleaned.append(True),
    )

    assert callbacks["first_close_result"] is False
    assert callbacks["cleaned_before_flush"] is False
    assert "DEEPER_NOTEBOOK_FLUSH_KNOWLEDGE_WORKSPACE" in str(
        callbacks["flush_source"]
    )
    assert callbacks["second_close_result"] is not False
    assert cleaned == [True]


def test_native_close_flush_does_not_block_the_appkit_event_thread():
    threading = window_module.threading

    class Event:
        def __init__(self):
            self.callback = None

        def __iadd__(self, callback):
            self.callback = callback
            return self

    closing = Event()
    flush_started = threading.Event()
    destroyed = threading.Event()
    evaluation_threads: list[int] = []
    native_event_thread = threading.get_ident()

    def evaluate_js(_source, callback=None):
        evaluation_threads.append(threading.get_ident())
        flush_started.set()
        if callback is not None:
            callback({"ok": True})

    fake_window = SimpleNamespace(
        events=SimpleNamespace(closing=closing),
        evaluate_js=evaluate_js,
        destroy=destroyed.set,
    )
    frontend_loaded = threading.Event()
    frontend_loaded.set()

    window_module._install_workspace_flush_close_gate(
        fake_window,
        frontend_loaded,
    )

    assert closing.callback() is False
    assert flush_started.wait(timeout=1)
    assert destroyed.wait(timeout=1)
    assert evaluation_threads != [native_event_thread]


def test_relaunch_helper_starts_only_after_the_flush_gated_window_closes(
    monkeypatch: pytest.MonkeyPatch,
):
    launched: list[tuple[list[str], dict[str, object]]] = []
    destroyed: list[bool] = []
    bridge = window_module._OnpJsApi()
    bridge._window = SimpleNamespace(
        destroy=lambda: destroyed.append(True),
    )
    monkeypatch.setattr(
        sys,
        "executable",
        "/Applications/Deeper Notebook.app/Contents/MacOS/Deeper Notebook",
    )
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda command, **kwargs: launched.append((command, kwargs)),
    )

    assert bridge.relaunch() is True

    assert destroyed == [True]
    assert launched == []

    bridge.complete_relaunch_after_close()

    assert len(launched) == 1
    assert launched[0][0][:2] == ["/bin/sh", "-c"]
    assert launched[0][1] == {"start_new_session": True}
