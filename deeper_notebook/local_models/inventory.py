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

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from deeper_notebook.local_models.contracts import (
    ExternalModelRootTrust,
    ModelReadinessEvidence,
    classify_model_readiness,
    trust_record_matches,
)
from deeper_notebook.local_models.gguf_metadata import (
    GGUFMetadata,
    parse_gguf_metadata,
    parse_param_count_b,
)


def model_root_fingerprint(path: Path | str) -> str:
    """Fingerprint a root identity without reading or changing its contents.

    The selected symlink's ``lstat`` identity is distinct from the resolved
    target identity.  A trust approval therefore cannot be replayed for a
    different link or a later target swap.
    """
    candidate = Path(path)
    try:
        stat = candidate.lstat()
        identity = f"{candidate.absolute()}\0{stat.st_dev}\0{stat.st_ino}"
    except OSError:
        identity = f"missing\0{candidate.absolute()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _trusted_external_targets(
    selected_root: Path,
    trusted_external_roots: object | None,
) -> list[Path]:
    """Return only approved symlink-directory targets below ``selected_root``.

    ``os.walk(..., followlinks=False)`` is load-bearing: an untrusted link is
    removed from traversal before any child path is inspected.  The caller may
    grant access only with a record for this exact link identity and resolved
    target identity.
    """
    records = [
        item
        for item in (trusted_external_roots or [])
        if isinstance(item, ExternalModelRootTrust)
    ]
    if not records:
        return []

    approved: list[Path] = []
    try:
        walker = os.walk(selected_root, followlinks=False)
        for current, directories, _files in walker:
            current_path = Path(current)
            for name in list(directories):
                link = current_path / name
                if not link.is_symlink():
                    continue
                directories.remove(name)
                resolved = _trusted_link_target(link, records)
                if resolved is not None:
                    approved.append(resolved)
    except OSError:
        return approved
    return approved


def _trusted_link_target(
    link: Path,
    records: list[ExternalModelRootTrust],
) -> Path | None:
    try:
        resolved = link.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    selected_fingerprint = model_root_fingerprint(link)
    target_fingerprint = model_root_fingerprint(resolved)
    if any(
        trust_record_matches(
            record,
            selected_root_fingerprint=selected_fingerprint,
            resolved_target_fingerprint=target_fingerprint,
        )
        for record in records
    ):
        return resolved
    return None


def _gguf_files_without_following_symlinks(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        for current, _directories, filenames in os.walk(root, followlinks=False):
            for filename in filenames:
                candidate = Path(current) / filename
                # Leaf symlinks are no safer than directory symlinks.  They
                # need a future explicit leaf-trust contract, not implicit IO.
                if candidate.is_symlink():
                    continue
                if candidate.suffix.lower() == ".gguf":
                    files.append(candidate)
    except OSError:
        return files
    return files


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


@dataclass(frozen=True)
class LocalModelReadinessInfo:
    """A redaction-safe row for planning and route eligibility surfaces."""

    model_id: str
    format: str
    modality: str
    readiness: str
    readiness_reason: str
    measured_tier: str | None
    accepted_roles: tuple[str, ...]
    route_eligible: bool


def build_readiness_inventory(
    model_dir: Path | str,
    *,
    manifest_entries: list[object] | None = None,
    active_model_path: str = "",
    trusted_external_roots: object | None = None,
) -> list[LocalModelReadinessInfo]:
    """Discover visible assets and apply only supplied, pure readiness facts.

    No model is treated as verified here: this read-only inventory has neither
    a bounded health result nor an accepted benchmark.  The active identity is
    intentionally the sole runtime fact this first foundation can observe.
    """
    root = Path(model_dir)
    rows = enumerate_models(
        root,
        trusted_external_roots=trusted_external_roots,
    )
    active = _canonical_path(active_model_path)
    result: list[LocalModelReadinessInfo] = []
    known_ids: set[str] = set()
    for row in rows:
        model_id = _inventory_model_id(row)
        known_ids.add(model_id)
        runtime = (row.runtime or "gguf").lower()
        supported = runtime in {"gguf", "mlx"}
        identity_matches = bool(
            active and runtime == "gguf" and _canonical_path(row.path) == active
        )
        assessment = classify_model_readiness(
            ModelReadinessEvidence(
                file_complete=True,
                supported_runtime=supported,
                runtime_identity_matches=identity_matches,
                health_checked=False,
                health_healthy=False,
                benchmark_accepted=False,
                symlink_trusted=True,
            )
        )
        result.append(
            _readiness_row(
                model_id=model_id,
                runtime=runtime,
                name=row.name,
                assessment=assessment,
                parameter_count_b=row.metadata.parameter_count_b,
            )
        )

    for partial in _partial_model_artifacts(root):
        name = _partial_model_name(partial.name)
        model_id = f"gguf:{name}"
        if model_id in known_ids:
            continue
        assessment = classify_model_readiness(
            ModelReadinessEvidence(file_complete=False, symlink_trusted=True)
        )
        result.append(
            _readiness_row(
                model_id=model_id,
                runtime="gguf",
                name=name,
                assessment=assessment,
                parameter_count_b=None,
            )
        )
        known_ids.add(model_id)

    for entry in manifest_entries or []:
        state = _manifest_state(getattr(entry, "estimated_status", ""))
        if state == "installed":
            continue
        repo = str(getattr(entry, "repo", "") or "manifest-model")
        runtime = str(getattr(entry, "runtime_type", "") or "gguf").lower()
        model_id = f"manifest:{repo}"
        assessment = classify_model_readiness(
            ModelReadinessEvidence(
                manifest_state=state,
                symlink_trusted=True,
            )
        )
        result.append(
            _readiness_row(
                model_id=model_id,
                runtime=runtime,
                name=repo,
                assessment=assessment,
                parameter_count_b=None,
                modality=_modality_for_text(
                    " ".join(
                        [
                            str(getattr(entry, "category", "") or ""),
                            str(getattr(entry, "role", "") or ""),
                            str(getattr(entry, "notes", "") or ""),
                        ]
                    )
                ),
            )
        )
    return sorted(result, key=lambda item: item.model_id.lower())


def _readiness_row(
    *,
    model_id: str,
    runtime: str,
    name: str,
    assessment,
    parameter_count_b: float | None,
    modality: str | None = None,
) -> LocalModelReadinessInfo:
    return LocalModelReadinessInfo(
        model_id=model_id,
        format=runtime,
        modality=modality or _modality_for_text(name),
        readiness=assessment.readiness,
        readiness_reason=assessment.readiness_reason,
        measured_tier=_measured_tier(parameter_count_b),
        accepted_roles=(),
        route_eligible=assessment.route_eligible,
    )


def _inventory_model_id(model: LocalModelInfo) -> str:
    return f"{(model.runtime or 'gguf').lower()}:{model.name}"


def _canonical_path(value: str) -> str:
    if not value:
        return ""
    try:
        return str(Path(value).expanduser().resolve())
    except OSError:
        return ""


def _partial_model_artifacts(root: Path) -> list[Path]:
    paths: list[Path] = []
    try:
        for current, _directories, filenames in os.walk(root, followlinks=False):
            for filename in filenames:
                candidate = Path(current) / filename
                if candidate.is_symlink() or "manifests" in candidate.parts:
                    continue
                if candidate.name.lower().endswith(_SKIP_SUFFIXES):
                    paths.append(candidate)
    except OSError:
        return paths
    return paths


def _partial_model_name(name: str) -> str:
    lowered = name.lower()
    for suffix in _SKIP_SUFFIXES:
        if lowered.endswith(suffix):
            return name[: -len(suffix)].removesuffix(".gguf")
    return Path(name).stem


def _manifest_state(status: str) -> str:
    normalized = str(status or "").lower()
    if "removed" in normalized or "retired" in normalized:
        return "removed"
    if "planned" in normalized:
        return "planned"
    return "installed"


def _modality_for_text(value: str) -> str:
    normalized = value.lower()
    if any(
        marker in normalized
        for marker in ("speech", "stt", "tts", "voice", "whisper", "audio")
    ):
        return "audio"
    if any(marker in normalized for marker in ("vision", "image", "vl")):
        return "image"
    return "text"


def _measured_tier(parameter_count_b: float | None) -> str | None:
    if parameter_count_b is None:
        return None
    if parameter_count_b <= 4:
        return "light"
    if parameter_count_b <= 14:
        return "standard"
    return "heavyweight"


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


def _named_roots(
    model_dir: Path,
    name: str,
    trusted_external_roots: object | None = None,
) -> list[Path]:
    # A user-selected root may itself be a symlink, but a category beneath
    # that root is an external boundary and needs the explicit pair trust.
    if model_dir.name == name:
        return [model_dir]
    candidate = model_dir / name
    if candidate.is_symlink():
        records = [
            item
            for item in (trusted_external_roots or [])
            if isinstance(item, ExternalModelRootTrust)
        ]
        target = _trusted_link_target(candidate, records)
        return [target] if target is not None else []
    return [candidate] if candidate.exists() and candidate.is_dir() else []


def _mlx_roots(
    model_dir: Path,
    trusted_external_roots: object | None = None,
) -> list[Path]:
    return _named_roots(model_dir, "MLX", trusted_external_roots)


def _transformers_roots(
    model_dir: Path,
    trusted_external_roots: object | None = None,
) -> list[Path]:
    return _named_roots(model_dir, "Transformers", trusted_external_roots)


def _experimental_roots(
    model_dir: Path,
    trusted_external_roots: object | None = None,
) -> list[Path]:
    return _named_roots(model_dir, "Experimental", trusted_external_roots)


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


def _enumerate_mlx_models(
    model_dir: Path,
    trusted_external_roots: object | None = None,
) -> list[LocalModelInfo]:
    rows: list[LocalModelInfo] = []
    for root in _mlx_roots(model_dir, trusted_external_roots):
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


def _enumerate_transformers_models(
    model_dir: Path,
    trusted_external_roots: object | None = None,
) -> list[LocalModelInfo]:
    rows: list[LocalModelInfo] = []
    for root in _transformers_roots(model_dir, trusted_external_roots):
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


def _enumerate_experimental_models(
    model_dir: Path,
    trusted_external_roots: object | None = None,
) -> list[LocalModelInfo]:
    rows: list[LocalModelInfo] = []
    for root in _experimental_roots(model_dir, trusted_external_roots):
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


def enumerate_models(
    model_dir: Path | str,
    *,
    trusted_external_roots: object | None = None,
) -> list[LocalModelInfo]:
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
    candidates = _gguf_files_without_following_symlinks(dir_path)
    for approved_target in _trusted_external_targets(
        dir_path,
        trusted_external_roots,
    ):
        candidates.extend(_gguf_files_without_following_symlinks(approved_target))

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
        results.append(
            LocalModelInfo(
                name=p.stem,
                path=str(p),
                metadata=md,
            )
        )

    results.extend(_enumerate_mlx_models(dir_path, trusted_external_roots))
    results.extend(_enumerate_transformers_models(dir_path, trusted_external_roots))
    results.extend(_enumerate_experimental_models(dir_path, trusted_external_roots))

    # Stable ordering for the UI — newest-first so a freshly downloaded
    # model lands at the top of the table.
    results.sort(key=lambda m: m.name.lower())
    return results
