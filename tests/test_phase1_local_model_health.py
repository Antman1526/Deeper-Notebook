"""Phase 1 — Local-model health module produces a structured
report the API can serve to the frontend."""
from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest


def test_probe_local_model_returns_unknown_for_zero_port():
    """A port of 0 means the supervisor never spawned this service;
    health must surface that as `status='not_configured'` rather
    than raising or returning a misleading 'down'."""
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="whisper",
        kind="openai_compatible",
        base_url="http://127.0.0.1:0/v1",
    )
    assert result["status"] == "not_configured"
    assert result["name"] == "whisper"
