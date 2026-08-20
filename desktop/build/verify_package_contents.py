"""Verify built wheel and frozen-stage Python package contents."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

LEGACY_SHIM_FILES = (
    "__init__.py",
    "_alias.py",
)
REQUIRED_CANONICAL_RUNTIME_FILES = (
    "domain/notebook.py",
    "database/migrations/1.surrealql",
    "prompt_optimizer/skillopt_base.yaml",
    "prompt_optimizer/skillopt_prompts/README.md",
    "ai/assets/test_speech.mp3",
)


class PackageContentError(RuntimeError):
    """A built artifact is missing its required Python package contents."""


def _require_exact_legacy_shim(paths: list[str], *, prefix: str) -> list[str]:
    actual = sorted(path for path in paths if path.startswith(prefix))
    expected = sorted(f"{prefix}{name}" for name in LEGACY_SHIM_FILES)
    if actual != expected:
        raise PackageContentError(
            f"legacy shim must contain exactly {expected}; found {actual}"
        )
    return actual


def _require_canonical_runtime(paths: list[str], *, prefix: str) -> list[str]:
    canonical = sorted(path for path in paths if path.startswith(prefix))
    missing = [
        f"{prefix}{relative}"
        for relative in REQUIRED_CANONICAL_RUNTIME_FILES
        if f"{prefix}{relative}" not in canonical
    ]
    if missing:
        raise PackageContentError(
            "canonical package runtime files are missing: " + ", ".join(missing)
        )
    return canonical


def inspect_wheel(wheel_path: Path) -> dict[str, list[str]]:
    """Inspect a real wheel archive for canonical data and the exact shim."""
    if not wheel_path.is_file():
        raise PackageContentError(f"wheel does not exist: {wheel_path}")
    with zipfile.ZipFile(wheel_path) as archive:
        paths = sorted(
            name for name in archive.namelist() if name and not name.endswith("/")
        )
    return {
        "canonical_runtime": _require_canonical_runtime(
            paths,
            prefix="deeper_notebook/",
        ),
        "legacy_shim": _require_exact_legacy_shim(
            paths,
            prefix="open_notebook/",
        ),
    }


def _find_upstream_tree(frozen_root: Path) -> Path:
    candidates = [
        candidate
        for candidate in [frozen_root / "upstream", *frozen_root.rglob("upstream")]
        if (candidate / "deeper_notebook").is_dir()
        and (candidate / "open_notebook").is_dir()
    ]
    unique_candidates = list(
        dict.fromkeys(candidate.resolve() for candidate in candidates)
    )
    if len(unique_candidates) != 1:
        raise PackageContentError(
            "expected exactly one frozen upstream tree containing "
            "deeper_notebook and open_notebook; found "
            + ", ".join(str(candidate) for candidate in unique_candidates)
        )
    return unique_candidates[0]


def inspect_frozen_root(frozen_root: Path) -> dict[str, list[str]]:
    """Inspect an actual staging or PyInstaller root for both package trees."""
    if not frozen_root.is_dir():
        raise PackageContentError(f"frozen root does not exist: {frozen_root}")
    upstream = _find_upstream_tree(frozen_root)
    paths = sorted(
        f"upstream/{path.relative_to(upstream).as_posix()}"
        for path in upstream.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    return {
        "package_roots": [
            "upstream/deeper_notebook",
            "upstream/open_notebook",
        ],
        "canonical_runtime": _require_canonical_runtime(
            paths,
            prefix="upstream/deeper_notebook/",
        ),
        "legacy_shim": _require_exact_legacy_shim(
            paths,
            prefix="upstream/open_notebook/",
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, action="append", default=[])
    parser.add_argument("--frozen-root", type=Path, action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.wheel and not args.frozen_root:
        raise SystemExit("at least one --wheel or --frozen-root is required")
    receipt: dict[str, dict[str, Any]] = {"wheels": {}, "frozen_roots": {}}
    for wheel in args.wheel:
        receipt["wheels"][str(wheel)] = inspect_wheel(wheel)
    for frozen_root in args.frozen_root:
        receipt["frozen_roots"][str(frozen_root)] = inspect_frozen_root(frozen_root)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
