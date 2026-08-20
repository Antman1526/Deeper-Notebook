import json
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop.config import Config
from desktop.launcher import ResourceGovernor, Supervisor


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


# v0.7.155 — Autouse fixture: stub the v0.7.142 singleton + orphan reaper
# for EVERY test in this file. Without this, any test calling
# Supervisor.start_all() raises AlreadyRunning when the user's real
# app is running (because acquire_singleton writes to the real
# ~/.open-notebook-plus/launcher.pid), or pollutes that file between
# test invocations even when the app isn't running. The 15 historic
# launcher-test failures (including all 4 chat_llm_n_ctx_* tests and
# all 11 supervisor_* tests) trace back to this single missing stub.
#
# Both imports are function-scoped inside Supervisor.start_all() at
# desktop/launcher.py:148 + :162, so we patch the SOURCE module
# (`desktop.singleton.*`) directly — that's what the local-import
# binds to at call time. Patching `desktop.launcher.acquire_singleton`
# would only work if the import were module-scoped.
@pytest.fixture(autouse=True)
def _stub_singleton(monkeypatch):
    class _FakeSingletonHandle:
        def release(self) -> None:
            pass

    monkeypatch.setattr(
        "desktop.singleton.acquire_singleton",
        lambda *a, **kw: _FakeSingletonHandle(),
    )
    monkeypatch.setattr(
        "desktop.singleton.reap_orphans",
        lambda *a, **kw: [],
    )
    yield


def _alive_proc():
    p = MagicMock()
    p.poll.return_value = None
    return p


def test_supervisor_uses_source_standalone_frontend_when_built(cfg, tmp_path):
    standalone = tmp_path / "frontend" / ".next" / "standalone"
    standalone.mkdir(parents=True)
    (standalone / "server.js").write_text("// standalone server\n")

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )

    assert sv._next_frontend_dir() == standalone


def test_supervisor_resolves_traced_source_standalone_and_assets(cfg, tmp_path):
    frontend = tmp_path / "frontend"
    standalone = frontend / ".next" / "standalone" / "frontend"
    standalone.mkdir(parents=True)
    (standalone / "server.js").write_text("// traced standalone server\n")
    (frontend / ".next" / "static" / "chunks").mkdir(parents=True)
    (frontend / ".next" / "static" / "chunks" / "app.js").write_text("app")
    (frontend / "public").mkdir()
    (frontend / "public" / "logo.svg").write_text("<svg />")
    (frontend / ".next" / "required-server-files.json").write_text(
        json.dumps(
            {
                "appDir": str(frontend),
                "config": {"outputFileTracingRoot": str(tmp_path)},
            }
        )
    )

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )

    assert sv._next_frontend_dir() == standalone
    assert (standalone / ".next" / "static" / "chunks" / "app.js").is_file()
    assert (standalone / "public" / "logo.svg").is_file()


def test_supervisor_keeps_packaged_frontend_layout_when_no_source_build(cfg, tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "server.js").write_text("// packaged server\n")

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )

    assert sv._next_frontend_dir() == frontend


def test_supervisor_starts_all_children_in_order(cfg, tmp_path, monkeypatch):
    started: list[str] = []
    procs = {name: _alive_proc() for name in ("surreal", "api", "worker", "next")}

    def fake_popen(args, **kw):
        first = args[0] if isinstance(args, list) else args.split()[0]
        joined = " ".join(args) if isinstance(args, list) else args
        # v0.3/v0.4 optional shims — just return an alive proc, don't record order.
        if (
            "llama_cpp" in joined
            or "whisper_shim" in joined
            or "piper_shim" in joined
            or "memory_shim" in joined
            or "openchronicle_shim" in joined
        ):
            return _alive_proc()
        # Check more specific patterns first — `surreal-commands-worker` would
        # otherwise match the bare-`surreal` arm.
        if "worker" in joined:
            started.append("worker")
            return procs["worker"]
        if (
            "surreal-darwin" in first
            or "surreal-windows" in first
            or first.endswith("/surreal")
        ):
            started.append("surreal")
            return procs["surreal"]
        if "uvicorn" in joined:
            started.append("api")
            return procs["api"]
        if "node" in first or "next" in joined:
            started.append("next")
            return procs["next"]
        raise AssertionError(f"unexpected popen: {args}")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    try:
        assert started == ["surreal", "api", "worker", "next"]
        assert sv.frontend_url.startswith("http://127.0.0.1:")
    finally:
        sv.stop_all()


def test_resource_governor_queues_second_heavyweight_and_releases_sidecar_reservation():
    governor = ResourceGovernor(memory_limit_bytes=10)

    assert governor.reserve("mlx-first", 6, heavyweight_mlx=True) == "reserved"
    assert governor.reserve("speech", 2) == "reserved"
    assert governor.reserve("mlx-second", 6, heavyweight_mlx=True) == "queued"
    governor.release("speech")

    assert governor.snapshot()["reservations"] == {"mlx-first": 6}
    assert governor.snapshot()["queued_heavyweight_swaps"] == ["mlx-second"]


def test_resource_governor_stops_partial_provider_after_failed_health_check():
    governor = ResourceGovernor(memory_limit_bytes=10)
    proc = MagicMock()

    started = governor.start_provider(
        "embed",
        reservation_bytes=2,
        spawn=lambda: proc,
        health_check=lambda _proc: False,
    )

    assert started is False
    proc.terminate.assert_called_once()
    assert governor.snapshot()["reservations"] == {}


def test_try_spawn_reserves_a_real_sidecar_and_cleans_it_up_after_failed_health(
    cfg, tmp_path, monkeypatch
):
    sv = Supervisor(cfg, tmp_path, tmp_path / "bin", "darwin-arm64", "darwin-arm64")
    proc = _alive_proc()
    monkeypatch.setattr(sv, "_sidecar_health_check", lambda _kind, _proc: False)

    def spawn(_port):
        sv._procs.append(proc)

    sv._try_spawn("supervisor.llamacpp_embed", spawn, 41234)

    proc.terminate.assert_called_once()
    assert sv.resource_governor.snapshot()["reservations"] == {}
    assert "embed" not in sv._sidecar_procs


def test_try_spawn_releases_reservation_when_sidecar_spawn_raises(
    cfg, tmp_path, monkeypatch
):
    sv = Supervisor(cfg, tmp_path, tmp_path / "bin", "darwin-arm64", "darwin-arm64")
    proc = _alive_proc()
    monkeypatch.setattr(sv, "_sidecar_health_check", lambda _kind, _proc: True)

    def partial_spawn(_port):
        sv._procs.append(proc)
        raise RuntimeError("health setup failed")

    sv._try_spawn("supervisor.llamacpp_embed", partial_spawn, 41234)

    proc.terminate.assert_called_once()
    assert sv.resource_governor.snapshot()["reservations"] == {}


def test_try_spawn_queues_a_heavyweight_mlx_chat_when_another_is_reserved(
    cfg, tmp_path
):
    mlx_cfg = Config(
        model_dir=cfg.model_dir,
        provider="mlx",
        default_model="",
        surreal_user=cfg.surreal_user,
        surreal_password=cfg.surreal_password,
    )
    sv = Supervisor(mlx_cfg, tmp_path, tmp_path / "bin", "darwin-arm64", "darwin-arm64")
    assert (
        sv.resource_governor.reserve("other-heavyweight", 1, heavyweight_mlx=True)
        == "reserved"
    )
    started: list[int] = []

    sv._try_spawn("supervisor.llamacpp_chat", lambda port: started.append(port), 41234)

    assert started == []
    assert sv.resource_governor.snapshot()["queued_heavyweight_swaps"] == ["chat"]


def test_restart_sidecar_replaces_its_reservation_under_a_tight_memory_limit(
    cfg, tmp_path, monkeypatch
):
    tight_cfg = Config(
        cfg.model_dir,
        "none",
        "",
        cfg.surreal_user,
        cfg.surreal_password,
        local_model_memory_limit_bytes=1024**3,
    )
    sv = Supervisor(
        tight_cfg, tmp_path, tmp_path / "bin", "darwin-arm64", "darwin-arm64"
    )
    old, new = _alive_proc(), _alive_proc()
    assert sv.resource_governor.reserve("embed", 1024**3) == "reserved"
    sv._sidecar_procs["embed"] = old
    sv._sidecar_spawn_args["embed"] = (41234, "supervisor.llamacpp_embed")
    sv._procs = [old]
    monkeypatch.setattr(
        "desktop.launcher.os.getpgid", lambda _pid: (_ for _ in ()).throw(OSError())
    )
    monkeypatch.setattr(
        sv, "_spawn_llamacpp_embed", lambda _port: sv._procs.append(new)
    )
    monkeypatch.setattr(sv, "_sidecar_health_check", lambda _kind, _proc: True)

    ok, _detail = sv.restart_sidecar("embed")

    assert ok is True
    old.terminate.assert_called_once()
    assert sv._sidecar_procs["embed"] is new
    assert sv.resource_governor.snapshot()["reservations"] == {"embed": 1024**3}


def test_restart_sidecar_replaces_its_heavyweight_mlx_reservation(
    cfg, tmp_path, monkeypatch
):
    mlx_cfg = Config(
        cfg.model_dir,
        "mlx",
        "",
        cfg.surreal_user,
        cfg.surreal_password,
        local_model_memory_limit_bytes=5 * 1024**3,
    )
    sv = Supervisor(mlx_cfg, tmp_path, tmp_path / "bin", "darwin-arm64", "darwin-arm64")
    old, new = _alive_proc(), _alive_proc()
    assert (
        sv.resource_governor.reserve("chat", 5 * 1024**3, heavyweight_mlx=True)
        == "reserved"
    )
    sv._sidecar_procs["chat"] = old
    sv._sidecar_spawn_args["chat"] = (41234, "supervisor.llamacpp_chat")
    sv._procs = [old]
    monkeypatch.setattr(
        "desktop.launcher.os.getpgid", lambda _pid: (_ for _ in ()).throw(OSError())
    )
    monkeypatch.setattr(sv, "_spawn_llamacpp_chat", lambda _port: sv._procs.append(new))
    monkeypatch.setattr(sv, "_sidecar_health_check", lambda _kind, _proc: True)

    ok, _detail = sv.restart_sidecar("chat")

    assert ok is True
    assert sv.resource_governor.snapshot()["reservations"] == {"chat": 5 * 1024**3}


def test_restart_sidecar_keeps_existing_tracking_when_kill_cannot_be_confirmed(
    cfg, tmp_path, monkeypatch
):
    tight_cfg = Config(
        cfg.model_dir,
        "none",
        "",
        cfg.surreal_user,
        cfg.surreal_password,
        local_model_memory_limit_bytes=1024**3,
    )
    sv = Supervisor(
        tight_cfg, tmp_path, tmp_path / "bin", "darwin-arm64", "darwin-arm64"
    )
    old = _alive_proc()
    old.wait.side_effect = subprocess.TimeoutExpired("embed", 5)
    assert sv.resource_governor.reserve("embed", 1024**3) == "reserved"
    sv._sidecar_procs["embed"] = old
    sv._sidecar_spawn_args["embed"] = (41234, "supervisor.llamacpp_embed")
    sv._procs = [old]
    pgids = iter((41234, OSError("missing process group")))

    def getpgid(_pid):
        value = next(pgids)
        if isinstance(value, OSError):
            raise value
        return value

    monkeypatch.setattr(
        "desktop.launcher.os.getpgid",
        getpgid,
    )
    spawned: list[int] = []
    monkeypatch.setattr(sv, "_spawn_llamacpp_embed", lambda port: spawned.append(port))

    ok, detail = sv.restart_sidecar("embed")

    assert ok is False
    assert "could not be confirmed" in detail
    assert spawned == []
    assert sv._sidecar_procs["embed"] is old
    assert sv._procs == [old]
    assert sv.resource_governor.snapshot()["reservations"] == {"embed": 1024**3}


def test_supervisor_stop_all_terminates_children(cfg, tmp_path, monkeypatch):
    # Supply enough procs for all possible spawns (4 core + up to 3 v0.3 shims + up to 2 v0.4 shims).
    procs = [_alive_proc() for _ in range(10)]
    seq = iter(procs)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: next(seq))
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    spawned_count = len(sv._procs)
    sv.stop_all()
    for p in procs[:spawned_count]:
        p.terminate.assert_called()


def test_supervisor_registers_owned_process_cleanup_for_launcher_signals(
    cfg, tmp_path, monkeypatch
):
    captured: dict[str, object] = {}
    procs = [_alive_proc() for _ in range(10)]
    seq = iter(procs)

    class _Handle:
        def release(self) -> None:
            pass

    def capture_singleton(*_args, **kwargs):
        captured.update(kwargs)
        return _Handle()

    monkeypatch.setattr(
        "desktop.singleton.acquire_singleton",
        capture_singleton,
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: next(seq))
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports",
        lambda n: list(range(40001, 40001 + n)),
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()

    cleanup = captured["on_signal_cleanup"]
    cleanup(signal.SIGTERM)

    assert all(proc.terminate.called for proc in procs[: len(sv._procs)])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups only")
def test_stop_all_escalates_a_surviving_owned_process_group(cfg, tmp_path, monkeypatch):
    proc = MagicMock()
    proc.pid = 41001
    proc.wait.return_value = 0
    group_alive = True
    signals: list[int] = []

    def fake_killpg(process_group: int, requested_signal: int) -> None:
        nonlocal group_alive
        assert process_group == proc.pid
        signals.append(requested_signal)
        if requested_signal == 0 and not group_alive:
            raise ProcessLookupError
        if requested_signal == signal.SIGKILL:
            group_alive = False

    monkeypatch.setattr("desktop.launcher.os.killpg", fake_killpg)
    monkeypatch.setenv("DEEPER_NOTEBOOK_SHUTDOWN_GRACE_SECS", "0.01")

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv._procs = [proc]

    sv.stop_all()

    assert signal.SIGTERM in signals
    assert signal.SIGKILL in signals
    assert group_alive is False


def test_supervisor_children_cannot_mutate_packaged_python_bytecode(
    cfg, tmp_path, monkeypatch
):
    """Runtime imports must not rewrite signed ``upstream/**/__pycache__``."""
    spawned_envs: list[dict[str, str]] = []

    def fake_popen(_args, **kwargs):
        spawned_envs.append(kwargs["env"])
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports",
        lambda n: list(range(40001, 40001 + n)),
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    try:
        assert spawned_envs
        assert all(env.get("PYTHONDONTWRITEBYTECODE") == "1" for env in spawned_envs)
    finally:
        sv.stop_all()


def test_supervisor_uses_venv_python_for_api_and_worker(cfg, tmp_path, monkeypatch):
    """Spawned API and worker commands must use the configured venv_python."""
    spawned_args: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned_args.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    fake_venv_python = Path("/tmp/fake/venv/bin/python")
    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        venv_python=fake_venv_python,
    )
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
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        extra_env={"OLLAMA_API_BASE": "http://127.0.0.1:11434"},
    )
    sv.start_all()
    try:
        assert sv.session_env["OLLAMA_API_BASE"] == "http://127.0.0.1:11434"
        assert sv.session_env["SURREAL_URL"].startswith("ws://127.0.0.1:")
        assert sv.session_env["SURREAL_USER"] == "root"
        assert sv.session_env["SURREAL_PASSWORD"] == "A" * 24
        assert sv.session_env["DEEPER_NOTEBOOK_MODEL_DIR"] == str(cfg.model_dir)
        assert sv.session_env["DEEPER_NOTEBOOK_COMPUTE_PROFILE"] == "balanced"
        # v0.8.4 — CRITICAL: DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL must be
        # in session_env so the API child can probe llama.cpp sidecar
        # health. Without this, v0.8.0 Phase 3 smart routing's
        # "prefer local when healthy" branch was dead in production —
        # `_local_chat_healthy_cached` always saw an empty URL and
        # returned False, so every routed turn went to cloud. Guards
        # against silent regression if a future edit drops the key.
        assert sv.session_env["DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL"].startswith(
            "http://127.0.0.1:"
        ), (
            "DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL missing from session_env; "
            "v0.8.4 fix regressed — smart router's local-prefer branch "
            "is dead again"
        )
        assert sv.session_env["DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL"].endswith("/v1")
        # And the port should match the chat_llm_port the launcher
        # already wires into MEMORY_CHAT_LLM_URL — same source of truth.
        memory_url = sv.session_env["MEMORY_CHAT_LLM_URL"]
        local_url = sv.session_env["DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL"]
        assert memory_url == local_url, (
            f"both env vars must point at the SAME chat_llm_port. "
            f"MEMORY_CHAT_LLM_URL={memory_url!r}, "
            f"DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL={local_url!r}"
        )
        # v0.8.7 — DEEPER_NOTEBOOK_LOCAL_N_CTX must be in session_env
        # carrying the launcher's resolved n_ctx, so the router's
        # pick_provider() math matches what the chat sidecar actually
        # binds. Pre-v0.8.7 this key wasn't set, so the router
        # defaulted to 32768 even when GGUF autodetect picked higher
        # (e.g. Hermes-3 131k) — operators with capable models
        # under-routed to cloud.
        assert "DEEPER_NOTEBOOK_LOCAL_N_CTX" in sv.session_env, (
            "DEEPER_NOTEBOOK_LOCAL_N_CTX missing from session_env; "
            "v0.8.7 fix regressed — router falls back to 32768 default "
            "instead of using launcher's auto-detected ceiling"
        )
        # v0.8.67i — no env override + no real GGUF falls back to the
        # RAM-aware default ceiling (was a hardcoded "32768"). Assert the
        # router's value tracks the launcher's own _default_ctx_max() so
        # the linkage holds on any machine (32768 on CI / small RAM,
        # higher on a big-RAM Mac).
        expected_ctx = str(sv._default_ctx_max())
        assert sv.session_env["DEEPER_NOTEBOOK_LOCAL_N_CTX"] == expected_ctx, (
            f"unexpected default n_ctx in session_env: "
            f"{sv.session_env['DEEPER_NOTEBOOK_LOCAL_N_CTX']!r} "
            f"(expected {expected_ctx!r} with no override and no GGUF)"
        )
    finally:
        sv.stop_all()


def test_chat_llm_n_ctx_propagates_to_session_env_via_env_override(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.7 — DEEPER_NOTEBOOK_CHAT_LLM_CTX explicit override must reach the
    router via DEEPER_NOTEBOOK_LOCAL_N_CTX. Pre-v0.8.7 the operator's
    DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192 made the SIDECAR bind 8k but the router
    still thought it had 32k headroom (no propagation). v0.8.5
    patched the router to read DEEPER_NOTEBOOK_CHAT_LLM_CTX as a fallback;
    v0.8.7 closes the propagation loop by exporting the resolved
    value directly so the explicit-router-knob path
    (DEEPER_NOTEBOOK_LOCAL_N_CTX, set by the launcher) wins."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", "8192")
    monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_N_CTX", raising=False)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _alive_proc())
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports",
        lambda n: list(range(40001, 40001 + n)),
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    try:
        assert sv.session_env["DEEPER_NOTEBOOK_LOCAL_N_CTX"] == "8192", (
            f"launcher's resolved n_ctx (from DEEPER_NOTEBOOK_CHAT_LLM_CTX env) "
            f"must propagate to DEEPER_NOTEBOOK_LOCAL_N_CTX in session_env; "
            f"got {sv.session_env.get('DEEPER_NOTEBOOK_LOCAL_N_CTX')!r}"
        )
        # And sv.chat_llm_n_ctx (the in-memory copy that
        # _spawn_llamacpp_chat reads for --n_ctx argv) must match —
        # single source of truth check, guards against a future edit
        # that double-resolves and drifts.
        assert sv.chat_llm_n_ctx == 8192, (
            f"chat_llm_n_ctx in-memory={sv.chat_llm_n_ctx!r} but "
            f"session_env says "
            f"{sv.session_env.get('DEEPER_NOTEBOOK_LOCAL_N_CTX')!r}; "
            f"two sources of truth — v0.8.7 fix regressed"
        )
    finally:
        sv.stop_all()


def test_supervisor_injects_data_folder_absolute_path(cfg, tmp_path, monkeypatch):
    """v0.7.147 regression test.

    The API subprocess inherits cwd=upstream_root which is read-only when
    the .app is launched from a mounted DMG. deeper_notebook/config.py used
    to hardcode "./data" → EROFS at module import → uvicorn crash →
    launcher's 180s /readyz wait timed out → silent exit.

    The supervisor must inject DATA_FOLDER as an absolute path under
    ~/.deeper-notebook/data so the API can always write its sqlite-db
    and uploads regardless of cwd writability.
    """
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _alive_proc())
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)
    # Force a known HOME so the assertion is deterministic.
    monkeypatch.setenv("HOME", str(tmp_path))

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    try:
        data_folder = sv.session_env.get("DATA_FOLDER")
        assert data_folder is not None, "DATA_FOLDER must be set in session_env"
        # MUST be absolute — relative paths are exactly the bug we fixed.
        assert Path(data_folder).is_absolute(), (
            f"DATA_FOLDER must be absolute, got: {data_folder!r}"
        )
        # MUST point under the user's per-app dir so subsequent makedirs succeed.
        assert ".deeper-notebook" in data_folder
        assert Path(data_folder).name == "data"
        # MUST already exist (we mkdir it before populating session_env).
        assert Path(data_folder).is_dir(), (
            f"DATA_FOLDER must exist on disk, got: {data_folder!r}"
        )
    finally:
        sv.stop_all()


def test_supervisor_spawns_v03_children_when_paths_set(cfg, tmp_path, monkeypatch):
    """The 3 new spawn methods fire iff their paths are provided."""
    spawned: list[list[str]] = []

    def fake_popen(args, **kw):
        spawned.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    embed = tmp_path / "nomic.gguf"
    embed.write_bytes(b"x" * 2_000_000)
    whisper = tmp_path / "whisper.bin"
    whisper.write_bytes(b"x" * 2_000_000)
    amy = tmp_path / "amy.onnx"
    amy.write_bytes(b"x" * 200_000)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        nomic_embed_path=embed,
        whisper_model_path=whisper,
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
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda a, **kw: (
            spawned.append(list(a)),
            # v0.8.66 — provide stdout/stderr (None) so the
            # launcher's v0.8.38 sidecar-log drainer branch
            # (`proc.stderr is not None`) sees a real attr.
            # A spec=subprocess.Popen mock blocks these
            # (instance attrs absent from the class) → the
            # pre-existing AttributeError on `proc.stderr`.
            MagicMock(poll=MagicMock(return_value=None), stdout=None, stderr=None),
        )[1],
    )
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
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
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    # Stub chat GGUF so `_spawn_llamacpp_chat` doesn't no-op out.
    chat_gguf = tmp_path / "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"
    chat_gguf.write_bytes(b"FAKE-GGUF")

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
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
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda a, **kw: (
            spawned.append(list(a)),
            # v0.8.66 — provide stdout/stderr (None) so the
            # launcher's v0.8.38 sidecar-log drainer branch
            # (`proc.stderr is not None`) sees a real attr.
            # A spec=subprocess.Popen mock blocks these
            # (instance attrs absent from the class) → the
            # pre-existing AttributeError on `proc.stderr`.
            MagicMock(poll=MagicMock(return_value=None), stdout=None, stderr=None),
        )[1],
    )
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
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
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda a, **kw: (
            spawned.append(list(a)),
            # v0.8.66 — provide stdout/stderr (None) so the
            # launcher's v0.8.38 sidecar-log drainer branch
            # (`proc.stderr is not None`) sees a real attr.
            # A spec=subprocess.Popen mock blocks these
            # (instance attrs absent from the class) → the
            # pre-existing AttributeError on `proc.stderr`.
            MagicMock(poll=MagicMock(return_value=None), stdout=None, stderr=None),
        )[1],
    )
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        chat_llm_path=None,
    )
    sv.start_all()
    try:
        joined = [" ".join(a) for a in spawned]
        assert not any("llama_cpp.server" in s and "Hermes-3" in s for s in joined)
        assert any("desktop_shims.memory_shim" in s for s in joined)
    finally:
        sv.stop_all()


def test_supervisor_logs_and_progresses_when_optional_service_fails(
    cfg, tmp_path, monkeypatch, caplog
):
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
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    progress_events: list[tuple[str, str, str]] = []
    progress = MagicMock()
    progress.publish = lambda step, status, message="": progress_events.append(
        (step, status, message)
    )

    # _spawn_piper requires the voice file to actually exist on disk;
    # otherwise it returns early without trying to spawn.
    voice_path = tmp_path / "fake.onnx"
    voice_path.write_bytes(b"")
    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
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
        piper_errors = [
            (s, st, m)
            for (s, st, m) in progress_events
            if s == "supervisor.piper" and st == "error"
        ]
        assert piper_errors, "expected an error progress event for piper"
        assert "piper voice asset missing" in piper_errors[0][2]
        # 3. Other services kept going (e.g. memory_retriever or openchronicle reached)
        steps_seen = {s for (s, _, _) in progress_events}
        assert "supervisor.memory" in steps_seen, (
            "memory spawn should still run after piper failure"
        )
    finally:
        sv.stop_all()


# ---------------------------------------------------------------------------
# v0.7.8 — DEEPER_NOTEBOOK_CHAT_LLM_CTX env-var handling in _spawn_llamacpp_chat
#
# The chat LLM server's --n_ctx was hardcoded to 8192, which (a) capped
# every chat session below the model's true context window for modern
# local models (Hermes-3 / Qwen2.5 / Mistral-7B / Llama-3.2 all support
# 32k+), and (b) contradicted v0.7.4's Studio fix that sizes combined
# inputs at ~15k tokens. These tests pin the new env-var contract so a
# future refactor can't silently regress the cap.
# ---------------------------------------------------------------------------


def _build_chat_sv(cfg, tmp_path):
    """Helper: build a Supervisor with a stub chat GGUF on disk.

    Without the GGUF file present, `_spawn_llamacpp_chat` returns early
    and no llama_cpp.server process is spawned — which would mask any
    n_ctx assertion.
    """
    chat_gguf = tmp_path / "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"
    chat_gguf.write_bytes(b"FAKE-GGUF")
    return Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        chat_llm_path=chat_gguf,
        openchronicle_available=False,
    )


def _capture_n_ctx(spawned: list[list[str]]) -> str | None:
    """Pull the --n_ctx value out of the llama_cpp.server command line."""
    for args in spawned:
        joined = " ".join(args)
        if "llama_cpp.server" in joined and "Hermes-3" in joined:
            # args is [..., "--n_ctx", "<value>", ...]
            for i, tok in enumerate(args):
                if tok == "--n_ctx" and i + 1 < len(args):
                    return args[i + 1]
    return None


def _stub_launcher_io(monkeypatch, spawned: list[list[str]]):
    def fake_popen(args, **kw):
        spawned.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: list(range(40001, 40001 + n))
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)
    # v0.7.155 — Singleton + reap_orphans are stubbed module-wide via
    # the autouse `_stub_singleton` fixture at the top of this file.
    # No per-test stubbing needed here.


def test_chat_llm_n_ctx_defaults_to_ram_aware_cap(cfg, tmp_path, monkeypatch):
    """v0.7.206 / v0.8.67i — No DEEPER_NOTEBOOK_CHAT_LLM_CTX env var → the server gets
    --n_ctx equal to the launcher's default ceiling.

    v0.7.206 bumped the floor from 16384 to 32768 after a user hit
    `400 context_length_exceeded` selecting 2-3 sources (~21k tokens; the
    16k cap dated to gemma-2-9b / codellama-13b). v0.8.67i then made that
    ceiling RAM-aware on Apple Silicon — a 26-source ~72K-token context
    overflowed even the flat 32768 on a 64GB Mac whose model (Hermes-3,
    131072 native) could hold it — so the default is now
    Supervisor._default_ctx_max(): 32768 on small-RAM / non-darwin hosts,
    higher on a big-RAM Mac. This test pins that the spawned --n_ctx
    tracks that default (deterministic on any machine).

    Auto-detection from GGUF metadata is also tried when no env var is set —
    this test uses a fake GGUF path so detection falls back to the cap.
    """
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX", raising=False)
    spawned: list[list[str]] = []
    _stub_launcher_io(monkeypatch, spawned)

    sv = _build_chat_sv(cfg, tmp_path)
    sv.start_all()
    try:
        n_ctx = _capture_n_ctx(spawned)
        expected = str(sv._default_ctx_max())
        assert n_ctx == expected, (
            f"expected RAM-aware default {expected!r}, got {n_ctx!r}"
        )
    finally:
        sv.stop_all()


def test_chat_llm_n_ctx_respects_env_var(cfg, tmp_path, monkeypatch):
    """DEEPER_NOTEBOOK_CHAT_LLM_CTX=<n> → server gets --n_ctx <n>.

    Users with capable models (Hermes-3 @ 131k, Qwen2.5 @ 32k) must be
    able to raise the ceiling without code edits; users on constrained
    hardware must be able to lower it for RAM budget reasons.
    """
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", "32768")
    spawned: list[list[str]] = []
    _stub_launcher_io(monkeypatch, spawned)

    sv = _build_chat_sv(cfg, tmp_path)
    sv.start_all()
    try:
        n_ctx = _capture_n_ctx(spawned)
        assert n_ctx == "32768", f"expected env-driven 32768, got {n_ctx!r}"
    finally:
        sv.stop_all()


def test_chat_llm_n_ctx_falls_back_on_non_int(cfg, tmp_path, monkeypatch):
    """v0.7.206 — Garbage in env var → falls back to DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX
    (default 32768) instead of passing through.

    llama-cpp's --n_ctx is an integer arg; forwarding "abc" would crash
    the server at spawn time and leave the memory writer permanently
    broken until the user noticed.
    """
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", "not-an-int")
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX", raising=False)
    spawned: list[list[str]] = []
    _stub_launcher_io(monkeypatch, spawned)

    sv = _build_chat_sv(cfg, tmp_path)
    sv.start_all()
    try:
        n_ctx = _capture_n_ctx(spawned)
        # v0.8.67i — the fallback target is the RAM-aware default cap
        # (Supervisor._default_ctx_max()), not a flat 32768.
        expected = str(sv._default_ctx_max())
        assert n_ctx == expected, (
            f"expected fallback to default cap {expected!r}, got {n_ctx!r}"
        )
    finally:
        sv.stop_all()


def test_chat_llm_n_ctx_falls_back_when_too_low(cfg, tmp_path, monkeypatch):
    """v0.7.206 — DEEPER_NOTEBOOK_CHAT_LLM_CTX < 512 → falls back to
    DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX (default 32768).

    Below ~512 tokens the chat server is effectively unusable (system
    prompt alone won't fit), so a fat-fingered "128" or "0" is almost
    certainly a typo.
    """
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", "128")
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX", raising=False)
    spawned: list[list[str]] = []
    _stub_launcher_io(monkeypatch, spawned)

    sv = _build_chat_sv(cfg, tmp_path)
    sv.start_all()
    try:
        n_ctx = _capture_n_ctx(spawned)
        # v0.8.67i — fallback target is the RAM-aware default cap.
        expected = str(sv._default_ctx_max())
        assert n_ctx == expected, (
            f"expected fallback to default cap {expected!r} for too-low "
            f"value, got {n_ctx!r}"
        )
    finally:
        sv.stop_all()
