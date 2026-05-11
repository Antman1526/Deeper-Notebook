"""Tests for desktop/bootstrap.py — first-launch venv provisioning."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from desktop.bootstrap import (
    _lock_hash,
    ensure_venv,
    is_venv_current,
    venv_dir,
    venv_marker,
    venv_python,
)


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

    # subprocess.run called twice: venv create + uv pip install.
    assert len(run_calls) == 2
    assert "venv" in run_calls[0]
    assert "install" in run_calls[1]

    # Marker should be written with the lock hash.
    assert fake_marker.exists()
    assert fake_marker.read_text().strip() == _lock_hash(lock)

    # .pth file written into site-packages.
    pth = site_packages / "open_notebook_upstream.pth"
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

    monkeypatch.setattr("desktop.bootstrap.is_venv_current", lambda _lock: True)

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
