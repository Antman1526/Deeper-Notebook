"""Regression tests for packaged-app startup recovery."""

from pathlib import Path


def test_reaps_surreal_orphan_from_a_previous_bundle(monkeypatch, tmp_path):
    """A prior build must not keep the shared database locked forever."""
    from desktop import singleton

    assert hasattr(singleton, "reap_surreal_data_orphans"), (
        "startup needs a data-directory-based orphan reaper"
    )

    data_dir = tmp_path / ".open-notebook-plus" / "surreal_data"
    old_command = (
        "/tmp/old-build/Open Notebook Plus.app/Contents/Frameworks/"
        "desktop/bin/surreal-darwin-arm64 start --bind=127.0.0.1:50780 "
        f"file://{data_dir}"
    )
    monkeypatch.setattr(
        singleton,
        "_list_processes_posix",
        lambda: [(424242, 1, old_command)],
    )
    monkeypatch.setattr(singleton.sys, "platform", "darwin")

    reaped = singleton.reap_surreal_data_orphans(data_dir, dry_run=True)

    assert [(item.pid, item.cmdline) for item in reaped] == [
        (424242, old_command)
    ]


def test_gguf_discovery_does_not_walk_unrelated_model_caches(tmp_path):
    """Startup scans the curated GGUF tree, not the entire model library."""
    from desktop.auto_register import _list_local_ggufs

    model_root = tmp_path / "models"
    gguf = model_root / "GGUF" / "repo" / "chat.gguf"
    cached = model_root / ".hf_cache" / "hub" / "cached.gguf"
    gguf.parent.mkdir(parents=True)
    cached.parent.mkdir(parents=True)
    gguf.write_bytes(b"model")
    cached.write_bytes(b"cache")

    discovered = _list_local_ggufs(model_root, min_bytes=1)

    assert discovered == ["GGUF/repo/chat.gguf"]
