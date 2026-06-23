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
    ensure_model.assert_called_once_with(
        client=client,
        existing_keys={("mlx-community/north-mini-code-1.0-6bit", "language")},
        name="mlx-community/North-Mini-Code-1.0-6bit",
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
