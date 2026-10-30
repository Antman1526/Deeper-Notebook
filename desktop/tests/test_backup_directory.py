"""v0.8.130 — each data folder has its own backups.

Automatic exports and pre-repair copies all went to ~/onp-backups whatever data
folder the app was using, so a second install or a test data folder read, pruned
and reported on the same backup set as the main one (a packaged test run on
2026-10-05 showed "Local backup is stale" for a data folder minutes old).

A default install is unchanged. A redirected data folder
(DEEPER_NOTEBOOK_DATA_DIR) gets a folder of its own beside it: beside, not
inside, so the backups still survive the data folder being deleted or damaged.
"""

from pathlib import Path

from desktop import data_root

REPOSITORY = Path(__file__).resolve().parents[2]


def test_a_default_install_keeps_its_backups_where_they_were(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPER_NOTEBOOK_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert data_root.backup_directory() == tmp_path / "onp-backups"
    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", "   ")  # blank means not redirected
    assert data_root.backup_directory() == tmp_path / "onp-backups"


def test_a_redirected_data_folder_gets_its_own_backups_beside_it(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    one, two = tmp_path / "work" / "data-one", tmp_path / "work" / "data-two"
    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", str(one))
    first = data_root.backup_directory()
    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", str(two) + "/")
    second = data_root.backup_directory()

    assert first == tmp_path / "work" / "data-one-backups"
    assert second == tmp_path / "work" / "data-two-backups"
    # Beside the data folder, never inside it, and never the shared one.
    assert one not in first.parents and first != one
    assert first != tmp_path / "home" / "onp-backups"


def test_asking_where_backups_go_creates_nothing(monkeypatch, tmp_path):
    target = tmp_path / "not-yet"
    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", str(target))
    data_root.backup_directory()
    assert list(tmp_path.iterdir()) == []


def test_an_unusable_redirect_falls_back_to_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    for bad in ("relative/path", "/"):
        monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", bad)
        assert data_root.backup_directory() == tmp_path / "onp-backups"


def test_the_writer_the_repair_copy_and_the_status_panel_agree(monkeypatch, tmp_path):
    from api.runtime_snapshot import default_auto_export_directory

    monkeypatch.setenv("DEEPER_NOTEBOOK_DATA_DIR", str(tmp_path / "data"))
    assert default_auto_export_directory() == data_root.backup_directory()

    # One place decides; nothing else spells the folder name.
    for path in ("desktop/launcher.py", "api/runtime_snapshot.py"):
        source = (REPOSITORY / path).read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
        assert '"onp-backups"' not in code, path
    assert (REPOSITORY / "desktop/launcher.py").read_text(encoding="utf-8").count("backup_directory()") >= 2
