"""ONP v0.6.3 — Tests for the Gmail OAuth router.

Covers pure helpers — _result_page HTML escaping, _purge_stale_states.
The full OAuth round-trip and the network-bound _refresh_access_token are
intentionally NOT covered here (would require mocking httpx + Google);
that's left for a future integration suite.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.routers import gmail as gmail_mod


def test_result_page_escapes_title_and_body():
    """Hostile content in title or body must not break out as raw HTML."""
    page = gmail_mod._result_page(
        title="<script>alert('t')</script>",
        body="<img src=x onerror=alert('b')>",
        ok=False,
    )
    html = page.body.decode("utf-8")
    # Raw tags absent…
    assert "<script>alert('t')</script>" not in html
    assert "<img src=x onerror=alert('b')>" not in html
    # …escaped versions present.
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(&#x27;b&#x27;)&gt;" in html
    # Title still rendered (escaped) inside <h1> and <title>.
    assert "<h1>" in html and "<title>" in html


def test_result_page_color_reflects_ok_flag():
    ok_page = gmail_mod._result_page("Connected!", "yay", ok=True).body.decode()
    fail_page = gmail_mod._result_page("Failed", "boo", ok=False).body.decode()
    assert "#14B870" in ok_page   # green
    assert "#C44" in fail_page     # red


def test_purge_stale_states_drops_expired_entries():
    """_purge_stale_states removes entries whose deadline is in the past."""
    # Start clean
    gmail_mod._oauth_states.clear()
    now = datetime.now(timezone.utc)
    gmail_mod._oauth_states["stale-1"] = now - timedelta(minutes=1)
    gmail_mod._oauth_states["stale-2"] = now - timedelta(hours=1)
    gmail_mod._oauth_states["fresh"] = now + timedelta(minutes=5)

    gmail_mod._purge_stale_states()

    assert "stale-1" not in gmail_mod._oauth_states
    assert "stale-2" not in gmail_mod._oauth_states
    assert "fresh" in gmail_mod._oauth_states
    # Cleanup so we don't pollute later runs
    gmail_mod._oauth_states.clear()
