from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from desktop.app import (
    _new_context,
    _phase_auto_register,
    _phase_select_provider,
    _stop_runtime,
)
from desktop.config import Config
from desktop.providers import ProviderEnv


class FakeMlxProvider:
    started: list[str] = []
    stopped = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def is_available(self):
        return True

    def pick_default_model(self):
        return "MLX/default-model"

    def start(self, model: str):
        self.started.append(model)
        return ProviderEnv(
            OPENAI_COMPATIBLE_BASE_URL="http://127.0.0.1:51231/v1",
            OPENAI_COMPATIBLE_API_KEY="sk-no-key",
        )

    def stop(self):
        type(self).stopped = True


def test_phase_select_provider_starts_mlx_and_stashes_runtime(monkeypatch, tmp_path):
    import desktop.providers.mlx as mlx_mod

    FakeMlxProvider.started = []
    FakeMlxProvider.stopped = False
    monkeypatch.setattr(mlx_mod, "MlxProvider", FakeMlxProvider)

    ctx = _new_context()
    ctx.cfg = Config(
        model_dir=tmp_path / "AI_Models",
        provider="mlx",
        default_model="MLX/mlx-community__North-Mini-Code-1.0-6bit",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    ctx.log_dir = tmp_path / "logs"
    ctx.venv_py = Path("/tmp/venv/bin/python")

    _phase_select_provider(ctx)

    assert FakeMlxProvider.started == ["MLX/mlx-community__North-Mini-Code-1.0-6bit"]
    assert ctx.extra_env["OPENAI_COMPATIBLE_BASE_URL"] == "http://127.0.0.1:51231/v1"
    assert ctx.extra_env["OPENAI_COMPATIBLE_API_KEY"] == "sk-no-key"
    assert (
        ctx.extra_env["OPEN_NOTEBOOK_ACTIVE_MLX_MODEL"]
        == "MLX/mlx-community__North-Mini-Code-1.0-6bit"
    )
    assert ctx.extra_env["ONP_CHAT_MODEL_NAME"] == "default_model"
    assert ctx.model_provider_runtime is not None

    _stop_runtime(ctx)
    assert FakeMlxProvider.stopped is True


def test_phase_select_provider_uses_default_mlx_model_when_config_blank(
    monkeypatch,
    tmp_path,
):
    import desktop.providers.mlx as mlx_mod

    FakeMlxProvider.started = []
    FakeMlxProvider.stopped = False
    monkeypatch.setattr(mlx_mod, "MlxProvider", FakeMlxProvider)

    ctx = _new_context()
    ctx.cfg = Config(
        model_dir=tmp_path / "AI_Models",
        provider="mlx",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    ctx.log_dir = tmp_path / "logs"
    ctx.venv_py = Path("/tmp/venv/bin/python")

    _phase_select_provider(ctx)

    assert FakeMlxProvider.started == ["MLX/default-model"]
    assert ctx.extra_env["OPEN_NOTEBOOK_ACTIVE_MLX_MODEL"] == "MLX/default-model"
    _stop_runtime(ctx)


def test_phase_select_provider_falls_back_to_mlx_when_chat_gguf_is_missing(
    monkeypatch,
    tmp_path,
):
    import desktop.app as app_mod
    import desktop.providers.mlx as mlx_mod

    FakeMlxProvider.started = []
    FakeMlxProvider.stopped = False
    monkeypatch.setattr(mlx_mod, "MlxProvider", FakeMlxProvider)
    monkeypatch.setattr(app_mod, "_scan_chat_llm_with_timeout", lambda _path: None)
    monkeypatch.setattr(app_mod.sys, "platform", "darwin")

    config_path = tmp_path / "config.toml"
    ctx = _new_context()
    ctx.cfg = Config(
        model_dir=tmp_path / "AI_Models",
        provider="llamacpp",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    ctx._cfg_path = config_path
    ctx.progress_bus = SimpleNamespace(publish=MagicMock())
    ctx.log_dir = tmp_path / "logs"
    ctx.venv_py = Path("/tmp/venv/bin/python")

    _phase_select_provider(ctx)

    assert ctx.cfg.provider == "mlx"
    assert ctx.cfg.default_model == "MLX/default-model"
    assert FakeMlxProvider.started == ["MLX/default-model"]
    assert "provider = 'mlx'" in config_path.read_text()
    assert "default_model = 'MLX/default-model'" in config_path.read_text()
    ctx.progress_bus.publish.assert_called_once_with(
        "provider.mlx",
        "done",
        "No chat GGUF was available; using MLX/default-model through MLX.",
    )
    _stop_runtime(ctx)


def test_phase_select_provider_keeps_llamacpp_when_chat_gguf_exists(
    monkeypatch,
    tmp_path,
):
    import desktop.app as app_mod
    import desktop.providers.mlx as mlx_mod

    FakeMlxProvider.started = []
    monkeypatch.setattr(mlx_mod, "MlxProvider", FakeMlxProvider)
    monkeypatch.setattr(
        app_mod,
        "_scan_chat_llm_with_timeout",
        lambda _path: tmp_path / "GGUF" / "chat.gguf",
    )
    monkeypatch.setattr(app_mod.sys, "platform", "darwin")

    ctx = _new_context()
    ctx.cfg = Config(
        model_dir=tmp_path / "AI_Models",
        provider="llamacpp",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    ctx._cfg_path = tmp_path / "config.toml"
    ctx.log_dir = tmp_path / "logs"
    ctx.venv_py = Path("/tmp/venv/bin/python")

    _phase_select_provider(ctx)

    assert ctx.cfg.provider == "llamacpp"
    assert FakeMlxProvider.started == []
    assert not ctx._cfg_path.exists()


def test_phase_auto_register_passes_mlx_runtime_to_auto_register(monkeypatch, tmp_path):
    import desktop.auto_register as auto_register_mod

    captured = {}

    def fake_auto_register(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(auto_register_mod, "auto_register", fake_auto_register)

    ctx = _new_context()
    ctx.cfg = Config(
        model_dir=tmp_path / "AI_Models",
        provider="mlx",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    ctx.extra_env = {
        "OPENAI_COMPATIBLE_BASE_URL": "http://127.0.0.1:51231/v1",
        "OPEN_NOTEBOOK_ACTIVE_MLX_MODEL": "MLX/mlx-community__North-Mini-Code-1.0-6bit",
    }
    ctx.sv = SimpleNamespace(
        session_env={"INTERNAL_API_URL": "http://127.0.0.1:5055"},
        chat_llm_port=0,
        whisper_port=0,
        piper_port=0,
        embed_port=0,
        memory_port=0,
    )
    ctx.log_dir = tmp_path / "logs"

    _phase_auto_register(ctx)

    assert captured["api_base_url"] == "http://127.0.0.1:5055"
    assert captured["mlx_base_url"] == "http://127.0.0.1:51231/v1"
    assert (
        captured["mlx_model_ref"]
        == "MLX/mlx-community__North-Mini-Code-1.0-6bit"
    )
