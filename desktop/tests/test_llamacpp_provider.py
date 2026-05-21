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


# ---------------------------------------------------------------------------
# pick_default_model
# ---------------------------------------------------------------------------


def test_pick_default_model_prefers_hermes(tmp_path):
    """Hermes-3 should win over any other filename."""
    for name, size in [
        ("Mistral-7B-Instruct-v0.3-Q4.gguf", 3 * 1024 * 1024),
        ("Hermes-3-Llama-3.1-8B-Q4_K_M.gguf", 4 * 1024 * 1024),
        ("Qwen2.5-7B-Instruct-Q4.gguf", 3 * 1024 * 1024),
    ]:
        (tmp_path / name).write_bytes(b"x" * size)
    p = LlamaCppProvider(model_dir=tmp_path)
    result = p.pick_default_model()
    assert "Hermes-3" in result


def test_pick_default_model_fallback_to_first(tmp_path):
    """When no preferred name matches, return the first sorted model."""
    for name in ("zebra-model.gguf", "alpha-model.gguf"):
        (tmp_path / name).write_bytes(b"x" * (2 * 1024 * 1024))
    p = LlamaCppProvider(model_dir=tmp_path)
    result = p.pick_default_model()
    # list_models() is sorted; alpha < zebra
    assert result == "alpha-model.gguf"


def test_pick_default_model_empty_dir_returns_empty_string(tmp_path):
    """Empty model directory should return empty string, not raise."""
    p = LlamaCppProvider(model_dir=tmp_path)
    assert p.pick_default_model() == ""


# ---------------------------------------------------------------------------
# v0.7.151 — llama_cpp.server stderr capture
# ---------------------------------------------------------------------------


def test_start_captures_stderr_to_log_file_on_premature_exit(gguf_dir, monkeypatch, tmp_path):
    """v0.7.151 regression.

    The user's launcher.log showed `RuntimeError: llama_cpp.server exited
    prematurely (returncode=1)` with no further diagnostic context —
    stderr was DEVNULL'd. Now:
      1. stderr is routed to ~/.open-notebook-plus/logs/llamacpp_chat_stderr.log
      2. The RuntimeError includes the tail of that file
      3. The log path is referenced in the exception so the user can tail it
    """
    log_dir = tmp_path / "logs"

    # Simulate llama_cpp.server writing diagnostic info to stderr and
    # exiting with returncode=1. We do this by capturing the actual file
    # handle the provider passes to Popen and writing into it ourselves.
    captured_stderr_fh: list = []

    def fake_popen(args, stdout=None, stderr=None, **kwargs):
        # Record the actual file handle so we can write into it.
        captured_stderr_fh.append(stderr)
        if hasattr(stderr, "write"):
            # Provider opened a real file — write a realistic Hermes-3 crash
            stderr.write(b"llama_model_load: error loading model architecture: unknown\n")
            stderr.write(b"unknown model architecture: 'hermes3'\n")
            stderr.write(b"llama_load_model_from_file: failed to load model\n")
            stderr.flush()
        proc = MagicMock()
        proc.poll.return_value = 1   # already exited
        proc.returncode = 1
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51113)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    p = LlamaCppProvider(
        model_dir=gguf_dir,
        ready_probe=lambda port: False,
        max_wait=0.01,
        log_dir=log_dir,
    )
    with pytest.raises(RuntimeError) as exc_info:
        p.start("model_b.gguf")

    msg = str(exc_info.value)
    # The exit code is still surfaced
    assert "returncode=1" in msg
    # The model name is named so the user knows WHICH model failed
    assert "model_b.gguf" in msg
    # The diagnostic stderr tail appears in the message
    assert "unknown model architecture" in msg, (
        f"v0.7.151: stderr tail must be included in the error message. Got:\n{msg}"
    )
    # The log file path is named so the user can tail it
    assert "llamacpp_chat_stderr.log" in msg

    # And the log file actually exists on disk with the captured stderr
    log_path = log_dir / "llamacpp_chat_stderr.log"
    assert log_path.exists(), "stderr logfile must persist for post-mortem"
    contents = log_path.read_text()
    assert "unknown model architecture" in contents


def test_start_includes_stderr_log_path_when_stderr_empty(gguf_dir, monkeypatch, tmp_path):
    """When stderr is empty (process died before writing anything), the
    error message must STILL reference the logfile path AND give a hint
    about likely causes — otherwise the user has no breadcrumb to follow.
    """
    log_dir = tmp_path / "logs"

    def fake_popen(args, stdout=None, stderr=None, **kwargs):
        # Don't write to stderr — simulate a process that segfaults before
        # the logger is set up.
        proc = MagicMock()
        proc.poll.return_value = 139  # SIGSEGV exit code
        proc.returncode = 139
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51114)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    p = LlamaCppProvider(
        model_dir=gguf_dir,
        ready_probe=lambda port: False,
        max_wait=0.01,
        log_dir=log_dir,
    )
    with pytest.raises(RuntimeError) as exc_info:
        p.start("model_b.gguf")

    msg = str(exc_info.value)
    assert "returncode=139" in msg
    # When stderr is empty, the message must say so + reference the path
    assert "Empty stderr" in msg or "stderr" in msg
    assert "llamacpp_chat_stderr.log" in msg


def test_start_falls_back_to_devnull_when_log_dir_unwritable(gguf_dir, monkeypatch, tmp_path):
    """If the log_dir can't be created (e.g. parent is read-only),
    fall back to DEVNULL — don't crash before even spawning.

    The error message in this case must explicitly say stderr capture
    is unavailable so the user knows to check fs permissions.
    """
    bad_log_dir = tmp_path / "definitely_unwritable"

    def fake_popen(args, stdout=None, stderr=None, **kwargs):
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.returncode = 1
        return proc

    # Force mkdir to fail by patching it on Path:
    real_mkdir = Path.mkdir

    def failing_mkdir(self, *args, **kwargs):
        if "definitely_unwritable" in str(self):
            raise PermissionError("read-only")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51115)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    p = LlamaCppProvider(
        model_dir=gguf_dir,
        ready_probe=lambda port: False,
        max_wait=0.01,
        log_dir=bad_log_dir,
    )
    with pytest.raises(RuntimeError) as exc_info:
        p.start("model_b.gguf")

    msg = str(exc_info.value)
    assert "Stderr capture unavailable" in msg, (
        "must explicitly say stderr capture failed so the user can act"
    )


def test_start_includes_stderr_tail_on_never_ready_timeout(gguf_dir, monkeypatch, tmp_path):
    """v0.7.151 — when the process is still alive but never binds the
    port (max_wait timeout), include the stderr tail too. The model may
    be silently hung (mmap blocking, slow GPU init) and the user needs
    to see the partial progress to diagnose.
    """
    log_dir = tmp_path / "logs"

    def fake_popen(args, stdout=None, stderr=None, **kwargs):
        if hasattr(stderr, "write"):
            stderr.write(b"llm_load_tensors: loading 8 of 65 layers to GPU\n")
            stderr.flush()
        proc = MagicMock()
        proc.poll.return_value = None  # still alive
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51116)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    p = LlamaCppProvider(
        model_dir=gguf_dir,
        ready_probe=lambda port: False,
        max_wait=0.01,
        log_dir=log_dir,
    )
    with pytest.raises(RuntimeError) as exc_info:
        p.start("model_b.gguf")

    msg = str(exc_info.value)
    assert "never became ready" in msg
    assert "loading 8 of 65 layers" in msg, (
        "timeout error must include the in-flight stderr so the user can "
        "see e.g. layer-load progress that stalled"
    )
