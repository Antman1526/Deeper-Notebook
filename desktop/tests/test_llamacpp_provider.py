# desktop/tests/test_llamacpp_provider.py
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from desktop.providers import ProviderEnv
from desktop.providers.llamacpp import LlamaCppProvider


@pytest.fixture
def gguf_dir(tmp_path: Path) -> Path:
    (tmp_path / "a" / "nested").mkdir(parents=True)
    (tmp_path / "a" / "nested" / "model_a.gguf").write_bytes(b"x" * (2 * 1024 * 1024))
    (tmp_path / "model_b.gguf").write_bytes(b"x" * (3 * 1024 * 1024))
    (tmp_path / "ignore_me.txt").write_text("nope")
    return tmp_path


def test_is_available_true_when_dir_has_gguf(gguf_dir):
    p = LlamaCppProvider(model_dir=gguf_dir)
    assert p.is_available() is True


def test_is_available_false_when_no_gguf(tmp_path):
    p = LlamaCppProvider(model_dir=tmp_path)
    assert p.is_available() is False


def test_list_models_returns_relative_paths_sorted(gguf_dir):
    p = LlamaCppProvider(model_dir=gguf_dir)
    assert p.list_models() == ["a/nested/model_a.gguf", "model_b.gguf"]


def test_list_models_skips_stub_files(gguf_dir):
    (gguf_dir / "stub.gguf").write_bytes(b"x" * 100)  # < 1 MB
    p = LlamaCppProvider(model_dir=gguf_dir)
    assert "stub.gguf" not in p.list_models()


def test_start_spawns_server_and_returns_env(gguf_dir, monkeypatch):
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51111)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    p = LlamaCppProvider(model_dir=gguf_dir, ready_probe=lambda port: True)
    env = p.start("model_b.gguf")
    assert isinstance(env, ProviderEnv)
    # Upstream uses esperanto's openai_compatible provider; env vars confirmed
    # by reading esperanto/providers/llm/openai_compatible.py.
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://127.0.0.1:51111/v1"
    assert env["OPENAI_COMPATIBLE_API_KEY"] == "sk-no-key"
    p.stop()
    fake_proc.terminate.assert_called_once()


def test_start_raises_if_model_missing(tmp_path):
    p = LlamaCppProvider(model_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        p.start("does_not_exist.gguf")


def test_start_raises_if_server_never_ready(gguf_dir, monkeypatch):
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51112)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    p = LlamaCppProvider(model_dir=gguf_dir, ready_probe=lambda port: False, max_wait=0.01)
    with pytest.raises(RuntimeError, match="ready"):
        p.start("model_b.gguf")
