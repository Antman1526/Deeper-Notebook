from pathlib import Path
from unittest.mock import MagicMock

import httpx

from desktop.auto_register import _do_register
from desktop.auto_register.mlx import _mlx_model_display_name, register_mlx_models
from desktop.config import Config


def test_mlx_model_display_name_matches_inventory_repo_name():
    assert (
        _mlx_model_display_name("MLX/mlx-community__North-Mini-Code-1.0-6bit")
        == "mlx-community/North-Mini-Code-1.0-6bit"
    )


def test_registered_mlx_model_name_is_the_string_the_server_accepts(monkeypatch):
    """v0.8.97 — the registered name IS the wire ``model`` field.

    ``deeper_notebook/ai/models.py`` builds every language model with
    ``model_name=model.name``, so whatever is registered here is sent verbatim
    as the OpenAI ``model`` parameter. ``mlx_lm.server`` keys its single loaded
    model on the exact ``--model`` string it was launched with and resolves
    anything else as a Hugging Face repo id — verified live against a running
    server on this machine:

        model="/…/MLX/PocketAiHub__Qwen3.8-27B-MLX-6bit"  → 200, generates
        model="PocketAiHub/Qwen3.8-27B-MLX-6bit"          → 404 Repository Not Found
        model="PocketAiHub__Qwen3.8-27B-MLX-6bit"         → 404 Repository Not Found

    Registering the prettified display name therefore produced a model row that
    could never answer. Register the launch reference itself.
    """
    client = MagicMock()
    ensure_model = MagicMock(return_value=True)
    monkeypatch.setattr(
        "desktop.auto_register.mlx._ensure_credential",
        MagicMock(return_value="credential:mlx"),
    )
    monkeypatch.setattr("desktop.auto_register.mlx._ensure_model", ensure_model)

    launch_ref = "/Volumes/models/MLX/PocketAiHub__Qwen3.8-27B-MLX-6bit"
    register_mlx_models(
        client,
        existing_cred_names=set(),
        existing_model_keys=set(),
        base_url="http://127.0.0.1:51231/v1",
        model_ref=launch_ref,
    )

    assert ensure_model.call_args.kwargs["name"] == launch_ref


def test_register_mlx_models_creates_openai_compatible_model(monkeypatch):
    client = MagicMock()
    ensure_credential = MagicMock(return_value="credential:mlx")
    ensure_model = MagicMock(return_value=True)
    monkeypatch.setattr("desktop.auto_register.mlx._ensure_credential", ensure_credential)
    monkeypatch.setattr("desktop.auto_register.mlx._ensure_model", ensure_model)

    registered = register_mlx_models(
        client,
        existing_cred_names=set(),
        existing_model_keys=set(),
        base_url="http://127.0.0.1:51231/v1",
        model_ref="MLX/mlx-community__North-Mini-Code-1.0-6bit",
    )

    assert registered is True
    ensure_credential.assert_called_once_with(
        client=client,
        existing_names={"mlx (local)"},
        name="MLX (local)",
        provider="openai_compatible",
        modalities=["language"],
        base_url="http://127.0.0.1:51231/v1",
    )
    # v0.8.97 — the registered name is the LAUNCH REFERENCE (what mlx_lm.server
    # accepts as the wire `model` field), not the prettified display name.
    ensure_model.assert_called_once_with(
        client=client,
        existing_keys={("mlx/mlx-community__north-mini-code-1.0-6bit", "language")},
        name="MLX/mlx-community__North-Mini-Code-1.0-6bit",
        provider="openai_compatible",
        model_type="language",
        credential_id="credential:mlx",
    )


def test_do_register_invokes_mlx_registration(monkeypatch, tmp_path: Path):
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.raise_for_status = MagicMock()
    response.json.side_effect = [
        [],
        [],
        {},
        [{"id": "model:mlx", "name": "mlx-community/North-Mini-Code-1.0-6bit"}],
    ]
    client.get.return_value = response
    client.put.return_value = MagicMock(status_code=200, text="{}")

    register_mlx = MagicMock(return_value=True)
    monkeypatch.setattr("desktop.auto_register._list_ollama_models", lambda: [])
    monkeypatch.setattr("desktop.auto_register._list_local_ggufs", lambda _model_dir: [])
    monkeypatch.setattr("desktop.auto_register.register_osaurus_models", lambda **_kwargs: False)
    monkeypatch.setattr("desktop.auto_register.register_mlx_models", register_mlx)

    cfg = Config(
        model_dir=tmp_path / "AI_Models",
        provider="mlx",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )

    _do_register(
        client,
        cfg,
        llamacpp_port=None,
        mlx_base_url="http://127.0.0.1:51231/v1",
        mlx_model_ref="MLX/mlx-community__North-Mini-Code-1.0-6bit",
    )

    register_mlx.assert_called_once()
    assert register_mlx.call_args.kwargs["base_url"] == "http://127.0.0.1:51231/v1"
    assert (
        register_mlx.call_args.kwargs["model_ref"]
        == "MLX/mlx-community__North-Mini-Code-1.0-6bit"
    )
