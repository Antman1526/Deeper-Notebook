from __future__ import annotations

import hashlib
import json
import plistlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from desktop import app as desktop_app
from desktop import data_root
from desktop import window as desktop_window
from desktop.app_migration import (
    COMPATIBLE_BUNDLE_ID,
    AppRecoveryController,
)


def _seed(root: Path, *, theme: str, source: str) -> None:
    files = {
        "config.toml": f"theme='{theme}'\npassword='never-log-this'\n",
        "data/source.txt": source,
    }
    for relative, contents in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _app(applications: Path, name: str) -> Path:
    app = applications / name
    contents = app / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as plist_file:
        plistlib.dump({"CFBundleIdentifier": COMPATIBLE_BUNDLE_ID}, plist_file)
    return app


def test_divergent_roots_enter_read_only_recovery_before_normal_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    _seed(canonical, theme="research-core", source="canonical-private\n")
    _seed(legacy, theme="light-blue", source="legacy-private\n")
    before = (_tree_hash(canonical), _tree_hash(legacy))

    applications = tmp_path / "Applications"
    _app(applications, "Open Notebook Plus.app")
    _app(applications, "Deeper Notebook.app")
    recovery_root = tmp_path / ".deeper-notebook-recovery"
    observed: dict[str, object] = {}

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    real_detect = AppRecoveryController.detect.__func__

    def detect_for_test(cls, **_kwargs):
        return real_detect(
            cls,
            applications_dir=applications,
            data_root=recovery_root,
        )

    monkeypatch.setattr(
        AppRecoveryController,
        "detect",
        classmethod(detect_for_test),
    )

    def fake_recovery_window(
        *,
        conflict_payload,
        app_recovery,
        storage_root,
    ) -> None:
        observed["conflict_payload"] = conflict_payload
        observed["app_payload"] = app_recovery.card_payload()
        observed["storage_root"] = storage_root
        app_recovery.keep_both()

    monkeypatch.setattr(
        desktop_window,
        "open_data_root_recovery_window",
        fake_recovery_window,
        raising=False,
    )

    def unexpected_normal_startup(_ctx) -> None:
        raise AssertionError("conflict recovery must not start normal services")

    for phase_name in (
        "_phase_load_config",
        "_phase_wizard_if_first_run",
        "_phase_bootstrap_runtime",
        "_phase_download_models",
        "_phase_select_provider",
        "_phase_detect_openchronicle",
        "_phase_register_memory_commands",
        "_phase_start_supervisor",
    ):
        monkeypatch.setattr(desktop_app, phase_name, unexpected_normal_startup)

    assert desktop_app.run() == 0

    conflict_payload = observed["conflict_payload"]
    assert conflict_payload["state"] == "migration-conflict"
    assert conflict_payload["reason_code"] == "non-equivalent-roots"
    assert conflict_payload["canonical"]["path"] == str(canonical)
    assert conflict_payload["legacy"]["path"] == str(legacy)
    assert conflict_payload["canonical"]["tree_sha256"] == before[0]
    assert conflict_payload["legacy"]["tree_sha256"] == before[1]
    assert "never-log-this" not in json.dumps(conflict_payload)

    app_payload = observed["app_payload"]
    assert app_payload["show_recovery_card"] is True
    assert app_payload["replace_label"] == "Replace Old App"
    assert app_payload["keep_label"] == "Keep Both"
    assert Path(app_payload["receipt_path"]).parent == recovery_root
    assert observed["storage_root"] == recovery_root

    receipt = recovery_root / "data-root-conflict-recovery.json"
    recovery_log = recovery_root / "logs" / "recovery.log"
    assert receipt.is_file()
    assert recovery_log.is_file()
    assert "never-log-this" not in receipt.read_text(encoding="utf-8")
    assert "never-log-this" not in recovery_log.read_text(encoding="utf-8")
    assert (_tree_hash(canonical), _tree_hash(legacy)) == before


def test_fresh_profile_does_not_enter_conflict_recovery(
    tmp_path: Path,
) -> None:
    ctx = desktop_app._new_context()

    desktop_app._phase_detect_data_root_recovery(ctx, home=tmp_path)

    assert ctx.data_root_decision.state == "not-needed"
    assert ctx.data_root_recovery_root is None
    assert not (tmp_path / ".deeper-notebook").exists()
    assert not (tmp_path / ".open-notebook-plus").exists()
    assert not (tmp_path / ".deeper-notebook-recovery").exists()


def test_legacy_only_profile_keeps_guarded_migration_path(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / ".open-notebook-plus"
    _seed(legacy, theme="research-core", source="legacy-only\n")
    before = _tree_hash(legacy)
    ctx = desktop_app._new_context()

    desktop_app._phase_detect_data_root_recovery(ctx, home=tmp_path)

    canonical = tmp_path / ".deeper-notebook"
    assert ctx.data_root_decision.state == "ready"
    assert ctx.data_root_recovery_root is None
    assert canonical.is_dir()
    assert _tree_hash(canonical) == before
    assert legacy.is_symlink()
    assert legacy.resolve(strict=True) == canonical.resolve(strict=True)
    assert not (tmp_path / ".deeper-notebook-recovery").exists()


def test_conflict_evidence_does_not_select_or_mutate_either_root(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    _seed(canonical, theme="research-core", source="canonical\n")
    _seed(legacy, theme="light-blue", source="legacy\n")
    before = (_tree_hash(canonical), _tree_hash(legacy))
    decision = data_root.classify_roots(canonical, legacy)

    recovery_root, payload = data_root.write_conflict_recovery_evidence(
        decision,
        home=tmp_path,
    )

    assert recovery_root == tmp_path / ".deeper-notebook-recovery"
    assert payload["selected_root"] is None
    assert payload["mutated_roots"] == []
    assert (
        json.loads(
            (recovery_root / "logs" / "recovery.log").read_text(encoding="utf-8")
        )["selected_root"]
        is None
    )
    assert not list(recovery_root.rglob("*.tmp"))
    assert (_tree_hash(canonical), _tree_hash(legacy)) == before


def test_conflict_evidence_rejects_symlinked_or_foreign_recovery_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    _seed(canonical, theme="research-core", source="canonical\n")
    _seed(legacy, theme="light-blue", source="legacy\n")
    before = (_tree_hash(canonical), _tree_hash(legacy))
    decision = data_root.classify_roots(canonical, legacy)
    recovery_root = tmp_path / ".deeper-notebook-recovery"
    recovery_root.symlink_to(canonical, target_is_directory=True)

    with pytest.raises(RuntimeError, match="recovery-metadata-directory-symlink"):
        data_root.write_conflict_recovery_evidence(decision, home=tmp_path)
    assert (_tree_hash(canonical), _tree_hash(legacy)) == before

    recovery_root.unlink()
    recovery_root.mkdir()
    if hasattr(data_root.os, "getuid"):
        actual_uid = data_root.os.getuid()
        monkeypatch.setattr(data_root.os, "getuid", lambda: actual_uid + 1)
        with pytest.raises(RuntimeError, match="recovery-metadata-directory-not-owned"):
            data_root.write_conflict_recovery_evidence(decision, home=tmp_path)
        assert (_tree_hash(canonical), _tree_hash(legacy)) == before


def test_conflict_evidence_dirfd_refuses_visible_root_swap_without_redirect(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    _seed(canonical, theme="research-core", source="canonical\n")
    _seed(legacy, theme="light-blue", source="legacy\n")
    before = (_tree_hash(canonical), _tree_hash(legacy))
    decision = data_root.classify_roots(canonical, legacy)
    recovery = tmp_path / ".deeper-notebook-recovery"
    held = tmp_path / ".recovery-held"

    def swap(stage: str, path: Path) -> None:
        if stage == "recovery-opened":
            path.rename(held)
            path.symlink_to(canonical, target_is_directory=True)

    with pytest.raises(RuntimeError, match="identity-changed"):
        data_root.write_conflict_recovery_evidence(
            decision,
            home=tmp_path,
            _race_hook=swap,
        )

    assert not (canonical / "data-root-conflict-recovery.json").exists()
    assert not (canonical / "logs" / "recovery.log").exists()
    assert (held / "data-root-conflict-recovery.json").is_file()
    assert (held / "logs" / "recovery.log").is_file()
    assert (_tree_hash(canonical), _tree_hash(legacy)) == before


def test_recovery_html_discloses_only_safe_root_summaries() -> None:
    payload = {
        "canonical": {
            "path": "/Users/test/.deeper-notebook",
            "tree_sha256": "a" * 64,
            "file_count": 2,
            "directory_count": 1,
        },
        "legacy": {
            "path": "/Users/test/.open-notebook-plus",
            "tree_sha256": "b" * 64,
            "file_count": 3,
            "directory_count": 2,
        },
    }

    page = desktop_window._data_root_recovery_html(payload)

    assert "No data root has been selected or changed." in page
    assert "/Users/test/.deeper-notebook" in page
    assert "/Users/test/.open-notebook-plus" in page
    assert "a" * 64 in page
    assert "b" * 64 in page
    assert "Replace Old App" not in page
    assert "never-log-this" not in page


def test_recovery_window_uses_isolated_storage_and_existing_app_choices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Event:
        def __init__(self) -> None:
            self.handler = None

        def __iadd__(self, handler):
            self.handler = handler
            return self

    loaded = Event()
    evaluated: list[str] = []
    fake_window = SimpleNamespace(
        events=SimpleNamespace(loaded=loaded),
        evaluate_js=lambda script: evaluated.append(script),
    )
    starts: list[dict[str, object]] = []

    canonical = tmp_path / ".deeper-notebook"
    canonical.mkdir()
    recovery_root = tmp_path / ".deeper-notebook-recovery"
    recovery_root.mkdir()
    original_recovery = tmp_path / ".recovery-original"

    def start(**kwargs) -> None:
        starts.append(kwargs)
        recovery_root.rename(original_recovery)
        recovery_root.symlink_to(canonical, target_is_directory=True)
        assert kwargs == {"private_mode": True}
        assert loaded.handler is not None
        loaded.handler()

    fake_webview = SimpleNamespace(
        create_window=lambda *_args, **_kwargs: fake_window,
        start=start,
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr(
        data_root,
        "active_data_root",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("recovery window resolved an ambiguous data root")
        ),
    )
    app_recovery = SimpleNamespace(
        card_payload=lambda: {
            "show_recovery_card": True,
            "title": "Two Deeper Notebook apps are installed",
            "message": "Choose explicitly.",
            "keep_label": "Keep Both",
            "replace_label": "Replace Old App",
        }
    )

    desktop_window.open_data_root_recovery_window(
        conflict_payload={
            "canonical": {
                "path": str(tmp_path / ".deeper-notebook"),
                "tree_sha256": "a" * 64,
                "file_count": 1,
                "directory_count": 0,
            },
            "legacy": {
                "path": str(tmp_path / ".open-notebook-plus"),
                "tree_sha256": "b" * 64,
                "file_count": 1,
                "directory_count": 0,
            },
        },
        app_recovery=app_recovery,
        storage_root=recovery_root,
    )

    assert starts == [{"private_mode": True}]
    assert "Replace Old App" in evaluated[0]
    assert "Keep Both" in evaluated[0]
    assert not (canonical / "webview_data").exists()
    assert not (tmp_path / ".open-notebook-plus").exists()
