"""v0.8.70 — regression tests for the concrete bug fixes.

1. connection_tester must restore os.environ after a "Test connection" so the
   tested key doesn't leak and shadow later provisioning.
2. CommandService.get_command_status must map a "not found" ValueError to None
   (so the HTTP layer returns 404) and re-raise other ValueErrors.
"""
from __future__ import annotations

import os

import pytest

import deeper_notebook.ai.connection_tester as ct
from api.command_service import CommandService

# --- 1. connection_tester env-leak fix ------------------------------------

async def test_connection_test_restores_absent_env_var(monkeypatch):
    """When the provider key wasn't set before, it must be removed after."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _boom(*args, **kwargs):
        raise RuntimeError("401 unauthorized")  # simulate a bad key

    monkeypatch.setattr(ct.AIFactory, "create_language", _boom)

    ok, _msg = await ct.test_provider_connection("openai")
    assert ok is False
    # The transient key set for the test must not persist.
    assert "OPENAI_API_KEY" not in os.environ


async def test_connection_test_restores_prior_env_var(monkeypatch):
    """A pre-existing key must be put back exactly as it was."""
    monkeypatch.setenv("OPENAI_API_KEY", "original-key")

    captured = {}

    def _capture(*args, **kwargs):
        captured["seen"] = os.environ.get("OPENAI_API_KEY")
        raise RuntimeError("boom")

    monkeypatch.setattr(ct.AIFactory, "create_language", _capture)

    # config_id path is skipped; pass the api_key via env-less route by
    # calling with a provider and letting the env var be the one we set.
    await ct.test_provider_connection("openai")
    # The original value is restored regardless of the test outcome.
    assert os.environ.get("OPENAI_API_KEY") == "original-key"


# --- 2. command status 404 mapping ----------------------------------------

async def test_get_command_status_returns_none_for_not_found(monkeypatch):
    async def _raise_not_found(job_id):
        raise ValueError(f"Command {job_id} not found")

    monkeypatch.setattr(
        "api.command_service.get_command_status", _raise_not_found
    )
    result = await CommandService.get_command_status("command:missing")
    assert result is None  # → router emits 404


async def test_get_command_status_reraises_other_valueerror(monkeypatch):
    async def _raise_other(job_id):
        raise ValueError("malformed job payload")

    monkeypatch.setattr(
        "api.command_service.get_command_status", _raise_other
    )
    with pytest.raises(ValueError, match="malformed"):
        await CommandService.get_command_status("command:bad")
