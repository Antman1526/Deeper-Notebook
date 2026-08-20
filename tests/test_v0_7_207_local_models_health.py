"""v0.7.207 — Diagnosed live against the running .app: three local-
model credentials were failing despite the underlying processes
being alive.

User report: "Local models are failing in the chat" + "Make sure all
file uploads are successful and the local models are running inside
of the application."

Three bugs surfaced while testing each credential via
`POST /api/credentials/{id}/test`:

1. **Memory (local) → "Cannot connect to server"** — memory_shim
   crashed at startup with:
     `TypeError: BaseEmbedderConfig.__init__() got an unexpected
     keyword argument 'base_url'`
   `desktop/memory/client.py` passed `base_url` to mem0's embedder
   / LLM configs. mem0's `BaseEmbedderConfig` and `BaseLlmConfig`
   use the field name `openai_base_url` (verified at
   `mem0/configs/embeddings/base.py:23` and
   `mem0/llms/openai.py:50`).

2. **Whisper (local) → "Server returned status 404"** — the shim
   only exposed `GET /health` and `POST /v1/audio/transcriptions`,
   but the connection tester probes `GET /v1/models` (the standard
   OpenAI-compatible discovery endpoint — see
   `connection_tester.py:_test_openai_compatible_connection`).
   Added a `/v1/models` route returning the loaded model name.

3. **Piper (local) → "Server returned status 404"** — same as
   Whisper. Added `/v1/models` returning the loaded voice list.

Source upload itself was fully working — verified end-to-end via
POST /api/sources against the live API.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_memory_client_uses_openai_base_url_field_name():
    """v0.7.207 — mem0 requires `openai_base_url`, not `base_url`."""
    src = _src("desktop/memory/client.py")
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert '"base_url": embed_url' not in code_only, (
        "v0.7.207 regression: memory client embedder config restored "
        "the bad `base_url` field name. mem0 TypeErrors at startup."
    )
    assert '"base_url": llm_url' not in code_only
    assert '"openai_base_url": embed_url' in code_only
    assert '"openai_base_url": llm_url' in code_only


def test_whisper_shim_exposes_v1_models_endpoint():
    """v0.7.207 — whisper_shim needs `GET /v1/models` for the
    OpenAI-compatible probe in the connection tester."""
    src = _src("desktop/desktop_shims/whisper_shim.py")
    assert '@app.get("/v1/models")' in src
    assert '"object": "list"' in src
    assert "v0.7.207 — OpenAI-compatible" in src


def test_piper_shim_exposes_v1_models_endpoint():
    """v0.7.207 — piper_shim same requirement."""
    src = _src("desktop/desktop_shims/piper_shim.py")
    assert '@app.get("/v1/models")' in src
    assert '"object": "list"' in src
    assert "v0.7.207 — OpenAI-compatible" in src
    assert "for name in voices.keys()" in src


def test_whisper_shim_v1_models_runtime():
    """v0.7.207 — runtime smoke: actually hit `GET /v1/models`."""
    from fastapi.testclient import TestClient

    from desktop.desktop_shims.whisper_shim import build_app

    app = build_app(model=object())
    with TestClient(app) as client:
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 1
        assert body["data"][0]["object"] == "model"


def test_piper_shim_v1_models_runtime():
    """v0.7.207 — runtime smoke for piper. Each voice becomes a model."""
    from fastapi.testclient import TestClient

    from desktop.desktop_shims.piper_shim import build_app

    voices = {"alex": object(), "sam": object()}
    app = build_app(voices=voices)
    with TestClient(app) as client:
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        names = {m["id"] for m in body["data"]}
        assert names == {"alex", "sam"}
