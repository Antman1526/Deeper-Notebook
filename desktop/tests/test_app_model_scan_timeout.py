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

    class Store:
        def load_chat_model(self, root):
            assert root == model_dir
            return cached

    def fail(_directory):
        raise AssertionError("cache hit must not enumerate GGUF files")

    monkeypatch.setattr(app, "_scan_chat_llm_with_timeout", fail)

    assert app._select_chat_llm_path(model_dir, Store()) == cached


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
