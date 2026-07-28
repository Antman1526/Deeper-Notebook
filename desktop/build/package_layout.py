"""Shared source-tree layout for PyInstaller data and package-stage proofs."""

from __future__ import annotations

import shutil
from pathlib import Path

UPSTREAM_PACKAGE_TREES = (
    ("deeper_notebook", "upstream/deeper_notebook"),
    ("open_notebook", "upstream/open_notebook"),
)


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
