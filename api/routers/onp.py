"""Open Notebook Plus — desktop-wrapper-specific endpoints.

These don't exist in upstream open-notebook; they wrap state that lives in
the user's `~/.open-notebook-plus/config.toml` so the React UI can read and
update it without a PyWebView bridge.

Endpoints:
  GET  /api/onp/theme         → {"theme": "<name>"}
  POST /api/onp/theme         {"theme": "<name>"} → 200 ok, persists to config

The theme set here is read by desktop/window.py's _theme_injection_js on
every page load, so live switches persist across navigation and across
app restarts (config.toml is the source of truth).
"""
from __future__ import annotations

from dataclasses import replace as _dc_replace

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()


# Kept in lockstep with desktop/window.py:_THEMES — adding a theme requires
# updating both. The UI shouldn't accept an arbitrary string.
_VALID_THEMES = {
    "light-blue", "system", "solarized-light", "github-light", "paper",
    "dark", "solarized-dark", "dracula", "nord",
}


class ThemeRequest(BaseModel):
    theme: str = Field(..., description="One of the 9 ONP themes")


class ThemeResponse(BaseModel):
    theme: str
    available: list[str]


def _load_config():
    """Lazy import — `desktop.config` lives inside the bundled upstream/desktop
    namespace at runtime. Tests can patch this if needed."""
    try:
        from desktop.config import default_config_path, load_or_create
    except ImportError as exc:
        # Surfaces the real issue (module not bundled) instead of generic 500
        raise HTTPException(
            status_code=500,
            detail=(
                "desktop.config not importable from upstream API process. "
                "PyInstaller spec must bundle desktop/config.py into "
                "upstream/desktop/. Underlying: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    return default_config_path(), load_or_create(default_config_path())


@router.get("/onp/theme", response_model=ThemeResponse)
async def get_theme() -> ThemeResponse:
    """v0.6.5 — HTTPException from `_load_config` (e.g. 'module not bundled')
    is intentionally let through so the user sees the actionable error;
    only the file-read fallback returns the default theme."""
    try:
        _, cfg = _load_config()
    except HTTPException:
        raise
    except Exception:
        # Config file unreadable / first-run before disk write — return
        # the default rather than 500'ing the UI.
        return ThemeResponse(theme="light-blue", available=sorted(_VALID_THEMES))
    return ThemeResponse(theme=cfg.theme, available=sorted(_VALID_THEMES))


@router.post("/onp/theme", response_model=ThemeResponse)
async def set_theme(body: ThemeRequest) -> ThemeResponse:
    if body.theme not in _VALID_THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown theme '{body.theme}' (valid: {sorted(_VALID_THEMES)})",
        )
    # Reuse the helper — same error message as GET if the module isn't bundled.
    path, cfg = _load_config()
    # v0.6.5 — dataclasses.replace() preserves any future Config fields
    # automatically. Previously this enumerated all 8 fields by hand, which
    # silently dropped any added field to its default on the next save.
    try:
        new_cfg = _dc_replace(cfg, theme=body.theme)
        new_cfg.save(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ThemeResponse(theme=body.theme, available=sorted(_VALID_THEMES))
