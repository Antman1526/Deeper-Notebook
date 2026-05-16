"""ONP v0.6.5 — Tests for api/routers/onp.py.

Covers:
  * GET /onp/theme passes HTTPException through (so the bundling error is
    visible) but swallows generic Exception (config not yet written on
    first run).
  * POST /onp/theme rejects unknown themes.
  * POST /onp/theme uses dataclasses.replace so adding fields to Config
    doesn't silently revert them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import onp as onp_mod

# --- Lightweight fake Config that mimics desktop.config.Config ------------


@dataclass(frozen=True)
class _FakeCfg:
    model_dir: Path = Path("/tmp/x")
    provider: str = "ollama"
    default_model: str = "qwen3"
    surreal_user: str = "root"
    surreal_password: str = "x" * 24
    theme: str = "light-blue"
    openchronicle_choice: str = "skip"
    encryption_key: str = "Y" * 32
    # Synthetic NEW field — tests that future additions survive POST.
    favorite_color: str = "indigo"

    def save(self, path: Path) -> None:
        self._saved_to = path  # type: ignore[attr-defined]


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(onp_mod.router, prefix="/api")
    return a


# --- GET /onp/theme -------------------------------------------------------


def test_get_theme_returns_default_when_config_file_missing(app, monkeypatch):
    """First-run case — _load_config raises FileNotFoundError; GET should
    silently fall back to the default theme, NOT 500."""
    def _broken_load():
        raise FileNotFoundError("config not yet written")
    monkeypatch.setattr(onp_mod, "_load_config", _broken_load)

    with TestClient(app) as client:
        r = client.get("/api/onp/theme")
    assert r.status_code == 200
    assert r.json()["theme"] == "light-blue"


def test_get_theme_propagates_http_exception(app, monkeypatch):
    """If _load_config raises HTTPException (e.g. 'module not bundled'),
    the user MUST see the actionable error, not a silent fallback."""
    def _bundling_err():
        raise HTTPException(status_code=500, detail="desktop.config not bundled")
    monkeypatch.setattr(onp_mod, "_load_config", _bundling_err)

    with TestClient(app) as client:
        r = client.get("/api/onp/theme")
    assert r.status_code == 500
    assert "not bundled" in r.json()["detail"]


def test_get_theme_returns_loaded_value(app, monkeypatch):
    monkeypatch.setattr(onp_mod, "_load_config",
                        lambda: (Path("/tmp/c.toml"), _FakeCfg(theme="dracula")))
    with TestClient(app) as client:
        r = client.get("/api/onp/theme")
    assert r.status_code == 200
    assert r.json()["theme"] == "dracula"
    assert "dracula" in r.json()["available"]


# --- POST /onp/theme ------------------------------------------------------


def test_post_theme_rejects_unknown(app, monkeypatch):
    monkeypatch.setattr(onp_mod, "_load_config",
                        lambda: (Path("/tmp/c.toml"), _FakeCfg()))
    with TestClient(app) as client:
        r = client.post("/api/onp/theme", json={"theme": "neon-purple"})
    assert r.status_code == 400
    assert "unknown theme" in r.json()["detail"]


def test_post_theme_preserves_other_fields_via_dataclasses_replace(app, monkeypatch):
    """The bug we just fixed: previously set_theme listed every Config
    field by hand. If a new field gets added to Config, the manual
    Config(...) call drops it. With dataclasses.replace() the new value
    flows through automatically.

    We use a fake Config that has a `favorite_color` field NOT enumerated
    in any old set_theme code. Saving with a new theme should keep
    favorite_color intact.
    """
    saved: dict[str, _FakeCfg] = {}
    original = _FakeCfg(theme="paper", favorite_color="indigo")

    def _save(self, path):
        saved["cfg"] = self

    monkeypatch.setattr(_FakeCfg, "save", _save)
    monkeypatch.setattr(onp_mod, "_load_config",
                        lambda: (Path("/tmp/c.toml"), original))

    with TestClient(app) as client:
        r = client.post("/api/onp/theme", json={"theme": "dark"})

    assert r.status_code == 200
    assert r.json()["theme"] == "dark"
    assert saved["cfg"].theme == "dark"
    # Crucial assertion — the field NOT mentioned in set_theme is preserved.
    assert saved["cfg"].favorite_color == "indigo"


def test_post_theme_surfaces_bundling_error(app, monkeypatch):
    """If desktop.config isn't bundled, POST should 500 with the helpful
    message — same path as GET. Previously POST duplicated the ImportError
    handling; now both go through _load_config."""
    def _bundling_err():
        raise HTTPException(status_code=500, detail="desktop.config not bundled")
    monkeypatch.setattr(onp_mod, "_load_config", _bundling_err)

    with TestClient(app) as client:
        r = client.post("/api/onp/theme", json={"theme": "dark"})
    assert r.status_code == 500
    assert "not bundled" in r.json()["detail"]
