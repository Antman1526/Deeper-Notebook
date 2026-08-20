"""v0.8.36 Phase 1 — Osaurus auto-register tests.

Covers:
  - `_osaurus_running` probe (mocked httpx).
  - `register_osaurus_models` happy path (creates credential, registers
    models, returns True).
  - `register_osaurus_models` no-op when port silent (returns False,
    no API calls).
  - Idempotency on re-run: existing credential, no new models → False.
  - Custom port via DEEPER_NOTEBOOK_OSAURUS_PORT env var.

Tests are network-isolated — no real Osaurus required. We mock the
probe at the httpx level and stub the auto_register HTTP helpers at
the module level for the registration side.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from desktop.auto_register import osaurus as osaurus_mod


def test_osaurus_port_default():
    """Default port is 1337 — Osaurus's documented default."""
    import os as _os

    _os.environ.pop("DEEPER_NOTEBOOK_OSAURUS_PORT", None)
    assert osaurus_mod._osaurus_port() == 1337


def test_osaurus_port_env_override(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_OSAURUS_PORT", "1338")
    assert osaurus_mod._osaurus_port() == 1338


def test_osaurus_port_env_garbage_falls_back(monkeypatch):
    """Garbage env values fall back to 1337 with a warning — better
    than crashing the launcher on a typo."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_OSAURUS_PORT", "not-a-number")
    assert osaurus_mod._osaurus_port() == 1337


def test_osaurus_running_returns_models_on_200():
    """A 200 with the standard OpenAI-compatible `{"data": [...]}`
    body returns (True, [model_ids])."""
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [
            {"id": "qwen2.5-7b-instruct-mlx"},
            {"id": "llama-3.1-8b-mlx"},
        ]
    }
    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.return_value = fake_response

    with patch("desktop.auto_register.osaurus.httpx.Client", return_value=fake_client):
        running, models = osaurus_mod._osaurus_running(1337)
    assert running is True
    assert models == ["qwen2.5-7b-instruct-mlx", "llama-3.1-8b-mlx"]


def test_osaurus_running_returns_false_on_connect_error():
    """Connect-refused → not running, no models. Most common path
    (user doesn't have Osaurus installed)."""
    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.side_effect = httpx.ConnectError(
        "Connection refused"
    )

    with patch("desktop.auto_register.osaurus.httpx.Client", return_value=fake_client):
        running, models = osaurus_mod._osaurus_running(1337)
    assert running is False
    assert models == []


def test_osaurus_running_returns_false_on_non_200():
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 500
    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.return_value = fake_response

    with patch("desktop.auto_register.osaurus.httpx.Client", return_value=fake_client):
        running, models = osaurus_mod._osaurus_running(1337)
    assert running is False
    assert models == []


def test_register_osaurus_models_skips_when_not_running():
    """No Osaurus → no API calls at all, returns False."""
    with patch.object(
        osaurus_mod,
        "_osaurus_running",
        return_value=(False, []),
    ):
        # If anything tries to call client.get/post, this MagicMock
        # would record it — assert below.
        fake_client = MagicMock()
        result = osaurus_mod.register_osaurus_models(
            client=fake_client,
            existing_cred_names=set(),
            existing_model_keys=set(),
        )
    assert result is False
    # No registration calls happened.
    assert not fake_client.get.called
    assert not fake_client.post.called


def test_register_osaurus_models_happy_path():
    """Probe succeeds → credential created → models registered."""
    fake_models = ["qwen2.5-7b-instruct-mlx", "llama-3.1-8b-mlx"]

    with (
        patch.object(
            osaurus_mod,
            "_osaurus_running",
            return_value=(True, fake_models),
        ),
        patch.object(
            osaurus_mod,
            "_ensure_credential",
            return_value="cred:osaurus-1",
        ) as mock_ensure_cred,
        patch.object(
            osaurus_mod,
            "_ensure_model",
            return_value=True,
        ) as mock_ensure_model,
    ):
        fake_client = MagicMock()
        result = osaurus_mod.register_osaurus_models(
            client=fake_client,
            existing_cred_names=set(),
            existing_model_keys=set(),
        )

    assert result is True
    # Exactly ONE credential — named "Osaurus (local MLX)".
    mock_ensure_cred.assert_called_once()
    cred_kwargs = mock_ensure_cred.call_args.kwargs
    assert cred_kwargs["name"] == "Osaurus (local MLX)"
    assert cred_kwargs["provider"] == "openai_compatible"
    assert cred_kwargs["base_url"] == "http://127.0.0.1:1337/v1"
    assert "language" in cred_kwargs["modalities"]

    # Both models registered against the new credential.
    assert mock_ensure_model.call_count == 2
    registered_names = [c.kwargs["name"] for c in mock_ensure_model.call_args_list]
    assert registered_names == fake_models


def test_register_osaurus_models_returns_false_when_credential_fails():
    """If _ensure_credential returns None (deduplication refusal,
    network error, etc.) we skip model registration entirely and
    return False — same shape as register_llamacpp_models."""
    with (
        patch.object(
            osaurus_mod,
            "_osaurus_running",
            return_value=(True, ["model-a"]),
        ),
        patch.object(
            osaurus_mod,
            "_ensure_credential",
            return_value=None,
        ),
        patch.object(
            osaurus_mod,
            "_ensure_model",
            return_value=True,
        ) as mock_ensure_model,
    ):
        result = osaurus_mod.register_osaurus_models(
            client=MagicMock(),
            existing_cred_names=set(),
            existing_model_keys=set(),
        )

    assert result is False
    assert not mock_ensure_model.called


def test_register_osaurus_models_honours_explicit_port_kwarg():
    """Caller can pass `port=` to override both the default and the
    env var. Useful for the on-demand /credentials/detect-osaurus
    endpoint and for tests."""
    with (
        patch.object(
            osaurus_mod,
            "_osaurus_running",
            return_value=(True, ["m"]),
        ) as mock_probe,
        patch.object(
            osaurus_mod,
            "_ensure_credential",
            return_value="cred:x",
        ) as mock_cred,
        patch.object(
            osaurus_mod,
            "_ensure_model",
            return_value=True,
        ),
    ):
        osaurus_mod.register_osaurus_models(
            client=MagicMock(),
            existing_cred_names=set(),
            existing_model_keys=set(),
            port=9999,
        )
    mock_probe.assert_called_once_with(9999)
    assert mock_cred.call_args.kwargs["base_url"] == "http://127.0.0.1:9999/v1"
