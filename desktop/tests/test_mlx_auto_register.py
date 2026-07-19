from pathlib import Path
from unittest.mock import MagicMock

import httpx

from desktop.auto_register import _do_register, _migrate_stale_llamacpp_defaults_to_mlx
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
        existing_keys={("default_model", "language")},
        name="default_model",
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
    gguf_scan = MagicMock(return_value=[])
    monkeypatch.setattr("desktop.auto_register._list_ollama_models", lambda: [])
    monkeypatch.setattr("desktop.auto_register._list_local_ggufs", gguf_scan)
    monkeypatch.setattr("desktop.auto_register.register_osaurus_models", lambda **_kwargs: False)
    monkeypatch.setattr("desktop.auto_register.register_mlx_models", register_mlx)
    monkeypatch.setattr(
        "desktop.auto_register._migrate_stale_llamacpp_defaults_to_mlx",
        lambda _client: {},
    )

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
    gguf_scan.assert_not_called()
    assert register_mlx.call_args.kwargs["base_url"] == "http://127.0.0.1:51231/v1"
    assert (
        register_mlx.call_args.kwargs["model_ref"]
        == "MLX/mlx-community__North-Mini-Code-1.0-6bit"
    )


def test_migrate_stale_llamacpp_defaults_to_active_mlx():
    client = MagicMock()
    responses = {
        "/api/models/defaults": {
            "default_chat_model": "model:old-gguf",
            "default_tools_model": "model:old-gguf",
            "default_transformation_model": "model:cloud",
            "large_context_model": None,
            "default_reasoning_model": None,
        },
        "/api/models": [
            {
                "id": "model:old-gguf",
                "name": "Qwen3.5-4B-Q4_K_M",
                "credential": "credential:gguf",
            },
            {
                "id": "model:mlx",
                "name": "default_model",
                "credential": "credential:mlx",
            },
            {
                "id": "model:cloud",
                "name": "cloud-model",
                "credential": "credential:cloud",
            },
        ],
        "/api/credentials": [
            {"id": "credential:gguf", "name": "Local GGUF (llama.cpp)"},
            {"id": "credential:mlx", "name": "MLX (local)"},
            {"id": "credential:cloud", "name": "Cloud"},
        ],
    }

    def fake_get(path):
        response = MagicMock()
        response.json.return_value = responses[path]
        return response

    client.get.side_effect = fake_get
    client.put.return_value = MagicMock(status_code=200, text="{}")

    migrated = _migrate_stale_llamacpp_defaults_to_mlx(client)

    assert migrated == {
        "default_chat_model": "model:mlx",
        "default_tools_model": "model:mlx",
    }
    client.put.assert_called_once_with(
        "/api/models/defaults",
        json=migrated,
    )
