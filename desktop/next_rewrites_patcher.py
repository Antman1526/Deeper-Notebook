"""v0.7.143 — Patch Next.js standalone-build rewrites for dynamic API port.

Background (real user bug, 2026-05-20):

  User launched the bundled `.app` and saw "Unable to Connect to API
  Server" with details:
    Attempted URL: http://127.0.0.1:53018/api/config
    Technical Details: API config endpoint returned status 500

  The API was running on port 53017 and responding correctly when
  curled directly. The Next.js server on 53018 was returning 500
  because its `rewrites()` config (forwarding `/api/*` to the API
  backend) was **baked at BUILD time** with the default
  `localhost:5055`. The launcher's runtime `INTERNAL_API_URL`
  env var, set to `127.0.0.1:53017`, was being IGNORED by the
  Next.js standalone server.

Why Next.js standalone behaves this way:

  `next build` evaluates `next.config.ts` ONCE at build time and
  writes the rewrite destinations as concrete strings into:
    - server.js
    - .next/required-server-files.json
    - .next/routes-manifest.json

  The standalone server reads these manifest files at boot — it
  does NOT re-run `next.config.ts` to re-evaluate rewrites. So
  any `process.env.INTERNAL_API_URL` reference in the rewrites
  function only takes effect at the `next build` step, not at
  launch time. Since the launcher needs DYNAMIC ports to avoid
  conflicts with other apps on 5055, this fundamentally clashes
  with Next.js's build-time-baked rewrites.

The fix:

  1. At launcher startup, BEFORE spawning Next.js, this module
     replaces the baked `localhost:5055` string with the dynamic
     `localhost:<api_port>` in all three manifest files.
  2. A `.orig` backup is created on first patch so the operation
     is round-trippable — every launch reads from `.orig` (pristine
     build) and writes to the live file, never compounding edits.
  3. If the bundle directory is read-only (e.g., `.app` installed
     to `/Applications` by another user), the patcher copies the
     frontend to `~/.deeper-notebook/frontend-runtime/` and
     patches there instead, returning that path for the launcher
     to use as `cwd`.

Long-term consideration:

  A cleaner architecture would be to skip Next.js rewrites entirely
  and have the frontend always use the absolute API URL from the
  `/config` endpoint (which DOES re-read env vars at request time).
  That requires API-side CORS + frontend-side client refactor.
  Tracked as a deferred follow-up. This module is the pragmatic
  unblock that works with the existing build artifacts.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from desktop.data_root import active_data_root

log = logging.getLogger(__name__)


# The three baked-rewrites manifest files inside a Next.js standalone
# build. Each contains exactly one `localhost:5055` string from the
# default in `frontend/next.config.ts` (line 33).
REWRITE_TARGET_FILES: tuple[str, ...] = (
    "server.js",
    ".next/required-server-files.json",
    ".next/routes-manifest.json",
)

# Build-time default that `next.config.ts` falls back to when
# `INTERNAL_API_URL` is unset (which it is during `next build`).
BUILD_TIME_DEFAULT_HOST = "localhost:5055"

# Where we copy the frontend to if the bundle directory is read-only.
# Same parent as other launcher runtime state (`~/.deeper-notebook/`).
WRITABLE_COPY_NAME = "frontend-runtime"


class PatchError(RuntimeError):
    """Raised when patching cannot proceed — caller decides whether
    to abort launch or limp along with degraded behavior."""


def _ensure_originals(frontend_dir: Path) -> None:
    """On first patch, create `.orig` backups of the pristine build
    output. Subsequent patches read FROM `.orig` so we never compound
    a previous patch's changes.

    Idempotent: if `.orig` already exists, leave it alone (it's the
    canonical pristine version).
    """
    for rel in REWRITE_TARGET_FILES:
        target = frontend_dir / rel
        orig = target.with_suffix(target.suffix + ".orig")
        if not target.exists():
            # Missing target file in this bundle — skip; the patcher
            # will surface a warning when it tries to patch.
            continue
        if not orig.exists():
            try:
                shutil.copy2(target, orig)
            except (PermissionError, OSError) as exc:
                # Can't write a .orig sidecar — caller will fall back
                # to writable-copy mode.
                raise PatchError(
                    f"Could not create backup {orig} (read-only bundle?): {exc}"
                ) from exc


def _is_writable(frontend_dir: Path) -> bool:
    """Heuristic: try to touch a sentinel file inside the bundle.
    True iff we can write here.

    Why not just check `os.access`: `.app` bundles on macOS often
    have permissions that LOOK writable to `os.access` but fail
    on actual write (extended attributes, code-signing seal).
    """
    sentinel = frontend_dir / ".__onp_writable_probe"
    try:
        sentinel.write_text("")
        sentinel.unlink()
        return True
    except (PermissionError, OSError):
        return False


def _copy_to_writable(frontend_dir: Path) -> Path:
    """Copy the bundled frontend to a writable per-user location and
    return the new path. Idempotent: only copies on first invocation
    or when the source has been updated.

    The destination is `~/.deeper-notebook/frontend-runtime/`.
    We compare source/dest mtimes on a sentinel file (`server.js`)
    to decide whether to re-copy after an app upgrade.
    """
    user_dir = active_data_root() / WRITABLE_COPY_NAME
    src_sentinel = frontend_dir / "server.js"
    dest_sentinel = user_dir / "server.js"
    # server.js itself often remains byte-for-byte identical across a frontend
    # dependency upgrade.  A previous runtime copy can therefore look current
    # by mtime while missing newly packaged dependencies such as ``next``.
    # Treat the traced Next package as a second upgrade sentinel when present.
    src_next = frontend_dir / "node_modules" / "next" / "package.json"
    dest_next = user_dir / "node_modules" / "next" / "package.json"

    needs_copy = (
        not dest_sentinel.exists()
        or src_sentinel.stat().st_mtime > dest_sentinel.stat().st_mtime
        or (src_next.exists() and not dest_next.exists())
        or (
            src_next.exists()
            and dest_next.exists()
            and src_next.stat().st_mtime > dest_next.stat().st_mtime
        )
    )
    if needs_copy:
        log.info(
            "Copying frontend to writable location: %s -> %s",
            frontend_dir, user_dir,
        )
        # Wipe + recopy. Using shutil.copytree with dirs_exist_ok=True
        # would merge with stale files from prior builds, leading to
        # subtle "old chunk still loaded" bugs.
        if user_dir.exists():
            # The user_dir might itself be partially read-only from
            # a prior copy of a read-only bundle. Force writability
            # on the tree before rmtree.
            _make_writable_recursive(user_dir)
            shutil.rmtree(user_dir)
        shutil.copytree(frontend_dir, user_dir, symlinks=True)
        # v0.7.143 — copytree preserves source permissions. If the
        # source bundle was read-only (the whole reason we copied in
        # the first place), the copy is ALSO read-only and we can't
        # patch it. Walk the tree and ensure the user can write
        # everywhere.
        _make_writable_recursive(user_dir)
    return user_dir


def _make_writable_recursive(root: Path) -> None:
    """Ensure user has write permission on every file and directory
    under `root`. Used to defang read-only-source-bundle copies and
    to permit cleanup before recopying.

    Best-effort: ignores per-file failures so a single un-chmod-able
    file doesn't block the whole operation. Logs at debug level
    rather than warning because in production this just makes file
    operations succeed that would otherwise fail later.
    """
    for path in [root] + list(root.rglob("*")):
        try:
            current = path.stat().st_mode
            # Add user-write bit (0o200) regardless of current mode
            os.chmod(path, current | 0o200)
        except OSError as exc:
            log.debug("Could not make %s writable: %s", path, exc)


def patch_rewrites_for_api_port(
    frontend_dir: Path,
    api_port: int,
) -> Path:
    """Patch the Next.js standalone build's rewrite destinations to
    target the launcher's dynamic API port. Returns the directory
    Next.js should be spawned from (may differ from `frontend_dir`
    if the bundle was read-only).

    Args:
        frontend_dir: The bundled frontend directory (typically
            `<bundle>/Contents/Resources/frontend` on macOS or
            `<bundle>\\frontend` on Windows).
        api_port: The TCP port the launcher allocated for uvicorn.

    Returns:
        Path to spawn Next.js from. Either `frontend_dir` (if it
        was writable) or `~/.deeper-notebook/frontend-runtime/`
        (writable per-user copy).

    Raises:
        PatchError: if no manifest files contain `localhost:5055`
            (suggests an unexpected build shape — caller should
            check next.config.ts didn't get refactored).
    """
    if api_port == 5055:
        # No-op shortcut: port already matches the baked default.
        # Avoids unnecessary file I/O on dev environments running
        # against the canonical port.
        log.debug(
            "api_port=5055 matches build-time default; no patch needed"
        )
        return frontend_dir

    # v0.8.65e — resolve the symlinked-bundle case. PyInstaller 6.x's macOS
    # BUNDLE step relocates the frontend to Contents/Resources/frontend (real
    # files) and leaves Contents/Frameworks/frontend/{server.js,.next,
    # package.json,public} as symlinks INTO Resources. The launcher passes the
    # Frameworks path (repo_root/frontend = MEIPASS/frontend). Copying that
    # read-only dir with copytree(symlinks=True) reproduces the symlinks in
    # ~/.deeper-notebook/frontend-runtime, where they DANGLE — they point
    # `../../Resources/...` relative to the new location, which does not exist.
    # The patcher then finds no server.js/.next manifests, can't inject the
    # dynamic API port, and the frontend falls back to the baked localhost:5055
    # — the exact "API config endpoint returned status 500" failure. Operate on
    # the RESOLVED real directory instead (it has all real files incl
    # node_modules). No-op when the frontend isn't symlinked (dev / Windows).
    server_js = frontend_dir / "server.js"
    if server_js.is_symlink():
        real_dir = server_js.resolve().parent
        log.info(
            "Frontend exposed via symlinks; using resolved real dir: %s -> %s",
            frontend_dir, real_dir,
        )
        frontend_dir = real_dir

    # A frozen bundle is signed even when its filesystem permissions allow
    # writes. Patching it in place invalidates the macOS code-signing seal, so
    # packaged runtimes always use a per-user copy. Development trees may
    # still patch in place when writable.
    work_dir = frontend_dir
    frozen_runtime = bool(getattr(sys, "frozen", False))
    if frozen_runtime or not _is_writable(frontend_dir):
        log.info(
            "Frontend at %s requires a writable runtime copy "
            "(frozen=%s)",
            frontend_dir, frozen_runtime,
        )
        try:
            work_dir = _copy_to_writable(frontend_dir)
        except (PermissionError, OSError) as exc:
            raise PatchError(
                f"Could not create writable copy of frontend: {exc}"
            ) from exc

    # Create `.orig` backups on first run. Subsequent runs read
    # FROM `.orig` so patches never compound.
    _ensure_originals(work_dir)

    replacement_host = f"localhost:{api_port}"
    files_patched = 0
    files_missing = 0
    total_hits = 0

    for rel in REWRITE_TARGET_FILES:
        target = work_dir / rel
        orig = target.with_suffix(target.suffix + ".orig")
        if not target.exists():
            files_missing += 1
            log.warning("Patch target missing: %s", target)
            continue
        if not orig.exists():
            # _ensure_originals failed for this file but didn't raise.
            # Skip it rather than patch from itself (would compound).
            log.warning(
                "No .orig backup for %s; skipping to avoid compounding edits",
                target,
            )
            continue
        pristine = orig.read_text()
        hits = pristine.count(BUILD_TIME_DEFAULT_HOST)
        if hits == 0:
            log.warning(
                "Expected %r in pristine %s but found none — has "
                "next.config.ts been changed?",
                BUILD_TIME_DEFAULT_HOST, target,
            )
            continue
        patched = pristine.replace(BUILD_TIME_DEFAULT_HOST, replacement_host)
        target.write_text(patched)
        files_patched += 1
        total_hits += hits

    if files_patched == 0:
        raise PatchError(
            f"Could not patch any rewrite-target file in {work_dir}. "
            f"Files missing: {files_missing}. The Next.js standalone "
            "build may have changed shape — check next.config.ts and "
            "the build pipeline."
        )

    log.info(
        "Patched %d Next.js rewrite manifest(s) for api_port=%d (%d substitutions total)",
        files_patched, api_port, total_hits,
    )
    return work_dir


def restore_originals(frontend_dir: Path) -> int:
    """Restore the pristine `.orig` versions over the patched files.
    Useful for tests and for explicitly resetting a botched bundle.

    Returns the count of files restored.
    """
    restored = 0
    for rel in REWRITE_TARGET_FILES:
        target = frontend_dir / rel
        orig = target.with_suffix(target.suffix + ".orig")
        if orig.exists():
            shutil.copy2(orig, target)
            restored += 1
    return restored
