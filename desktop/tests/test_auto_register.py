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

    # On a fresh first run _ensure_credential gets the new cred's id directly
    # from the POST response, so there is no follow-up GET /credentials. The
    # next two GETs come from v0.5's capability-aware assignment:
    #   GET /api/models/defaults — read current to preserve manual overrides
    #   GET /api/models          — read all to score
    registered_model = {"id": "model:1", "name": "llama3.1:latest", "type": "language"}
    client.get.side_effect = [
        make_resp(200, credentials_list),    # GET /credentials (existence check)
        make_resp(200, models_list),         # GET /models      (existence check)
        make_resp(200, {}),                  # GET /api/models/defaults (no manual overrides)
        make_resp(200, [registered_model]),  # GET /api/models  (scoring pool)
    ]

    # POST /credentials, POST /models (auto-assign endpoint no longer called)
    client.post.side_effect = [
        make_resp(201, {"id": post_credential_id, "name": "Ollama (local)"}),  # POST /credentials
        make_resp(200, registered_model),                                       # POST /models
    ]
    # v0.5 — PUT /api/models/defaults replaces the old auto-assign POST
    client.put.side_effect = [
        make_resp(200, {}),
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

        # v0.5: POST /credentials + POST /models. The old POST /models/auto-assign
        # was replaced by PUT /api/models/defaults (asserted separately below).
        assert client1.post.call_count == 2
        assert client1.put.call_count == 1

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

        # No POSTs / PUTs should happen on second run — nothing new registered,
        # so we don't even enter the assignment phase.
        assert client2.post.call_count == 0
        assert client2.put.call_count == 0


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


def test_register_voice_models_is_idempotent_when_creds_already_exist():
    """v0.6.21 regression: pre-fix, register_voice_models always passed
    existing_names=set() to _ensure_credential, so the existence check
    was a no-op and every relaunch POSTed a duplicate creation request.

    With the fix, the caller passes its already-fetched set of credential
    names; voice.py uses it. When all names are already in the set,
    NO /api/credentials POST should happen at all.
    """
    from desktop.auto_register import register_voice_models
    from desktop.config import Config
    from pathlib import Path

    posted: list[tuple[str, dict]] = []
    gotten: list[str] = []

    class FakeClient:
        def post(self, path, json=None):
            posted.append((path, json))
            class R:
                status_code = 201
                text = ""
                def json(self): return {"id": "id-x"}
            return R()
        def get(self, path):
            gotten.append(path)
            class R:
                status_code = 200
                text = ""
                def raise_for_status(self): pass
                def json(self):
                    # Simulate existing creds (so _ensure_credential's
                    # "name already exists" GET path returns the real ID)
                    return [
                        {"name": "Whisper (local)", "id": "cred:1"},
                        {"name": "Piper (local)", "id": "cred:2"},
                        {"name": "Local Embeddings (llama.cpp)", "id": "cred:3"},
                    ]
            return R()

    cfg = Config(model_dir=Path("/tmp"), provider="none", default_model="",
                 surreal_user="root", surreal_password="x" * 24)
    existing_cred_names = {
        "whisper (local)", "piper (local)", "local embeddings (llama.cpp)"
    }
    existing_model_keys = {
        ("whisper-base-en", "speech_to_text"),
        ("piper-amy-en", "text_to_speech"),
        ("piper-ryan-en", "text_to_speech"),
        ("nomic-embed-text-v1.5", "embedding"),
    }
    register_voice_models(
        FakeClient(),
        whisper_port=1234, piper_port=2345, embed_port=3456, cfg=cfg,
        existing_cred_names=existing_cred_names,
        existing_model_keys=existing_model_keys,
    )

    # The crucial assertion: NO POST happened — neither for credentials
    # nor models. The pre-fix code would have POSTed every credential
    # and every model, regardless of the existing sets.
    assert not posted, (
        f"Expected zero POST calls when all entities already exist, got: {posted}"
    )


def test_register_memory_credential_is_idempotent_when_cred_exists():
    """v0.6.22 regression: pre-fix memory.py passed existing_names=set()
    and therefore POSTed a duplicate 'Memory (local)' on every relaunch."""
    from desktop.auto_register.memory import register_memory_credential

    posted: list[tuple[str, dict]] = []

    class FakeClient:
        def post(self, path, json=None):
            posted.append((path, json))
            class R:
                status_code = 201
                text = ""
                def json(self): return {"id": "id-x"}
            return R()
        def get(self, path):
            class R:
                status_code = 200
                text = ""
                def raise_for_status(self): pass
                def json(self):
                    return [{"name": "Memory (local)", "id": "cred:42"}]
            return R()

    existing = {"memory (local)"}
    register_memory_credential(
        FakeClient(), memory_port=8767, cfg=None,
        existing_cred_names=existing,
    )
    # No POST: credential already exists, the existing-set tells us so.
    assert not posted, f"expected zero POSTs when cred exists, got {posted}"


def test_episode_profile_picks_qwen_chat_model_over_voice_models():
    """v0.6.22 regression: the old hardcoded fallback chain checked for
    'Hermes-3-Llama-3.1-8B-Q4_K_M' and 'Mistral-7B-Instruct-v0.3-Q4_K_M'
    first. On a 64 GB Mac running v0.6.11's auto-assigner the registered
    chat model is named e.g. 'Qwen3.6-35B-A3B-Q4_K_M'. The new code
    picks the first non-voice/embed model regardless of its name."""
    from desktop.auto_register.episode_profile import register_default_episode_profile

    posted_episode_profiles: list[dict] = []

    class FakeClient:
        def get(self, path):
            class R:
                status_code = 200
                def raise_for_status(self): pass
                def json(self):
                    if path == "/api/episode_profiles":
                        return []  # no existing profile
                    if path == "/api/models":
                        # Order matters — the function picks the first non-voice.
                        return [
                            {"name": "Qwen3.6-35B-A3B-Q4_K_M", "id": "model:qwen"},
                            {"name": "piper-amy-en", "id": "model:amy"},
                            {"name": "piper-ryan-en", "id": "model:ryan"},
                            {"name": "nomic-embed-text-v1.5", "id": "model:nomic"},
                        ]
                    return []
            return R()

        def post(self, path, json=None):
            if path == "/api/episode_profiles":
                posted_episode_profiles.append(json)
            class R:
                status_code = 201
                text = ""
                def json(self): return {}
            return R()

    register_default_episode_profile(FakeClient())
    # v0.7.30 — preset library expanded from 1 → 9 presets. Each gets
    # POSTed when no existing profiles match. All must share the same
    # chat model + speaker IDs.
    from desktop.auto_register.episode_profile import _PRESETS
    assert len(posted_episode_profiles) == len(_PRESETS), (
        f"expected {len(_PRESETS)} preset POSTs, got {len(posted_episode_profiles)}"
    )
    for profile in posted_episode_profiles:
        assert profile["chat_model_id"] == "model:qwen", (
            f"chat model should be Qwen, got {profile['chat_model_id']}"
        )
        assert profile["speakers"][0]["tts_model_id"] == "model:amy"
        assert profile["speakers"][1]["tts_model_id"] == "model:ryan"
        # Each preset must carry its purpose-built briefing + segments.
        assert profile["default_briefing"], (
            f"preset {profile['name']!r} has no briefing"
        )
        assert 3 <= profile["num_segments"] <= 20, (
            f"preset {profile['name']!r} has out-of-range num_segments"
        )
    # Names are unique
    names = [p["name"] for p in posted_episode_profiles]
    assert len(set(names)) == len(names), "duplicate preset names"
    # Default preset is still in the set (back-compat)
    assert "Open Notebook Plus Local" in names


def test_episode_profile_skips_bge_embedding_in_chat_pick():
    """The old fallback used only prefix matching (piper-, whisper-, nomic-).
    A user with bge-large-en-v1.5 in their model dir (no matching prefix)
    would get it picked as chat model — wrong. The fix also runs the
    embedding heuristic."""
    from desktop.auto_register.episode_profile import register_default_episode_profile

    posted: list[dict] = []

    class FakeClient:
        def get(self, path):
            class R:
                def raise_for_status(self): pass
                def json(self):
                    if path == "/api/episode_profiles":
                        return []
                    if path == "/api/models":
                        return [
                            # bge-large-en-v1.5 — NOT matching any old prefix
                            # but IS an embedding model. Old code would have
                            # picked it as chat. New code correctly skips it.
                            {"name": "bge-large-en-v1.5", "id": "model:bge"},
                            {"name": "Qwen-7B-chat", "id": "model:qwen7"},
                            {"name": "piper-amy-en", "id": "model:amy"},
                            {"name": "piper-ryan-en", "id": "model:ryan"},
                        ]
                    return []
            return R()
        def post(self, path, json=None):
            if path == "/api/episode_profiles":
                posted.append(json)
            class R:
                status_code = 201
                def json(self): return {}
            return R()

    register_default_episode_profile(FakeClient())
    assert posted[0]["chat_model_id"] == "model:qwen7", (
        "should skip bge-* embedding and pick the real chat model"
    )


def test_episode_profile_library_is_idempotent():
    """v0.7.30 — re-running registration when SOME presets already exist
    only creates the missing ones. Customised existing profiles are
    never overwritten (we POST, not PUT)."""
    from desktop.auto_register.episode_profile import (
        register_default_episode_profile,
        _PRESETS,
    )

    posted: list[dict] = []
    # Simulate a partial install: the user already has "Deep Dive" and
    # "Quick Brief" (perhaps from a prior run, or hand-edited copies).
    existing_names = {"Deep Dive", "Quick Brief"}

    class FakeClient:
        def get(self, path):
            class R:
                def raise_for_status(self): pass
                def json(self):
                    if path == "/api/episode_profiles":
                        return [{"name": n} for n in existing_names]
                    if path == "/api/models":
                        return [
                            {"name": "Qwen-7B-chat", "id": "model:q"},
                            {"name": "piper-amy-en", "id": "model:amy"},
                            {"name": "piper-ryan-en", "id": "model:ryan"},
                        ]
                    return []
            return R()
        def post(self, path, json=None):
            if path == "/api/episode_profiles":
                posted.append(json)
            class R:
                status_code = 201
                text = ""
                def json(self): return {}
            return R()

    register_default_episode_profile(FakeClient())
    expected_new = len(_PRESETS) - len(existing_names)
    assert len(posted) == expected_new, (
        f"expected {expected_new} new POSTs (skipping existing), got {len(posted)}"
    )
    posted_names = {p["name"] for p in posted}
    # The skipped presets are NOT in the POSTed set
    assert not (existing_names & posted_names), (
        f"presets that existed got re-posted: {existing_names & posted_names}"
    )


def test_ensure_credential_does_not_post_when_existing_set_lies():
    """v0.6.30 regression: if pre-fetched existing_names claims a credential
    exists but the /api/credentials response doesn't actually contain it
    (e.g. case mismatch, race with delete, server response variance), the
    old code FELL THROUGH to a POST — creating a duplicate. The fix returns
    None so the caller logs + skips, never creating an unintended duplicate."""
    from desktop.auto_register._http import _ensure_credential

    posted = []

    class FakeClient:
        def get(self, path):
            class R:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return [{"name": "Other Cred", "id": "cred:other"}]
            return R()
        def post(self, path, json=None):
            posted.append((path, json))
            class R:
                status_code = 201
                text = ""
                def json(self): return {"id": "id-new"}
            return R()

    existing = {"mismatch cred"}  # claims to exist
    result = _ensure_credential(
        client=FakeClient(),
        existing_names=existing,
        name="Mismatch Cred",
        provider="ollama",
        modalities=["language"],
    )
    # Returns None, NOT the new ID — and crucially never POSTed.
    assert result is None
    assert not posted, f"expected zero POST calls, got: {posted}"


def test_ensure_credential_returns_existing_id_on_match():
    """Happy path control test — when GET response DOES contain the
    credential, return its ID without POSTing."""
    from desktop.auto_register._http import _ensure_credential

    posted = []

    class FakeClient:
        def get(self, path):
            class R:
                status_code = 200
                def raise_for_status(self): pass
                def json(self):
                    return [{"name": "Whisper (local)", "id": "cred:whisper-1"}]
            return R()
        def post(self, path, json=None):
            posted.append((path, json))
            class R:
                status_code = 201
                def json(self): return {"id": "would-be-duplicate"}
            return R()

    result = _ensure_credential(
        client=FakeClient(),
        existing_names={"whisper (local)"},
        name="Whisper (local)",
        provider="openai_compatible",
        modalities=["speech_to_text"],
    )
    assert result == "cred:whisper-1"
    assert not posted
