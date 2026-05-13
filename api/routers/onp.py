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
    from desktop.config import default_config_path, load_or_create
    return default_config_path(), load_or_create(default_config_path())


@router.get("/onp/theme", response_model=ThemeResponse)
async def get_theme() -> ThemeResponse:
    try:
        _, cfg = _load_config()
        return ThemeResponse(theme=cfg.theme, available=sorted(_VALID_THEMES))
    except Exception as exc:
        # Don't break the UI if config can't be read; return the default
        return ThemeResponse(theme="light-blue", available=sorted(_VALID_THEMES))


@router.post("/onp/theme", response_model=ThemeResponse)
async def set_theme(body: ThemeRequest) -> ThemeResponse:
    if body.theme not in _VALID_THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown theme '{body.theme}' (valid: {sorted(_VALID_THEMES)})",
        )
    try:
        from desktop.config import Config, default_config_path, load_or_create
        path = default_config_path()
        cfg = load_or_create(path)
        new_cfg = Config(
            model_dir=cfg.model_dir,
            provider=cfg.provider,
            default_model=cfg.default_model,
            surreal_user=cfg.surreal_user,
            surreal_password=cfg.surreal_password,
            theme=body.theme,
            openchronicle_choice=cfg.openchronicle_choice,
            encryption_key=cfg.encryption_key,
        )
        new_cfg.save(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ThemeResponse(theme=body.theme, available=sorted(_VALID_THEMES))
