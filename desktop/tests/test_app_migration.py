"""Safety contracts for the renamed macOS application bundle."""

from __future__ import annotations

import json
import plistlib
import shutil
import sys
import types
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from desktop import app_migration
from desktop.app_migration import (
    COMPATIBLE_BUNDLE_ID,
    AppReplacementRefused,
    detect_legacy_app_replacement,
    replace_legacy_app,
)


def _app(applications: Path, name: str, bundle_id: str) -> Path:
    app = applications / name
    contents = app / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as plist:
        plistlib.dump({"CFBundleIdentifier": bundle_id}, plist)
    return app


def test_same_bundle_coexistence_exposes_one_time_recovery_card(tmp_path: Path) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    canonical = _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"

    decision = detect_legacy_app_replacement(applications, data_root)

    assert decision.state == "recovery-available"
    assert decision.show_recovery_card is True
    assert decision.action == "move-legacy-app-to-trash"
    assert decision.legacy_app == legacy
    assert decision.canonical_app == canonical
    assert decision.receipt_path.parent == data_root


@pytest.mark.parametrize(
    "present_name",
    [None, "Open Notebook Plus.app", "Deeper Notebook.app"],
)
def test_detection_is_a_no_op_unless_both_exact_apps_exist(
    tmp_path: Path, present_name: str | None
) -> None:
    applications = tmp_path / "Applications"
    applications.mkdir()
    if present_name:
        _app(applications, present_name, COMPATIBLE_BUNDLE_ID)

    decision = detect_legacy_app_replacement(
        applications, tmp_path / ".deeper-notebook"
    )

    assert decision.state == "not-needed"
    assert decision.show_recovery_card is False


def test_detection_refuses_mismatched_bundle_identity(tmp_path: Path) -> None:
    applications = tmp_path / "Applications"
    _app(applications, "Open Notebook Plus.app", "example.wrong.legacy")
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)

    decision = detect_legacy_app_replacement(
        applications, tmp_path / ".deeper-notebook"
    )

    assert decision.state == "refused"
    assert decision.reason_code == "bundle-identifier-mismatch"
    assert decision.show_recovery_card is False


def test_default_detection_resolves_canonical_receipt_root_without_migrating_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    applications = tmp_path / "Applications"
    _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    def unexpected_data_migration() -> Path:
        raise AssertionError("pure app detection must not resolve/migrate desktop data")

    monkeypatch.setattr(
        "desktop.data_root.active_data_root", unexpected_data_migration
    )

    decision = detect_legacy_app_replacement(applications)

    assert decision.receipt_path.parent == tmp_path / "home" / ".deeper-notebook"


def test_explicit_replacement_uses_recoverable_move_and_writes_one_receipt(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    trash = tmp_path / "Trash"

    def recycle(source: Path) -> Path:
        trash.mkdir()
        destination = trash / source.name
        shutil.move(source, destination)
        return destination

    receipt_path = replace_legacy_app(
        legacy,
        applications_dir=applications,
        data_root=data_root,
        recycler=recycle,
    )

    assert not legacy.exists()
    assert (trash / legacy.name).is_dir()
    assert receipt_path.is_file()
    receipts = list(data_root.glob("app-bundle-replacement*.json"))
    assert receipts == [receipt_path]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["bundle_identifier"] == COMPATIBLE_BUNDLE_ID
    assert receipt["legacy_app"] == str(legacy)
    assert receipt["trash_destination"] == str(trash / legacy.name)
    assert "delete" not in json.dumps(receipt).lower()

    decision = detect_legacy_app_replacement(applications, data_root)
    assert decision.state == "already-recovered"
    assert decision.show_recovery_card is False


def test_replacement_refuses_wrong_or_outside_exact_legacy_bundle(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "Applications"
    exact = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    renamed = _app(applications, "Old Copy.app", COMPATIBLE_BUNDLE_ID)
    outside = _app(tmp_path / "Other", "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    calls: list[Path] = []

    for candidate in (renamed, outside):
        with pytest.raises(AppReplacementRefused, match="exact legacy"):
            replace_legacy_app(
                candidate,
                applications_dir=applications,
                data_root=tmp_path / ".deeper-notebook",
                recycler=lambda path: calls.append(path) or path,
            )

    assert exact.is_dir()
    assert calls == []


def test_replacement_refuses_symlink_substitution_before_recycling(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "Applications"
    real = _app(tmp_path / "Elsewhere", "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    applications.mkdir()
    legacy = applications / "Open Notebook Plus.app"
    legacy.symlink_to(real, target_is_directory=True)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)

    with pytest.raises(AppReplacementRefused, match="symlink"):
        replace_legacy_app(
            legacy,
            applications_dir=applications,
            data_root=tmp_path / ".deeper-notebook",
            recycler=lambda path: path,
        )


def test_completed_receipt_makes_replacement_one_time(tmp_path: Path) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    data_root.mkdir()
    receipt = data_root / "app-bundle-replacement.json"
    receipt.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    with pytest.raises(AppReplacementRefused, match="already completed"):
        replace_legacy_app(
            legacy,
            applications_dir=applications,
            data_root=data_root,
            recycler=lambda path: path,
        )

    assert legacy.is_dir()


def test_native_recycler_uses_headless_nsfilemanager_trash_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "Open Notebook Plus.app"
    destination = tmp_path / "Trash" / source.name
    calls: list[object] = []

    class FakeURL:
        @staticmethod
        def fileURLWithPath_(path: str) -> str:
            calls.append(("url", path))
            return f"url:{path}"

    class ResultURL:
        def path(self) -> str:
            return str(destination)

    class FakeManager:
        def trashItemAtURL_resultingItemURL_error_(
            self, url: object, result: object, error: object
        ) -> tuple[bool, ResultURL, None]:
            calls.append(("trash", url, result, error))
            return True, ResultURL(), None

    class FakeFileManager:
        @staticmethod
        def defaultManager() -> FakeManager:
            return FakeManager()

    monkeypatch.setattr(app_migration.sys, "platform", "darwin")
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        types.SimpleNamespace(NSFileManager=FakeFileManager, NSURL=FakeURL),
    )
    assert app_migration._native_macos_recycle(source) == destination
    assert calls == [
        ("url", str(source)),
        ("trash", f"url:{source}", None, None),
    ]
