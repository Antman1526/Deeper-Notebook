"""ONP v0.7.90 — Filesystem listing endpoints for host-machine access.

The desktop bundle runs natively on the user's host (macOS .dmg, Windows
local install) — it can see and write to anywhere the user can. The
Docker-compose deployment is limited to mounted volumes, which is fine
because the user explicitly mounts what they want exposed.

These endpoints let the frontend present a directory-picker UI so the
user can choose where to export notebooks / notes, or where to import
files from. They are NOT a general "browse the universe" API — they're
the minimum needed for picker dialogs.

Safety rationale:
  * The API is already password-protected via the standard middleware,
    so any caller is already "the user".
  * We refuse known system roots (/etc, /System, /Windows, /proc, …)
    not because they'd be a security boundary — the user owns the
    process — but because surfacing them in a UI list would be noisy
    and accidentally-destructive.
  * We resolve all paths to their canonical form and reject anything
    containing `..` after resolve, so the frontend can't be tricked
    into asking for traversal outside whatever the user typed.
  * Directory listings are capped at MAX_ENTRIES so a user pointing the
    picker at /tmp doesn't OOM the API.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/fs", tags=["filesystem"])


# Hard-denied path prefixes. Listing or writing under these is refused so
# the UI never surfaces them. None of these are useful as a notebook
# export target. The user owns the machine; this is UX, not a security
# boundary.
_DENIED_PREFIXES: tuple[str, ...] = (
    "/etc",
    "/private/etc",
    "/usr/bin",
    "/usr/sbin",
    "/usr/lib",
    "/System",  # macOS
    "/Library/Apple",
    "/private/var/db",
    "/proc",  # Linux
    "/sys",  # Linux
    "/dev",
    "/Windows",  # Windows (PyInstaller bundle on win sees this case-insensitively)
    "/$Recycle.Bin",
)

# Cap entries per listing. Large dirs (e.g. ~/Downloads with 5000 files)
# would otherwise flood the JSON response.
MAX_ENTRIES = 500


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FsEntry(BaseModel):
    name: str
    path: str  # absolute, canonical
    is_dir: bool
    size: Optional[int] = None  # bytes; None for dirs
    modified: Optional[str] = None  # ISO 8601


class FsListResponse(BaseModel):
    path: str
    parent: Optional[str] = None
    entries: list[FsEntry]
    truncated: bool = False  # True if MAX_ENTRIES was reached
    warnings: list[str] = []


class FsHomeResponse(BaseModel):
    home: str
    desktop: Optional[str] = None
    documents: Optional[str] = None
    downloads: Optional[str] = None
    default_exports: str  # ~/DeeperNotebook-Exports


class FsMkdirRequest(BaseModel):
    path: str = Field(..., description="Absolute path of the directory to create")
    parents: bool = Field(True, description="Create intermediate directories as needed")


class FsMkdirResponse(BaseModel):
    path: str
    created: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_and_validate(path: str, *, must_exist: bool = True) -> Path:
    """Normalize a user-supplied path. Rejects:
      - Empty / non-absolute paths after expansion
      - Paths under a denied prefix
      - Paths that resolve through `..` to a denied location
      - (Optional) paths that don't exist

    Returns the canonical Path. Raises HTTPException on rejection.
    """
    if not path or not isinstance(path, str):
        raise HTTPException(status_code=400, detail="path must be a non-empty string")
    expanded = os.path.expanduser(path.strip())
    try:
        resolved = Path(expanded).resolve()
    except (OSError, RuntimeError) as exc:
        # Resolve can raise on Windows reparse-point loops, etc.
        raise HTTPException(status_code=400, detail=f"Could not normalize path: {exc}")
    if not resolved.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="path must resolve to an absolute location",
        )
    resolved_str = str(resolved)
    # v0.7.185 — Audit finding #5: previously this just did
    # `.lower().startswith(prefix.lower())`. On Windows, Path.resolve()
    # produces `C:\Windows\System32\...` — startswith against `/windows`
    # (POSIX-style prefix) returns False, so the denylist SILENTLY
    # didn't fire and the file picker happily browsed into C:\Windows
    # and friends. The fix: normalize backslashes to forward slashes
    # so a Windows path like `c:\windows\system32` becomes
    # `c:/windows/system32`, then ALSO match the Windows variant
    # `<drive>:/windows` against the bare-`/windows` prefix by
    # stripping a leading drive letter.
    resolved_lower = resolved_str.lower().replace("\\", "/")
    # Strip a leading drive letter (e.g. `c:`) for matching, so the
    # POSIX-shaped prefix list catches both forms uniformly.
    if len(resolved_lower) >= 2 and resolved_lower[1] == ":":
        comparable = resolved_lower[2:]
    else:
        comparable = resolved_lower
    for prefix in _DENIED_PREFIXES:
        if comparable.startswith(prefix.lower()):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Refusing to access system path {resolved_str!r}. "
                    "Pick a path under your home directory instead."
                ),
            )
    if must_exist and not resolved.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Path does not exist: {resolved_str}",
        )
    return resolved


def _format_entry(entry: Path) -> FsEntry:
    """Build an FsEntry from a Path. Catches stat() errors so a single
    bad inode (permission denied, broken symlink) doesn't abort listing."""
    is_dir = False
    size: Optional[int] = None
    modified: Optional[str] = None
    try:
        stat = entry.stat()
        is_dir = entry.is_dir()
        if not is_dir:
            size = stat.st_size
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    except (OSError, PermissionError):
        # Probably a broken symlink or permission-denied. Surface as a
        # zero-sized file rather than crash the listing.
        pass
    return FsEntry(
        name=entry.name,
        path=str(entry),
        is_dir=is_dir,
        size=size,
        modified=modified,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/home", response_model=FsHomeResponse)
def fs_home() -> FsHomeResponse:
    """Return the user's home directory plus common subfolders. Lets the
    frontend skip the "browse to your home folder" step on first launch."""
    home = Path(os.path.expanduser("~")).resolve()
    desktop = home / "Desktop"
    documents = home / "Documents"
    downloads = home / "Downloads"
    canonical_exports = home / "DeeperNotebook-Exports"
    legacy_exports = home / "OpenNotebookPlus-Exports"
    default_exports = (
        legacy_exports
        if legacy_exports.exists() and not canonical_exports.exists()
        else canonical_exports
    )
    return FsHomeResponse(
        home=str(home),
        desktop=str(desktop) if desktop.exists() else None,
        documents=str(documents) if documents.exists() else None,
        downloads=str(downloads) if downloads.exists() else None,
        default_exports=str(default_exports),
    )


@router.get("/list", response_model=FsListResponse)
def fs_list(
    path: str = Query(..., description="Absolute path to a directory"),
    show_hidden: bool = Query(False, description="Include dotfiles"),
    only: Literal["all", "dirs", "files"] = Query(
        "all",
        description="Filter entries by kind",
    ),
) -> FsListResponse:
    """List the contents of a directory on the host filesystem.

    Sorted: directories first, then files; both alphabetical, case-insensitive.
    Capped at MAX_ENTRIES to keep responses small. Hidden entries excluded
    by default — match Finder / Explorer behavior.
    """
    resolved = _resolve_and_validate(path)
    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {resolved}",
        )

    warnings: list[str] = []
    truncated = False
    raw_entries: list[Path] = []
    try:
        # iterdir() is lazy; we materialize so we can sort + cap.
        for child in resolved.iterdir():
            if not show_hidden and child.name.startswith("."):
                continue
            raw_entries.append(child)
            if len(raw_entries) >= MAX_ENTRIES * 2:
                # Stop scanning past 2× cap; we'll truncate after sorting.
                # Keeps the worst-case cost bounded even for huge dirs.
                truncated = True
                break
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied listing {resolved}: {exc}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not list {resolved}: {exc}",
        )

    formatted = [_format_entry(c) for c in raw_entries]
    if only == "dirs":
        formatted = [e for e in formatted if e.is_dir]
    elif only == "files":
        formatted = [e for e in formatted if not e.is_dir]

    # Dirs first, then files; case-insensitive name sort within each group.
    formatted.sort(key=lambda e: (not e.is_dir, e.name.lower()))

    if len(formatted) > MAX_ENTRIES:
        formatted = formatted[:MAX_ENTRIES]
        truncated = True
        warnings.append(
            f"Listing capped at {MAX_ENTRIES} entries; the directory contains "
            "more. Filter by `only=` or pick a more specific path."
        )

    parent = str(resolved.parent) if resolved.parent != resolved else None
    return FsListResponse(
        path=str(resolved),
        parent=parent,
        entries=formatted,
        truncated=truncated,
        warnings=warnings,
    )


@router.post("/mkdir", response_model=FsMkdirResponse)
def fs_mkdir(req: FsMkdirRequest) -> FsMkdirResponse:
    """Create a directory at the requested path. Idempotent — if the
    directory already exists, returns created=False without erroring."""
    # must_exist=False here since we're creating it.
    resolved = _resolve_and_validate(req.path, must_exist=False)
    if resolved.exists():
        if resolved.is_dir():
            return FsMkdirResponse(path=str(resolved), created=False)
        raise HTTPException(
            status_code=409,
            detail=f"Path exists but is not a directory: {resolved}",
        )
    try:
        resolved.mkdir(parents=req.parents, exist_ok=True)
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied creating {resolved}: {exc}",
        )
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not create {resolved}: {exc}",
        )
    logger.info("fs/mkdir: created {!r}", str(resolved))
    return FsMkdirResponse(path=str(resolved), created=True)
