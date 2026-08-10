"""v0.8.23 SECURITY — regression test for the sibling-prefix bug in
api/routers/sources.py download-path helpers.

Pre-v0.8.23, `_resolve_source_file` and `_is_source_file_available` did:

    safe_root = os.path.realpath(UPLOADS_FOLDER)
    resolved_path = os.path.realpath(file_path)
    if not resolved_path.startswith(safe_root):
        ...

That is the classic v0.6.31 / v0.6.34 / v0.7.2 sibling-prefix bug:
`/var/uploadsbypass/etc-passwd`.startswith(`/var/uploads`) is True, so
a tampered or stale `source.asset.file_path` pointing OUTSIDE the
uploads folder would pass the check. The download endpoint would then
serve the file via FileResponse, and the GET /sources/{id} response's
`file_available` field would tell the UI the file exists.

The fix uses `Path.is_relative_to()` (Python 3.9+), matching the
v0.7.2 podcasts.py `_resolve_audio_path` pattern.

Tests:
1. is_source_file_available rejects sibling-prefix path
2. is_source_file_available accepts a legitimate path inside the root
3. _resolve_source_file raises 403 (not 200) on sibling-prefix path
4. Both helpers tolerate OSError / ValueError on malformed paths
   without crashing (treat as "not found").
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_source_with_file_path(file_path: str):
    """Construct a minimal Source-like mock with .asset.file_path set."""
    src = MagicMock()
    src.asset = MagicMock()
    src.asset.file_path = file_path
    return src


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_is_source_file_available_rejects_sibling_prefix(tmp_path, monkeypatch):
    """The classic sibling-prefix attack: UPLOADS_FOLDER=/var/uploads,
    file_path=/var/uploadsbypass/file. Pre-v0.8.23 returned True;
    must now return False."""
    # Build the sibling-prefix scenario inside tmp_path so we don't
    # need root permissions to mkdir /var/anything.
    uploads = tmp_path / "uploads"
    sibling = tmp_path / "uploadsbypass"
    uploads.mkdir()
    sibling.mkdir()
    bad_file = sibling / "secret.txt"
    bad_file.write_text("ATTACKER SHOULD NOT GET THIS")

    # Patch UPLOADS_FOLDER seen by the sources router. The helpers
    # read it at call time (not import time) via the module-level
    # symbol — patch on the module.
    import api.routers.sources as sources_mod
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(uploads))

    src = _build_source_with_file_path(str(bad_file))
    result = sources_mod._is_source_file_available(src)

    assert result is False, (
        f"_is_source_file_available returned {result!r} for a sibling-"
        f"prefix path. v0.8.23 fix: use Path.is_relative_to() instead "
        f"of resolved_path.startswith(safe_root). Without the trailing "
        f"separator, '/var/uploadsbypass'.startswith('/var/uploads') "
        f"is True — the exact sibling-prefix bug that v0.6.31 and "
        f"v0.6.34 fixed elsewhere and v0.7.2 fixed in podcasts.py."
    )


def test_is_source_file_available_accepts_legitimate_path(tmp_path, monkeypatch):
    """A path genuinely inside UPLOADS_FOLDER must still return True."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    good_file = uploads / "ok.pdf"
    good_file.write_text("fake pdf")

    import api.routers.sources as sources_mod
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(uploads))

    src = _build_source_with_file_path(str(good_file))
    assert sources_mod._is_source_file_available(src) is True, (
        "v0.8.23 fix must not over-reject legitimate paths inside the "
        "uploads folder. Path.is_relative_to should return True for "
        f"{good_file} relative to {uploads}."
    )


def test_is_source_file_available_tolerates_malformed_path(tmp_path, monkeypatch):
    """A file_path that Path.resolve() can't handle (e.g. a null byte)
    must produce False — not an unhandled exception that 500s the
    /sources/{id} endpoint."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    import api.routers.sources as sources_mod
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(uploads))

    # Embedded null byte → Path.resolve raises ValueError on most OSes.
    src = _build_source_with_file_path("/tmp/has\0null.txt")
    result = sources_mod._is_source_file_available(src)

    assert result is False, (
        f"v0.8.23: malformed paths must return False (not raise). "
        f"Got {result!r} for a path with an embedded null byte."
    )


@pytest.mark.asyncio
async def test_resolve_source_file_rejects_sibling_prefix(tmp_path, monkeypatch):
    """The CRITICAL one: _resolve_source_file is called by
    GET /sources/{id}/download. A sibling-prefix attack here means
    the API actually serves the file. Pre-v0.8.23 the endpoint
    returned 200 + the wrong file's bytes; must now return 403."""
    from fastapi import HTTPException

    uploads = tmp_path / "uploads"
    sibling = tmp_path / "uploadsbypass"
    uploads.mkdir()
    sibling.mkdir()
    bad_file = sibling / "secret.txt"
    bad_file.write_text("ATTACKER SHOULD NOT GET THIS")

    import api.routers.sources as sources_mod
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(uploads))

    # Mock Source.get to return a source with the malicious asset.
    fake_source = _build_source_with_file_path(str(bad_file))

    async def _fake_get(_id):
        return fake_source

    monkeypatch.setattr(sources_mod.Source, "get", _fake_get)

    with pytest.raises(HTTPException) as exc_info:
        await sources_mod._resolve_source_file("source:attacker")

    assert exc_info.value.status_code == 403, (
        f"Expected 403 Forbidden for sibling-prefix attack; got "
        f"{exc_info.value.status_code}. v0.8.23 fix: switch from "
        f"startswith() to Path.is_relative_to() so /var/uploadsbypass "
        f"is correctly rejected when UPLOADS_FOLDER=/var/uploads."
    )


@pytest.mark.asyncio
async def test_resolve_source_file_serves_legitimate_path(tmp_path, monkeypatch):
    """Sanity: a legitimate path inside UPLOADS_FOLDER must still be
    served (the fix is a tightening; it must not break the happy path)."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    good_file = uploads / "ok.pdf"
    good_file.write_text("fake pdf")

    import api.routers.sources as sources_mod
    monkeypatch.setattr(sources_mod, "UPLOADS_FOLDER", str(uploads))

    fake_source = _build_source_with_file_path(str(good_file))

    async def _fake_get(_id):
        return fake_source

    monkeypatch.setattr(sources_mod.Source, "get", _fake_get)

    resolved_path, filename = await sources_mod._resolve_source_file("source:ok")

    assert filename == "ok.pdf"
    # Path equality survives Path<->str round-trip.
    assert Path(resolved_path) == good_file.resolve()


def test_no_startswith_path_check_in_source_helpers():
    """Source-text contract: the two fixed helpers must never reintroduce
    the bare `startswith(safe_root)` pattern. Catches a future refactor
    that 'simplifies' is_relative_to() back to startswith()."""
    import ast
    from pathlib import Path as _P

    src = _P("api/routers/sources.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Use AST instead of text heuristics: extract the exact body span of
    # each helper function (handles blank lines inside the body that
    # would defeat a "\n\n" boundary scan).
    helpers = {"_resolve_source_file", "_is_source_file_available"}
    found = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in helpers
        ):
            found[node.name] = ast.unparse(node)

    for helper in helpers:
        assert helper in found, (
            f"Could not locate {helper} in api/routers/sources.py via AST."
        )
        body = found[helper]
        assert "is_relative_to" in body, (
            f"{helper} must use Path.is_relative_to() (v0.8.23 fix). "
            f"Found body without it; refactor may have reintroduced "
            f"the sibling-prefix bug."
        )
        # The bare startswith pattern is the bug. The v0.8.23 idiom
        # is is_relative_to, so we keep this strict.
        assert "resolved_path.startswith(safe_root)" not in body, (
            f"{helper} reintroduced the bare startswith() check that "
            f"v0.8.23 fixed. This is the sibling-prefix bug — "
            f"`/var/uploadsbypass`.startswith(`/var/uploads`) is True. "
            f"Use Path.is_relative_to() instead."
        )
