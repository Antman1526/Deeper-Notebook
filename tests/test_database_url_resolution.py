"""ONP v0.7.6 — Tests for get_database_url backward-compat path.

The legacy `SURREAL_ADDRESS` + `SURREAL_PORT` fallback path produced a
malformed WebSocket URL pre-v0.7.6:

    ws://localhost/rpc:8000   ← port AFTER /rpc — broken

SurrealDB's WebSocket endpoint is `ws://host:port/rpc`. The malformed
URL parses as host=`localhost`, port=`80` (default for ws://),
path=`/rpc:8000`. Any deployment relying on these legacy env vars
without setting SURREAL_URL hit a connection failure with a cryptic
URL-parse error.

The desktop bundle always sets SURREAL_URL explicitly (in
desktop/launcher.py:136), so it's unaffected. The fix unblocks the
documented backward-compat path for Docker users and pre-2024 deploys.
"""

from __future__ import annotations

import pytest

from deeper_notebook.database.repository import get_database_url


def test_surreal_url_env_takes_precedence(monkeypatch):
    """If SURREAL_URL is set, it wins — no fallback construction."""
    monkeypatch.setenv("SURREAL_URL", "ws://override:9000/rpc")
    # Even with the legacy vars set, the URL var must win.
    monkeypatch.setenv("SURREAL_ADDRESS", "ignored")
    monkeypatch.setenv("SURREAL_PORT", "1234")
    assert get_database_url() == "ws://override:9000/rpc"


def test_fallback_builds_port_before_path(monkeypatch):
    """v0.7.6 regression: previously produced ws://host/rpc:port —
    invalid. Must produce ws://host:port/rpc."""
    monkeypatch.delenv("SURREAL_URL", raising=False)
    monkeypatch.setenv("SURREAL_ADDRESS", "db.example.com")
    monkeypatch.setenv("SURREAL_PORT", "8123")
    assert get_database_url() == "ws://db.example.com:8123/rpc"


def test_fallback_uses_localhost_default(monkeypatch):
    """Default address when only PORT is set (or neither) is localhost."""
    monkeypatch.delenv("SURREAL_URL", raising=False)
    monkeypatch.delenv("SURREAL_ADDRESS", raising=False)
    monkeypatch.delenv("SURREAL_PORT", raising=False)
    assert get_database_url() == "ws://localhost:8000/rpc"


def test_fallback_url_is_parseable_websocket(monkeypatch):
    """Sanity: produced URL must round-trip through urllib's parser
    and end up with the right components (catches the off-by-one path
    bug if anyone re-introduces it)."""
    from urllib.parse import urlparse

    monkeypatch.delenv("SURREAL_URL", raising=False)
    monkeypatch.setenv("SURREAL_ADDRESS", "host.local")
    monkeypatch.setenv("SURREAL_PORT", "7777")

    parsed = urlparse(get_database_url())
    assert parsed.scheme == "ws"
    assert parsed.hostname == "host.local"
    assert parsed.port == 7777
    assert parsed.path == "/rpc"


def test_fallback_path_was_malformed_pre_v076(monkeypatch):
    """Documents the pre-fix bug so a future "simplification" can't
    re-introduce it. The OLD form ws://host/rpc:port parses as
    host=host, port=None (default 80 for ws), path=/rpc:port — wrong.
    """
    from urllib.parse import urlparse

    # The buggy form — what we used to produce
    buggy = "ws://localhost/rpc:8000"
    parsed = urlparse(buggy)
    # urllib's parser doesn't recognize the port-after-path form
    assert parsed.hostname == "localhost"
    assert parsed.port is None  # no port extracted — that was the bug
    assert parsed.path == "/rpc:8000"  # port lives in the path instead
