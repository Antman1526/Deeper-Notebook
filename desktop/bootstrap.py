# desktop/bootstrap.py
"""First-launch bootstrap: creates ~/.deeper-notebook/venv via uv.

The launcher's frozen Python only carries pywebview/aiohttp/httpx; upstream's
FastAPI + langchain + esperanto stack lives in a user-managed venv that uv
provisions on first launch (or whenever requirements.lock changes).
"""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

from desktop.build.archive_validation import (
    validate_tar_members,
    validate_zip_members,
)
from desktop.data_root import active_data_root

# Max bytes kept in bootstrap-subprocess.log before truncation (P2-MED-19).
# 5 MB is plenty for the heaviest install we run; rotating on next launch
# keeps the file from growing forever across many launches.
_BOOTSTRAP_LOG_MAX_BYTES = 5 * 1024 * 1024


def extract_python_runtime(tarball: Path, dest_parent: Path) -> Path:
    """Extract the python-build-standalone tarball on first launch.

    python-build-standalone ``install_only`` tarballs contain a single
    top-level ``python/`` directory, so extracting into
    ``dest_parent/python-runtime/`` yields:

        dest_parent/python-runtime/python/bin/python3   (macOS/Linux)
        dest_parent/python-runtime/python/python.exe    (Windows)

    If the interpreter already exists the function returns immediately without
    re-extracting.

    Parameters
    ----------
    tarball:
        Path to the ``python-<arch>.tar.gz`` (or ``.zip`` on Windows) file
        shipped inside the bundle.
    dest_parent:
        Directory under which ``python-runtime/`` will be created
        (typically ``~/.deeper-notebook``).

    Returns
    -------
    Path
        Absolute path to the extracted python interpreter binary.
    """
    is_win = sys.platform == "win32"
    runtime_dir = dest_parent / "python-runtime"
    if is_win:
        interpreter = runtime_dir / "python" / "python.exe"
    else:
        interpreter = runtime_dir / "python" / "bin" / "python3"

    # v0.7.212 — Partial-extraction recovery.
    # Previously: a `python3` file existing was treated as proof that
    # the runtime was fully extracted. If a previous extraction was
    # interrupted mid-write (user Force Quit, disk full, Time Machine
    # restore that copies the interpreter binary but not all the
    # .so files), this function returned early — but the runtime is
    # actually broken; the interpreter can't import its own stdlib.
    # Subsequent `venv` create from this interpreter fails with a
    # cryptic error and the user has to manually `rm -rf
    # ~/.deeper-notebook/python-runtime` to recover.
    #
    # Health check: if the file is present, ensure it's executable
    # AND can print its version. Anything else means the install is
    # broken — wipe the runtime dir and re-extract.
    if interpreter.exists():
        if _interpreter_is_healthy(interpreter):
            return interpreter
        # Broken — log and reset.
        import logging
        logging.getLogger(__name__).warning(
            "v0.7.212: detected partial/broken python-runtime at %s; "
            "wiping and re-extracting", runtime_dir,
        )
        shutil.rmtree(runtime_dir, ignore_errors=True)

    suffix = tarball.suffix.lower()
    # Handle double-extension .tar.gz
    if tarball.name.endswith(".tar.gz"):
        with tarfile.open(tarball, "r:gz") as t:
            validate_tar_members(t, expected_root="python")
    elif suffix == ".zip":
        with zipfile.ZipFile(tarball) as z:
            validate_zip_members(z.infolist(), expected_root="python")
    else:
        raise ValueError(f"Unsupported archive format: {tarball}")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    if tarball.name.endswith(".tar.gz"):
        with tarfile.open(tarball, "r:gz") as t:
            t.extractall(runtime_dir, filter="data")  # nosec B202 - validated above
    else:
        with zipfile.ZipFile(tarball) as z:
            z.extractall(runtime_dir)  # nosec B202 - validated above

    if not is_win and interpreter.exists():
        interpreter.chmod(0o755)

    return interpreter


def _interpreter_is_healthy(interpreter: Path) -> bool:
    """v0.7.212 — Probe that the extracted Python interpreter can
    actually run. Returns False on any failure (missing executable
    bit, broken stdlib link, partial tarball extraction).

    Implementation: best-effort `python -c "import sys; print(sys.version)"`
    with a tight 5-second timeout. Anything other than rc=0 means
    the runtime is unusable; the caller will wipe + re-extract.
    """
    if not interpreter.exists():
        return False
    if not os.access(interpreter, os.X_OK):
        # File present but not executable — never functional.
        try:
            interpreter.chmod(0o755)
        except OSError:
            return False
    try:
        proc = subprocess.run(
            [str(interpreter), "-c", "import sys, encodings; print(sys.version)"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def venv_dir() -> Path:
    return active_data_root() / "venv"


def venv_python() -> Path:
    if sys.platform == "win32":
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def venv_marker() -> Path:
    return venv_dir().parent / "venv-marker"


def _lock_hash(lock_path: Path) -> str:
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()


def _bootstrap_log_path() -> Path:
    """Append-only diagnostic log next to bootstrap.log (same dir)."""
    return active_data_root() / "logs" / "bootstrap-subprocess.log"


def _rotate_log_if_oversized(log_path: Path) -> None:
    """P2-MED-19 — keep bootstrap-subprocess.log bounded. Called on every
    `_run_logged` invocation (cheap stat). If the file exceeds the cap, move
    it to `<name>.old` (clobbering the previous .old) and start fresh."""
    try:
        if log_path.exists() and log_path.stat().st_size > _BOOTSTRAP_LOG_MAX_BYTES:
            old = log_path.with_suffix(log_path.suffix + ".old")
            old.unlink(missing_ok=True)
            log_path.rename(old)
    except Exception:
        pass  # never fatal


def _run_logged(args: list[str], tag: str) -> None:
    """subprocess.run with stdout+stderr captured to disk, then raised on
    non-zero exit. Without this, errors from `uv pip install` vanish when the
    .app is launched from Finder (no terminal attached).

    Uses shlex.join for the header (P1-HIGH-07 — robust to args containing
    spaces). Flushes the file before reading the tail back for the error
    message so all subprocess output is on disk before we reach for it.
    """
    log_path = _bootstrap_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_log_if_oversized(log_path)
    with log_path.open("ab") as f:
        # shlex.join produces a copy-pasteable, shell-safe representation
        cmd_repr = shlex.join(args)
        f.write(f"\n===== [{tag}] $ {cmd_repr} =====\n".encode())
        f.flush()
        proc = subprocess.run(
            args,
            stdout=f,
            stderr=subprocess.STDOUT,
        )
        f.write(f"\n===== [{tag}] exit={proc.returncode} =====\n".encode())
        f.flush()
        try:
            os.fsync(f.fileno())  # ensure on disk before exception reads it
        except (OSError, AttributeError):
            pass
    if proc.returncode != 0:
        # Include the tail of the log in the exception so callers (and the
        # frozen launcher's traceback handler) surface something actionable.
        try:
            tail = log_path.read_text(errors="replace").splitlines()[-25:]
            tail_str = "\n".join(tail)
        except Exception:
            tail_str = "(could not read bootstrap-subprocess.log)"
        raise RuntimeError(
            f"[{tag}] subprocess failed with exit={proc.returncode}. "
            f"Last 25 lines of {log_path}:\n{tail_str}"
        )


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
    upstream_dir — bundled source root containing the canonical
    deeper_notebook package, open_notebook compatibility shim, api/, and
    commands/.
    """
    progress = progress or (lambda msg: None)

    if is_venv_current(lock_path):
        # v0.7.141 — Message includes the recovery command so a user
        # who hits the rare case of a hash-match-but-deps-broken
        # situation (corrupted venv, manually mutated venv directory)
        # can self-recover without needing to read source code. The
        # post-install verification in `ensure_venv` catches most of
        # this, but only on the first install. On subsequent
        # "up to date" reuses we can't re-verify without paying the
        # subprocess cost on every launch — so we document the manual
        # path instead.
        progress(
            f"Environment is up to date (delete {venv_dir()} to force "
            "reinstall if the app fails to start)."
        )
        return venv_python()

    # Fresh venv. Wipe any partial state.
    if venv_dir().exists():
        progress("Removing stale environment…")
        shutil.rmtree(venv_dir())
    venv_dir().parent.mkdir(parents=True, exist_ok=True)

    progress("Creating Python environment…")
    _run_logged(
        [str(standalone_python), "-m", "venv", str(venv_dir())],
        "venv-create",
    )

    progress("Installing dependencies (this takes about a minute)…")
    _run_logged(
        [
            str(uv_binary), "pip", "install",
            "--python", str(venv_python()),
            "-r", str(lock_path),
        ],
        "uv-install",
    )

    # Make upstream importable from the venv by writing a .pth file pointing
    # at the bundled upstream/ source dir.
    site_packages = next(venv_dir().glob("lib/python*/site-packages"), None) \
        or (venv_dir() / "Lib" / "site-packages")  # Windows
    (site_packages / "deeper_notebook_upstream.pth").write_text(
        str(upstream_dir) + "\n"
    )

    # v0.7.141 — Defensive post-install verification (Area for Review,
    # found by real user). Before this check existed, a stale bundled
    # lockfile (e.g., prometheus-client added to pyproject.toml but
    # desktop/requirements.lock never regenerated) would silently
    # install the wrong package set. The first symptom was the API
    # crashing 3 minutes into launch with a cryptic
    # `ModuleNotFoundError: No module named 'prometheus_client'`,
    # followed by the launcher timing out waiting for /readyz that
    # never came up.
    #
    # The Makefile-side fix (v0.7.141 build-mac-lock target) prevents
    # the lockfile from going stale in the first place. This check is
    # belt-and-suspenders: if any future regression slips through (or
    # someone hand-edits a lockfile and removes a critical dep), the
    # bootstrap fails LOUDLY here with a 1-line cause + the recovery
    # command, instead of waiting for the API to crash and the user
    # to hunt through logs.
    #
    # The critical-import list intentionally only covers modules whose
    # absence would crash `api.main` at import time. Optional deps
    # (esperanto provider-specific clients, podcast-creator, etc.) are
    # not checked here — they fail at use-time with their own clear
    # errors via the credential / model layer.
    _CRITICAL_IMPORTS = [
        "prometheus_client",   # api/metrics.py — v0.7.124
        "surrealdb",           # database layer
        "fastapi",             # API framework itself
        "langgraph",           # all graph workflows
        "loguru",              # logging
        "pydantic",            # request/response models
    ]
    progress("Verifying critical packages installed…")
    missing = _verify_critical_imports(venv_python(), _CRITICAL_IMPORTS)
    if missing:
        raise RuntimeError(
            "Bootstrap finished `uv pip install` against the bundled "
            "lockfile, but the venv is missing critical packages: "
            f"{', '.join(missing)}. The lockfile shipped in this bundle "
            "is stale relative to the application code (most likely the "
            "Makefile build skipped `build-mac-lock`).\n\n"
            "Recover by force-rebuilding the venv on next launch:\n"
            f"    rm -rf {venv_dir()} {venv_marker()}\n"
            "    open 'Deeper Notebook.app'\n\n"
            "If the issue persists after rebuild, the bundled "
            "requirements.lock itself is broken — rebuild the bundle "
            "with `make build-mac` (which now includes the missing "
            "`build-mac-lock` step automatically)."
        )

    progress("Finalising…")
    venv_marker().write_text(_lock_hash(lock_path))
    progress("Done.")
    return venv_python()


def _verify_critical_imports(
    python_exe: Path, modules: list[str],
) -> list[str]:
    """v0.7.141 — Run each `import X` in the freshly-installed venv,
    return the list of modules that failed.

    Uses subprocess.run with a tiny one-shot script per module so a
    failed import doesn't take down later checks. Returns [] when
    every module imports cleanly.
    """
    failed: list[str] = []
    for module in modules:
        try:
            proc = subprocess.run(
                [str(python_exe), "-c", f"import {module}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                failed.append(module)
        except subprocess.TimeoutExpired:
            failed.append(f"{module} (timeout)")
        except Exception:
            failed.append(f"{module} (exec failure)")
    return failed
