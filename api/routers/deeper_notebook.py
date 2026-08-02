"""Deeper Notebook desktop-wrapper-specific endpoints.

These don't exist in upstream open-notebook; they wrap state that lives in
the user's `~/.deeper-notebook/config.toml` so the React UI can read and
update it without a PyWebView bridge.

Routes are namespace-relative so ``api.main`` can mount both the canonical
``/api/deeper-notebook`` namespace and the hidden legacy ``/api/onp`` alias.

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
    "research-core-dark", "research-core-light", "deep-ocean", "graphite-lab",
    "arctic-research", "archive-paper", "high-contrast-dark", "high-contrast-light",
    "light-blue", "system", "solarized-light", "github-light", "paper",
    "dark", "solarized-dark", "dracula", "nord",
    # v0.8.72 — premium theme pack (must mirror desktop/window.py:_THEMES
    # and frontend ThemeSwitcher:DEEPER_NOTEBOOK_THEMES).
    "midnight-aurora", "tokyo-night", "catppuccin-mocha", "rose-pine",
    "gruvbox-dark", "one-dark", "catppuccin-latte", "rose-pine-dawn",
}


class ThemeRequest(BaseModel):
    theme: str = Field(
        ..., description="One of the Deeper Notebook themes (see _VALID_THEMES)"
    )


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


@router.get("/theme", response_model=ThemeResponse)
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
        return ThemeResponse(theme="research-core-dark", available=sorted(_VALID_THEMES))
    return ThemeResponse(theme=cfg.theme, available=sorted(_VALID_THEMES))


@router.post("/theme", response_model=ThemeResponse)
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
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as exc:
        # v0.8.25 — sanitize: same family as the v0.7.177 / v0.8.22 /
        # v0.8.24 sanitization sweep. `new_cfg.save(path)` can raise
        # OSError (disk full, read-only FS), PermissionError (config
        # directory perms), JSONEncodeError (corrupted dataclass field),
        # or anything Config.save uses internally. `str(exc)` typically
        # includes the resolved config-file path under the user's home
        # directory plus the OS-level error reason — both noise to the
        # client and a minor info-disclosure of the operator's
        # filesystem layout. Full detail stays in logger.
        from loguru import logger
        logger.exception("Theme save failed")
        raise HTTPException(
            status_code=500,
            detail=f"Theme save failed ({type(exc).__name__}). "
            "Check launcher.log for details.",
        )
    return ThemeResponse(theme=body.theme, available=sorted(_VALID_THEMES))
