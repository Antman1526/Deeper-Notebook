"""Regression coverage for the final MCP outbound URL boundary."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:169.254.169.254]/latest/meta-data/",
        "file:///etc/passwd",
    ],
)
async def test_mcp_session_rejects_blocked_authorities_before_transport(
    monkeypatch, url
):
    """A directly edited registry URL must not reach streamable HTTP."""
    import mcp.client.streamable_http as streamable_http

    transport_calls: list[str] = []

    @asynccontextmanager
    async def _transport(target, **kwargs):
        transport_calls.append(target)
        raise AssertionError("blocked MCP URL reached the transport")
        yield  # pragma: no cover

    monkeypatch.setattr(streamable_http, "streamablehttp_client", _transport)

    from deeper_notebook.mcp.client import _open_session

    with pytest.raises(ValueError):
        async with _open_session(url):
            pass

    assert transport_calls == []


@pytest.mark.asyncio
async def test_chat_discovery_fails_soft_for_directly_edited_link_local_url(monkeypatch):
    """Legacy/link-local rows produce no tools and never initiate transport."""
    import mcp.client.streamable_http as streamable_http

    transport_calls: list[str] = []

    @asynccontextmanager
    async def _transport(target, **kwargs):
        transport_calls.append(target)
        raise AssertionError("blocked MCP URL reached the transport")
        yield  # pragma: no cover

    monkeypatch.setattr(streamable_http, "streamablehttp_client", _transport)

    import deeper_notebook.graphs.chat as chat_module

    chat_module._clear_tool_discovery_cache()
    tools = await chat_module._resolve_chat_tools(
        force_servers=[
            {
                "id": "mcp_server:legacy",
                "name": "legacy metadata row",
                "url": "http://169.254.169.254/latest/meta-data/",
                "enabled": True,
            }
        ]
    )

    assert tools == []
    assert transport_calls == []


@pytest.mark.asyncio
async def test_mcp_session_preserves_allowed_loopback_transport(monkeypatch):
    """The existing self-hosted loopback policy remains compatible."""
    import mcp.client.session as session_module
    import mcp.client.streamable_http as streamable_http

    transport_calls: list[str] = []

    @asynccontextmanager
    async def _transport(target, **kwargs):
        transport_calls.append(target)
        yield object(), object(), object()

    class _Session:
        def __init__(self, read, write):
            self.read = read
            self.write = write

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            return None

    monkeypatch.setattr(streamable_http, "streamablehttp_client", _transport)
    monkeypatch.setattr(session_module, "ClientSession", _Session)

    from deeper_notebook.mcp.client import _open_session

    async with _open_session("http://127.0.0.1:8742/mcp"):
        pass

    assert transport_calls == ["http://127.0.0.1:8742/mcp"]
