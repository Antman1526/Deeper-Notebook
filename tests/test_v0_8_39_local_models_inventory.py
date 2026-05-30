"""v0.8.39 Phase 4a — GGUF inventory + metadata tests.

Backend-only this phase. Covers:
  - parse_quant_from_filename
  - parse_param_count_b
  - parse_gguf_metadata (filename-fallback path; the gguf-library
    path is tested implicitly by the existing v0.7.206 launcher
    fixture — we don't re-cover it here to avoid coupling to whether
    the optional `gguf` dep is installed in CI)
  - enumerate_models (real tempdir with hand-written `.gguf` stubs)
  - GET /api/local-models/inventory endpoint (env precedence, dir
    missing, dir present)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_notebook.local_models.gguf_metadata import (
    parse_gguf_metadata,
    parse_param_count_b,
    parse_quant_from_filename,
)
from open_notebook.local_models.inventory import (
    LocalModelInfo,
    enumerate_models,
)
from api.routers import local_models as local_models_router


# ---------------------------------------------------------------------------
# parse_quant_from_filename
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,expected", [
    ("qwen2.5-7b-instruct-q4_k_m.gguf", "Q4_K_M"),
    ("hermes-3-llama-3.1-8b.Q5_K_M.gguf", "Q5_K_M"),
    ("Llama-3.2-3B-Instruct-Q8_0.gguf", "Q8_0"),
    ("phi-3-mini-4k-instruct.IQ4_XS.gguf", "IQ4_XS"),
    # Longest-match-wins: Q5_K_M not Q5
    ("foo-q5_k_m.gguf", "Q5_K_M"),
    # No quant marker
    ("model.gguf", None),
    ("", None),
])
def test_parse_quant_from_filename(filename, expected):
    assert parse_quant_from_filename(filename) == expected


# ---------------------------------------------------------------------------
# parse_param_count_b
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,expected", [
    ("qwen2.5-7b-instruct-q4_k_m.gguf", 7.0),
    ("hermes-3-8b.gguf", 8.0),
    ("llama-3.2-1.5b-instruct-q4.gguf", 1.5),
    ("model-13b.gguf", 13.0),
    # No param marker → None
    ("model.gguf", None),
    ("foo-bar.gguf", None),
    ("", None),
])
def test_parse_param_count_b(filename, expected):
    assert parse_param_count_b(filename) == expected


# ---------------------------------------------------------------------------
# parse_gguf_metadata (filename-fallback path)
# ---------------------------------------------------------------------------


def test_parse_gguf_metadata_filename_fallback(tmp_path):
    """When the `gguf` library is missing OR the file isn't really a
    GGUF, we fall back to filename heuristics for arch/quant/params
    and `os.stat` for size. context_length stays None."""
    p = tmp_path / "qwen2.5-7b-instruct-q4_k_m.gguf"
    p.write_bytes(b"NOT-A-REAL-GGUF-FILE")
    md = parse_gguf_metadata(p)
    # Heuristics from filename
    assert md.quant == "Q4_K_M"
    assert md.parameter_count_b == 7.0
    assert md.architecture == "qwen2"  # via _parse_arch_from_filename
    # File size is always real
    assert md.file_size_bytes == len(b"NOT-A-REAL-GGUF-FILE")
    # context_length can't be inferred without library + valid file
    assert md.context_length is None


def test_parse_gguf_metadata_handles_missing_file(tmp_path):
    """Non-existent file → file_size_bytes=0, everything else best-effort
    from filename. Never raises.

    Note: the quant patterns require fully-qualified llama.cpp names
    (Q5_0, Q5_K_M, etc) — a bare `-q5` in a filename is ambiguous and
    intentionally NOT matched. Use a tagged filename here so the test
    covers the happy path."""
    p = tmp_path / "hermes-3-8b-q5_0.gguf"
    md = parse_gguf_metadata(p)
    assert md.file_size_bytes == 0
    assert md.quant == "Q5_0"
    assert md.parameter_count_b == 8.0


# ---------------------------------------------------------------------------
# enumerate_models
# ---------------------------------------------------------------------------


def test_enumerate_models_empty_dir(tmp_path):
    """Empty dir → empty list, no error."""
    assert enumerate_models(tmp_path) == []


def test_enumerate_models_missing_dir():
    """Non-existent dir → empty list (no exception)."""
    assert enumerate_models(Path("/no/such/dir/exists/anywhere/v0_8_39")) == []


def test_enumerate_models_filters_non_gguf(tmp_path):
    """Filters: non-.gguf files, dotfiles, .tmp/.part, zero-byte stubs."""
    # Real .gguf files
    (tmp_path / "qwen2.5-7b-q4_k_m.gguf").write_bytes(b"x" * 100)
    (tmp_path / "hermes-3-8b-q5.gguf").write_bytes(b"x" * 200)
    # Junk we should skip
    (tmp_path / "README.md").write_text("not a model")
    (tmp_path / ".hidden.gguf").write_bytes(b"x" * 50)
    (tmp_path / "download-in-progress.gguf.tmp").write_bytes(b"x" * 50)
    (tmp_path / "zero-byte.gguf").write_bytes(b"")
    # A subdir — must NOT recurse
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "should-not-show.gguf").write_bytes(b"x" * 100)

    rows = enumerate_models(tmp_path)
    names = sorted(r.name for r in rows)
    assert names == ["hermes-3-8b-q5", "qwen2.5-7b-q4_k_m"]


def test_enumerate_models_returns_metadata(tmp_path):
    """Each row carries the full GGUFMetadata bundle."""
    (tmp_path / "qwen2.5-7b-instruct-q4_k_m.gguf").write_bytes(b"x" * 1024)
    rows = enumerate_models(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, LocalModelInfo)
    assert row.name == "qwen2.5-7b-instruct-q4_k_m"
    assert row.path.endswith(".gguf")
    assert row.metadata.quant == "Q4_K_M"
    assert row.metadata.parameter_count_b == 7.0
    assert row.metadata.architecture == "qwen2"
    assert row.metadata.file_size_bytes == 1024


def test_enumerate_models_stable_sort(tmp_path):
    """Alphabetical name sort — UI shouldn't see random ordering."""
    (tmp_path / "zebra-1b.gguf").write_bytes(b"x" * 10)
    (tmp_path / "alpha-1b.gguf").write_bytes(b"x" * 10)
    (tmp_path / "mike-1b.gguf").write_bytes(b"x" * 10)
    rows = enumerate_models(tmp_path)
    assert [r.name for r in rows] == ["alpha-1b", "mike-1b", "zebra-1b"]


# ---------------------------------------------------------------------------
# GET /api/local-models/inventory
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a


def test_inventory_endpoint_returns_unavailable_when_dir_missing(
    app, monkeypatch, tmp_path,
):
    bogus = tmp_path / "does-not-exist"
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_DIR", str(bogus))
    with TestClient(app) as client:
        resp = client.get("/api/local-models/inventory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["models"] == []
    assert body["model_dir"] == str(bogus)


def test_inventory_endpoint_lists_models(app, monkeypatch, tmp_path):
    """Happy path — env var points at a dir with GGUFs; endpoint returns them."""
    (tmp_path / "qwen2.5-7b-instruct-q4_k_m.gguf").write_bytes(b"x" * 2048)
    (tmp_path / "hermes-3-8b-q5_k_m.gguf").write_bytes(b"y" * 4096)
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/inventory")
    body = resp.json()
    assert body["available"] is True
    assert body["model_dir"] == str(tmp_path)
    assert len(body["models"]) == 2
    by_name = {m["name"]: m for m in body["models"]}
    qwen = by_name["qwen2.5-7b-instruct-q4_k_m"]
    assert qwen["quant"] == "Q4_K_M"
    assert qwen["parameter_count_b"] == 7.0
    assert qwen["file_size_bytes"] == 2048
    assert qwen["architecture"] == "qwen2"
    hermes = by_name["hermes-3-8b-q5_k_m"]
    assert hermes["quant"] == "Q5_K_M"
    assert hermes["parameter_count_b"] == 8.0


def test_inventory_endpoint_env_precedence(app, monkeypatch, tmp_path):
    """OPEN_NOTEBOOK_MODEL_DIR wins over the launcher default."""
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (explicit / "m-1b-q4.gguf").write_bytes(b"x" * 10)

    launcher_default = tmp_path / "launcher_default"
    launcher_default.mkdir()
    (launcher_default / "other-1b-q4.gguf").write_bytes(b"y" * 10)

    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_DIR", str(explicit))
    monkeypatch.setenv("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT", str(launcher_default))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/inventory")
    body = resp.json()
    assert body["model_dir"] == str(explicit)
    assert [m["name"] for m in body["models"]] == ["m-1b-q4"]
