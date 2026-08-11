"""v0.8.67f — the chat-GGUF directory scan is time-bounded at boot.

Regression for the boot-hang: `pick_chat_llm_file` runs `os.scandir` on the
launch's main thread, and a stalling model folder (iCloud-evicted / TCC-gated
Desktop, sleeping external drive) can block `open()` UNINTERRUPTIBLY and hang the
whole app. `_scan_chat_llm_with_timeout` runs it in a daemon thread and gives up
after DEEPER_NOTEBOOK_MODEL_SCAN_TIMEOUT seconds, returning None (degraded local chat) so the
app still boots.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import desktop.app as app
import desktop.auto_register.assigner as asg


def test_fast_scan_returns_result(monkeypatch):
    monkeypatch.setattr(asg, "pick_chat_llm_file", lambda d: "X/model.gguf")
    assert app._scan_chat_llm_with_timeout("/x") == "X/model.gguf"


def test_slow_scan_times_out_to_none_without_hanging(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_SCAN_TIMEOUT", "1")

    def slow(_d):
        time.sleep(6)  # simulates a wedged scandir/open
        return "SHOULD_NOT_RETURN"

    monkeypatch.setattr(asg, "pick_chat_llm_file", slow)
    t = time.time()
    result = app._scan_chat_llm_with_timeout("/x")
    elapsed = time.time() - t
    assert result is None
    assert elapsed < 3, f"timeout did not engage (waited {elapsed:.1f}s, expected ~1s)"


def test_garbage_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_SCAN_TIMEOUT", "not-a-number")
    monkeypatch.setattr(asg, "pick_chat_llm_file", lambda d: "OK")
    assert app._scan_chat_llm_with_timeout("/x") == "OK"


def test_scan_exception_degrades_to_none(monkeypatch):
    def boom(_d):
        raise OSError("model dir vanished")

    monkeypatch.setattr(asg, "pick_chat_llm_file", boom)
    # A raising scan must not crash the boot — it degrades to None.
    assert app._scan_chat_llm_with_timeout("/x") is None


def test_matching_model_cache_skips_bounded_scan(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    cached = model_dir / "GGUF" / "cached.gguf"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"cached")
    records: list[tuple[str, int]] = []

    class Store:
        def load_chat_model(self, root):
            assert root == model_dir
            return cached

        def record(self, stage, elapsed_ms):
            records.append((stage, elapsed_ms))

    def fail(_directory):
        raise AssertionError("cache hit must not enumerate GGUF files")

    monkeypatch.setattr(app, "_scan_chat_llm_with_timeout", fail)

    assert app._select_chat_llm_path(model_dir, Store()) == cached
    assert records and records[0][0] == "chat_model_cache_hit"
    assert records[0][1] >= 0


def test_cache_miss_uses_bounded_scan_and_updates_cache(monkeypatch, tmp_path):
    model_dir = tmp_path / "models"
    selected = model_dir / "GGUF" / "scanned.gguf"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"scanned")
    calls: list[Path] = []

    class Store:
        def load_chat_model(self, root):
            assert root == model_dir
            return None

        def cache_chat_model(self, path, *, root):
            calls.append(Path(path))

        def record(self, stage, elapsed_ms):
            assert stage == "chat_model_scan"
            assert elapsed_ms >= 0

    monkeypatch.setattr(
        app,
        "_scan_chat_llm_with_timeout",
        lambda directory: selected if directory == model_dir / "GGUF" else None,
    )

    assert app._select_chat_llm_path(model_dir, Store()) == selected
    assert calls == [selected]


def test_cache_write_failure_still_records_scan_outcome(monkeypatch, tmp_path):
    """A metadata-write failure must not hide the bounded scan outcome."""
    model_dir = tmp_path / "models"
    selected = model_dir / "GGUF" / "scanned.gguf"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"scanned")
    records: list[tuple[str, int]] = []

    class Store:
        def load_chat_model(self, root):
            assert root == model_dir
            return None

        def cache_chat_model(self, path, *, root):
            raise OSError("receipt metadata unavailable")

        def record(self, stage, elapsed_ms):
            records.append((stage, elapsed_ms))

    monkeypatch.setattr(app, "_scan_chat_llm_with_timeout", lambda _directory: selected)

    assert app._select_chat_llm_path(model_dir, Store()) == selected
    assert records and records[0][0] == "chat_model_scan"
    assert records[0][1] >= 0


def _supervisor_context(tmp_path, receipt_store):
    model_dir = tmp_path / "models"
    (model_dir / "GGUF").mkdir(parents=True)
    ctx = app._new_context()
    ctx.cfg = SimpleNamespace(model_dir=model_dir, provider="none")
    ctx.log_dir = tmp_path / "logs"
    ctx.log_dir.mkdir()
    ctx.bin_dir = tmp_path / "bin"
    ctx.bin_dir.mkdir()
    ctx.arch = "darwin-arm64"
    ctx.startup_receipts = receipt_store
    ctx.progress_bus = SimpleNamespace(publish=lambda *args: None)
    return ctx


class _RecordingReceiptStore:
    def __init__(self, *, fail=False):
        self.records: list[tuple[str, int]] = []
        self.fail = fail

    def load_chat_model(self, root):
        return None

    def cache_chat_model(self, path, *, root):
        return None

    def clear_chat_model(self):
        return None

    def record(self, stage, elapsed_ms):
        if self.fail:
            raise OSError("receipt storage unavailable")
        self.records.append((stage, elapsed_ms))


def test_launcher_start_receipt_is_recorded(monkeypatch, tmp_path):
    from desktop import config, startup_receipts

    data_root = tmp_path / "data"
    records: list[tuple[str, int]] = []

    class Store:
        def __init__(self, root):
            assert root == data_root

        def record(self, stage, elapsed_ms):
            records.append((stage, elapsed_ms))

    monkeypatch.setattr(app, "active_data_root", lambda: data_root)
    monkeypatch.setattr(config, "default_config_path", lambda: data_root / "config.toml")
    monkeypatch.setattr(startup_receipts, "StartupReceiptStore", Store)
    monkeypatch.setattr(app, "_setup_launcher_log_handler", lambda _path: None)

    ctx = app._new_context()
    app._phase_load_config(ctx)

    assert records == [("launcher_start", 0)]


def test_normal_supervisor_success_records_core_ready(monkeypatch, tmp_path):
    from desktop import launcher

    store = _RecordingReceiptStore()
    monkeypatch.setattr(app, "_scan_chat_llm_with_timeout", lambda _directory: None)

    class Supervisor:
        instance = None

        def __init__(self, **kwargs):
            self.start_calls = 0
            self.stop_calls = 0
            Supervisor.instance = self

        def start_all(self):
            self.start_calls += 1

        def stop_all(self):
            self.stop_calls += 1

    monkeypatch.setattr(launcher, "Supervisor", Supervisor)
    ctx = _supervisor_context(tmp_path, store)

    app._phase_start_supervisor(ctx)

    assert ctx.sv is Supervisor.instance
    assert Supervisor.instance.start_calls == 1
    assert [stage for stage, _elapsed in store.records].count("core_ready") == 1


def test_retrying_supervisor_success_records_core_ready(monkeypatch, tmp_path):
    from desktop import launcher, singleton

    store = _RecordingReceiptStore()
    monkeypatch.setattr(app, "_scan_chat_llm_with_timeout", lambda _directory: None)

    class RetrySignal(Exception):
        pass

    monkeypatch.setattr(singleton, "AlreadyRunning", RetrySignal)
    monkeypatch.setattr(app, "_handle_already_running", lambda _exc, _ctx: True)

    class Supervisor:
        instance = None

        def __init__(self, **kwargs):
            self.start_calls = 0
            Supervisor.instance = self

        def start_all(self):
            self.start_calls += 1
            if self.start_calls == 1:
                raise RetrySignal("another launcher")

        def stop_all(self):
            return None

    monkeypatch.setattr(launcher, "Supervisor", Supervisor)
    ctx = _supervisor_context(tmp_path, store)

    app._phase_start_supervisor(ctx)

    assert ctx.sv is Supervisor.instance
    assert Supervisor.instance.start_calls == 2
    assert [stage for stage, _elapsed in store.records].count("core_ready") == 1


def test_supervisor_failure_preserves_error_when_receipt_write_fails(
    monkeypatch, tmp_path
):
    from desktop import launcher

    store = _RecordingReceiptStore(fail=True)
    monkeypatch.setattr(app, "_scan_chat_llm_with_timeout", lambda _directory: None)

    class Supervisor:
        instance = None

        def __init__(self, **kwargs):
            self.stop_calls = 0
            Supervisor.instance = self

        def start_all(self):
            raise RuntimeError("supervisor unavailable")

        def stop_all(self):
            self.stop_calls += 1

    monkeypatch.setattr(launcher, "Supervisor", Supervisor)
    ctx = _supervisor_context(tmp_path, store)

    with pytest.raises(RuntimeError, match="supervisor unavailable"):
        app._phase_start_supervisor(ctx)

    assert Supervisor.instance.stop_calls == 1
