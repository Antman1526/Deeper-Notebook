"""v0.8.67q — GET /api/system/db-repair-needed reports the launcher's
.needs_db_repair flag, so the frontend can show a "restart to auto-repair"
banner while source processing is stuck.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import system


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(system.router)
    return TestClient(app)


def test_reports_false_when_flag_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    resp = _client().get("/api/system/db-repair-needed")
    assert resp.status_code == 200
    assert resp.json() == {"needs_repair": False}


def test_reports_true_when_flag_present(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    data_home = tmp_path / ".deeper-notebook"
    data_home.mkdir()
    (data_home / ".needs_db_repair").write_text("2026-06-02 00:00:00\n")

    resp = _client().get("/api/system/db-repair-needed")
    assert resp.status_code == 200
    assert resp.json() == {"needs_repair": True}


def test_never_raises_on_unreadable_home(tmp_path, monkeypatch):
    # Path.exists() raising must degrade to needs_repair=False, not 500.
    class _Boom(Path):
        def exists(self):  # type: ignore[override]
            raise OSError("no permission")

    monkeypatch.setattr(system, "active_data_root", lambda: _Boom(tmp_path))
    resp = _client().get("/api/system/db-repair-needed")
    assert resp.status_code == 200
    assert resp.json() == {"needs_repair": False}
