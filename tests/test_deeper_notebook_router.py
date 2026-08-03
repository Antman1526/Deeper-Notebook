"""Tests for the canonical Deeper Notebook theme router.

Covers:
  * GET /theme passes HTTPException through (so the bundling error is
    visible) but swallows generic Exception (config not yet written on
    first run).
  * POST /theme rejects unknown themes.
  * POST /theme uses dataclasses.replace so adding fields to Config
    doesn't silently revert them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import deeper_notebook as deeper_notebook_mod

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
    a.include_router(deeper_notebook_mod.router, prefix="/api/deeper-notebook")
    return a


# --- GET /theme -----------------------------------------------------------


def test_get_theme_returns_default_when_config_file_missing(app, monkeypatch):
    """First-run case — _load_config raises FileNotFoundError; GET should
    silently fall back to the default theme, NOT 500."""
    def _broken_load():
        raise FileNotFoundError("config not yet written")
    monkeypatch.setattr(deeper_notebook_mod, "_load_config", _broken_load)

    with TestClient(app) as client:
        r = client.get("/api/deeper-notebook/theme")
    assert r.status_code == 200
    assert r.json()["theme"] == "research-core-dark"


def test_get_theme_propagates_http_exception(app, monkeypatch):
    """If _load_config raises HTTPException (e.g. 'module not bundled'),
    the user MUST see the actionable error, not a silent fallback."""
    def _bundling_err():
        raise HTTPException(status_code=500, detail="desktop.config not bundled")
    monkeypatch.setattr(deeper_notebook_mod, "_load_config", _bundling_err)

    with TestClient(app) as client:
        r = client.get("/api/deeper-notebook/theme")
    assert r.status_code == 500
    assert "not bundled" in r.json()["detail"]


def test_get_theme_returns_loaded_value(app, monkeypatch):
    monkeypatch.setattr(deeper_notebook_mod, "_load_config",
                        lambda: (Path("/tmp/c.toml"), _FakeCfg(theme="dracula")))
    with TestClient(app) as client:
        r = client.get("/api/deeper-notebook/theme")
    assert r.status_code == 200
    assert r.json()["theme"] == "dracula"
    assert "dracula" in r.json()["available"]


# --- POST /theme ----------------------------------------------------------


def test_post_theme_rejects_unknown(app, monkeypatch):
    monkeypatch.setattr(deeper_notebook_mod, "_load_config",
                        lambda: (Path("/tmp/c.toml"), _FakeCfg()))
    with TestClient(app) as client:
        r = client.post("/api/deeper-notebook/theme", json={"theme": "neon-purple"})
    assert r.status_code == 400
    assert "unknown theme" in r.json()["detail"]


@pytest.mark.parametrize(
    "theme",
    [
        "research-core-dark", "research-core-light", "deep-ocean", "graphite-lab",
        "arctic-research", "archive-paper", "high-contrast-dark", "high-contrast-light",
    ],
)
def test_post_theme_accepts_each_research_core_palette(app, monkeypatch, theme):
    monkeypatch.setattr(_FakeCfg, "save", lambda self, path: None)
    monkeypatch.setattr(
        deeper_notebook_mod, "_load_config", lambda: (Path("/tmp/c.toml"), _FakeCfg())
    )

    with TestClient(app) as client:
        response = client.post("/api/deeper-notebook/theme", json={"theme": theme})

    assert response.status_code == 200
    assert response.json()["theme"] == theme


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
    monkeypatch.setattr(deeper_notebook_mod, "_load_config",
                        lambda: (Path("/tmp/c.toml"), original))

    with TestClient(app) as client:
        r = client.post("/api/deeper-notebook/theme", json={"theme": "dark"})

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
    monkeypatch.setattr(deeper_notebook_mod, "_load_config", _bundling_err)

    with TestClient(app) as client:
        r = client.post("/api/deeper-notebook/theme", json={"theme": "dark"})
    assert r.status_code == 500
    assert "not bundled" in r.json()["detail"]


def test_v0825_post_theme_sanitizes_save_failure_detail(app, monkeypatch):
    """v0.8.25 — `new_cfg.save(path)` exceptions must NOT echo raw error
    text into the 500 response. The save call can raise OSError /
    PermissionError carrying the resolved config-file path under the
    user's home directory (info disclosure of operator FS layout) and
    OS-level error reasons. Same family as v0.7.177 / v0.8.22 / v0.8.24
    sanitization sweep — this site was missed in those passes.
    """
    secret_in_exception = (
        "[Errno 13] Permission denied: "
        "'/Users/operator/.open-notebook-plus/config.toml' "
        "INTERNAL_TRACE: SurrealDB ws://127.0.0.1:8765"
    )

    def _save_boom(self, path):
        raise OSError(secret_in_exception)

    monkeypatch.setattr(_FakeCfg, "save", _save_boom)
    monkeypatch.setattr(
        deeper_notebook_mod, "_load_config",
        lambda: (Path("/tmp/c.toml"), _FakeCfg()),
    )

    with TestClient(app) as client:
        r = client.post("/api/deeper-notebook/theme", json={"theme": "dark"})

    assert r.status_code == 500, r.text
    detail = r.json().get("detail", "")
    # CRITICAL: no leak of operator home path, errno, or trace fragment.
    assert "/Users/operator" not in detail, (
        f"Operator home path leaked into 500 detail: {detail!r}. "
        f"v0.8.25 fix: emit type(exc).__name__ only."
    )
    assert "[Errno 13]" not in detail, (
        f"Errno fragment leaked into 500 detail: {detail!r}."
    )
    assert "ws://127.0.0.1" not in detail, (
        f"Internal URL leaked: {detail!r}."
    )
    # And the type name IS present so the operator can correlate
    # with the log line written by logger.exception above.
    assert "OSError" in detail, (
        f"Expected exception type name in {detail!r} for triage."
    )
