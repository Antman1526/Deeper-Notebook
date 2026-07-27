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

import json
import re
from dataclasses import dataclass
from pathlib import Path

from deeper_notebook.local_models.gguf_metadata import (
    GGUFMetadata,
    parse_gguf_metadata,
    parse_param_count_b,
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
    runtime: str = "gguf"


# Skip these — they're not user-facing models, they're cache or
# partial-download artifacts.
_SKIP_SUFFIXES = (".tmp", ".part", ".incomplete", ".downloading")
_SKIP_PREFIXES = (".",)  # dotfiles
_AUXILIARY_NAME_MARKERS = ("mmproj",)


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
    if any(marker in p.name.lower() for marker in _AUXILIARY_NAME_MARKERS):
        # v0.8.69 — multimodal projector GGUFs are companion files, not
        # runnable chat models. Listing them invites a broken hot-swap.
        return False
    try:
        if p.stat().st_size == 0:
            # Zero-byte file — likely a failed download placeholder.
            return False
    except OSError:
        return False
    return True


def _mlx_roots(model_dir: Path) -> list[Path]:
    if model_dir.name == "MLX":
        return [model_dir]
    mlx_dir = model_dir / "MLX"
    return [mlx_dir] if mlx_dir.exists() and mlx_dir.is_dir() else []


def _transformers_roots(model_dir: Path) -> list[Path]:
    if model_dir.name == "Transformers":
        return [model_dir]
    transformers_dir = model_dir / "Transformers"
    return [transformers_dir] if transformers_dir.exists() and transformers_dir.is_dir() else []


def _experimental_roots(model_dir: Path) -> list[Path]:
    if model_dir.name == "Experimental":
        return [model_dir]
    experimental_dir = model_dir / "Experimental"
    return [experimental_dir] if experimental_dir.exists() and experimental_dir.is_dir() else []


def _is_mlx_repo_candidate(p: Path) -> bool:
    if not p.is_dir() or p.name.startswith("."):
        return False
    if not (p / "config.json").is_file():
        return False
    try:
        return any(child.is_file() for child in p.glob("*.safetensors"))
    except OSError:
        return False


def _is_transformers_repo_candidate(p: Path) -> bool:
    if not p.is_dir() or p.name.startswith("."):
        return False
    if not (p / "config.json").is_file():
        return False
    try:
        return any(child.is_file() for child in p.glob("*.safetensors")) or any(
            child.is_file() for child in p.glob("*.bin")
        )
    except OSError:
        return False


def _repo_display_name(path: Path) -> str:
    return path.name.replace("__", "/", 1)


def _parse_mlx_quant_from_name(name: str) -> str | None:
    match = re.search(r"(\d+)\s*bit", name, flags=re.IGNORECASE)
    return f"{match.group(1)}bit" if match else None


def _repo_weight_file_size_bytes(path: Path, patterns: tuple[str, ...]) -> int:
    total = 0
    files: list[Path] = []
    for pattern in patterns:
        try:
            files.extend(path.glob(pattern))
        except OSError:
            return total
    for item in files:
        try:
            total += item.stat().st_size
        except OSError:
            continue
    return total


def _parse_repo_config_metadata(
    path: Path,
    *,
    quant: str | None,
    weight_patterns: tuple[str, ...],
) -> GGUFMetadata:
    config: dict = {}
    try:
        config = json.loads((path / "config.json").read_text())
    except (OSError, json.JSONDecodeError):
        config = {}

    context_length = None
    for key in (
        "max_position_embeddings",
        "model_max_length",
        "max_sequence_length",
        "seq_length",
    ):
        value = config.get(key)
        if isinstance(value, int) and value > 0:
            context_length = value
            break

    name = _repo_display_name(path)
    return GGUFMetadata(
        architecture=config.get("model_type"),
        context_length=context_length,
        quant=quant,
        parameter_count_b=parse_param_count_b(name),
        file_size_bytes=_repo_weight_file_size_bytes(path, weight_patterns),
    )


def _parse_mlx_metadata(path: Path) -> GGUFMetadata:
    return _parse_repo_config_metadata(
        path,
        quant=_parse_mlx_quant_from_name(_repo_display_name(path)),
        weight_patterns=("*.safetensors",),
    )


def _parse_transformers_metadata(path: Path) -> GGUFMetadata:
    return _parse_repo_config_metadata(
        path,
        quant=None,
        weight_patterns=("*.safetensors", "*.bin"),
    )


def _parse_experimental_metadata(path: Path) -> GGUFMetadata:
    return _parse_repo_config_metadata(
        path,
        quant=None,
        weight_patterns=("*.safetensors", "*.bin", "*.gguf"),
    )


def _enumerate_mlx_models(model_dir: Path) -> list[LocalModelInfo]:
    rows: list[LocalModelInfo] = []
    for root in _mlx_roots(model_dir):
        try:
            candidates = list(root.iterdir())
        except OSError:
            continue
        for repo in candidates:
            if not _is_mlx_repo_candidate(repo):
                continue
            rows.append(
                LocalModelInfo(
                    name=_repo_display_name(repo),
                    path=str(repo),
                    metadata=_parse_mlx_metadata(repo),
                    runtime="mlx",
                )
            )
    return rows


def _enumerate_transformers_models(model_dir: Path) -> list[LocalModelInfo]:
    rows: list[LocalModelInfo] = []
    for root in _transformers_roots(model_dir):
        try:
            candidates = list(root.iterdir())
        except OSError:
            continue
        for repo in candidates:
            if not _is_transformers_repo_candidate(repo):
                continue
            rows.append(
                LocalModelInfo(
                    name=_repo_display_name(repo),
                    path=str(repo),
                    metadata=_parse_transformers_metadata(repo),
                    runtime="transformers",
                )
            )
    return rows


def _enumerate_experimental_models(model_dir: Path) -> list[LocalModelInfo]:
    rows: list[LocalModelInfo] = []
    for root in _experimental_roots(model_dir):
        try:
            candidates = list(root.iterdir())
        except OSError:
            continue
        for repo in candidates:
            if not _is_transformers_repo_candidate(repo):
                continue
            rows.append(
                LocalModelInfo(
                    name=_repo_display_name(repo),
                    path=str(repo),
                    metadata=_parse_experimental_metadata(repo),
                    runtime="experimental",
                )
            )
    return rows


def enumerate_models(model_dir: Path | str) -> list[LocalModelInfo]:
    """Enumerate every `*.gguf` file in `model_dir` with its parsed
    metadata. Recurses through HuggingFace-style repo folders so the
    Settings inventory matches the launcher's local auto-register scan.

    Returns an EMPTY list when the directory doesn't exist or isn't
    readable — callers (the API endpoint) treat that as "no models
    available" rather than as an error.
    """
    dir_path = Path(model_dir) if isinstance(model_dir, str) else model_dir
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    results: list[LocalModelInfo] = []
    try:
        candidates = list(dir_path.rglob("*.gguf"))
    except OSError:
        # v0.8.69 — keep the endpoint fail-soft if a nested model folder
        # is unreadable. The launcher already treats local-model discovery
        # as best-effort; Settings should do the same instead of failing
        # the whole inventory page.
        return []

    for p in candidates:
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

    results.extend(_enumerate_mlx_models(dir_path))
    results.extend(_enumerate_transformers_models(dir_path))
    results.extend(_enumerate_experimental_models(dir_path))

    # Stable ordering for the UI — newest-first so a freshly downloaded
    # model lands at the top of the table.
    results.sort(key=lambda m: m.name.lower())
    return results
