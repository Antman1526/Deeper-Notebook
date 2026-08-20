"""v0.8.68 — welcome splash contract.

The main window opens on an inline splash that probes the frontend and
replaces itself with the app. These tests pin what makes that safe:
self-contained (paints with zero network), correct URL embedding, a
probe/replace loop with no terminal error state, and the loaded-event
gating that keeps the watchdog armed while the splash is showing.
"""

from __future__ import annotations

import json
import re

from desktop.splash import build_splash_html

URL = "http://127.0.0.1:54321/"


def test_embeds_frontend_url_json_escaped():
    html = build_splash_html(URL)
    assert f"var TARGET = {json.dumps(URL)};" in html
    assert "__FRONTEND_URL__" not in html  # placeholder fully replaced


def test_splash_is_self_contained():
    """No external resources — the splash must paint before ANY server is
    up, so a single src/href to the network would defeat its purpose."""
    html = build_splash_html(URL)
    refs = re.findall(r'(?:src|href)\s*=\s*["\'](.*?)["\']', html)
    external = [r for r in refs if r.startswith(("http", "//"))]
    assert external == []
    assert "@import" not in html and "url(" not in html


def test_splash_is_presentation_only():
    """The python handoff controller owns navigation (an in-page no-cors
    probe cannot see HTTP status, so Next's warm-up 404 read as "ready"
    and the splash navigated onto an error page — seen live). The splash
    must NOT navigate or probe on its own."""
    html = build_splash_html(URL)
    assert "location.replace" not in html
    assert "fetch(" not in html
    # Status rotation still present (the user watches this while booting).
    assert "setStatus" in html


def test_quote_safe_url_embedding():
    html = build_splash_html('http://127.0.0.1:1/"</script><script>alert(1)')
    assert "<script>alert(1)" not in html  # json.dumps escaped the breakout


def test_loaded_gating_uses_in_page_sentinel_not_urls():
    """URL checks were proven unable to distinguish the splash (URL None),
    WebKit's error page (reports the target URL), and Next's warm-up 404 —
    the loaded handler must interrogate the page itself."""
    from desktop.window import _FRONTEND_SENTINEL_JS

    assert "__next_f" in _FRONTEND_SENTINEL_JS
