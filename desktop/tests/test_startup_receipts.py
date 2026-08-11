"""Focused contracts for the bounded desktop startup receipt store."""
from __future__ import annotations

import json
import os
from pathlib import Path

from desktop.startup_receipts import (
    MAX_ELAPSED_MS,
    MAX_STAGES,
    StartupReceiptStore,
)


def _model(root: Path, name: str = "chat.gguf") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model = root / name
    model.write_bytes(b"gguf fixture")
    return model


def test_malformed_receipt_is_ignored_and_replaced_atomically(tmp_path):
    receipt = tmp_path / "startup_receipt.json"
    receipt.write_text("{not-json", encoding="utf-8")

    store = StartupReceiptStore(tmp_path)
    assert store.load_chat_model(tmp_path / "models") is None

    store.record("core_ready", 125)

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["stages"] == [{"stage": "core_ready", "elapsed_ms": 125}]
    assert (receipt.stat().st_mode & 0o777) == 0o600
    assert not list(tmp_path.glob(".startup_receipt.json.*.tmp"))


def test_matching_model_metadata_is_a_cache_hit(tmp_path):
    model_root = tmp_path / "models"
    model = _model(model_root)
    store = StartupReceiptStore(tmp_path)

    store.cache_chat_model(model, root=model_root)

    assert store.load_chat_model(model_root) == model


def test_cached_model_must_remain_inside_requested_root(tmp_path):
    model_root = tmp_path / "models"
    outside = _model(tmp_path / "outside")
    store = StartupReceiptStore(tmp_path)

    store.cache_chat_model(outside)

    assert store.load_chat_model(model_root) is None


def test_cached_model_symlink_cannot_escape_requested_root(tmp_path):
    model_root = tmp_path / "models"
    outside = _model(tmp_path / "outside")
    model_root.mkdir()
    link = model_root / "chat.gguf"
    link.symlink_to(outside)
    store = StartupReceiptStore(tmp_path)
    store.cache_chat_model(link)

    assert store.load_chat_model(model_root) is None


def test_stale_model_metadata_is_a_cache_miss(tmp_path):
    model_root = tmp_path / "models"
    model = _model(model_root)
    store = StartupReceiptStore(tmp_path)
    store.cache_chat_model(model, root=model_root)

    original_stat = model.stat()
    model.write_bytes(b"changed!")
    os.utime(model, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000))

    assert store.load_chat_model(model_root) is None


def test_receipt_stages_and_elapsed_values_are_bounded(tmp_path):
    store = StartupReceiptStore(tmp_path)

    for index in range(MAX_STAGES + 4):
        store.record(f"stage-{index}", MAX_ELAPSED_MS * 10)

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert len(payload["stages"]) == MAX_STAGES
    assert payload["stages"][0]["stage"] == "stage-4"
    assert payload["stages"][-1]["stage"] == f"stage-{MAX_STAGES + 3}"
    assert all(
        0 <= entry["elapsed_ms"] <= MAX_ELAPSED_MS
        for entry in payload["stages"]
    )
