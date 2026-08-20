"""Final-window destination-race regression for guarded root migration."""

from __future__ import annotations

from pathlib import Path

from desktop import data_root


def test_canonical_created_inside_root_rename_window_is_not_replaced(
    tmp_path, monkeypatch
):
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    receipts = tmp_path / ".deeper-notebook-migrations"
    legacy.mkdir()
    (legacy / "config.toml").write_text("theme='legacy'")
    real_rename = data_root._rename_directory_no_replace

    def destination_race(source, destination):
        if Path(source) == legacy and Path(destination) == canonical:
            canonical.mkdir()
        return real_rename(source, destination)

    monkeypatch.setattr(data_root, "_rename_directory_no_replace", destination_race)

    decision = data_root.migrate_data_root(canonical, legacy, receipt_dir=receipts)

    assert decision.state == "migration-conflict"
    assert decision.reason_code == "canonical-root-appeared"
    assert canonical.is_dir()
    assert legacy.is_dir()
