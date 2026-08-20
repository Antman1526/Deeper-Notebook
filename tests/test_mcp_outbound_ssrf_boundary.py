"""Regression coverage for the final MCP outbound URL boundary."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
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
async def test_chat_discovery_fails_soft_for_directly_edited_link_local_url(
    monkeypatch,
):
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


@pytest.mark.asyncio
async def test_mcp_validate_allows_ipv6_loopback(monkeypatch):
    """The explicit IPv6 loopback endpoint remains a supported local plugin."""
    import deeper_notebook.security.mcp_transport as policy

    class _Loop:
        async def getaddrinfo(self, hostname, port, *, type):
            assert hostname == "::1"
            assert port == 8742
            return [(0, 1, 6, "", ("::1", port, 0, 0))]

    monkeypatch.setattr(policy.asyncio, "get_running_loop", lambda: _Loop())

    receipt = await policy.validate_mcp_url("http://[::1]:8742/mcp")

    assert receipt.url == "http://[::1]:8742/mcp"
    assert receipt.hostname == "::1"
    assert receipt.port == 8742
    assert receipt.addresses == ("::1",)


@pytest.mark.asyncio
async def test_mcp_ipv6_loopback_connect_and_factory_are_pinned():
    """IPv6 loopback uses the approved address and the safe HTTPX factory."""
    from deeper_notebook.security.mcp_transport import (
        PinnedMCPHTTPTransport,
        PinnedMCPNetworkBackend,
        ValidatedMCPURL,
        build_mcp_httpx_client_factory,
    )

    receipt = ValidatedMCPURL(
        url="http://[::1]:8742/mcp",
        hostname="::1",
        port=8742,
        addresses=("::1",),
    )
    calls: list[tuple[str, int]] = []

    class _Delegate:
        async def connect_tcp(self, host, port, **kwargs):
            calls.append((host, port))
            return object()

    backend = PinnedMCPNetworkBackend(receipt, delegate=_Delegate())
    await backend.connect_tcp("::1", 8742)
    assert calls == [("::1", 8742)]

    client = build_mcp_httpx_client_factory(receipt)()
    try:
        assert isinstance(client._transport, PinnedMCPHTTPTransport)
        pinned = client._transport._pool._network_backend
        assert isinstance(pinned, PinnedMCPNetworkBackend)
        assert pinned._receipt == receipt
        assert client.follow_redirects is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",
        "169.254.169.254",
        "224.0.0.1",
        "240.0.0.1",
        "::",
        "::2",
        "::ffff:169.254.169.254",
        "ff02::1",
        "fe80::1",
    ],
)
async def test_mcp_validate_rejects_unsafe_ipv4_and_ipv6_addresses(
    monkeypatch, address
):
    """Unspecified, multicast, link-local, and reserved answers stay blocked."""
    import deeper_notebook.security.mcp_transport as policy

    class _Loop:
        async def getaddrinfo(self, hostname, port, *, type):
            return [(0, 1, 6 if ":" in address else 2, "", (address, port, 0, 0))]

    monkeypatch.setattr(policy.asyncio, "get_running_loop", lambda: _Loop())
    host = f"[{address}]" if ":" in address else address

    with pytest.raises(policy.MCPTransportPolicyError):
        await policy.validate_mcp_url(f"http://{host}:8742/mcp")


@pytest.mark.asyncio
async def test_mcp_transport_does_not_follow_redirect_to_link_local_target():
    """The SDK's redirect-following default must not cross the MCP policy."""
    from deeper_notebook.mcp.client import _build_mcp_httpx_client_factory
    from deeper_notebook.security.mcp_transport import ValidatedMCPURL

    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/mcp":
            return httpx.Response(
                307,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
                request=request,
            )
        raise AssertionError("redirect target reached")

    factory = _build_mcp_httpx_client_factory(
        ValidatedMCPURL(
            url="http://127.0.0.1:8742/mcp",
            hostname="127.0.0.1",
            port=8742,
            addresses=("127.0.0.1",),
        )
    )
    client = factory()
    client._transport = httpx.MockTransport(handler)
    try:
        response = await client.get("http://127.0.0.1:8742/mcp")
        assert response.status_code == 307
        assert client.follow_redirects is False
    finally:
        await client.aclose()
    assert requests == ["http://127.0.0.1:8742/mcp"]


@pytest.mark.asyncio
async def test_mcp_transport_connects_only_to_resolution_approved_before_rebinding(
    monkeypatch,
):
    """A resolver answer changing after validation cannot steer the socket."""
    import deeper_notebook.security.mcp_transport as policy
    from deeper_notebook.security.mcp_transport import (
        PinnedMCPNetworkBackend,
    )

    resolver_calls = 0

    async def first_resolution(hostname, port):
        nonlocal resolver_calls
        resolver_calls += 1
        return ("192.168.1.20",)

    monkeypatch.setattr(policy, "resolve_mcp_addresses", first_resolution)
    approved = await policy.validate_mcp_url("http://plugin.example.test/mcp")
    calls: list[tuple[str, int]] = []

    class _Delegate:
        async def connect_tcp(self, host, port, **kwargs):
            calls.append((host, port))
            return object()

    backend = PinnedMCPNetworkBackend(approved, delegate=_Delegate())

    # Simulate a second DNS answer that would be link-local. The backend must
    # use the immutable validation receipt rather than resolve again.
    async def changed_resolution(hostname, port):
        nonlocal resolver_calls
        resolver_calls += 1
        return ("169.254.169.254",)

    monkeypatch.setattr(policy, "resolve_mcp_addresses", changed_resolution)
    await backend.connect_tcp("plugin.example.test", 80)

    assert calls == [("192.168.1.20", 80)]
    assert resolver_calls == 1


@pytest.mark.asyncio
async def test_mcp_transport_rejects_unapproved_authority_at_connect_boundary():
    from deeper_notebook.security.mcp_transport import (
        MCPTransportPolicyError,
        PinnedMCPNetworkBackend,
        ValidatedMCPURL,
    )

    approved = ValidatedMCPURL(
        url="http://127.0.0.1:8742/mcp",
        hostname="127.0.0.1",
        port=8742,
        addresses=("127.0.0.1",),
    )

    class _Delegate:
        async def connect_tcp(self, host, port, **kwargs):  # pragma: no cover
            raise AssertionError("unapproved authority reached delegate")

    backend = PinnedMCPNetworkBackend(approved, delegate=_Delegate())
    with pytest.raises(MCPTransportPolicyError):
        await backend.connect_tcp("169.254.169.254", 80)
