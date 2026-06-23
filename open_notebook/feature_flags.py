"""Feature flags for Open Notebook Plus product surfaces."""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "t", "yes", "y", "on", "enabled"}


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def onp_visual_refresh_enabled() -> bool:
    return _env_flag("ONP_VISUAL_REFRESH", default=True)


def evidence_studio_enabled() -> bool:
    return _env_flag("ONP_EVIDENCE_STUDIO", default=True)


def model_fleet_enabled() -> bool:
    return _env_flag("ONP_MODEL_FLEET", default=True)


def research_runs_enabled() -> bool:
    return _env_flag("ONP_RESEARCH_RUNS")
