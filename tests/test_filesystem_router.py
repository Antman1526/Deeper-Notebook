"""v0.7.90 — tests for api/routers/filesystem.py.

These tests use a real tempdir on disk rather than mocking the filesystem,
because the whole point of the router is host-FS access. Each test creates
its own isolated temp tree via the `tmp_path` fixture so they're parallel-safe.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import filesystem as fs_mod


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(fs_mod.router, prefix="/api")
    return TestClient(app)


# ----------------------------------------------------------------------------
# /fs/home
# ----------------------------------------------------------------------------


def test_fs_home_returns_user_home_and_defaults(client: TestClient) -> None:
    r = client.get("/api/fs/home")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["home"] == str(Path(os.path.expanduser("~")).resolve())
    # Default exports path is always returned even if the folder doesn't exist.
    assert body["default_exports"].endswith("DeeperNotebook-Exports")
    # Desktop/Documents/Downloads are platform-conditional — assert they are
    # either absent or absolute paths.
    for key in ("desktop", "documents", "downloads"):
        v = body.get(key)
        if v is not None:
            assert os.path.isabs(v)


def test_fs_home_falls_back_to_existing_legacy_exports_without_moving(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / "OpenNotebookPlus-Exports"
    canonical = tmp_path / "DeeperNotebook-Exports"
    legacy.mkdir()

    body = client.get("/api/fs/home").json()

    assert body["default_exports"] == str(legacy)
    assert legacy.is_dir()
    assert not canonical.exists()


def test_fs_home_prefers_canonical_exports_when_both_exist(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / "OpenNotebookPlus-Exports"
    canonical = tmp_path / "DeeperNotebook-Exports"
    legacy.mkdir()
    canonical.mkdir()

    body = client.get("/api/fs/home").json()

    assert body["default_exports"] == str(canonical)
    assert legacy.is_dir()
    assert canonical.is_dir()


# ----------------------------------------------------------------------------
# /fs/list — happy path + safety
# ----------------------------------------------------------------------------


def test_fs_list_returns_entries_sorted_dirs_first(
    client: TestClient,
    tmp_path: Path,
) -> None:
    (tmp_path / "z-folder").mkdir()
    (tmp_path / "a-folder").mkdir()
    (tmp_path / "b-file.txt").write_text("hello")
    (tmp_path / "Z-file.md").write_text("z")
    r = client.get("/api/fs/list", params={"path": str(tmp_path)})
    assert r.status_code == 200, r.text
    body = r.json()
    names = [e["name"] for e in body["entries"]]
    # Directories first, then files. Within each: case-insensitive alpha.
    assert names == ["a-folder", "z-folder", "b-file.txt", "Z-file.md"]
    # Each entry has the right shape
    for e in body["entries"]:
        assert "path" in e and os.path.isabs(e["path"])
        assert isinstance(e["is_dir"], bool)
        if not e["is_dir"]:
            assert e["size"] is not None and e["size"] >= 0


def test_fs_list_hidden_files_excluded_by_default(
    client: TestClient,
    tmp_path: Path,
) -> None:
    (tmp_path / "visible.txt").write_text("v")
    (tmp_path / ".hidden").write_text("h")
    r = client.get("/api/fs/list", params={"path": str(tmp_path)})
    names = [e["name"] for e in r.json()["entries"]]
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_fs_list_show_hidden_includes_dotfiles(
    client: TestClient,
    tmp_path: Path,
) -> None:
    (tmp_path / ".hidden").write_text("h")
    r = client.get(
        "/api/fs/list",
        params={"path": str(tmp_path), "show_hidden": True},
    )
    names = [e["name"] for e in r.json()["entries"]]
    assert ".hidden" in names


def test_fs_list_only_dirs_filter(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    (tmp_path / "f.txt").write_text("x")
    r = client.get(
        "/api/fs/list",
        params={"path": str(tmp_path), "only": "dirs"},
    )
    names = [e["name"] for e in r.json()["entries"]]
    assert names == ["d"]


def test_fs_list_expands_home_directory(client: TestClient) -> None:
    """`~` must be expanded to the user's home so the frontend can pass it
    raw without doing its own expansion."""
    r = client.get("/api/fs/list", params={"path": "~"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == str(Path(os.path.expanduser("~")).resolve())


def test_fs_list_rejects_system_paths(client: TestClient) -> None:
    """System-root paths must be refused with 403 so the UI doesn't
    accidentally encourage the user to browse there."""
    for sys_path in ("/etc", "/System", "/proc"):
        r = client.get("/api/fs/list", params={"path": sys_path})
        # 403 if exists, 404 if not (Linux doesn't have /System; macOS
        # doesn't have /proc). Either way it's blocked one way or
        # another — what we must NOT see is a 200 with directory listing.
        assert r.status_code in (403, 404), f"{sys_path}: {r.status_code} {r.text}"


def test_fs_list_404_on_missing_path(client: TestClient, tmp_path: Path) -> None:
    r = client.get(
        "/api/fs/list",
        params={"path": str(tmp_path / "does-not-exist")},
    )
    assert r.status_code == 404


def test_fs_list_400_when_path_is_file(
    client: TestClient,
    tmp_path: Path,
) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x")
    r = client.get("/api/fs/list", params={"path": str(f)})
    assert r.status_code == 400
    assert "not a directory" in r.json()["detail"]


def test_fs_list_truncated_for_large_directory(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the directory has more than MAX_ENTRIES, the response is
    truncated and the flag set so the UI can show a "load more" hint."""
    monkeypatch.setattr(fs_mod, "MAX_ENTRIES", 3)
    for i in range(10):
        (tmp_path / f"file-{i:02d}.txt").write_text("x")
    r = client.get("/api/fs/list", params={"path": str(tmp_path)})
    body = r.json()
    assert len(body["entries"]) == 3
    assert body["truncated"] is True
    assert any("capped" in w for w in body["warnings"])


# ----------------------------------------------------------------------------
# /fs/mkdir
# ----------------------------------------------------------------------------


def test_fs_mkdir_creates_directory(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "new-folder"
    r = client.post("/api/fs/mkdir", json={"path": str(target)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["path"] == str(target.resolve())
    assert target.exists() and target.is_dir()


def test_fs_mkdir_idempotent_when_exists(
    client: TestClient,
    tmp_path: Path,
) -> None:
    target = tmp_path / "already-exists"
    target.mkdir()
    r = client.post("/api/fs/mkdir", json={"path": str(target)})
    assert r.status_code == 200, r.text
    assert r.json()["created"] is False


def test_fs_mkdir_409_when_path_is_file(
    client: TestClient,
    tmp_path: Path,
) -> None:
    f = tmp_path / "conflict"
    f.write_text("x")
    r = client.post("/api/fs/mkdir", json={"path": str(f)})
    assert r.status_code == 409
    assert "not a directory" in r.json()["detail"]


def test_fs_mkdir_creates_parents(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    r = client.post(
        "/api/fs/mkdir",
        json={"path": str(target), "parents": True},
    )
    assert r.status_code == 200, r.text
    assert target.exists()


def test_fs_mkdir_refuses_system_paths(client: TestClient) -> None:
    r = client.post("/api/fs/mkdir", json={"path": "/etc/onp-test"})
    assert r.status_code == 403
