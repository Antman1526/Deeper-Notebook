"""v0.8.65e — regression test for the symlinked-bundle patch failure.

PyInstaller 6.x's macOS BUNDLE step relocates the Next.js frontend to
Contents/Resources/frontend (real files) and leaves
Contents/Frameworks/frontend/{server.js,.next,package.json,public} as symlinks
INTO Resources. The launcher passes the Frameworks path. Pre-v0.8.65e the
patcher copied that read-only dir with copytree(symlinks=True), reproducing the
symlinks in ~/.open-notebook-plus/frontend-runtime where they DANGLE — so it
found no server.js/.next manifests, couldn't inject the dynamic API port, and
the frontend fell back to the baked localhost:5055 ("/api/config returned
status 500"). This test reproduces that bundle shape and asserts the patch now
resolves to the real dir and succeeds.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from desktop import next_rewrites_patcher as nrp


def _make_symlinked_bundle(root: Path) -> Path:
    """Build a fake .app frontend layout and return the Frameworks/frontend
    path (the symlinked one the launcher passes)."""
    res = root / "Contents" / "Resources" / "frontend"
    res_next = res / ".next"
    res_next.mkdir(parents=True)
    # The 3 rewrite-target files, each carrying the baked default host.
    (res / "server.js").write_text('const dest = "http://localhost:5055/api";\n')
    (res_next / "required-server-files.json").write_text(
        json.dumps({"config": {"rewrites": [{"destination": "http://localhost:5055/api/:p*"}]}})
    )
    (res_next / "routes-manifest.json").write_text(
        json.dumps({"rewrites": [{"destination": "http://localhost:5055/api/:p*"}]})
    )
    (res / "package.json").write_text('{"name":"frontend"}')
    (res / "public").mkdir()
    (res / "node_modules").mkdir()
    (res / "node_modules" / "marker.txt").write_text("dep")
    (res / "node_modules" / "next").mkdir()
    (res / "node_modules" / "next" / "package.json").write_text("{}")

    fw = root / "Contents" / "Frameworks" / "frontend"
    fw.mkdir(parents=True)
    # node_modules is a REAL dir in Frameworks (mirrors the actual bundle).
    (fw / "node_modules").mkdir()
    (fw / "node_modules" / "marker.txt").write_text("dep")
    # The rest are RELATIVE symlinks into Resources (../../Resources/frontend/X).
    for name in ("server.js", ".next", "package.json", "public"):
        os.symlink(Path("../../Resources/frontend") / name, fw / name)
    return fw


def test_patch_resolves_symlinked_bundle_to_real_files(tmp_path, monkeypatch):
    fw = _make_symlinked_bundle(tmp_path / "app")
    home = tmp_path / "home"
    home.mkdir()
    windows_profile = tmp_path / "windows-profile"
    windows_profile.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(windows_profile))
    # On Windows, Path.home() can prefer USERPROFILE even when HOME is set.
    # The runtime-copy location must honor the explicit HOME override instead.
    monkeypatch.setattr(
        nrp.Path,
        "home",
        classmethod(lambda cls: windows_profile),
    )
    # Force the read-only-bundle path (copy to a writable per-user location),
    # which is where the dangling-symlink bug bit in production.
    monkeypatch.setattr(nrp, "_is_writable", lambda d: False)

    work = nrp.patch_rewrites_for_api_port(fw, 53999)

    # Patched into the writable runtime copy.
    assert work == home / ".deeper-notebook" / nrp.WRITABLE_COPY_NAME

    server = work / "server.js"
    assert server.exists(), "server.js missing in runtime copy (the original bug)"
    assert not server.is_symlink(), "server.js must be a REAL file, not a symlink"
    assert "localhost:53999" in server.read_text()
    assert "localhost:5055" not in server.read_text()

    # All three rewrite-target files patched.
    for rel in nrp.REWRITE_TARGET_FILES:
        target = work / rel
        assert target.exists(), f"missing patch target {rel}"
        assert "localhost:53999" in target.read_text()
        assert "localhost:5055" not in target.read_text()

    # node_modules came along (a complete, runnable frontend).
    assert (work / "node_modules" / "marker.txt").exists()

    # The app can be upgraded without a server.js source change. A stale
    # per-user runtime that lacks the newly packaged Next dependency must be
    # refreshed instead of looking current solely by the server mtime.
    (work / "node_modules" / "next" / "package.json").unlink()
    refreshed = nrp._copy_to_writable((fw / "server.js").resolve().parent)
    assert refreshed == work
    assert (work / "node_modules" / "next" / "package.json").exists()


def test_patch_real_dir_unchanged_path(tmp_path, monkeypatch):
    """Non-symlinked (dev / Windows) frontend: writable dir is patched in place,
    no resolution/copy. Guards the no-op branch."""
    fe = tmp_path / "frontend"
    (fe / ".next").mkdir(parents=True)
    (fe / "server.js").write_text('dest "http://localhost:5055/api"\n')
    (fe / ".next" / "required-server-files.json").write_text("http://localhost:5055/x")
    (fe / ".next" / "routes-manifest.json").write_text("http://localhost:5055/y")

    work = nrp.patch_rewrites_for_api_port(fe, 51234)
    assert work == fe  # patched in place
    assert "localhost:51234" in (fe / "server.js").read_text()
    assert "localhost:5055" not in (fe / "server.js").read_text()


def test_frozen_runtime_never_mutates_the_signed_frontend(
    tmp_path, monkeypatch
):
    """A writable app bundle is still signed and must remain immutable."""
    fe = tmp_path / "Deeper Notebook.app" / "Contents" / "Resources" / "frontend"
    (fe / ".next").mkdir(parents=True)
    (fe / "server.js").write_text('dest "http://localhost:5055/api"\n')
    (fe / ".next" / "required-server-files.json").write_text(
        "http://localhost:5055/x"
    )
    (fe / ".next" / "routes-manifest.json").write_text(
        "http://localhost:5055/y"
    )
    source_before = {
        rel: (fe / rel).read_bytes()
        for rel in nrp.REWRITE_TARGET_FILES
    }
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    work = nrp.patch_rewrites_for_api_port(fe, 51234)

    assert work == home / ".deeper-notebook" / nrp.WRITABLE_COPY_NAME
    assert work != fe
    assert all((fe / rel).read_bytes() == source_before[rel] for rel in source_before)
    assert not any(fe.rglob("*.orig"))
    assert "localhost:51234" in (work / "server.js").read_text()
