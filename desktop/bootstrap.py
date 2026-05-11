# desktop/bootstrap.py
"""First-launch bootstrap: creates ~/.open-notebook-plus/venv via uv.

The launcher's frozen Python only carries pywebview/aiohttp/httpx; upstream's
FastAPI + langchain + esperanto stack lives in a user-managed venv that uv
provisions on first launch (or whenever requirements.lock changes).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable


def venv_dir() -> Path:
    base = Path(os.environ.get("USERPROFILE") or os.environ["HOME"])
    return base / ".open-notebook-plus" / "venv"


def venv_python() -> Path:
    if sys.platform == "win32":
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def venv_marker() -> Path:
    return venv_dir().parent / "venv-marker"


def _lock_hash(lock_path: Path) -> str:
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()


def is_venv_current(lock_path: Path) -> bool:
    """True iff venv exists AND was provisioned against this exact lock."""
    if not venv_python().exists():
        return False
    marker = venv_marker()
    if not marker.exists():
        return False
    return marker.read_text().strip() == _lock_hash(lock_path)


def ensure_venv(
    standalone_python: Path,
    uv_binary: Path,
    lock_path: Path,
    upstream_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Create or update the user venv. Returns the venv's python path.

    standalone_python — bundled portable interpreter used to create the venv.
    uv_binary — bundled uv binary used to install requirements.
    lock_path — pinned requirements.lock shipped in the bundle.
    upstream_dir — bundled upstream source (api/, open_notebook/, commands/).
    """
    progress = progress or (lambda msg: None)

    if is_venv_current(lock_path):
        progress("Environment is up to date.")
        return venv_python()

    # Fresh venv. Wipe any partial state.
    if venv_dir().exists():
        progress("Removing stale environment…")
        shutil.rmtree(venv_dir())
    venv_dir().parent.mkdir(parents=True, exist_ok=True)

    progress("Creating Python environment…")
    subprocess.run(
        [str(standalone_python), "-m", "venv", str(venv_dir())],
        check=True,
    )

    progress("Installing dependencies (this takes about a minute)…")
    subprocess.run(
        [
            str(uv_binary), "pip", "install",
            "--python", str(venv_python()),
            "-r", str(lock_path),
        ],
        check=True,
    )

    # Make upstream importable from the venv by writing a .pth file pointing
    # at the bundled upstream/ source dir.
    site_packages = next(venv_dir().glob("lib/python*/site-packages"), None) \
        or (venv_dir() / "Lib" / "site-packages")  # Windows
    (site_packages / "open_notebook_upstream.pth").write_text(str(upstream_dir) + "\n")

    progress("Finalising…")
    venv_marker().write_text(_lock_hash(lock_path))
    progress("Done.")
    return venv_python()
