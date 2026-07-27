"""Fail-closed destination validation for user-controlled outbound HTTP requests.

This policy is intentionally separate from the MCP/credential URL validator: the
desktop app may legitimately talk to a locally hosted MCP server, while a web
source must never be allowed to reach the local network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2_048
ALLOWED_SCHEMES = frozenset({"http", "https"})


class OutboundURLPolicyError(ValueError):
    """Raised when a URL is not safe to fetch from the research boundary."""


@dataclass(frozen=True)
class ValidatedOutboundURL:
    """Canonical URL and its checked addresses for an individual request hop."""

    url: str
    hostname: str
    addresses: tuple[str, ...]


def _reject(message: str) -> None:
    raise OutboundURLPolicyError(message)


def _canonical_hostname(hostname: str) -> str:
    if not hostname or "%" in hostname or "\\" in hostname:
        _reject("URL hostname is malformed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Python's URL parser accepts some legacy numeric forms that network
        # stacks interpret as IP literals. Refuse them instead of guessing.
        if hostname.lower().startswith("0x") or all(
            char in "0123456789abcdefABCDEFxX." for char in hostname
        ):
            _reject("URL hostname uses a non-canonical IP address")
        try:
            canonical = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise OutboundURLPolicyError("URL hostname cannot be normalized") from exc
        if canonical == "localhost" or canonical.endswith(".localhost"):
            _reject("URL hostname is not publicly routable")
        return canonical
    canonical = str(address)
    if hostname.lower() != canonical.lower():
        _reject("URL IP address is not canonical")
    if not is_public_address(canonical):
        _reject("URL address is not publicly routable")
    return canonical


def normalize_outbound_url(raw_url: str) -> str:
    """Return one unambiguous HTTP(S) URL or reject the input before DNS."""
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > MAX_URL_LENGTH:
        _reject("URL is missing or exceeds the maximum length")
    if raw_url != raw_url.strip() or any(ord(char) < 32 for char in raw_url):
        _reject("URL contains whitespace or control characters")

    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise OutboundURLPolicyError("URL has an invalid port") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        _reject("Only HTTP(S) URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        _reject("URLs with embedded credentials are not supported")
    if not parsed.hostname or parsed.hostname.endswith("."):
        _reject("URL hostname is missing or non-canonical")

    hostname = _canonical_hostname(parsed.hostname)
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 80 if scheme == "http" else 443
    netloc = host_for_url if port in (None, default_port) else f"{host_for_url}:{port}"
    # URL fragments are client-side only and never belong in a fetch receipt.
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))


def is_public_address(value: str) -> bool:
    """Return whether an address is acceptable for an untrusted web fetch."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_unspecified,
            address.is_reserved,
            getattr(address, "is_site_local", False),
        )
    )


async def resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve *all* records and fail if any answer reaches a local range."""
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise OutboundURLPolicyError("URL hostname could not be resolved") from exc

    addresses = tuple(sorted({record[4][0] for record in records}))
    if not addresses or any(not is_public_address(address) for address in addresses):
        _reject("URL resolves to a non-public network address")
    return addresses


async def validate_outbound_url(raw_url: str) -> ValidatedOutboundURL:
    """Normalize and resolve a URL immediately before opening a connection."""
    url = normalize_outbound_url(raw_url)
    parsed = urlsplit(url)
    assert parsed.hostname is not None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await resolve_public_addresses(parsed.hostname, port)
    if any(not is_public_address(address) for address in addresses):
        _reject("URL resolves to a non-public network address")
    return ValidatedOutboundURL(url=url, hostname=parsed.hostname, addresses=addresses)
