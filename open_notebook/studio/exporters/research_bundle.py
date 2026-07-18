"""Integrity-checked, path-safe research bundle exports."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

_MANIFEST_PATH = "manifest.json"


def normalize_bundle_path(value: str) -> str:
    """Accept only normalized, portable relative ZIP entry names."""
    if not value or "\\" in value or "\x00" in value:
        raise ValueError("bundle paths must be non-empty POSIX relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("bundle paths must not contain traversal or empty segments")
    normalized = path.as_posix()
    if normalized != value or normalized == _MANIFEST_PATH:
        raise ValueError("bundle path is not a permitted normalized entry")
    return normalized


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_research_bundle(
    path: Path,
    *,
    artifact: Mapping[str, Any],
    markdown: str,
    citations: list[Mapping[str, Any]],
    source_metadata: list[Mapping[str, Any]],
    evaluation_report: Mapping[str, Any],
    generated_files: Mapping[str, Path] | None = None,
) -> None:
    """Write a ZIP whose manifest hashes every non-manifest entry.

    The manifest intentionally does not hash itself; a self-referential hash
    cannot be stable. Every payload entry is verified on read instead.
    """
    if path.suffix.lower() != ".zip":
        raise ValueError("research bundle path must end in .zip")
    entries: dict[str, bytes] = {
        "artifact.json": _json_bytes(dict(artifact)),
        "artifact.md": markdown.encode("utf-8"),
        "citations.json": _json_bytes(list(citations)),
        "sources.json": _json_bytes(list(source_metadata)),
        "evaluation.json": _json_bytes(dict(evaluation_report)),
    }
    for relative_path, generated_path in (generated_files or {}).items():
        normalized = normalize_bundle_path(relative_path)
        if normalized in entries:
            raise ValueError(f"duplicate bundle path: {normalized}")
        if not generated_path.is_file():
            raise ValueError(f"generated export is missing: {generated_path.name}")
        entries[normalized] = generated_path.read_bytes()

    manifest = {
        "schema_version": 1,
        "format": "open-notebook-plus-research-bundle",
        "entries": [
            {"path": name, "sha256": _sha256(data), "size": len(data)}
            for name, data in sorted(entries.items())
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(entries.items()):
            bundle.writestr(name, data)
        bundle.writestr(_MANIFEST_PATH, _json_bytes(manifest))


def verify_research_bundle(path: Path) -> dict[str, object]:
    """Fail closed when a bundle's paths, manifest, or hashes are invalid."""
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or _MANIFEST_PATH not in names:
            raise ValueError("research bundle has an invalid entry set")
        payload_names = [name for name in names if name != _MANIFEST_PATH]
        for name in payload_names:
            normalize_bundle_path(name)
        manifest = json.loads(bundle.read(_MANIFEST_PATH))
        entries = manifest.get("entries") if isinstance(manifest, dict) else None
        if not isinstance(entries, list):
            raise ValueError("research bundle manifest is invalid")
        expected = {
            entry.get("path"): entry for entry in entries if isinstance(entry, dict)
        }
        if set(expected) != set(payload_names):
            raise ValueError(
                "research bundle manifest entries do not match ZIP entries"
            )
        for name in payload_names:
            entry = expected[name]
            data = bundle.read(name)
            if entry.get("sha256") != _sha256(data) or entry.get("size") != len(data):
                raise ValueError(f"research bundle integrity check failed for {name}")
        return manifest


__all__ = ["build_research_bundle", "normalize_bundle_path", "verify_research_bundle"]
