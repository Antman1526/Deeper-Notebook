"""Tests for desktop/bootstrap.py — first-launch venv provisioning."""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop.bootstrap import (
    _lock_hash,
    ensure_venv,
    extract_python_runtime,
    is_venv_current,
    venv_dir,
    venv_marker,
    venv_python,
)

# ---------------------------------------------------------------------------
# extract_python_runtime
# ---------------------------------------------------------------------------

def _make_python_tarball(tmp_path: Path) -> Path:
    """Create a minimal synthetic python-build-standalone-style .tar.gz."""
    tarball = tmp_path / "python-darwin-arm64.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        # python-build-standalone uses "python/" as the top-level dir.
        for rel in ("python/bin/python3", "python/lib/libpython.a"):
            content = b"#!/bin/sh\n# fake\n" if rel.endswith("python3") else b""
            info = tarfile.TarInfo(name=rel)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    tarball.write_bytes(buf.getvalue())
    return tarball


def _make_python_zip(tmp_path: Path) -> Path:
    """Create a minimal synthetic python-build-standalone-style .zip."""
    zpath = tmp_path / "python-windows-x86_64.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("python/python.exe", b"MZ\x00\x00")
        z.writestr("python/lib/python.lib", b"")
    return zpath


def test_extract_python_runtime_extracts_tarball(tmp_path: Path) -> None:
    """extract_python_runtime unpacks the tarball and returns the interpreter path."""
    tarball = _make_python_tarball(tmp_path)
    dest_parent = tmp_path / "home" / ".open-notebook-plus"

    # Monkeypatch sys.platform so we get the unix path logic.
    original_platform = sys.platform
    try:
        sys.platform = "darwin"  # type: ignore[assignment]
        result = extract_python_runtime(tarball, dest_parent)
    finally:
        sys.platform = original_platform  # type: ignore[assignment]

    expected = dest_parent / "python-runtime" / "python" / "bin" / "python3"
    assert result == expected
    assert result.exists(), "interpreter file should be extracted"


def test_extract_python_runtime_skips_when_already_extracted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract_python_runtime returns early when the interpreter
    already exists AND passes the v0.7.212 health probe.

    v0.7.212 — the function now runs a quick `python -V`-style
    probe before deciding to skip extraction, so a placeholder
    file (like the test's `b"existing"` blob) would be treated as
    a corrupt/partial install and re-extracted. Monkeypatch the
    health helper to True so we exercise the skip path that the
    original test covered (re-extraction is exercised by the new
    v0.7.212 partial-extraction-recovery test below).
    """
    tarball = _make_python_tarball(tmp_path)
    dest_parent = tmp_path / "home" / ".open-notebook-plus"

    # Pre-create the interpreter so extraction should be skipped.
    interpreter = dest_parent / "python-runtime" / "python" / "bin" / "python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"existing")

    # v0.8.83 — skipping additionally requires the extraction stamp to match
    # the bundled tarball, so a runtime bump invalidates a healthy-but-stale
    # extraction. Write the matching stamp to exercise the pure skip path.
    import hashlib as _hashlib
    (dest_parent / "python-runtime" / ".source-tarball.sha256").write_text(
        _hashlib.sha256(tarball.read_bytes()).hexdigest() + "\n"
    )

    # v0.7.212 — stub the health probe so the placeholder file is
    # treated as healthy. The probe itself is exercised by the
    # behavioural tests in test_v0_7_212_audit_followup.py.
    from desktop import bootstrap
    monkeypatch.setattr(
        bootstrap, "_interpreter_is_healthy", lambda _p: True,
    )

    original_platform = sys.platform
    try:
        sys.platform = "darwin"  # type: ignore[assignment]
        result = extract_python_runtime(tarball, dest_parent)
    finally:
        sys.platform = original_platform  # type: ignore[assignment]

    assert result == interpreter
    # The content should be unchanged — we did not re-extract.
    assert interpreter.read_bytes() == b"existing"


def test_extract_python_runtime_extracts_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """extract_python_runtime handles .zip archives (Windows path)."""
    zpath = _make_python_zip(tmp_path)
    dest_parent = tmp_path / "home" / ".open-notebook-plus"

    monkeypatch.setattr(sys, "platform", "win32")
    result = extract_python_runtime(zpath, dest_parent)

    expected = dest_parent / "python-runtime" / "python" / "python.exe"
    assert result == expected
    assert result.exists()


# ---------------------------------------------------------------------------
# v0.8.66 (audit H7) — the Windows python-build-standalone artifact is a gzip
# TARBALL, not a zip. The bundle previously named it `python-windows-x86_64.zip`,
# so bootstrap dispatched on the `.zip` suffix and called zipfile.ZipFile() on
# gzip-tar bytes → BadZipFile → a deterministic Windows first-launch crash.
# ---------------------------------------------------------------------------


def _make_windows_python_targz(tmp_path: Path) -> Path:
    """Gzip-tar with the Windows python-build-standalone layout, but correctly
    named `.tar.gz` (the post-fix bundled name)."""
    tarball = tmp_path / "python-windows-x86_64.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, content in (
            ("python/python.exe", b"MZ\x00\x00"),
            ("python/lib/python.lib", b""),
        ):
            info = tarfile.TarInfo(name=rel)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    tarball.write_bytes(buf.getvalue())
    return tarball


def test_bundled_python_tarball_is_targz_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bundled python artifact path must be `.tar.gz` on Windows too — never
    `.zip`. (Regression for the mislabeled-archive Windows bootstrap crash.)"""
    from desktop.app import _bundled_python_tarball

    monkeypatch.setattr(sys, "platform", "win32")
    p = _bundled_python_tarball("windows-x86_64")
    assert p.name.endswith(".tar.gz"), p.name
    assert not p.name.endswith(".zip"), (
        "Windows python artifact must NOT be named .zip — it is gzip-tar bytes "
        "and bootstrap would raise BadZipFile."
    )


def test_extract_windows_targz_uses_tarfile_not_zipfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On Windows, a correctly-named `.tar.gz` extracts via tarfile and yields
    python.exe — proving the post-H7 bundled name boots."""
    tarball = _make_windows_python_targz(tmp_path)
    dest_parent = tmp_path / "home" / ".open-notebook-plus"

    monkeypatch.setattr(sys, "platform", "win32")
    result = extract_python_runtime(tarball, dest_parent)

    expected = dest_parent / "python-runtime" / "python" / "python.exe"
    assert result == expected
    assert result.exists()


def test_gzip_tar_bytes_named_zip_would_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Documents the H7 root cause: gzip-tar bytes with a `.zip` name (the OLD
    Windows bundled name) make extract_python_runtime raise BadZipFile."""
    good = _make_windows_python_targz(tmp_path)
    mislabeled = tmp_path / "python-windows-x86_64.zip"
    mislabeled.write_bytes(good.read_bytes())  # same gzip-tar bytes, .zip name
    dest_parent = tmp_path / "home" / ".open-notebook-plus"

    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(zipfile.BadZipFile):
        extract_python_runtime(mislabeled, dest_parent)


# ---------------------------------------------------------------------------
# _lock_hash
# ---------------------------------------------------------------------------

def test_lock_hash_is_sha256_hex(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"somepackage==1.0\n")
    expected = hashlib.sha256(b"somepackage==1.0\n").hexdigest()
    assert _lock_hash(lock) == expected


def test_lock_hash_changes_with_content(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"pkgA==1.0\n")
    h1 = _lock_hash(lock)
    lock.write_bytes(b"pkgA==2.0\n")
    h2 = _lock_hash(lock)
    assert h1 != h2


# ---------------------------------------------------------------------------
# is_venv_current
# ---------------------------------------------------------------------------

def test_is_venv_current_false_when_no_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"pkgA==1.0\n")

    # Point venv_dir / venv_python / venv_marker at tmp paths that don't exist.
    monkeypatch.setattr("desktop.bootstrap.venv_python", lambda: tmp_path / "bin" / "python")
    monkeypatch.setattr("desktop.bootstrap.venv_marker", lambda: tmp_path / "venv-marker")

    assert is_venv_current(lock) is False


def test_is_venv_current_false_when_marker_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"pkgA==1.0\n")

    fake_python = tmp_path / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.touch()

    marker = tmp_path / "venv-marker"
    marker.write_text("stalehash")

    monkeypatch.setattr("desktop.bootstrap.venv_python", lambda: fake_python)
    monkeypatch.setattr("desktop.bootstrap.venv_marker", lambda: marker)

    assert is_venv_current(lock) is False


def test_is_venv_current_true_when_marker_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"pkgA==1.0\n")
    correct_hash = _lock_hash(lock)

    fake_python = tmp_path / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.touch()

    marker = tmp_path / "venv-marker"
    marker.write_text(correct_hash)

    monkeypatch.setattr("desktop.bootstrap.venv_python", lambda: fake_python)
    monkeypatch.setattr("desktop.bootstrap.venv_marker", lambda: marker)

    assert is_venv_current(lock) is True


# ---------------------------------------------------------------------------
# ensure_venv — happy path (subprocess mocked)
# ---------------------------------------------------------------------------

def test_ensure_venv_creates_venv_and_writes_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"fastapi==0.104.0\n")

    # Fake venv layout that ensure_venv will create/query.
    fake_venv = tmp_path / "venv"
    fake_venv_python = fake_venv / "bin" / "python"
    fake_marker = tmp_path / "venv-marker"

    # Simulate site-packages directory being present after venv creation.
    site_packages = fake_venv / "lib" / "python3.12" / "site-packages"

    def fake_venv_dir():
        return fake_venv

    def fake_venv_python_fn():
        return fake_venv_python

    def fake_venv_marker():
        return fake_marker

    monkeypatch.setattr("desktop.bootstrap.venv_dir", fake_venv_dir)
    monkeypatch.setattr("desktop.bootstrap.venv_python", fake_venv_python_fn)
    monkeypatch.setattr("desktop.bootstrap.venv_marker", fake_venv_marker)

    # is_venv_current will return False (no marker yet).
    # subprocess.run: first call creates venv (side-effect: make dirs + python),
    # second call installs deps (no-op in test).
    run_calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        run_calls.append(list(args))
        if "-m" in args and "venv" in args:
            # Simulate venv creation: create the python executable + site-packages.
            fake_venv_python.parent.mkdir(parents=True, exist_ok=True)
            fake_venv_python.touch()
            site_packages.mkdir(parents=True, exist_ok=True)
        mock_result = MagicMock()
        mock_result.returncode = 0
        return mock_result

    monkeypatch.setattr(subprocess, "run", fake_run)
    # v0.8.83 — the marker now keys on interpreter identity + lock hash. Pin
    # the stamp so it neither shells out (which would pollute run_calls with a
    # non-depcheck call) nor varies by host interpreter.
    monkeypatch.setattr(
        "desktop.bootstrap._interpreter_stamp", lambda _p: "py-test-stamp"
    )

    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()

    progress_msgs: list[str] = []
    result = ensure_venv(
        standalone_python=tmp_path / "python3",
        uv_binary=tmp_path / "uv",
        lock_path=lock,
        upstream_dir=upstream_dir,
        progress=progress_msgs.append,
    )

    # Should return the venv python path.
    assert result == fake_venv_python

    # v0.7.166 — Updated to reflect v0.7.141's depcheck additions.
    # Bootstrap now runs venv-create + uv-pip-install + one
    # `python -c 'import X'` per critical dep (prometheus_client,
    # surrealdb, fastapi, langgraph, esperanto, content_core).
    # The exact count is venv-create=1 + uv-install=1 + N depchecks,
    # so we pin the FIRST two calls (the contract this test was
    # originally written to enforce) and just sanity-check the rest
    # are import probes against the fake venv python.
    assert len(run_calls) >= 2, (
        f"expected at least venv-create + uv-install, got {len(run_calls)}"
    )
    assert "venv" in run_calls[0]
    assert "install" in run_calls[1]
    # Each remaining call should be a `python -c 'import X'` probe
    # against the fake venv interpreter — verifies v0.7.141's
    # `_verify_critical_imports()` is wired up and reaches every dep.
    for call in run_calls[2:]:
        assert str(fake_venv_python) in call, (
            f"depcheck probe didn't use the freshly-created venv python: {call!r}"
        )
        assert "-c" in call and any("import " in a for a in call), (
            f"v0.7.141 expected `python -c 'import X'` shape, got {call!r}"
        )

    # Marker should be written with the interpreter stamp + lock hash
    # (v0.8.83) so a bundled-runtime bump invalidates the venv.
    assert fake_marker.exists()
    assert fake_marker.read_text().strip() == f"py-test-stamp {_lock_hash(lock)}"

    # .pth file written into site-packages.
    pth = site_packages / "deeper_notebook_upstream.pth"
    assert pth.exists()
    assert str(upstream_dir) in pth.read_text()

    # Progress messages emitted.
    assert any("Creating" in m for m in progress_msgs)
    assert any("Done" in m for m in progress_msgs)


def test_ensure_venv_skips_when_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"fastapi==0.104.0\n")

    monkeypatch.setattr(
        "desktop.bootstrap.is_venv_current", lambda _lock, _python=None: True
    )

    fake_python = tmp_path / "venv" / "bin" / "python"
    monkeypatch.setattr("desktop.bootstrap.venv_python", lambda: fake_python)

    run_calls: list = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: run_calls.append(a))

    result = ensure_venv(
        standalone_python=tmp_path / "python3",
        uv_binary=tmp_path / "uv",
        lock_path=lock,
        upstream_dir=tmp_path / "upstream",
    )

    assert result == fake_python
    assert run_calls == [], "subprocess.run must not be called when venv is current"


def test_runtime_bump_invalidates_lock_only_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v0.8.83 — a marker written before interpreter keying (lock hash only)
    must NOT satisfy is_venv_current when the interpreter is supplied, so the
    first launch after a bundled-runtime bump rebuilds the venv exactly once.
    """
    from desktop.bootstrap import is_venv_current

    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"fastapi==0.104.0\n")
    fake_python = tmp_path / "venv" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.touch()
    marker = tmp_path / "venv-marker"

    monkeypatch.setattr("desktop.bootstrap.venv_python", lambda: fake_python)
    monkeypatch.setattr("desktop.bootstrap.venv_marker", lambda: marker)
    monkeypatch.setattr(
        "desktop.bootstrap._interpreter_stamp", lambda _p: "3.12.14 OpenSSL 3.5"
    )

    # Pre-v0.8.83 marker: lock hash alone.
    marker.write_text(_lock_hash(lock))
    assert is_venv_current(lock) is True, "legacy check still honours legacy marker"
    assert is_venv_current(lock, tmp_path / "python3") is False, (
        "interpreter-aware check must invalidate a lock-only marker"
    )

    # Current combined marker: matches only the same interpreter stamp.
    marker.write_text(f"3.12.14 OpenSSL 3.5 {_lock_hash(lock)}")
    assert is_venv_current(lock, tmp_path / "python3") is True
    monkeypatch.setattr(
        "desktop.bootstrap._interpreter_stamp", lambda _p: "3.12.8 OpenSSL 3.0"
    )
    assert is_venv_current(lock, tmp_path / "python3") is False, (
        "a different bundled interpreter must invalidate the venv"
    )


def test_extract_python_runtime_reextracts_on_tarball_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v0.8.83 — a healthy extraction from a DIFFERENT tarball must be wiped
    and re-extracted, otherwise a bundled-runtime bump never reaches existing
    installs (the venv stamp then re-keys off the stale interpreter too).
    A pre-v0.8.83 extraction (no stamp at all) takes the same path.
    """
    import hashlib as _hashlib

    from desktop import bootstrap

    tarball = _make_python_tarball(tmp_path)
    dest_parent = tmp_path / "home" / ".open-notebook-plus"

    interpreter = dest_parent / "python-runtime" / "python" / "bin" / "python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"stale-interpreter")
    stamp = dest_parent / "python-runtime" / ".source-tarball.sha256"
    stamp.write_text(_hashlib.sha256(b"a different tarball").hexdigest() + "\n")

    monkeypatch.setattr(bootstrap, "_interpreter_is_healthy", lambda _p: True)

    original_platform = sys.platform
    try:
        sys.platform = "darwin"  # type: ignore[assignment]
        result = extract_python_runtime(tarball, dest_parent)
    finally:
        sys.platform = original_platform  # type: ignore[assignment]

    assert result == interpreter
    assert interpreter.read_bytes() != b"stale-interpreter", "must re-extract"
    assert stamp.read_text().strip() == _hashlib.sha256(
        tarball.read_bytes()
    ).hexdigest(), "stamp must record the new source tarball"
