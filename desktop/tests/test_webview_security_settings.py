"""v0.8.82 — the app shell's navigation policy is pinned, not inherited.

The shell renders source-controlled URLs (`window.open(source.asset.url,
'_blank')` and `target="_blank"` links in the source detail view). pywebview
5.4 sends those to the system browser by default, but nothing asserted it, so a
future default flip would quietly let a hostile source URL replace the app UI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.window import apply_webview_security_settings


class _FakeWebview:
    def __init__(self, settings):
        self.settings = settings


def test_external_links_are_forced_to_the_system_browser():
    fake = _FakeWebview(
        {
            "OPEN_EXTERNAL_LINKS_IN_BROWSER": False,
            "ALLOW_DOWNLOADS": True,
            "OPEN_DEVTOOLS_IN_DEBUG": True,
        }
    )
    applied = apply_webview_security_settings(fake)

    assert fake.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True
    assert fake.settings["ALLOW_DOWNLOADS"] is False
    assert fake.settings["OPEN_DEVTOOLS_IN_DEBUG"] is False
    assert applied["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True


def test_unknown_keys_are_not_invented():
    """Forward-compatible: never add a key this pywebview does not define."""
    fake = _FakeWebview({"OPEN_EXTERNAL_LINKS_IN_BROWSER": False})
    apply_webview_security_settings(fake)

    assert set(fake.settings) == {"OPEN_EXTERNAL_LINKS_IN_BROWSER"}


def test_missing_settings_dict_is_tolerated():
    """A pywebview without a settings mapping must not crash window startup."""
    class _NoSettings:
        pass

    assert apply_webview_security_settings(_NoSettings()) == {}


def test_real_pywebview_exposes_the_keys_we_pin():
    """Guards against pinning names that silently no longer exist."""
    webview = __import__("webview")
    settings = getattr(webview, "settings", None)
    if not isinstance(settings, dict):  # pragma: no cover - env without pywebview
        return
    applied = apply_webview_security_settings(webview)
    assert "OPEN_EXTERNAL_LINKS_IN_BROWSER" in applied, (
        "pywebview no longer defines OPEN_EXTERNAL_LINKS_IN_BROWSER; the shell "
        "navigation policy needs rechecking against the new API"
    )
