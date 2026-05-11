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
        # v0.3 optional shims — just return an alive proc, don't record order.
        if "llama_cpp" in joined or "whisper_shim" in joined or "piper_shim" in joined:
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
    # Supply enough procs for all possible spawns (4 core + up to 3 v0.3 shims).
    procs = [_alive_proc() for _ in range(7)]
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
