"""Release manifest CLI contract tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "release_manifest.py"
INSTALLER_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "open-notebook-plus.iss"
WORKFLOW_FILE = REPOSITORY_ROOT / ".github" / "workflows" / "build-desktop.yml"


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


def test_rejects_invalid_platform_or_architecture(tmp_path: Path) -> None:
    artifact = tmp_path / "Open-Notebook-Plus-mac-arm64.dmg"
    artifact.write_bytes(b"release artifact")
    output = tmp_path / "release-manifest.json"

    invalid_platform = run_manifest(
        "--artifact",
        str(artifact),
        "--platform",
        "linux",
        "--arch",
        "arm64",
        "--output",
        str(output),
    )
    invalid_architecture = run_manifest(
        "--artifact",
        str(artifact),
        "--platform",
        "macos",
        "--arch",
        "ppc64",
        "--output",
        str(output),
    )

    assert invalid_platform.returncode != 0
    assert "invalid choice" in invalid_platform.stderr
    assert invalid_architecture.returncode != 0
    assert "invalid choice" in invalid_architecture.stderr


def test_rejects_output_that_would_overwrite_the_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "Open-Notebook-Plus-mac-arm64.dmg"
    artifact_contents = b"release artifact"
    artifact.write_bytes(artifact_contents)

    result = run_manifest(
        "--artifact",
        str(artifact),
        "--platform",
        "macos",
        "--arch",
        "arm64",
        "--output",
        str(artifact),
    )

    assert result.returncode != 0
    assert "must not overwrite artifact" in result.stderr
    assert artifact.read_bytes() == artifact_contents


def test_writes_manifest_with_same_directory_atomic_replace() -> None:
    source = MANIFEST_SCRIPT.read_text(encoding="utf-8")

    assert "tempfile.NamedTemporaryFile(" in source
    assert "dir=output.parent" in source
    assert "os.replace(temporary_path, output)" in source


def test_windows_installer_and_ci_keep_installation_per_user_and_verifiable() -> None:
    installer = INSTALLER_SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")

    assert "SourceDir=..\\.." in installer
    assert "OutputDir=dist" in installer
    assert 'Source: "dist\\Open Notebook Plus\\*"' in installer
    assert "PrivilegesRequired=lowest" in installer
    assert "PrivilegesRequiredOverridesAllowed" not in installer
    assert '"/DIR=""$installDir"""' in workflow
    assert "$installProcess = Start-Process" in workflow
    assert "if ($installProcess.ExitCode -ne 0)" in workflow
    assert "$upgradeProcess = Start-Process" in workflow
    assert "if ($upgradeProcess.ExitCode -ne 0)" in workflow
    assert "$uninstallProcess = Start-Process" in workflow
    assert "if ($uninstallProcess.ExitCode -ne 0)" in workflow
    assert "if (Test-Path $installDir)" in workflow
