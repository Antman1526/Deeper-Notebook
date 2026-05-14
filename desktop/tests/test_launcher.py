import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop.config import Config
from desktop.launcher import Supervisor


def make_config(tmp_path: Path) -> Config:
    return Config(
        model_dir=tmp_path,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="A" * 24,
    )


@pytest.fixture
def cfg(tmp_path):
    return make_config(tmp_path)


def _alive_proc():
    p = MagicMock()
    p.poll.return_value = None
    return p


def test_supervisor_starts_all_children_in_order(cfg, tmp_path, monkeypatch):
    started: list[str] = []
    procs = {name: _alive_proc() for name in ("surreal", "api", "worker", "next")}

    def fake_popen(args, **kw):
        first = args[0] if isinstance(args, list) else args.split()[0]
        joined = " ".join(args) if isinstance(args, list) else args
        # v0.3/v0.4 optional shims — just return an alive proc, don't record order.
        if ("llama_cpp" in joined or "whisper_shim" in joined or "piper_shim" in joined
                or "memory_shim" in joined or "openchronicle_shim" in joined):
            return _alive_proc()
        # Check more specific patterns first — `surreal-commands-worker` would
        # otherwise match the bare-`surreal` arm.
        if "worker" in joined:
            started.append("worker"); return procs["worker"]
        if "surreal-darwin" in first or "surreal-windows" in first or first.endswith("/surreal"):
            started.append("surreal"); return procs["surreal"]
        if "uvicorn" in joined:
            started.append("api"); return procs["api"]
        if "node" in first or "next" in joined:
            started.append("next"); return procs["next"]
        raise AssertionError(f"unexpected popen: {args}")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
                    surreal_arch="darwin-arm64", node_arch="darwin-arm64")
    sv.start_all()
    try:
        assert started == ["surreal", "api", "worker", "next"]
        assert sv.frontend_url.startswith("http://127.0.0.1:")
    finally:
        sv.stop_all()


def test_supervisor_stop_all_terminates_children(cfg, tmp_path, monkeypatch):
    # Supply enough procs for all possible spawns (4 core + up to 3 v0.3 shims + up to 2 v0.4 shims).
    procs = [_alive_proc() for _ in range(10)]
    seq = iter(procs)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: next(seq))
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
                    surreal_arch="darwin-arm64", node_arch="darwin-arm64")
    sv.start_all()
    spawned_count = len(sv._procs)
    sv.stop_all()
    for p in procs[:spawned_count]:
        p.terminate.assert_called()


def test_supervisor_uses_venv_python_for_api_and_worker(cfg, tmp_path, monkeypatch):
    """Spawned API and worker commands must use the configured venv_python."""
    spawned_args: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned_args.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    fake_venv_python = Path("/tmp/fake/venv/bin/python")
    sv = Supervisor(cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
                    surreal_arch="darwin-arm64", node_arch="darwin-arm64",
                    venv_python=fake_venv_python)
    sv.start_all()
    try:
        # API spawn: [<venv_python>, "-m", "uvicorn", ...]
        api_cmd = next(a for a in spawned_args if "uvicorn" in " ".join(a))
        assert api_cmd[0] == str(fake_venv_python)
        assert "-m" in api_cmd
        assert "uvicorn" in api_cmd

        # Worker spawn: [<venv_python>, "-m", "surreal_commands.cli.worker", ...]
        worker_cmd = next(a for a in spawned_args if "surreal_commands" in " ".join(a))
        assert worker_cmd[0] == str(fake_venv_python)
    finally:
        sv.stop_all()


def test_supervisor_writes_session_env(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _alive_proc())
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
                    surreal_arch="darwin-arm64", node_arch="darwin-arm64",
                    extra_env={"OLLAMA_API_BASE": "http://127.0.0.1:11434"})
    sv.start_all()
    try:
        assert sv.session_env["OLLAMA_API_BASE"] == "http://127.0.0.1:11434"
        assert sv.session_env["SURREAL_URL"].startswith("ws://127.0.0.1:")
        assert sv.session_env["SURREAL_USER"] == "root"
        assert sv.session_env["SURREAL_PASSWORD"] == "A" * 24
    finally:
        sv.stop_all()


def test_supervisor_spawns_v03_children_when_paths_set(cfg, tmp_path, monkeypatch):
    """The 3 new spawn methods fire iff their paths are provided."""
    spawned: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    embed = tmp_path / "nomic.gguf"; embed.write_bytes(b"x" * 2_000_000)
    whisper = tmp_path / "whisper.bin"; whisper.write_bytes(b"x" * 2_000_000)
    amy = tmp_path / "amy.onnx"; amy.write_bytes(b"x" * 200_000)

    sv = Supervisor(
        cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64", node_arch="darwin-arm64",
        nomic_embed_path=embed, whisper_model_path=whisper,
        piper_voices={"alex": amy},
    )
    sv.start_all()
    try:
        joined_args = [" ".join(a) for a in spawned]
        assert any("llama_cpp.server" in s and "--embedding" in s for s in joined_args)
        assert any("desktop_shims.whisper_shim" in s for s in joined_args)
        assert any("desktop_shims.piper_shim" in s for s in joined_args)
        assert any("alex=" in s for s in joined_args)
    finally:
        sv.stop_all()


def test_supervisor_skips_v03_children_when_paths_missing(cfg, tmp_path, monkeypatch):
    spawned: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda a, **kw: (spawned.append(list(a)),
                                         MagicMock(spec=subprocess.Popen,
                                                   poll=MagicMock(return_value=None)))[1])
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
                    surreal_arch="darwin-arm64", node_arch="darwin-arm64")
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert not any("whisper_shim" in s for s in joined)
        assert not any("piper_shim" in s for s in joined)
    finally:
        sv.stop_all()


def test_supervisor_spawns_chat_llm_and_memory_retriever(cfg, tmp_path, monkeypatch):
    """v0.4: with a chat_llm_path and openchronicle_available=False,
    Supervisor.start_all should spawn both llamacpp_chat and memory_shim,
    but NOT openchronicle_shim."""
    spawned: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.launcher.find_free_ports",
                       lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    # Stub chat GGUF so `_spawn_llamacpp_chat` doesn't no-op out.
    chat_gguf = tmp_path / "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"
    chat_gguf.write_bytes(b"FAKE-GGUF")

    sv = Supervisor(
        cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64", node_arch="darwin-arm64",
        chat_llm_path=chat_gguf,
        openchronicle_available=False,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert any("llama_cpp.server" in s and "Hermes-3" in s for s in joined)
        assert any("desktop_shims.memory_shim" in s for s in joined)
        assert not any("openchronicle_shim" in s for s in joined)
        assert sv.chat_llm_port != 0
        assert sv.memory_port != 0
        assert sv.openchronicle_port == 0
    finally:
        sv.stop_all()


def test_supervisor_spawns_openchronicle_when_available(cfg, tmp_path, monkeypatch):
    spawned: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda a, **kw: (spawned.append(list(a)),
                                         MagicMock(spec=subprocess.Popen,
                                                   poll=MagicMock(return_value=None)))[1])
    monkeypatch.setattr("desktop.launcher.find_free_ports",
                       lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64", node_arch="darwin-arm64",
        openchronicle_available=True,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert any("openchronicle_shim" in s for s in joined)
        assert sv.openchronicle_port != 0
    finally:
        sv.stop_all()


def test_supervisor_skips_chat_llm_when_no_path(cfg, tmp_path, monkeypatch):
    """No chat_llm_path → no llamacpp_chat process spawned; chat_llm_port stays 0."""
    spawned: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda a, **kw: (spawned.append(list(a)),
                                         MagicMock(spec=subprocess.Popen,
                                                   poll=MagicMock(return_value=None)))[1])
    monkeypatch.setattr("desktop.launcher.find_free_ports",
                       lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64", node_arch="darwin-arm64",
        chat_llm_path=None,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert not any("llama_cpp.server" in s and "Hermes-3" in s for s in joined)
        assert any("desktop_shims.memory_shim" in s for s in joined)
    finally:
        sv.stop_all()


def test_supervisor_logs_and_progresses_when_optional_service_fails(cfg, tmp_path, monkeypatch, caplog):
    """v0.6.5 regression test: when an optional spawn raises, we must:
      1. log the exception (so users debugging missing binaries can grep logs)
      2. publish progress event with the error message (so the UI status shows it)
      3. NOT crash the launcher (other services keep going)
    """
    import logging

    # Make every spawn succeed EXCEPT piper, which raises a recognizable error.
    def fake_popen(args, **kw):
        joined = " ".join(args) if isinstance(args, list) else args
        if "piper_shim" in joined:
            raise FileNotFoundError("piper voice asset missing: /no/such/path.onnx")
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n)))
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    progress_events: list[tuple[str, str, str]] = []
    progress = MagicMock()
    progress.publish = lambda step, status, message="": progress_events.append((step, status, message))

    # _spawn_piper requires the voice file to actually exist on disk;
    # otherwise it returns early without trying to spawn.
    voice_path = tmp_path / "fake.onnx"
    voice_path.write_bytes(b"")
    sv = Supervisor(
        cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64", node_arch="darwin-arm64",
        progress=progress,
        piper_voices={"en-us-amy": voice_path},
    )

    with caplog.at_level(logging.WARNING, logger="desktop.launcher"):
        sv.start_all()
    try:
        # 1. Logged the exception with traceback (exc_info=True path)
        piper_logs = [r for r in caplog.records if "supervisor.piper" in r.getMessage()]
        assert piper_logs, "expected a warning log for the failed piper spawn"
        assert "piper voice asset missing" in piper_logs[0].getMessage()
        # 2. Progress event includes the error message (not just status)
        piper_errors = [(s, st, m) for (s, st, m) in progress_events
                        if s == "supervisor.piper" and st == "error"]
        assert piper_errors, "expected an error progress event for piper"
        assert "piper voice asset missing" in piper_errors[0][2]
        # 3. Other services kept going (e.g. memory_retriever or openchronicle reached)
        steps_seen = {s for (s, _, _) in progress_events}
        assert "supervisor.memory" in steps_seen, "memory spawn should still run after piper failure"
    finally:
        sv.stop_all()
