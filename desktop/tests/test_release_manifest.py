"""Release manifest CLI contract tests."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "release_manifest.py"
INSTALLER_SCRIPT = REPOSITORY_ROOT / "desktop" / "build" / "deeper-notebook.iss"
WORKFLOW_FILE = REPOSITORY_ROOT / ".github" / "workflows" / "build-desktop.yml"
WINDOWS_WORKFLOW_FILE = (
    REPOSITORY_ROOT / ".github" / "workflows" / "build-windows.yml"
)
PYINSTALLER_SPEC = REPOSITORY_ROOT / "desktop" / "build" / "pyinstaller.spec"
MAC_POST_BUILD = REPOSITORY_ROOT / "desktop" / "build" / "post_build_mac.sh"
WINDOWS_POST_BUILD = (
    REPOSITORY_ROOT / "desktop" / "build" / "post_build_windows.ps1"
)
WINDOWS_BUILD = REPOSITORY_ROOT / "desktop" / "build" / "build_windows.ps1"
MAKEFILE = REPOSITORY_ROOT / "Makefile"

COMPATIBLE_BUNDLE_ID = "com.antman1526.open-notebook-plus"
STABLE_WINDOWS_APP_ID = "{{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}"


def run_manifest(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_writes_manifest_with_artifact_integrity_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "Deeper-Notebook-mac-arm64.dmg"
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
    artifact = tmp_path / "Deeper-Notebook-mac-arm64.dmg"
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
    artifact = tmp_path / "Deeper-Notebook-mac-arm64.dmg"
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
    assert 'Source: "dist\\Deeper Notebook\\*"' in installer
    assert "PrivilegesRequired=lowest" in installer
    assert "PrivilegesRequiredOverridesAllowed" not in installer
    assert '"/DIR=""$installDir"""' in workflow
    assert "$installProcess = Start-Process" in workflow
    assert "if ($installProcess.ExitCode -ne 0)" in workflow
    assert "$repairProcess = Start-Process" in workflow
    assert "if ($repairProcess.ExitCode -ne 0)" in workflow
    assert "$uninstallProcess = Start-Process" in workflow
    assert "if ($uninstallProcess.ExitCode -ne 0)" in workflow
    assert workflow.count("verify_windows_uninstall.py") == 2


def test_release_surfaces_use_exact_deeper_notebook_artifact_names() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    compatibility_start = workflow.index("  macos-compatibility-upgrade:")
    release_start = workflow.index("  release:")
    active_workflow = workflow[:compatibility_start] + workflow[release_start:]
    release_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            WINDOWS_WORKFLOW_FILE,
            PYINSTALLER_SPEC,
            MAC_POST_BUILD,
            WINDOWS_POST_BUILD,
            WINDOWS_BUILD,
            INSTALLER_SCRIPT,
        )
    ) + active_workflow

    for artifact_name in (
        "Deeper-Notebook-mac-arm64.dmg",
        "Deeper-Notebook-mac-x86_64.dmg",
        "Deeper-Notebook-windows-x64.zip",
        "Deeper-Notebook-Setup-x64.exe",
    ):
        assert artifact_name in release_sources
    assert "Open-Notebook-Plus-" not in release_sources


def test_macos_checksum_manifests_are_portable_after_artifact_download() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")

    assert (
        "cd release\n"
        "          shasum -a 256 Deeper-Notebook-mac-arm64.dmg > SHA256SUMS"
        in workflow
    )
    assert (
        "cd release\n"
        "          shasum -a 256 Deeper-Notebook-mac-x86_64.dmg > SHA256SUMS"
        in workflow
    )
    assert "shasum -a 256 release/Deeper-Notebook-mac-" not in workflow


def test_windows_checksum_manifests_are_portable_after_artifact_download() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")

    assert workflow.count("| Set-Content -NoNewline -Encoding utf8") == 2
    assert (
        '"  Deeper-Notebook-windows-x64.zip" '
        "| Set-Content -NoNewline -Encoding utf8 "
        "release/windows-zip/SHA256SUMS"
        in workflow
    )
    assert (
        '"  Deeper-Notebook-Setup-x64.exe" '
        "| Set-Content -NoNewline -Encoding utf8 "
        "release/windows-setup/SHA256SUMS"
        in workflow
    )


def test_pyinstaller_uses_canonical_visible_names_and_compatible_bundle_id() -> None:
    spec = PYINSTALLER_SPEC.read_text(encoding="utf-8")

    assert 'name="Deeper Notebook"' in spec
    assert 'name="Deeper Notebook.app"' in spec
    assert '"CFBundleName": "Deeper Notebook"' in spec
    assert '"CFBundleDisplayName": "Deeper Notebook"' in spec
    assert "Deeper Notebook uses your microphone" in spec
    assert f'bundle_identifier="{COMPATIBLE_BUNDLE_ID}"' in spec
    assert "compatibility identifier" in spec.lower()
    assert '"desktop.app_migration"' in spec


def test_installer_rebrands_visible_identity_but_pins_upgrade_app_id() -> None:
    installer = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert '#define MyAppName "Deeper Notebook"' in installer
    assert '#define MyAppExeName "Deeper Notebook.exe"' in installer
    assert f"AppId={STABLE_WINDOWS_APP_ID}" in installer
    assert "DefaultDirName={localappdata}\\Programs\\Deeper Notebook" in installer
    assert "OutputBaseFilename=Deeper-Notebook-Setup-x64" in installer
    assert 'Name: "{app}\\Open Notebook Plus.exe"' in installer


def test_legacy_installer_filename_was_git_moved() -> None:
    assert INSTALLER_SCRIPT.is_file()
    assert not (
        REPOSITORY_ROOT / "desktop" / "build" / "open-notebook-plus.iss"
    ).exists()


def test_compatibility_jobs_build_exact_approved_baseline_in_separate_worktree() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")

    assert "macos-compatibility-upgrade:" in workflow
    assert "windows-compatibility-upgrade:" in workflow
    assert workflow.count("7888102") >= 2
    assert workflow.count("git worktree add") >= 2
    assert "legacy-source" in workflow
    assert "synthetic-state" in workflow
    assert "state-before.sha256" in workflow
    assert "state-after.sha256" in workflow
    assert "desktop.app_migration" in workflow
    assert "Open Notebook Plus.app" in workflow
    assert "Deeper Notebook.app" in workflow
    assert "Open-Notebook-Plus-Setup-x64.exe" in workflow
    assert "Deeper-Notebook-Setup-x64.exe" in workflow
    assert "Open Notebook Plus.exe" in workflow
    assert "Deeper Notebook.exe" in workflow
    assert "stable AppId" in workflow
    assert "repair test" in workflow.lower()
    assert "upgrade-path" not in workflow.lower()
    assert (
        'Copy-Item "desktop\\requirements.lock" '
        '(Join-Path $legacySource "desktop\\requirements.lock")'
    ) in workflow


def test_compatibility_workflows_never_mutate_real_applications() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")

    assert "/Applications/Open Notebook Plus.app" not in workflow
    assert "/Applications/Deeper Notebook.app" not in workflow
    assert 'applications_dir="$RUNNER_TEMP/Applications"' in workflow


def test_makefile_build_contract_is_portable_and_uses_canonical_outputs() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "/Users/Antman/Desktop/OpenNotebook" not in makefile
    assert "$(BUILD_PY) -m pytest desktop/tests/ desktop/memory/tests/ -q" in makefile
    assert "dist/Deeper Notebook.app" in makefile
    assert "dist/Deeper-Notebook-mac-<arch>.dmg" in makefile
    assert "/Applications/Deeper Notebook.app" in makefile


def test_makefile_prepares_build_venv_before_desktop_memory_precondition_tests() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "build-mac-test: build-mac-venv" in makefile
    assert "$(BUILD_PY) -m pytest desktop/tests/ desktop/memory/tests/ -q" in makefile
    assert "uv run pytest tests/ -q --ignore=tests/integration" in makefile


def test_makefile_requires_a_deep_strict_codesign_verification() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    verify_lines = [
        line for line in makefile.splitlines()
        if "codesign" in line and "--verify" in line
    ]

    assert verify_lines, "the local package build must hard-gate the final seal"
    assert any("--deep" in line and "--strict" in line for line in verify_lines)
    assert all("|| true" not in line for line in verify_lines)
    assert all("|" not in line for line in verify_lines)


def test_installer_version_matches_the_canonical_desktop_version() -> None:
    installer = INSTALLER_SCRIPT.read_text(encoding="utf-8")
    version_source = (REPOSITORY_ROOT / "desktop" / "__init__.py").read_text(
        encoding="utf-8"
    )
    installer_match = re.search(
        r'^#define MyAppVersion "([^"]+)"$', installer, re.MULTILINE
    )
    desktop_match = re.search(
        r'^__version__ = "([^"]+)"$', version_source, re.MULTILINE
    )

    assert installer_match is not None
    assert desktop_match is not None
    assert installer_match.group(1) == desktop_match.group(1) == "0.8.103"


def test_installer_removes_only_the_exact_retired_start_menu_shortcut() -> None:
    installer = INSTALLER_SCRIPT.read_text(encoding="utf-8")
    install_delete = installer.split("[InstallDelete]", 1)[1].split("[Icons]", 1)[0]
    shortcut_cleanup = (
        'Type: files; Name: "{autoprograms}\\Open Notebook Plus.lnk"'
    )

    assert shortcut_cleanup in install_delete
    assert install_delete.count("{autoprograms}") == 1
    assert "Open Notebook Plus" in shortcut_cleanup


def test_compatibility_jobs_probe_real_readiness_then_leave_no_sidecars() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    compatibility = workflow[workflow.index("  macos-compatibility-upgrade:") :]

    assert "wait_for_packaged_ready" in compatibility
    assert "Wait-PackagedReady" in compatibility
    assert "__next_f" in compatibility
    assert "/readyz" in compatibility
    assert "desktop-readiness.json" in compatibility
    assert "sleep 15" not in compatibility
    assert "Start-Sleep -Seconds 15" not in compatibility
    assert "NSRunningApplication" in compatibility
    assert "kill -TERM" in compatibility  # bounded failure cleanup only
    assert "CloseMainWindow()" in compatibility
    assert "sidecar" in compatibility.lower()
    assert "ps eww" not in compatibility
    assert "ps -axo pid=,command=" in compatibility
    assert 'ENVIRON["DEEPER_NOTEBOOK_CI_SCOPE_PATTERN"]' in compatibility
    assert "remaining-sidecars.txt" in compatibility
    assert "applying bounded compatibility cleanup" in compatibility
    assert '"$RUNNER_TEMP/legacy-descendants.txt" legacy' in compatibility
    assert '"$RUNNER_TEMP/canonical-descendants.txt" legacy' not in compatibility
    assert "canonical shutdown remains strict" in compatibility


def test_legacy_macos_probe_requires_a_visible_window_owned_by_legacy_pid() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    compatibility = workflow[workflow.index("  macos-compatibility-upgrade:") :]

    assert "wait_for_pid_visible_window()" in compatibility
    assert "CGWindowListCopyWindowInfo" in compatibility
    assert "kCGWindowOwnerPID" in compatibility
    assert "kCGWindowLayer" in compatibility
    assert "kCGWindowBounds" in compatibility
    assert "kCGWindowName" in compatibility
    assert "kCGWindowOwnerName" in compatibility
    assert (
        'wait_for_pid_visible_window "$legacy_pid" '
        '"Open notebook+" "Open notebook+"'
    ) in compatibility
    assert compatibility.index(
        'wait_for_pid_visible_window "$legacy_pid"'
    ) < compatibility.index(
        'graceful_stop_and_assert_clean \\\n            "$legacy_pid"'
    )


def test_windows_upgrade_leaves_only_the_canonical_start_menu_shortcut() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    compatibility = workflow[workflow.index("  windows-compatibility-upgrade:") :]

    assert "[Environment]::GetFolderPath('Programs')" in compatibility
    assert "[Environment]::GetFolderPath('CommonPrograms')" in compatibility
    assert (
        '$canonicalShortcuts = @($programs | ForEach-Object { '
        'Join-Path $_ "Deeper Notebook.lnk" } | Where-Object { Test-Path $_ })'
        in compatibility
    )
    assert (
        '$legacyShortcuts = @($programs | ForEach-Object { '
        'Join-Path $_ "Open Notebook Plus.lnk" } | Where-Object { Test-Path $_ })'
        in compatibility
    )
    assert "Expected one canonical Start Menu shortcut" in compatibility
    assert "Retired Start Menu shortcut remains" in compatibility


def test_macos_dmg_creation_retries_only_resource_busy_and_verifies_image() -> None:
    post_build = MAC_POST_BUILD.read_text(encoding="utf-8")

    assert "DMG_CREATE_ATTEMPTS=3" in post_build
    assert '"Resource busy"' in post_build
    assert "hdiutil verify" in post_build
    assert "exit \"${_status}\"" in post_build


def test_windows_installer_replaces_and_removes_reserved_internal_tree() -> None:
    installer = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    internal_cleanup = 'Type: filesandordirs; Name: "{app}\\_internal"'
    assert installer.count(internal_cleanup) == 2
    assert "[InstallDelete]" in installer
    assert "[UninstallDelete]" in installer


def test_windows_repair_closes_package_before_replacing_internal_tree() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    stopper = (
        REPOSITORY_ROOT / "desktop" / "build" / "stop_windows_package.ps1"
    ).read_text(encoding="utf-8")

    assert (
        "pwsh desktop/build/stop_windows_package.ps1 "
        "-ProcessId $process.Id -ScopePath \"$installDir\""
    ) in workflow
    assert "Stop-Process -Id $process.Id -Force" not in workflow
    assert "CloseMainWindow()" in stopper
    assert "WaitForExit(90000)" in stopper
    assert "Get-CimInstance Win32_Process" in stopper
