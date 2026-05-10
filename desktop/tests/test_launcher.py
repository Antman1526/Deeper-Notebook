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
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: [40001, 40002, 40003])
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
    procs = [_alive_proc() for _ in range(4)]
    seq = iter(procs)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: next(seq))
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: [40001, 40002, 40003])
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(cfg=cfg, repo_root=tmp_path, bin_dir=tmp_path / "bin",
                    surreal_arch="darwin-arm64", node_arch="darwin-arm64")
    sv.start_all()
    sv.stop_all()
    for p in procs:
        p.terminate.assert_called()


def test_supervisor_writes_session_env(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _alive_proc())
    monkeypatch.setattr("desktop.launcher.find_free_ports", lambda n: [40001, 40002, 40003])
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
