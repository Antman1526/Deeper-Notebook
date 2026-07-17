"""Write integrity metadata for a desktop release artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def desktop_version() -> str:
    namespace: dict[str, str] = {}
    version_file = REPOSITORY_ROOT / "desktop" / "__init__.py"
    exec(version_file.read_text(encoding="utf-8"), namespace)
    return namespace["__version__"]


def git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, text=True
    ).strip()


def build_manifest(artifact: Path, platform: str, architecture: str) -> dict[str, object]:
    if not artifact.is_file():
        raise ValueError(f"artifact does not exist: {artifact}")

    byte_size = artifact.stat().st_size
    if byte_size == 0:
        raise ValueError(f"artifact is empty: {artifact}")

    digest = hashlib.sha256()
    with artifact.open("rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)

    return {
        "desktop_version": desktop_version(),
        "git_sha": git_sha(),
        "build_time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "platform": platform,
        "architecture": architecture,
        "artifact_filename": artifact.name,
        "byte_size": byte_size,
        "sha256": digest.hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_manifest(args.artifact, args.platform, args.arch)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
