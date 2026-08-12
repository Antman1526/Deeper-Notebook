"""MCP URL policy and address-pinned HTTPX transport.

MCP servers are an explicit local/plugin integration, so loopback and private
network addresses remain allowed. Link-local, reserved, multicast, and
unspecified destinations are rejected. The validated DNS answer is captured
before opening the SDK transport and the HTTP connection backend dials only
those addresses while retaining the requested hostname for TLS/SNI.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import httpcore
import httpx

MAX_MCP_URL_LENGTH = 2_048
MAX_MCP_REDIRECTS = 0


class MCPTransportPolicyError(ValueError):
    """Raised when an MCP destination is not safe to contact."""


@dataclass(frozen=True)
class ValidatedMCPURL:
    """Immutable URL/DNS receipt used by one MCP transport instance."""

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _reject(message: str) -> None:
    raise MCPTransportPolicyError(message)


def _canonical_hostname(hostname: str) -> str:
    if not hostname or "%" in hostname or "\\" in hostname:
        _reject("MCP URL hostname is malformed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Refuse legacy integer/hex IP spellings instead of allowing the
        # resolver and socket layer to interpret them differently.
        if hostname.lower().startswith("0x") or all(
            char in "0123456789abcdefABCDEFxX." for char in hostname
        ):
            _reject("MCP URL hostname uses a non-canonical IP address")
        try:
            canonical = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise MCPTransportPolicyError("MCP URL hostname cannot be normalized") from exc
        if not canonical or canonical.endswith("."):
            _reject("MCP URL hostname is non-canonical")
        return canonical
    canonical = str(address)
    if hostname.lower() != canonical.lower():
        _reject("MCP URL IP address is not canonical")
    return canonical


def normalize_mcp_url(raw_url: str) -> str:
    """Return one unambiguous HTTP(S) MCP endpoint or reject it."""
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > MAX_MCP_URL_LENGTH:
        _reject("MCP URL is missing or exceeds the maximum length")
    if raw_url != raw_url.strip() or any(ord(char) < 32 for char in raw_url):
        _reject("MCP URL contains whitespace or control characters")
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise MCPTransportPolicyError("MCP URL has an invalid port") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        _reject("Only HTTP(S) MCP URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        _reject("MCP URLs with embedded credentials are not supported")
    if not parsed.hostname:
        _reject("MCP URL hostname is missing")
    hostname = _canonical_hostname(parsed.hostname)
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    netloc = host_for_url if port in (None, default_port) else f"{host_for_url}:{port}"
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def _is_allowed_mcp_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # Private and loopback are deliberate MCP plugin support. Link-local is
    # always denied (including IPv4-mapped IPv6 metadata addresses).
    if address.is_link_local:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None and mapped.is_link_local:
        return False
    return not any(
        (
            address.is_unspecified,
            address.is_multicast,
            address.is_reserved,
        )
    )


def _is_link_local_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_link_local or (mapped is not None and mapped.is_link_local)


async def resolve_mcp_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve all records and fail closed if any answer is unsafe."""
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise MCPTransportPolicyError("MCP URL hostname could not be resolved") from exc
    addresses = tuple(sorted({record[4][0] for record in records}))
    if any(_is_link_local_address(address) for address in addresses):
        _reject("MCP URL resolves to a link-local address")
    if not addresses or any(not _is_allowed_mcp_address(address) for address in addresses):
        _reject("MCP URL resolves to a blocked network address")
    return addresses


async def validate_mcp_url(raw_url: str) -> ValidatedMCPURL:
    """Normalize and resolve an MCP URL immediately before connecting."""
    url = normalize_mcp_url(raw_url)
    parsed = urlsplit(url)
    assert parsed.hostname is not None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await resolve_mcp_addresses(parsed.hostname, port)
    return ValidatedMCPURL(
        url=url,
        hostname=parsed.hostname,
        port=port,
        addresses=addresses,
    )


class PinnedMCPNetworkBackend(httpcore.AsyncNetworkBackend):
    """Dial only the DNS addresses captured in a :class:`ValidatedMCPURL`.

    ``httpcore`` still receives the original authority as its connection
    origin, so HTTPS TLS/SNI remains bound to the requested hostname. Only the
    TCP dial target is replaced with an approved literal address.
    """

    def __init__(self, receipt: ValidatedMCPURL, delegate: Any | None = None) -> None:
        self._receipt = receipt
        if delegate is None:
            from httpcore._backends.auto import AutoBackend

            delegate = AutoBackend()
        self._delegate = delegate

    def _authority_matches(self, host: str, port: int) -> bool:
        return host.lower().rstrip(".") == self._receipt.hostname.lower().rstrip(".") and port == self._receipt.port

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if not self._authority_matches(host, port):
            raise MCPTransportPolicyError("MCP connection authority changed")
        approved = tuple(self._receipt.addresses)
        if not approved or any(not _is_allowed_mcp_address(address) for address in approved):
            raise MCPTransportPolicyError("MCP connection receipt contains a blocked address")

        last_error: Exception | None = None
        for address in approved:
            try:
                return await self._delegate.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # pragma: no cover - exercised by real fallback dials
                last_error = exc
        if last_error is not None:
            raise last_error
        raise MCPTransportPolicyError("MCP connection has no approved address")

    async def connect_unix_socket(self, path: str, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise MCPTransportPolicyError("Unix-socket MCP transport is not supported")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class PinnedMCPHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport using the MCP address-pinning backend."""

    def __init__(self, receipt: ValidatedMCPURL) -> None:
        # Do not allow HTTP_PROXY/HTTPS_PROXY to bypass the destination policy.
        super().__init__(trust_env=False, retries=0)
        pool = getattr(self, "_pool", None)
        if pool is None or not hasattr(pool, "_network_backend"):
            raise MCPTransportPolicyError("Installed HTTPX transport has no safe backend seam")
        # httpx 0.28/httpcore 1.x expose this pool seam; TLS and SNI remain in
        # AsyncHTTPConnection while the backend controls only TCP resolution.
        pool._network_backend = PinnedMCPNetworkBackend(receipt)


def build_mcp_httpx_client_factory(receipt: ValidatedMCPURL):
    """Build the SDK ``httpx_client_factory`` with redirects disabled."""

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "follow_redirects": False,
            "transport": PinnedMCPHTTPTransport(receipt),
        }
        if headers is not None:
            kwargs["headers"] = headers
        if timeout is not None:
            kwargs["timeout"] = timeout
        if auth is not None:
            kwargs["auth"] = auth
        return httpx.AsyncClient(**kwargs)

    return factory


# Private alias kept short for focused transport regressions and local callers.
_build_mcp_httpx_client_factory = build_mcp_httpx_client_factory
