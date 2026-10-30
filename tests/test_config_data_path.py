"""v0.8.130 — /api/config reports where this install keeps its data.

Home's tip said "All data lives in ~/.deeper-notebook/" whatever the real
folder was (seen in a packaged run with DEEPER_NOTEBOOK_DATA_DIR set).
"""

import os
from pathlib import Path

from api.routers import config as config_router


def test_default_root_is_shown_relative_to_home(monkeypatch, tmp_path):
    home = Path(os.path.realpath(tmp_path)) / "home"
    root = home / ".deeper-notebook"
    root.mkdir(parents=True)
    monkeypatch.setattr(config_router, "active_data_root", lambda: root)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert config_router._data_path_display() == "~/.deeper-notebook/"


def test_a_root_outside_home_is_shown_in_full(monkeypatch, tmp_path):
    home = Path(os.path.realpath(tmp_path)) / "home"
    root = Path(os.path.realpath(tmp_path)) / "elsewhere" / "data"
    root.mkdir(parents=True)
    monkeypatch.setattr(config_router, "active_data_root", lambda: root)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert config_router._data_path_display() == f"{root}/"


def test_an_unresolvable_root_is_reported_as_unknown(monkeypatch):
    def blocked():
        raise ValueError("data root is not usable")

    monkeypatch.setattr(config_router, "active_data_root", blocked)

    assert config_router._data_path_display() is None


def test_config_endpoint_carries_the_data_path(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setattr(config_router, "_data_path_display", lambda: "~/somewhere/")

    response = TestClient(app).get("/api/config")

    assert response.status_code == 200
    assert response.json()["dataPath"] == "~/somewhere/"
