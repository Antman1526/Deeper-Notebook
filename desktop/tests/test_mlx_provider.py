import subprocess
import time
from pathlib import Path, PureWindowsPath
from unittest.mock import MagicMock

import pytest

from desktop.providers import ProviderEnv
from desktop.providers.mlx import MlxProvider


@pytest.fixture
def mlx_model_root(tmp_path: Path) -> Path:
    root = tmp_path / "AI_Models"
    repo = root / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    repo.mkdir(parents=True)
    (repo / "config.json").write_text("{}")
    (repo / "tokenizer.json").write_text("{}")
    (repo / "model.safetensors").write_bytes(b"x" * (2 * 1024 * 1024))
    (repo / ".download_complete").write_text("ok")
    incomplete = root / "MLX" / "mlx-community__Incomplete"
    incomplete.mkdir()
    (incomplete / "config.json").write_text("{}")
    return root


def test_is_available_true_when_complete_mlx_repo_exists(mlx_model_root):
    provider = MlxProvider(model_dir=mlx_model_root)
    assert provider.is_available() is True


def test_is_available_false_when_no_mlx_repo(tmp_path):
    provider = MlxProvider(model_dir=tmp_path)
    assert provider.is_available() is False


def test_list_models_returns_complete_mlx_repos(mlx_model_root):
    provider = MlxProvider(model_dir=mlx_model_root)
    assert provider.list_models() == ["MLX/mlx-community__North-Mini-Code-1.0-6bit"]


def test_list_models_uses_forward_slashes_for_windows_public_ids(monkeypatch):
    model_dir = PureWindowsPath(r"C:\AI_Models")
    root = model_dir / "MLX"
    repo = root / "mlx-community__North-Mini-Code-1.0-6bit"

    class CandidateRoot:
        def iterdir(self):
            return iter([repo])

    monkeypatch.setattr("desktop.providers.mlx._mlx_roots", lambda _: [CandidateRoot()])
    monkeypatch.setattr("desktop.providers.mlx._is_complete_mlx_repo", lambda _: True)

    provider = MlxProvider(model_dir=model_dir)
    assert provider.list_models() == ["MLX/mlx-community__North-Mini-Code-1.0-6bit"]


def test_start_spawns_mlx_server_and_returns_openai_compatible_env(
    mlx_model_root,
    monkeypatch,
):
    captured: list[list[str]] = []
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None

    def fake_popen(args, **kwargs):
        captured.append(list(args))
        return fake_proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.providers.mlx.find_free_port", lambda: 51231)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    configured_python = "/tmp/venv/bin/python"
    provider = MlxProvider(
        model_dir=mlx_model_root,
        ready_probe=lambda port: True,
        python_executable=configured_python,
    )
    env = provider.start("MLX/mlx-community__North-Mini-Code-1.0-6bit")

    assert isinstance(env, ProviderEnv)
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://127.0.0.1:51231/v1"
    assert env["OPENAI_COMPATIBLE_API_KEY"] == "sk-no-key"
    assert captured == [
        [
            configured_python,
            "-m",
            "mlx_lm.server",
            "--model",
            str(mlx_model_root / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"),
            "--host",
            "127.0.0.1",
            "--port",
            "51231",
        ]
    ]

    provider.stop()
    fake_proc.terminate.assert_called_once()


def test_start_raises_for_incomplete_model(mlx_model_root):
    provider = MlxProvider(model_dir=mlx_model_root)
    with pytest.raises(FileNotFoundError, match="complete MLX model repo"):
        provider.start("MLX/mlx-community__Incomplete")


def test_start_can_defer_configured_model_validation(mlx_model_root, monkeypatch):
    incomplete = mlx_model_root / "MLX" / "mlx-community__Deferred"
    incomplete.mkdir()
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_proc)
    monkeypatch.setattr("desktop.providers.mlx.find_free_port", lambda: 51232)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    provider = MlxProvider(
        model_dir=mlx_model_root,
        ready_probe=lambda _port: True,
    )
    result = provider.start("MLX/mlx-community__Deferred", validate=False)

    assert result["OPENAI_COMPATIBLE_BASE_URL"] == "http://127.0.0.1:51232/v1"
    provider.stop()


def test_start_can_return_before_a_configured_worker_is_ready(
    mlx_model_root, monkeypatch
):
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: fake_proc)
    monkeypatch.setattr("desktop.providers.mlx.find_free_port", lambda: 51233)

    provider = MlxProvider(
        model_dir=mlx_model_root,
        ready_probe=lambda _port: False,
    )
    result = provider.start(
        "MLX/mlx-community__North-Mini-Code-1.0-6bit",
        wait_for_ready=False,
    )

    assert result["OPENAI_COMPATIBLE_BASE_URL"] == "http://127.0.0.1:51233/v1"
    provider.stop()


def test_start_raises_if_server_never_ready(mlx_model_root, monkeypatch):
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr("desktop.providers.mlx.find_free_port", lambda: 51232)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    provider = MlxProvider(
        model_dir=mlx_model_root,
        ready_probe=lambda port: False,
        max_wait=0.01,
    )
    with pytest.raises(RuntimeError, match="never became ready"):
        provider.start("MLX/mlx-community__North-Mini-Code-1.0-6bit")


def test_start_refuses_missing_path_even_without_validation(
    mlx_model_root, monkeypatch
):
    """v0.8.84 — a configured model (validate=False) deleted from disk must
    fail loudly BEFORE spawning: mlx_lm.server runs with stderr=DEVNULL, so a
    doomed spawn dies silently and leaves a credential pointing at a dead
    port with no visible cause ("Degraded" and nothing else).
    """
    spawned = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **kw: spawned.append(a) or MagicMock()
    )

    provider = MlxProvider(model_dir=mlx_model_root)
    with pytest.raises(FileNotFoundError, match="no longer exists on disk"):
        provider.start(
            "MLX/deleted-after-configuration",
            validate=False,
            wait_for_ready=False,
        )
    assert spawned == [], "must not spawn a server for a nonexistent model"


def test_start_captures_stderr_to_data_root_log(mlx_model_root, monkeypatch, tmp_path):
    """v0.8.85 — the MLX server's stderr must land in a log, not DEVNULL:
    a dying server's traceback was the missing evidence for hours."""
    captured = {}

    def fake_popen(args, stdout=None, stderr=None, **kw):
        captured["stderr"] = stderr
        # NOTE: no spec= here — subprocess.Popen is already patched to this
        # function, so spec'ing against it would strip Popen's real attrs.
        proc = MagicMock()
        proc.poll.return_value = None
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.providers.mlx.find_free_port", lambda: 51230)
    monkeypatch.setattr("desktop.data_root.active_data_root", lambda: tmp_path)

    provider = MlxProvider(model_dir=mlx_model_root)
    provider.start(
        "MLX/mlx-community__North-Mini-Code-1.0-6bit",
        validate=False,
        wait_for_ready=False,
    )

    assert captured["stderr"] is not subprocess.DEVNULL
    assert (tmp_path / "logs" / "mlx_server.log").exists()
    provider.stop()
