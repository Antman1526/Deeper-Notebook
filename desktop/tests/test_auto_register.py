"""Tests for desktop.auto_register — model discovery and idempotent registration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from desktop.auto_register import (
    _list_local_ggufs,
    _list_ollama_models,
    auto_register,
)
from desktop.config import Config


# ---------------------------------------------------------------------------
# _list_ollama_models
# ---------------------------------------------------------------------------


def _make_ollama_response(model_names: list[str]) -> httpx.Response:
    """Build a fake Ollama /api/tags response."""
    import json

    body = json.dumps({"models": [{"name": n} for n in model_names]}).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def test_list_ollama_models_returns_names_when_reachable(monkeypatch):
    names = ["llama3.1:latest", "mistral:7b"]
    fake_response = _make_ollama_response(names)

    with patch("httpx.get", return_value=fake_response) as mock_get:
        result = _list_ollama_models()

    mock_get.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=1.0)
    assert result == names


def test_list_ollama_models_returns_empty_when_unreachable():
    with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        result = _list_ollama_models()
    assert result == []


def test_list_ollama_models_returns_empty_on_non_200():
    fake_response = httpx.Response(503, content=b"service unavailable")
    with patch("httpx.get", return_value=fake_response):
        result = _list_ollama_models()
    assert result == []


# ---------------------------------------------------------------------------
# _list_local_ggufs
# ---------------------------------------------------------------------------


def test_list_local_ggufs_skips_small_files(tmp_path):
    big = tmp_path / "big.gguf"
    big.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
    small = tmp_path / "tiny.gguf"
    small.write_bytes(b"x" * 100)  # 100 bytes — below 1 MB threshold

    result = _list_local_ggufs(tmp_path)
    assert result == ["big.gguf"]


def test_list_local_ggufs_returns_empty_for_missing_dir(tmp_path):
    result = _list_local_ggufs(tmp_path / "nonexistent")
    assert result == []


def test_list_local_ggufs_is_sorted(tmp_path):
    for name in ("zebra.gguf", "alpha.gguf", "middle.gguf"):
        (tmp_path / name).write_bytes(b"x" * (2 * 1024 * 1024))
    result = _list_local_ggufs(tmp_path)
    assert result == sorted(result)


# ---------------------------------------------------------------------------
# auto_register — idempotency test
# ---------------------------------------------------------------------------


def _make_cfg(tmp_path: Path) -> Config:
    return Config(
        model_dir=tmp_path / "models",
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="A" * 24,
    )


def _mock_client_responses(
    credentials_list: list[dict],
    models_list: list[dict],
    post_credential_id: str = "credential:1",
) -> MagicMock:
    """Build a mock httpx.Client that returns predictable responses."""
    import json

    def make_resp(status: int, data) -> MagicMock:
        r = MagicMock(spec=httpx.Response)
        r.status_code = status
        r.json.return_value = data
        r.text = json.dumps(data)
        r.raise_for_status = MagicMock()
        return r

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    # GET /credentials → empty list on first call, then with the new cred
    cred_with_id = {"id": post_credential_id, "name": "Ollama (local)"}
    client.get.side_effect = [
        make_resp(200, credentials_list),   # first GET /credentials
        make_resp(200, models_list),        # GET /models
        make_resp(200, [cred_with_id]),     # GET /credentials (fetch id after create)
    ]

    # POST /credentials
    client.post.side_effect = [
        make_resp(201, {"id": post_credential_id, "name": "Ollama (local)"}),  # POST /credentials
        make_resp(200, {"id": "model:1", "name": "llama3.1:latest", "type": "language"}),  # POST /models
        make_resp(200, {"assigned": {"default_chat_model": "model:1"}, "skipped": [], "missing": []}),  # auto-assign
    ]
    return client


def test_auto_register_is_idempotent(tmp_path):
    """Running auto_register twice should only POST credentials/models once."""
    cfg = _make_cfg(tmp_path)
    ollama_names = ["llama3.1:latest"]

    # Simulate: first run creates everything; second run finds it all existing.
    with (
        patch("desktop.auto_register._list_ollama_models", return_value=ollama_names),
        patch("desktop.auto_register._list_local_ggufs", return_value=[]),
        patch("httpx.Client") as mock_client_cls,
    ):
        # First run: no existing creds/models
        client1 = _mock_client_responses([], [])
        mock_client_cls.return_value = client1

        auto_register("http://127.0.0.1:9999", cfg)

        # POST /credentials + POST /models + POST /models/auto-assign
        assert client1.post.call_count == 3

        # Second run: credential and model already exist
        import json

        def make_resp2(status: int, data) -> MagicMock:
            r = MagicMock(spec=httpx.Response)
            r.status_code = status
            r.json.return_value = data
            r.text = json.dumps(data)
            r.raise_for_status = MagicMock()
            return r

        client2 = MagicMock()
        client2.__enter__ = MagicMock(return_value=client2)
        client2.__exit__ = MagicMock(return_value=False)
        # Both credential and model already exist — nothing to create.
        existing_cred = {"id": "credential:1", "name": "Ollama (local)"}
        existing_model = {"id": "model:1", "name": "llama3.1:latest", "type": "language"}
        client2.get.side_effect = [
            make_resp2(200, [existing_cred]),   # GET /credentials
            make_resp2(200, [existing_model]),  # GET /models
        ]
        mock_client_cls.return_value = client2

        auto_register("http://127.0.0.1:9999", cfg)

        # No POSTs should happen on second run (everything exists)
        assert client2.post.call_count == 0


def test_register_voice_models_creates_credentials_and_models(monkeypatch):
    from desktop.auto_register import register_voice_models
    from desktop.config import Config
    from pathlib import Path

    created = []
    class FakeClient:
        def post(self, path, json=None):
            created.append((path, json))
            class R:
                status_code = 201
                text = ""
                def json(self):
                    return {"id": f"id-{json.get('name', '')}" if json else "id"}
            return R()
        def get(self, path):
            class R:
                status_code = 200
                text = ""
                def raise_for_status(self): pass
                def json(self):
                    return []
            return R()

    cfg = Config(model_dir=Path("/tmp"), provider="none", default_model="",
                 surreal_user="root", surreal_password="x" * 24)
    register_voice_models(FakeClient(),
                          whisper_port=1234, piper_port=2345, embed_port=3456,
                          cfg=cfg)
    paths = [p for p, _ in created]
    assert "/api/credentials" in paths
    payloads = [j for _, j in created if j is not None]
    assert any(j.get("name") == "Whisper (local)" for j in payloads)
    assert any(j.get("name") == "Piper (local)" for j in payloads)
    assert any(j.get("name") == "Local Embeddings (llama.cpp)" for j in payloads)
    assert any(j.get("name") == "piper-amy-en" for j in payloads)
    assert any(j.get("name") == "piper-ryan-en" for j in payloads)
