"""v0.8.39 — enumerate locally-available GGUF models.

Read-only directory scan; calls `parse_gguf_metadata` per file. Skips
non-`.gguf` extensions, dotfiles, partial-download `.tmp` / `.part`
files, and zero-byte stubs.

Distinct from `desktop/auto_register/_http.py:_list_local_ggufs`:
that one runs at launcher startup and returns a list of filename
strings for credential registration. This one runs from the API at
request time and returns full metadata for the Settings UI. The two
should never collide (different processes, different purposes); the
launcher version stays as-is to avoid touching the v0.7.197 +
v0.8.x auto-register chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from open_notebook.local_models.gguf_metadata import (
    GGUFMetadata,
    parse_gguf_metadata,
)


@dataclass(frozen=True)
class LocalModelInfo:
    """One row of the local-models inventory.

    - `name`: filename without extension; used for display.
    - `path`: absolute path. Used by future hot-swap calls.
    - `metadata`: GGUFMetadata (best-effort, fields may be None).
    """
    name: str
    path: str  # str instead of Path so it serializes cleanly to JSON
    metadata: GGUFMetadata


# Skip these — they're not user-facing models, they're cache or
# partial-download artifacts.
_SKIP_SUFFIXES = (".tmp", ".part", ".incomplete", ".downloading")
_SKIP_PREFIXES = (".",)  # dotfiles


def _is_gguf_candidate(p: Path) -> bool:
    """Filter for "real" GGUF files we want to surface in the UI."""
    if not p.is_file():
        return False
    if p.suffix.lower() != ".gguf":
        return False
    if any(p.name.startswith(pfx) for pfx in _SKIP_PREFIXES):
        return False
    if any(p.name.lower().endswith(sfx) for sfx in _SKIP_SUFFIXES):
        return False
    try:
        if p.stat().st_size == 0:
            # Zero-byte file — likely a failed download placeholder.
            return False
    except OSError:
        return False
    return True


def enumerate_models(model_dir: Path | str) -> list[LocalModelInfo]:
    """Enumerate every `*.gguf` file in `model_dir` with its parsed
    metadata. Non-recursive — only the top-level dir is scanned. (We
    don't crawl subdirs by design: HuggingFace cache subdirs can be
    huge and the user-facing inventory should match what the launcher
    expects in its configured flat dir.)

    Returns an EMPTY list when the directory doesn't exist or isn't
    readable — callers (the API endpoint) treat that as "no models
    available" rather than as an error.
    """
    dir_path = Path(model_dir) if isinstance(model_dir, str) else model_dir
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    results: list[LocalModelInfo] = []
    try:
        entries = list(dir_path.iterdir())
    except OSError:
        # Unreadable dir (perms, etc) — return empty rather than crash.
        return []

    for p in entries:
        if not _is_gguf_candidate(p):
            continue
        try:
            md = parse_gguf_metadata(p)
        except Exception:
            # Defensive: never let one bad file kill the whole inventory.
            # parse_gguf_metadata is already broadly try/excepted; this
            # is belt-and-braces for the directory walk.
            continue
        results.append(LocalModelInfo(
            name=p.stem,
            path=str(p),
            metadata=md,
        ))

    # Stable ordering for the UI — newest-first so a freshly downloaded
    # model lands at the top of the table.
    results.sort(key=lambda m: m.name.lower())
    return results
