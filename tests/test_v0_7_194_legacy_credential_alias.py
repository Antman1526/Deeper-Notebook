"""v0.7.194 — `register_llamacpp_models` prefers the legacy
`Local GGUF (llama.cpp)` credential name when it exists.

End-user-visible bug discovered by inspecting `/api/credentials`
on a freshly-launched v0.7.193 .app:

  - Pre-v0.6.x installs created the local-GGUF credential under
    the name `Local GGUF (llama.cpp)` with `base_url=http://127.0.0.1:8080/v1`
    (the hardcoded port from v0.5.9 era).
  - 10-20+ local chat / embedding models were linked to that
    credential.
  - v0.6.x silently renamed the canonical-form to `llama.cpp
    (local)`, but pre-existing installs never got renamed.
  - v0.7.193 auto-register ran with the new name, didn't find a
    match by name (case-sensitive lookup), and CREATED a fresh
    "llama.cpp (local)" credential — orphaned with 0 models linked.
  - The user's chat still hit the broken hardcoded port 8080
    because their models pointed at the legacy credential, which
    auto-register never touched.

  Fix: at the credential-creation step in
  `register_llamacpp_models`, check whether the legacy name
  `Local GGUF (llama.cpp)` already exists in
  `existing_cred_names`. If so, target THAT credential by name
  — v0.7.193's `_ensure_credential` PUT branch then refreshes
  its base_url to the current chat_llm_port and the existing
  model links keep working. New installs (no legacy credential)
  get the modern name.

This test is AST-level — it pins the canonical-name resolution
in llamacpp.py without depending on a running SurrealDB.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AST pin: legacy-name awareness in source code
# ---------------------------------------------------------------------------


def test_register_llamacpp_models_recognizes_legacy_name():
    """v0.7.194: llamacpp.py must explicitly check for the legacy
    `Local GGUF (llama.cpp)` name and prefer it when present.

    Without this, a fresh `llama.cpp (local)` credential is created
    and the pre-existing 10-20+ models stay linked to the broken
    port-8080 credential."""
    src = _read_source("desktop/auto_register/llamacpp.py")
    assert "Local GGUF (llama.cpp)" in src, (
        "v0.7.194 regression: legacy credential name lookup is gone "
        "from llamacpp.py. Pre-v0.6.x installs will get orphaned "
        "duplicate credentials again."
    )
    assert "legacy_name = " in src
    assert "modern_name = " in src


# ---------------------------------------------------------------------------
# Behavioural pin: routes to legacy name when it exists
# ---------------------------------------------------------------------------


def test_legacy_name_used_when_pre_existing(monkeypatch, tmp_path):
    """v0.7.194: with `Local GGUF (llama.cpp)` already in
    existing_cred_names, register_llamacpp_models must look up
    THAT credential (and refresh its URL via _ensure_credential's
    PUT branch), NOT POST a fresh `llama.cpp (local)` duplicate."""
    from desktop.auto_register.llamacpp import register_llamacpp_models

    # Fake httpx client. GET returns the legacy credential
    # pointing at the broken port 8080. _ensure_credential should
    # PUT the new URL to it.
    client = MagicMock()
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [
            {
                "id": "credential:legacy-abc",
                "name": "Local GGUF (llama.cpp)",
                "base_url": "http://127.0.0.1:8080/v1",
            }
        ],
    )
    client.put.return_value = MagicMock(status_code=200, text="ok")

    register_llamacpp_models(
        client,
        existing_cred_names={"local gguf (llama.cpp)"},  # lowercased
        existing_model_keys=set(),
        model_dir=tmp_path,
        llamacpp_port=51027,  # the current dynamic port
        local_ggufs=[],  # don't bother creating models in this test
    )

    # The PUT must have hit the LEGACY credential id with the new URL.
    client.put.assert_called_once()
    put_call = client.put.call_args
    assert put_call.args[0] == "/api/credentials/credential:legacy-abc"
    assert put_call.kwargs["json"] == {"base_url": "http://127.0.0.1:51027/v1"}
    # And no POST should have been issued (which would create a duplicate).
    client.post.assert_not_called()


def test_modern_name_used_when_no_legacy_credential(monkeypatch, tmp_path):
    """v0.7.194: clean installs (no legacy credential in the DB)
    get the modern `llama.cpp (local)` name. Forward-compat: the
    legacy-alias logic only fires when the legacy entry exists."""
    from desktop.auto_register.llamacpp import register_llamacpp_models

    client = MagicMock()
    # /credentials returns []; nothing matches.
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [],
    )
    # POST creates the new credential.
    client.post.return_value = MagicMock(
        status_code=201,
        json=lambda: {"id": "credential:new-xyz"},
    )

    register_llamacpp_models(
        client,
        existing_cred_names=set(),  # nothing pre-existing
        existing_model_keys=set(),
        model_dir=tmp_path,
        llamacpp_port=51027,
        local_ggufs=[],
    )

    # POST must have used the MODERN name.
    client.post.assert_called_once()
    post_payload = client.post.call_args.kwargs["json"]
    assert post_payload["name"] == "llama.cpp (local)"
    assert post_payload["base_url"] == "http://127.0.0.1:51027/v1"
