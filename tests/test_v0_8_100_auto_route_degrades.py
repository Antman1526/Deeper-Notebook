"""v0.8.100 — auto-route degrades to the chat default instead of hard-failing.

`provision_langchain_chat_model` resolves a local candidate from
DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID or, failing that, from
`_measured_local_chat_model_id()` — which only returns a model when BENCHMARK
HISTORY proves one. A fresh install has no benchmark history. With no cloud
credential either, both candidates came back None and `pick_provider` raised
its step-5 "No model available — neither local nor cloud", killing every chat
turn for a local-only operator who had merely flipped the Settings toggle.

The configured `default_chat_model` was fine the whole time, and the identical
call with the toggle OFF answered normally. Routing between zero candidates is
not routing, so auto-route now delegates to that same default path.
"""

from __future__ import annotations

import pytest

from deeper_notebook.ai import provision
from deeper_notebook.ai.router import pick_provider


def test_pick_provider_still_raises_with_no_candidates():
    """The router is a correct pure function — this is NOT what changed.

    With genuinely nothing to choose between, raising is right. The defect was
    the caller handing it two Nones instead of degrading, so this behaviour is
    pinned to keep the fix in the caller where it belongs.
    """
    with pytest.raises(ValueError, match="No model available"):
        pick_provider(
            content_tokens=10,
            local_chat_healthy=False,
            local_chat_n_ctx=32768,
            cloud_model_id=None,
            local_model_id=None,
        )


class _Defaults:
    auto_route_enabled = True
    auto_route_cloud = None
    default_chat_model = "model:configured-default"


@pytest.fixture
def _no_candidates(monkeypatch):
    """Auto-route ON, no env overrides, no benchmark history, no cloud."""

    async def _get_defaults():
        return _Defaults()

    async def _no_measured():
        return None

    monkeypatch.setattr(provision, "resolve_env", lambda *a, **k: "")
    monkeypatch.setattr(provision.model_manager, "get_defaults", _get_defaults)
    monkeypatch.setattr(provision, "_measured_local_chat_model_id", _no_measured)


@pytest.mark.asyncio
async def test_auto_route_with_no_candidates_uses_the_chat_default(
    monkeypatch, _no_candidates
):
    """The regression test: this raised ValueError before the fix."""
    seen: dict = {}

    async def _fake_default_path(content, *, model_id, default_type, **kwargs):
        seen["model_id"] = model_id
        seen["default_type"] = default_type
        return "DEFAULT-PATH-MODEL"

    monkeypatch.setattr(provision, "provision_langchain_model", _fake_default_path)

    result = await provision.provision_langchain_chat_model("hello")

    assert result == "DEFAULT-PATH-MODEL"
    # model_id=None means "let DefaultModels config choose" — the same call the
    # toggle-off branch makes, so the degraded path is the documented one.
    assert seen == {"model_id": None, "default_type": "chat"}


@pytest.mark.asyncio
async def test_degraded_path_reports_no_local_cloud_label(monkeypatch, _no_candidates):
    """selection_out stays unlabelled, matching the toggle-off path.

    The default path has no local/cloud distinction, so claiming either would be
    a lie. Absent keys are the truthful answer.
    """

    async def _fake_default_path(content, *, model_id, default_type, **kwargs):
        return "DEFAULT-PATH-MODEL"

    monkeypatch.setattr(provision, "provision_langchain_model", _fake_default_path)

    selection: dict = {}
    await provision.provision_langchain_chat_model("hello", selection_out=selection)

    assert "selected_provider" not in selection
