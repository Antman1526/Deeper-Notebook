"""Release manifest CLI contract tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "release_manifest.py"


def run_manifest(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_writes_manifest_with_artifact_integrity_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "Open-Notebook-Plus-mac-arm64.dmg"
    artifact.write_bytes(b"release artifact")
    output = tmp_path / "release-manifest.json"

    result = run_manifest(
        "--artifact",
        str(artifact),
        "--platform",
        "macos",
        "--arch",
        "arm64",
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["desktop_version"]
    assert manifest["git_sha"]
    assert manifest["build_time"].endswith("Z")
    assert manifest["platform"] == "macos"
    assert manifest["architecture"] == "arm64"
    assert manifest["artifact_filename"] == artifact.name
    assert manifest["byte_size"] == artifact.stat().st_size
    assert manifest["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_rejects_missing_or_empty_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "release-manifest.json"
    missing = run_manifest(
        "--artifact",
        str(tmp_path / "missing.dmg"),
        "--platform",
        "macos",
        "--arch",
        "arm64",
        "--output",
        str(output),
    )
    empty_artifact = tmp_path / "empty.dmg"
    empty_artifact.touch()
    empty = run_manifest(
        "--artifact",
        str(empty_artifact),
        "--platform",
        "macos",
        "--arch",
        "arm64",
        "--output",
        str(output),
    )

    assert missing.returncode != 0
    assert "does not exist" in missing.stderr
    assert empty.returncode != 0
    assert "empty" in empty.stderr
