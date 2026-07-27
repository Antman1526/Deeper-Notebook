"""Bounded, redirect-aware HTTP fetches for untrusted research sources."""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from deeper_notebook.security.outbound_url import (
    OutboundURLPolicyError,
    ValidatedOutboundURL,
    validate_outbound_url,
)

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 25 * 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 20.0
TOTAL_TIMEOUT_SECONDS = 45.0
SUPPORTED_MIME_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "application/xml",
        "application/xhtml+xml",
        "application/zip",
        "audio/mpeg",
        "audio/mp4",
        "audio/wav",
        "text/csv",
        "text/html",
        "text/markdown",
        "text/plain",
        "text/xml",
        "video/mp4",
    }
)
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class SafeFetchError(ValueError):
    """A source could not be fetched without crossing a security boundary."""


@dataclass(frozen=True)
class SafeFetchResponse:
    url: str
    content_type: str
    body: bytes
    checked_hops: tuple[ValidatedOutboundURL, ...]

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _mime_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].lower()


def _is_supported_mime_type(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in SUPPORTED_MIME_TYPES


def _parse_content_length(response: httpx.Response) -> int | None:
    value = response.headers.get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise SafeFetchError("Source returned an invalid content length") from exc


def _decompress(body: bytes, encoding: str) -> bytes:
    encoding = encoding.lower().strip()
    try:
        if encoding in ("", "identity"):
            return body
        if encoding == "gzip":
            return gzip.decompress(body)
        if encoding == "deflate":
            return zlib.decompress(body)
    except (OSError, zlib.error) as exc:
        raise SafeFetchError("Source returned an invalid compressed body") from exc
    raise SafeFetchError("Source returned an unsupported content encoding")


class SafeFetcher:
    """Fetches one document while revalidating every redirect destination."""

    def __init__(self, *, validator=validate_outbound_url) -> None:
        self._validator = validator

    async def fetch(
        self, raw_url: str, *, client: httpx.AsyncClient | None = None
    ) -> SafeFetchResponse:
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,  # Never inherit a proxy which could reach private networks.
                timeout=httpx.Timeout(
                    TOTAL_TIMEOUT_SECONDS,
                    connect=CONNECT_TIMEOUT_SECONDS,
                    read=READ_TIMEOUT_SECONDS,
                ),
                headers={"User-Agent": "DeeperNotebook/0.8 safe-research-fetch"},
            )

        current_url = raw_url
        checked_hops: list[ValidatedOutboundURL] = []
        try:
            for redirect_count in range(MAX_REDIRECTS + 1):
                # Resolve immediately before each request; redirects therefore cannot
                # turn a public URL into a private-network request.
                checked = await self._validator(current_url)
                checked_hops.append(checked)
                request = client.build_request("GET", checked.url)
                response = await client.send(
                    request, stream=True, follow_redirects=False
                )
                try:
                    if response.status_code in REDIRECT_STATUS_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise SafeFetchError(
                                "Source returned a redirect without a location"
                            )
                        if redirect_count >= MAX_REDIRECTS:
                            raise SafeFetchError("Source exceeded the redirect limit")
                        current_url = urljoin(checked.url, location)
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise SafeFetchError(
                            f"Source returned HTTP {response.status_code}"
                        )

                    content_type = _mime_type(response)
                    if not _is_supported_mime_type(content_type):
                        raise SafeFetchError("Source returned an unsupported MIME type")
                    content_length = _parse_content_length(response)
                    if content_length is not None and (
                        content_length < 0 or content_length > MAX_BODY_BYTES
                    ):
                        raise SafeFetchError("Source exceeds the 25 MB body limit")

                    if response.is_stream_consumed:
                        # Mock transports and a few custom transports may return a
                        # pre-buffered response even when client.send(stream=True).
                        compressed = bytearray(response.content)
                    else:
                        compressed = bytearray()
                        async for chunk in response.aiter_raw():
                            compressed.extend(chunk)
                            if len(compressed) > MAX_BODY_BYTES:
                                raise SafeFetchError(
                                    "Source exceeds the 25 MB body limit"
                                )
                    if len(compressed) > MAX_BODY_BYTES:
                        raise SafeFetchError("Source exceeds the 25 MB body limit")
                    body = _decompress(
                        bytes(compressed), response.headers.get("content-encoding", "")
                    )
                    if len(body) > MAX_BODY_BYTES:
                        raise SafeFetchError("Source exceeds the 25 MB body limit")
                    return SafeFetchResponse(
                        url=checked.url,
                        content_type=content_type,
                        body=body,
                        checked_hops=tuple(checked_hops),
                    )
                finally:
                    await response.aclose()
        except (httpx.HTTPError, OutboundURLPolicyError) as exc:
            raise SafeFetchError("Source could not be fetched safely") from exc
        finally:
            if owns_client:
                await client.aclose()
        raise SafeFetchError("Source exceeded the redirect limit")


async def fetch_public_url(url: str) -> SafeFetchResponse:
    """Convenience API for all regular URL-source ingestion paths."""
    return await SafeFetcher().fetch(url)
