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
from desktop.window import _is_frontend_page

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


def test_probe_and_handoff_logic_present():
    html = build_splash_html(URL)
    # no-cors probe (CORS-free reachability signal) + consecutive-success
    # gate + replace() so the splash doesn't pollute history.
    assert 'mode: "no-cors"' in html
    assert "okStreak" in html
    assert "window.location.replace(TARGET)" in html
    # Failure path retries forever — no terminal error branch exists.
    assert "setTimeout(probe" in html


def test_quote_safe_url_embedding():
    html = build_splash_html('http://127.0.0.1:1/"</script><script>alert(1)')
    assert "<script>alert(1)" not in html  # json.dumps escaped the breakout


def test_is_frontend_page_gating():
    assert _is_frontend_page("http://127.0.0.1:54321/setup-wizard", URL)
    assert _is_frontend_page("http://127.0.0.1:54321/", URL)
    assert not _is_frontend_page("about:blank", URL)  # splash
    assert not _is_frontend_page(None, URL)
    assert not _is_frontend_page("", URL)
    assert not _is_frontend_page("http://127.0.0.1:9999/", URL)
