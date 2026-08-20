"""Safety contracts for the renamed macOS application bundle."""

from __future__ import annotations

import json
import plistlib
import shutil
import sys
import threading
import types
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from desktop import app as desktop_app
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

    monkeypatch.setattr("desktop.data_root.active_data_root", unexpected_data_migration)

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


def test_bridge_pre_move_receipt_failure_reports_confirmed_not_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop.window import _OnpJsApi

    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    controller = app_migration.AppRecoveryController.detect(
        applications_dir=applications,
        data_root=tmp_path / ".deeper-notebook",
        recycler=lambda path: path,
    )
    monkeypatch.setattr(
        app_migration,
        "_write_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = _OnpJsApi(controller).replace_old_app(True)

    assert result["ok"] is False
    assert result["move_outcome"] == "not-moved"
    assert "was not moved" in result["error"]
    assert "verify" not in result["error"].lower()
    assert legacy.is_dir()


def test_bridge_post_trash_receipt_failure_reports_uncertain_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop.window import _OnpJsApi

    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    trash = tmp_path / "Trash"

    def recycle(source: Path) -> Path:
        trash.mkdir()
        destination = trash / source.name
        shutil.move(source, destination)
        return destination

    controller = app_migration.AppRecoveryController.detect(
        applications_dir=applications,
        data_root=tmp_path / ".deeper-notebook",
        recycler=recycle,
    )
    real_write = app_migration._write_receipt

    def fail_completed(directory, path: Path, receipt: dict[str, object]) -> None:
        if receipt["status"] == "completed":
            raise OSError("final receipt failed")
        real_write(directory, path, receipt)

    monkeypatch.setattr(app_migration, "_write_receipt", fail_completed)

    result = _OnpJsApi(controller).replace_old_app(True)

    assert result["ok"] is False
    assert result["move_outcome"] == "moved-receipt-uncertain"
    assert "Verify the macOS Trash" in result["error"]
    assert "was not moved" not in result["error"]
    assert not legacy.exists()
    assert (trash / legacy.name).is_dir()


def test_app_receipt_dirfd_cannot_redirect_after_directory_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop.window import _OnpJsApi

    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    canonical_data = tmp_path / ".deeper-notebook"
    canonical_data.mkdir()
    recovery = tmp_path / ".deeper-notebook-recovery"
    recovery.mkdir()
    held = tmp_path / ".recovery-held"
    controller = app_migration.AppRecoveryController.detect(
        applications_dir=applications,
        data_root=recovery,
        recycler=lambda path: path,
    )
    real_replace = app_migration.atomic_replace_json
    raced = False

    def swap_then_replace(directory, name, payload) -> None:
        nonlocal raced
        if payload["status"] == "started" and not raced:
            raced = True
            recovery.rename(held)
            recovery.symlink_to(canonical_data, target_is_directory=True)
        real_replace(directory, name, payload)

    monkeypatch.setattr(
        app_migration,
        "atomic_replace_json",
        swap_then_replace,
    )

    result = _OnpJsApi(controller).replace_old_app(True)

    assert raced is True
    assert result["move_outcome"] == "move-uncertain"
    assert legacy.is_dir()
    assert not (canonical_data / "app-bundle-replacement.json").exists()
    assert not (held / "app-bundle-replacement.json").exists()


def test_replacement_holds_one_receipt_directory_handle_for_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    trash = tmp_path / "Trash"
    real_open = app_migration.open_owned_directory
    opens = 0

    @contextmanager
    def counted_open(path: Path):
        nonlocal opens
        opens += 1
        with real_open(path) as directory:
            yield directory

    def recycle(source: Path) -> Path:
        trash.mkdir()
        destination = trash / source.name
        shutil.move(source, destination)
        return destination

    monkeypatch.setattr(app_migration, "open_owned_directory", counted_open)

    replace_legacy_app(
        legacy,
        applications_dir=applications,
        data_root=data_root,
        recycler=recycle,
    )

    assert opens == 1


def test_receipt_cleanup_unlink_stays_on_held_dirfd_after_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    recovery = tmp_path / ".deeper-notebook-recovery"
    recovery.mkdir()
    held = tmp_path / ".recovery-held"
    canonical = tmp_path / ".deeper-notebook"
    canonical.mkdir()
    canonical_receipt = canonical / "app-bundle-replacement.json"
    canonical_receipt.write_text('{"sentinel": true}\\n', encoding="utf-8")
    real_write = app_migration._write_receipt
    raced = False

    def swap_after_started(*args, **kwargs) -> None:
        nonlocal raced
        receipt = args[-1]
        real_write(*args, **kwargs)
        if receipt["status"] == "started" and not raced:
            raced = True
            recovery.rename(held)
            recovery.symlink_to(canonical, target_is_directory=True)
            legacy.rename(applications / "Original Legacy.app")
            _app(
                applications,
                "Open Notebook Plus.app",
                COMPATIBLE_BUNDLE_ID,
            )

    monkeypatch.setattr(app_migration, "_write_receipt", swap_after_started)

    with pytest.raises(Exception):
        replace_legacy_app(
            legacy,
            applications_dir=applications,
            data_root=recovery,
            recycler=lambda path: path,
        )

    assert raced is True
    assert canonical_receipt.read_text(encoding="utf-8") == ('{"sentinel": true}\\n')
    assert not (held / "app-bundle-replacement.json").exists()


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


def test_detection_refuses_a_symlinked_applications_root(tmp_path: Path) -> None:
    real_applications = tmp_path / "Real Applications"
    _app(real_applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(real_applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    applications = tmp_path / "Applications"
    applications.symlink_to(real_applications, target_is_directory=True)

    decision = detect_legacy_app_replacement(
        applications, tmp_path / ".deeper-notebook"
    )

    assert decision.state == "refused"
    assert decision.reason_code == "unsafe-applications-root"


def test_replacement_refuses_bundle_swap_after_confirmation_without_receipt(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    decision = detect_legacy_app_replacement(applications, data_root)
    original = applications / "Original Legacy.app"
    legacy.rename(original)
    replacement = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    calls: list[Path] = []

    with pytest.raises(AppReplacementRefused, match="changed after confirmation"):
        replace_legacy_app(
            replacement,
            applications_dir=applications,
            data_root=data_root,
            expected_decision=decision,
            recycler=lambda path: calls.append(path) or path,
        )

    assert calls == []
    assert not (data_root / "app-bundle-replacement.json").exists()
    assert original.is_dir()
    assert replacement.is_dir()


def test_replacement_refuses_root_swap_after_confirmation_without_receipt(
    tmp_path: Path,
) -> None:
    applications = tmp_path / "Applications"
    _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    decision = detect_legacy_app_replacement(applications, data_root)
    original_root = tmp_path / "Original Applications"
    applications.rename(original_root)
    applications.mkdir()
    replacement = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    calls: list[Path] = []

    with pytest.raises(AppReplacementRefused, match="changed after confirmation"):
        replace_legacy_app(
            replacement,
            applications_dir=applications,
            data_root=data_root,
            expected_decision=decision,
            recycler=lambda path: calls.append(path) or path,
        )

    assert calls == []
    assert not (data_root / "app-bundle-replacement.json").exists()
    assert (original_root / "Open Notebook Plus.app").is_dir()
    assert replacement.is_dir()


def test_replacement_refuses_bundle_swap_at_final_trash_boundary_without_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    applications = tmp_path / "Applications"
    legacy = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    decision = detect_legacy_app_replacement(applications, data_root)
    original_write = app_migration._write_receipt
    raced = False

    def swap_after_started_receipt(*args, **kwargs) -> None:
        nonlocal raced
        receipt = args[-1]
        original_write(*args, **kwargs)
        if receipt["status"] == "started" and not raced:
            raced = True
            legacy.rename(applications / "Original Legacy.app")
            _app(
                applications,
                "Open Notebook Plus.app",
                COMPATIBLE_BUNDLE_ID,
            )

    monkeypatch.setattr(app_migration, "_write_receipt", swap_after_started_receipt)
    calls: list[Path] = []

    with pytest.raises(AppReplacementRefused, match="changed after confirmation"):
        replace_legacy_app(
            legacy,
            applications_dir=applications,
            data_root=data_root,
            expected_decision=decision,
            recycler=lambda path: calls.append(path) or path,
        )

    assert raced is True
    assert calls == []
    assert not (data_root / "app-bundle-replacement.json").exists()


def test_production_recovery_controller_is_explicit_and_non_persistent_on_keep(
    tmp_path: Path,
) -> None:
    controller_type = getattr(app_migration, "AppRecoveryController", None)
    assert controller_type is not None, "production recovery controller is absent"

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

    controller = controller_type.detect(
        applications_dir=applications,
        data_root=data_root,
        recycler=recycle,
    )
    payload = controller.card_payload()
    assert payload["show_recovery_card"] is True
    assert payload["title"] == "Two Deeper Notebook apps are installed"
    assert payload["replace_label"] == "Replace Old App"
    assert payload["keep_label"] == "Keep Both"

    controller.keep_both()
    assert legacy.is_dir()
    assert not (data_root / "app-bundle-replacement.json").exists()
    assert controller.card_payload()["show_recovery_card"] is False

    resurfaced = controller_type.detect(
        applications_dir=applications,
        data_root=data_root,
        recycler=recycle,
    )
    assert resurfaced.card_payload()["show_recovery_card"] is True
    receipt = resurfaced.replace_old_app(confirmed=True)
    assert receipt.is_file()
    assert not legacy.exists()
    assert resurfaced.card_payload()["show_recovery_card"] is False


def test_startup_phase_detects_recovery_and_passes_it_to_the_packaged_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = getattr(desktop_app, "_phase_detect_app_recovery", None)
    assert phase is not None, "desktop startup never runs app-bundle detection"

    applications = tmp_path / "Applications"
    _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)
    _app(applications, "Deeper Notebook.app", COMPATIBLE_BUNDLE_ID)
    data_root = tmp_path / ".deeper-notebook"
    ctx = desktop_app._new_context()

    phase(ctx, applications_dir=applications, data_root=data_root)

    assert ctx.app_recovery is not None
    assert ctx.app_recovery.card_payload()["show_recovery_card"] is True
    source = Path(desktop_app.__file__).read_text(encoding="utf-8")
    assert "_phase_detect_app_recovery(ctx)" in source
    assert "app_recovery=ctx.app_recovery" in source


def test_production_startup_to_rendered_confirmation_replacement_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import window as desktop_window

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

    ctx = desktop_app._new_context()
    desktop_app._phase_detect_app_recovery(
        ctx,
        applications_dir=applications,
        data_root=data_root,
        recycler=recycle,
    )
    stopped: list[bool] = []
    events: list[tuple[str, str, str]] = []
    ctx.sv = SimpleNamespace(
        frontend_url="http://127.0.0.1:62001/",
        session_env={"INTERNAL_API_URL": "http://127.0.0.1:62000"},
        whisper_port=0,
        piper_port=0,
        stop_all=lambda: stopped.append(True),
    )
    ctx.cfg = SimpleNamespace(
        theme="light-blue",
        openchronicle_choice="skip",
    )
    ctx.progress_bus = SimpleNamespace(
        publish=lambda step, status, message="": events.append((step, status, message))
    )
    ctx.log_dir = data_root / "logs"
    ctx.log_dir.mkdir(parents=True)
    observed: dict[str, object] = {}

    def fake_open_window(*_args, **kwargs) -> None:
        controller = kwargs["app_recovery"]
        payload = controller.card_payload()
        observed["js"] = desktop_window._app_recovery_injection_js(payload)
        bridge = desktop_window._OnpJsApi(controller)
        result = bridge.replace_old_app(True)
        assert result["ok"] is True
        kwargs["on_ready"]()
        marker = ctx.log_dir / "desktop-readiness.json"
        observed["marker"] = json.loads(marker.read_text(encoding="utf-8"))
        kwargs["on_close"]()
        observed["marker_cleared_on_close"] = not marker.exists()

    monkeypatch.setattr(desktop_window, "open_window", fake_open_window)

    desktop_app._phase_open_window(ctx)

    assert "Replace Old App" in str(observed["js"])
    assert "Keep Both" in str(observed["js"])
    assert "confirm(" in str(observed["js"])
    assert not legacy.exists()
    receipt = json.loads(
        (data_root / "app-bundle-replacement.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "completed"
    assert observed["marker"] == {
        "api_url": "http://127.0.0.1:62000",
        "frontend_url": "http://127.0.0.1:62001/",
        "pid": observed["marker"]["pid"],
        "schema_version": 1,
        "status": "ready",
        "window_marker": "__next_f",
    }
    assert observed["marker_cleared_on_close"] is True
    assert not (ctx.log_dir / "desktop-readiness.json").exists()
    assert ("window.ready", "done", "http://127.0.0.1:62001/") in events
    assert stopped


def _window_phase_context(tmp_path: Path, supervisor_stops: list[bool]):
    ctx = desktop_app._new_context()
    ctx.sv = SimpleNamespace(
        frontend_url="http://127.0.0.1:62001/",
        session_env={"INTERNAL_API_URL": "http://127.0.0.1:62000"},
        whisper_port=0,
        piper_port=0,
        stop_all=lambda: supervisor_stops.append(True),
    )
    ctx.cfg = SimpleNamespace(
        theme="light-blue",
        openchronicle_choice="skip",
    )
    ctx.progress_bus = SimpleNamespace(publish=lambda *_args, **_kwargs: None)
    ctx.log_dir = tmp_path / "logs"
    ctx.log_dir.mkdir()
    return ctx


def test_phase_native_termination_callback_tears_down_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import window as desktop_window

    supervisor_stops: list[bool] = []
    runtime_stops: list[bool] = []
    ctx = _window_phase_context(tmp_path, supervisor_stops)

    def fake_open_window(*_args, **kwargs) -> None:
        native_callback = threading.Thread(target=kwargs["on_close"])
        native_callback.start()
        native_callback.join()

    monkeypatch.setattr(desktop_window, "open_window", fake_open_window)
    monkeypatch.setattr(
        desktop_app, "_stop_runtime", lambda _ctx: runtime_stops.append(True)
    )

    desktop_app._phase_open_window(ctx)

    assert supervisor_stops == [True]
    assert runtime_stops == [True]


def test_phase_pywebview_close_callback_tears_down_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import window as desktop_window

    supervisor_stops: list[bool] = []
    runtime_stops: list[bool] = []
    ctx = _window_phase_context(tmp_path, supervisor_stops)

    def fake_open_window(*_args, **kwargs) -> None:
        kwargs["on_close"]()

    monkeypatch.setattr(desktop_window, "open_window", fake_open_window)
    monkeypatch.setattr(
        desktop_app, "_stop_runtime", lambda _ctx: runtime_stops.append(True)
    )

    desktop_app._phase_open_window(ctx)

    assert supervisor_stops == [True]
    assert runtime_stops == [True]


def test_phase_window_startup_exception_tears_down_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import window as desktop_window

    supervisor_stops: list[bool] = []
    runtime_stops: list[bool] = []
    ctx = _window_phase_context(tmp_path, supervisor_stops)

    def fake_open_window(*_args, **_kwargs) -> None:
        raise RuntimeError("window startup failed")

    monkeypatch.setattr(desktop_window, "open_window", fake_open_window)
    monkeypatch.setattr(
        desktop_app, "_stop_runtime", lambda _ctx: runtime_stops.append(True)
    )

    with pytest.raises(RuntimeError, match="window startup failed"):
        desktop_app._phase_open_window(ctx)

    assert supervisor_stops == [True]
    assert runtime_stops == [True]


def test_phase_native_and_pywebview_close_race_tears_down_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import window as desktop_window

    supervisor_stops: list[bool] = []
    runtime_stops: list[bool] = []
    ctx = _window_phase_context(tmp_path, supervisor_stops)

    def fake_open_window(*_args, **kwargs) -> None:
        start = threading.Barrier(3)

        def dispatch_close() -> None:
            start.wait()
            kwargs["on_close"]()

        native_callback = threading.Thread(target=dispatch_close)
        pywebview_callback = threading.Thread(target=dispatch_close)
        native_callback.start()
        pywebview_callback.start()
        start.wait()
        native_callback.join()
        pywebview_callback.join()

    monkeypatch.setattr(desktop_window, "open_window", fake_open_window)
    monkeypatch.setattr(
        desktop_app, "_stop_runtime", lambda _ctx: runtime_stops.append(True)
    )

    desktop_app._phase_open_window(ctx)

    assert supervisor_stops == [True]
    assert runtime_stops == [True]


def test_phase_waits_for_inflight_callback_cleanup_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import window as desktop_window

    supervisor_stops: list[bool] = []
    runtime_stops: list[bool] = []
    cleanup_started = threading.Event()
    allow_cleanup = threading.Event()
    phase_returned = threading.Event()
    callback_threads: list[threading.Thread] = []
    phase_errors: list[BaseException] = []
    ctx = _window_phase_context(tmp_path, supervisor_stops)

    def stop_all() -> None:
        cleanup_started.set()
        if not allow_cleanup.wait(timeout=5):
            raise TimeoutError("test did not release cleanup")
        supervisor_stops.append(True)

    ctx.sv.stop_all = stop_all

    def fake_open_window(*_args, **kwargs) -> None:
        callback = threading.Thread(target=kwargs["on_close"])
        callback_threads.append(callback)
        callback.start()
        assert cleanup_started.wait(timeout=1)

    def run_phase() -> None:
        try:
            desktop_app._phase_open_window(ctx)
        except BaseException as exc:
            phase_errors.append(exc)
        finally:
            phase_returned.set()

    monkeypatch.setattr(desktop_window, "open_window", fake_open_window)
    monkeypatch.setattr(
        desktop_app, "_stop_runtime", lambda _ctx: runtime_stops.append(True)
    )

    phase_thread = threading.Thread(target=run_phase)
    phase_thread.start()
    assert cleanup_started.wait(timeout=1)
    try:
        assert not phase_returned.wait(timeout=0.1)
    finally:
        allow_cleanup.set()
        phase_thread.join(timeout=2)
        for callback in callback_threads:
            callback.join(timeout=2)

    assert not phase_thread.is_alive()
    assert all(not callback.is_alive() for callback in callback_threads)
    assert phase_errors == []
    assert supervisor_stops == [True]
    assert runtime_stops == [True]


def test_tray_quit_and_destroy_close_callback_share_one_runtime_teardown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop import tray as desktop_tray

    supervisor_stops: list[bool] = []
    provider_stops: list[bool] = []
    captured_callbacks: dict[str, object] = {}
    quit_errors: list[BaseException] = []
    ctx = desktop_app._new_context()
    ctx.sv = SimpleNamespace(
        stop_all=lambda: supervisor_stops.append(True),
    )
    ctx.model_provider_runtime = SimpleNamespace(
        stop=lambda: provider_stops.append(True),
    )
    ctx.log_dir = tmp_path / "logs"
    ctx.log_dir.mkdir()

    def capture_tray(**callbacks) -> None:
        captured_callbacks.update(callbacks)

    class Window:
        def destroy(self) -> None:
            runtime_stop_count_at_destroy.append(len(supervisor_stops))
            desktop_app._stop_app_runtime_once(ctx)

    webview = types.ModuleType("webview")
    webview.windows = [Window()]
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(desktop_tray, "install_tray", capture_tray)

    runtime_stop_count_at_destroy: list[int] = []

    desktop_app._phase_install_tray(ctx)

    def invoke_quit() -> None:
        try:
            captured_callbacks["on_quit"]()
        except BaseException as exc:
            quit_errors.append(exc)

    quit_thread = threading.Thread(target=invoke_quit)
    quit_thread.start()
    quit_thread.join(timeout=2)

    assert not quit_thread.is_alive(), "tray Quit deadlocked with close callback"
    assert quit_errors == []
    assert runtime_stop_count_at_destroy == [0]
    assert supervisor_stops == [True]
    assert provider_stops == [True]
