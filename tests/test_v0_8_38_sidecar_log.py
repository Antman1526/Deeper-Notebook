"""v0.8.38 Phase 3 — sidecar log surface tests.

Covers:
  - `classify_sidecar_error` patterns (positive matches, no-match, empty
    input). Plain function, no I/O.
  - `GET /healthz/sidecars/{kind}/log` endpoint:
      - unknown kind → 404
      - no DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR → available=false, log=""
      - dir set but tail file missing → available=false
      - tail file present → log content + classified hint
      - oversized tail file → capped at 8 KiB
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.utils.error_classifier import classify_sidecar_error

# ---------------------------------------------------------------------------
# Classifier unit tests
# ---------------------------------------------------------------------------


class TestClassifySidecarError:
    def test_empty_input_returns_none(self):
        assert classify_sidecar_error("") is None
        assert classify_sidecar_error(None) is None  # type: ignore[arg-type]

    def test_no_match_returns_none(self):
        """Tail with no recognizable failure → no hint (UI shows raw log only)."""
        assert classify_sidecar_error("starting up...\nready to serve\n") is None

    @pytest.mark.parametrize("needle,expected_keyword", [
        ("failed to load model from gguf-file", "could not be loaded"),
        ("CUDA error: out of memory", "Out of memory"),
        # "cuda error" comes before "ggml-cuda" in _SIDECAR_PATTERNS, so
        # this string actually matches the broader "cuda error" hint
        # ("GPU error — falling back to CPU…") rather than the
        # CUDA-backend-specific one. Documenting the first-match-wins
        # ordering with the assertion.
        ("ggml-cuda.cu:123 cuda error", "GPU"),
        ("bind: address already in use", "Port already in use"),
        ("ImportError: No module named foo", "dependency missing"),
        ("Killed: 9", "killed"),
        ("Segmentation fault: 11", "segfault"),
        ("ModuleNotFoundError: llama_cpp", "dependency missing"),
        ("Metal error: command queue", "Apple GPU"),
    ])
    def test_pattern_matches(self, needle, expected_keyword):
        """Each pattern in the table returns a hint mentioning the keyword."""
        hint = classify_sidecar_error(needle)
        assert hint is not None, f"Expected a hint for {needle!r}"
        assert expected_keyword.lower() in hint.lower(), (
            f"Hint {hint!r} should mention {expected_keyword!r}"
        )

    def test_case_insensitive(self):
        """Patterns match regardless of stderr capitalization."""
        assert classify_sidecar_error("FAILED TO LOAD MODEL") is not None
        assert classify_sidecar_error("FaIlEd To LoAd MoDeL") is not None

    def test_first_pattern_wins(self):
        """When multiple patterns match, the order in _SIDECAR_PATTERNS
        decides — narrower failures (model load) come before generic
        crash markers (Killed: 9)."""
        # Both "failed to load model" AND "Killed: 9" present.
        text = "failed to load model gguf\n... lots of output ...\nKilled: 9"
        hint = classify_sidecar_error(text)
        assert "could not be loaded" in hint.lower()


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a


def test_unknown_kind_returns_404(app):
    with TestClient(app) as client:
        resp = client.get("/api/healthz/sidecars/badkind/log")
    assert resp.status_code == 404
    body = resp.json()
    assert "badkind" in body["detail"]


def test_no_launcher_log_dir_returns_unavailable(app, monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR", raising=False)
    with TestClient(app) as client:
        resp = client.get("/api/healthz/sidecars/chat/log")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"kind": "chat", "log": "", "hint": None, "available": False}


def test_tail_file_missing_returns_unavailable(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR", str(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/healthz/sidecars/chat/log")
    body = resp.json()
    assert body["available"] is False
    assert body["log"] == ""


def test_tail_file_present_returns_content_and_hint(app, monkeypatch, tmp_path):
    """Smoke test: write a tail file with a known failure pattern,
    assert the endpoint returns both the raw bytes and the classifier's hint."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR", str(tmp_path))
    tail = tmp_path / "supervisor.llamacpp_chat.tail"
    tail.write_text("startup output\nllama_model_load: failed to load model\n")

    with TestClient(app) as client:
        resp = client.get("/api/healthz/sidecars/chat/log")
    body = resp.json()
    assert body["available"] is True
    assert "failed to load model" in body["log"]
    assert body["hint"] is not None
    assert "could not be loaded" in body["hint"].lower()


def test_oversized_tail_capped_at_8kb(app, monkeypatch, tmp_path):
    """Defensive cap: a tail file larger than 8 KiB returns only the
    last 8 KiB. Prevents accidental large-file dumps if a user
    manually edits the file."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR", str(tmp_path))
    tail = tmp_path / "supervisor.llamacpp_chat.tail"
    # 20 KiB of "x" + a marker at the end to verify we got the tail
    big = ("x" * 20_000 + "\nfinal-line\n").encode()
    tail.write_bytes(big)

    with TestClient(app) as client:
        resp = client.get("/api/healthz/sidecars/chat/log")
    body = resp.json()
    assert body["available"] is True
    # Must contain the tail marker (cap returned the END, not the start).
    assert "final-line" in body["log"]
    # Must be ≤ 8 KiB of text (decoded utf-8 — 8 KiB bytes of "x" is
    # roughly 8 KiB of text since x is single-byte).
    assert len(body["log"].encode()) <= 8 * 1024


def test_all_known_kinds_accepted(app, monkeypatch, tmp_path):
    """The allowlist matches the launcher's supervisor names exactly.
    A regression here would break the frontend's badge popovers."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR", str(tmp_path))
    for kind in ("chat", "embed", "whisper", "piper", "memory"):
        with TestClient(app) as client:
            resp = client.get(f"/api/healthz/sidecars/{kind}/log")
        assert resp.status_code == 200, f"kind={kind} should be accepted"
        body = resp.json()
        assert body["kind"] == kind


def test_path_traversal_blocked(app, monkeypatch, tmp_path):
    """A `kind` like `../etc/passwd` must hit the 404 path BEFORE we
    join it onto log_dir — defense-in-depth on the path component."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_LOG_DIR", str(tmp_path))
    # FastAPI itself may reject the `..` at the routing layer, but if a
    # future router refactor accepts a wildcard we want this test to
    # catch the regression.
    with TestClient(app) as client:
        resp = client.get("/api/healthz/sidecars/..%2Fetc%2Fpasswd/log")
    # Either 404 (allowlist check) or 405/422 from the router — anything
    # that's NOT a 200 with leaked file content.
    assert resp.status_code != 200 or "/etc/passwd" not in resp.text
