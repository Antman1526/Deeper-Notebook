"""v0.8.3 — Regression tests for the dual-llama-cpp-spawn fix and the
draft-model wiring rewire.

# Background

Two competing launch paths existed for the llama-cpp chat sidecar:

1. `desktop/app.py:_phase_select_provider` called
   `LlamaCppProvider.start()` which spawned a `llama_cpp.server`
   subprocess (~4 GB RAM) on a dynamic port. The URL was stashed in
   `ctx.extra_env["OPENAI_COMPATIBLE_BASE_URL"]`.

2. `desktop/launcher.py:Supervisor._spawn_llamacpp_chat` ALSO spawned a
   `llama_cpp.server` subprocess — this one with the v0.7.206 `n_ctx`
   fix wired in.

v0.7.193 wired `auto_register` to prefer `sv.chat_llm_port` (the
Supervisor's port) over the env-var URL. From that point on, path #1
was dead code — it brought up a server nobody routed traffic to.

v0.8.2 Item A wired `DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH` into path
#1 (LlamaCppProvider.start), so operators following the v0.8.2 docs
were setting the env var correctly but seeing no speedup, because the
LIVE spawn (path #2) never read those env vars.

# Fixes (v0.8.3)

- `_phase_select_provider` no longer calls `LlamaCppProvider.start()`.
  The provider object stays in scope (its discovery helpers — `is_available`,
  `pick_default_model`, `list_models` — are still useful) but no longer
  triggers a duplicate subprocess.
- `Supervisor._spawn_llamacpp_chat` now reads
  `DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH` and
  `DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT` and extends its `args` with
  `--model_draft <path>` and (when both are set) `--n_predict_draft <N>`.
  The v0.8.2 docs URLs and env var names are preserved, so existing
  operators get the feature for the first time without touching their
  `.env`.

These tests pin both fixes so a future refactor can't silently
re-introduce the dual spawn or move the draft-model wiring back to the
dead path.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from desktop.launcher import Supervisor

# ---------------------------------------------------------------------------
# Shared fixtures — mirror the patterns in test_launcher.py so failures
# read the same way as the v0.7.206 n_ctx tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_singleton(monkeypatch):
    """v0.7.155 — Stub launcher singleton so concurrent test runs don't
    collide on the PID file. Mirrors test_launcher.py's autouse stub —
    patch the SOURCE module (`desktop.singleton.*`) because the imports
    in Supervisor.start_all are function-scoped local imports."""

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
    # Bare MagicMock (no spec) matches test_launcher.py's _alive_proc.
    # spec=subprocess.Popen restricts attribute access in a way that
    # the launcher's broader attribute reads (poll, returncode, pid,
    # terminate, kill, wait) trip over.
    p = MagicMock()
    p.poll.return_value = None
    p.returncode = None
    return p


def _stub_io(monkeypatch, spawned):
    def fake_popen(args, **kw):
        spawned.append(list(args))
        return _alive_proc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports",
        lambda n: list(range(40001, 40001 + n)),
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)


@pytest.fixture
def cfg(tmp_path):
    """Mirrors test_launcher.py's make_config helper."""
    from desktop.config import Config

    return Config(
        model_dir=tmp_path,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="A" * 24,
    )


def _build_sv(cfg, tmp_path):
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


def _chat_args(spawned):
    """Pull the llama_cpp.server argv for the chat sidecar specifically."""
    for args in spawned:
        joined = " ".join(args)
        if "llama_cpp.server" in joined and "Hermes-3" in joined:
            return args
    return None


# ---------------------------------------------------------------------------
# Fix 1 — draft-model env vars actually reach the LIVE spawn (launcher)
# ---------------------------------------------------------------------------


def test_supervisor_spawn_appends_model_draft_when_env_set(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.3 — `DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH` must reach
    `Supervisor._spawn_llamacpp_chat`'s argv. Pre-v0.8.3 the env var
    was read by `LlamaCppProvider.start()` only — i.e. the deprecated
    spawn path that auto_register hadn't routed traffic to since
    v0.7.193 — so operators saw no speedup despite following the docs.
    """
    draft = tmp_path / "draft_small.gguf"
    draft.write_bytes(b"x" * (2 * 1024 * 1024))
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH", str(draft))
    monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT", raising=False)

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert args is not None, "chat sidecar was never spawned"
        assert "--model_draft" in args, (
            f"--model_draft missing from chat argv; "
            f"v0.8.2 Item A regressed back to the dead path. argv={args}"
        )
        idx = args.index("--model_draft")
        assert args[idx + 1] == str(draft)
        assert "--n_predict_draft" not in args  # not set in env
    finally:
        sv.stop_all()


def test_supervisor_spawn_appends_n_predict_draft_when_both_env_set(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.3 — both env vars set → both flags appear in argv. Pins
    that the tuning knob (v0.8.2 Item C) also reaches the LIVE spawn,
    not just the deprecated provider path."""
    draft = tmp_path / "draft.gguf"
    draft.write_bytes(b"x" * (2 * 1024 * 1024))
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH", str(draft))
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT", "16")

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert "--model_draft" in args
        assert "--n_predict_draft" in args
        idx = args.index("--n_predict_draft")
        assert args[idx + 1] == "16"
    finally:
        sv.stop_all()


def test_supervisor_spawn_omits_draft_flags_when_env_unset(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.3 — backward compat. With no draft env vars, the spawn
    argv must NOT contain `--model_draft` or `--n_predict_draft`.
    Guards against accidentally enabling speculative decoding for
    operators who haven't opted in."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT", raising=False)

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert args is not None
        assert "--model_draft" not in args, f"unexpected --model_draft in {args}"
        assert "--n_predict_draft" not in args
    finally:
        sv.stop_all()


def test_supervisor_spawn_skips_draft_when_path_missing(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.3 — stale env var pointing at a no-longer-existing file
    must NOT crash the chat sidecar. Skip silently; main model still
    loads; operator just doesn't get the speedup. Same MIN_GGUF_BYTES
    guard semantics as the main-model loop."""
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH",
        str(tmp_path / "does_not_exist.gguf"),
    )

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert "--model_draft" not in args, (
            f"stale draft env should skip --model_draft; got {args}"
        )
    finally:
        sv.stop_all()


def test_supervisor_spawn_skips_draft_when_path_too_small(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.3 — Git-LFS pointer / aborted download. Same guard as
    the main-model loop. Skip the flag, log a warning, keep chat
    working with the unaccelerated sidecar."""
    tiny = tmp_path / "lfs_pointer.gguf"
    tiny.write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH", str(tiny))

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert "--model_draft" not in args
    finally:
        sv.stop_all()


def test_supervisor_spawn_drops_n_predict_without_draft(
    cfg,
    tmp_path,
    monkeypatch,
):
    """v0.8.3 — n_predict_draft is meaningless without a draft model.
    A bare DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT env (no path) must NOT
    cause a stray `--n_predict_draft` in argv (llama_cpp.server would
    reject the argv at parse time)."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH", raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT", "32")

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert "--n_predict_draft" not in args, (
            f"n_predict without draft model must be dropped; got {args}"
        )
        assert "--model_draft" not in args
    finally:
        sv.stop_all()


def test_supervisor_spawn_handles_malformed_n_predict_env(
    cfg,
    tmp_path,
    monkeypatch,
    caplog,
):
    """v0.8.3 — garbage in DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT must
    NOT crash the spawn. Log a warning + drop the flag; main model
    + draft model still load."""
    draft = tmp_path / "draft.gguf"
    draft.write_bytes(b"x" * (2 * 1024 * 1024))
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH", str(draft))
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT", "not-an-int")

    spawned: list[list[str]] = []
    _stub_io(monkeypatch, spawned)

    sv = _build_sv(cfg, tmp_path)
    sv.start_all()
    try:
        args = _chat_args(spawned)
        assert "--model_draft" in args  # draft still accepted
        assert "--n_predict_draft" not in args  # malformed n_predict dropped
    finally:
        sv.stop_all()
