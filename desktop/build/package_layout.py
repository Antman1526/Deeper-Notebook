"""Shared source-tree layout for PyInstaller data and package-stage proofs."""

from __future__ import annotations

import shutil
from pathlib import Path

UPSTREAM_PACKAGE_TREES = (
    ("deeper_notebook", "upstream/deeper_notebook"),
    ("open_notebook", "upstream/open_notebook"),
)


def standalone_frontend_root(standalone_root: Path) -> Path:
    """Return the one Next standalone application directory.

    Next can preserve a workspace-relative path below ``.next/standalone``.
    PyInstaller must package the directory that directly owns the application
    ``server.js`` as ``frontend/``; copying the standalone root leaves the
    launcher looking for a non-existent top-level server entry point.
    """
    candidates = sorted(
        {
            server.parent
            for server in standalone_root.rglob("server.js")
            if (server.parent / ".next").is_dir()
            and (server.parent / "package.json").is_file()
        }
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one Next standalone frontend root under "
            f"{standalone_root}, found {len(candidates)}"
        )
    return candidates[0]


def standalone_frontend_node_modules(standalone_root: Path) -> Path:
    """Return the one standalone dependency directory that contains Next.

    With a workspace build, Next can place the application ``server.js``
    below the workspace-relative path while leaving its traced dependencies
    below the package-relative path.  Both locations must be flattened into
    the packaged ``frontend/`` root or the writable runtime copy cannot
    resolve ``require('next')``.
    """
    candidates = sorted(
        node_modules
        for node_modules in standalone_root.rglob("node_modules")
        if (node_modules / "next").is_dir()
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one Next standalone node_modules directory under "
            f"{standalone_root}, found {len(candidates)}"
        )
    return candidates[0]


def pyinstaller_upstream_package_datas(
    project_root: Path,
) -> list[tuple[str, str]]:
    """Return the canonical and compatibility source trees for PyInstaller."""
    return [
        (str(project_root / source), destination)
        for source, destination in UPSTREAM_PACKAGE_TREES
    ]


def stage_upstream_packages(
    *,
    project_root: Path,
    stage_root: Path,
) -> Path:
    """Materialize the same package trees that PyInstaller receives."""
    for source, destination in UPSTREAM_PACKAGE_TREES:
        source_path = project_root / source
        if not source_path.is_dir():
            raise FileNotFoundError(f"package source tree is missing: {source_path}")
        destination_path = stage_root / destination
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source_path,
            destination_path,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    return stage_root
