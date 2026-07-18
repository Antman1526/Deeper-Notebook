"""Portable, security-conscious path helpers for generated podcast audio."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def file_uri_to_local_path(
    file_uri: str,
    *,
    pathname_converter: Callable[[str], str] = url2pathname,
) -> str:
    """Convert a local ``file:`` URI into a path string for this platform.

    ``urlparse`` preserves the leading slash in Windows drive URIs such as
    ``file:///C:/podcasts/episode.mp3``.  ``url2pathname`` removes that URI
    syntax using the active platform's rules before callers construct a Path.
    Remote file authorities are not valid podcast output locations.
    """
    parsed = urlparse(file_uri)
    if parsed.scheme.lower() != "file":
        raise ValueError("Expected a file URI")
    if parsed.netloc not in ("", "localhost"):
        raise ValueError("Podcast audio file URI must use a local authority")
    # v0.8.95 — Windows needs this conversion before Path containment checks.
    return pathname_converter(unquote(parsed.path))
