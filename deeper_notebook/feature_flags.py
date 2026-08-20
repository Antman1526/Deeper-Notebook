"""Feature flags for Deeper Notebook product surfaces."""

from __future__ import annotations

from deeper_notebook.environment import resolve_env

_TRUTHY = {"1", "true", "t", "yes", "y", "on", "enabled"}


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = resolve_env(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def onp_visual_refresh_enabled() -> bool:
    return _env_flag("DEEPER_NOTEBOOK_VISUAL_REFRESH", default=True)


def evidence_studio_enabled() -> bool:
    return _env_flag("DEEPER_NOTEBOOK_EVIDENCE_STUDIO", default=True)


def model_fleet_enabled() -> bool:
    return _env_flag("DEEPER_NOTEBOOK_MODEL_FLEET", default=True)


def research_runs_enabled() -> bool:
    return _env_flag("DEEPER_NOTEBOOK_RESEARCH_RUNS", default=True)


def study_workbench_enabled() -> bool:
    return _env_flag("DEEPER_NOTEBOOK_STUDY_WORKBENCH", default=True)


def source_visuals_enabled() -> bool:
    """Return whether source-derived visual extraction is enabled."""
    return _env_flag("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", default=True)
