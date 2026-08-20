"""Regression coverage for the browser upload path.

The backend source endpoint defaults to a 500 MB upload cap. Browser uploads
reach it through Next.js rewrites, so the Next proxy cap must not be lower than
the backend default or large-but-valid source files fail before FastAPI can
return the app's friendly 413/error path.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.routers import sources as sources_mod


def _parse_next_size_to_bytes(raw: str) -> int:
    match = re.fullmatch(r"\s*['\"]?(\d+)\s*(b|kb|mb|gb)?['\"]?\s*", raw, re.I)
    assert match, f"Unsupported Next.js proxyClientMaxBodySize value: {raw!r}"
    amount = int(match.group(1))
    unit = (match.group(2) or "b").lower()
    factor = {
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
        "gb": 1024 * 1024 * 1024,
    }[unit]
    return amount * factor


def test_next_proxy_cap_matches_backend_default_source_upload_cap():
    repo_root = Path(__file__).resolve().parents[1]
    next_config = (repo_root / "frontend" / "next.config.ts").read_text()

    match = re.search(r"proxyClientMaxBodySize:\s*([^,\n]+)", next_config)
    assert match, "frontend/next.config.ts must set proxyClientMaxBodySize"

    proxy_cap = _parse_next_size_to_bytes(match.group(1).strip())

    assert proxy_cap >= sources_mod._SOURCE_UPLOAD_MAX_BYTES_DEFAULT
