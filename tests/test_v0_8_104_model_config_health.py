"""v0.8.104 — a broken model configuration must say so, not fail silently.

Each case below is a failure this project actually shipped. The point of the
health check is not that it detects something in the abstract, but that the
specific states that killed chat in the field now produce a message naming the
setting and the fix.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.runtime_snapshot import RuntimeSnapshotProviders, build_runtime_snapshot
from deeper_notebook.health.model_config import evaluate_model_config_health


def _defaults(**overrides):
    base = {
        "default_chat_model": "model:good",
        "auto_route_enabled": False,
        "auto_route_cloud": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _model(name="Local Chat", provider="openai_compatible", credential="credential:c1"):
    return SimpleNamespace(name=name, provider=provider, credential=credential)


def _credential(name="Local (llama.cpp)", base_url="http://127.0.0.1:1234/v1"):
    return SimpleNamespace(name=name, base_url=base_url)


async def _evaluate(defaults, model=None, credential=None):
    async def defaults_loader():
        return defaults

    async def model_loader(model_id):
        if model is None:
            raise LookupError(model_id)
        return model

    async def credential_loader(credential_id):
        if credential is None:
            raise LookupError(credential_id)
        return credential

    return await evaluate_model_config_health(
        defaults_loader=defaults_loader,
        model_loader=model_loader,
        credential_loader=credential_loader,
    )


@pytest.mark.asyncio
async def test_a_healthy_configuration_reports_no_issues():
    health = await _evaluate(_defaults(), _model(), _credential())
    assert health.ok
    assert health.issues == []


@pytest.mark.asyncio
async def test_no_chat_default_is_reported():
    health = await _evaluate(_defaults(default_chat_model=None))
    assert not health.ok
    assert [i.code for i in health.issues] == ["chat_default_missing"]
    assert "Settings" in health.issues[0].remedy


@pytest.mark.asyncio
async def test_a_dangling_default_names_the_missing_row():
    """The env-migration-artifact shape: a well-formed id pointing at nothing."""
    health = await _evaluate(_defaults(default_chat_model="model:deleted"), model=None)
    codes = [i.code for i in health.issues]
    assert "chat_default_dangling" in codes
    detail = next(i.detail for i in health.issues if i.code == "chat_default_dangling")
    # The operator cannot act on "something is wrong"; they can act on an id.
    assert "model:deleted" in detail


@pytest.mark.asyncio
async def test_endpoint_provider_without_a_base_url_is_reported():
    health = await _evaluate(
        _defaults(), _model(), _credential(base_url="")
    )
    assert "chat_default_endpoint_missing" in [i.code for i in health.issues]


@pytest.mark.asyncio
async def test_cloud_provider_without_a_base_url_is_not_an_issue():
    """openai/anthropic carry their own endpoints — absence is normal there."""
    health = await _evaluate(
        _defaults(), _model(provider="openai"), _credential(base_url="")
    )
    assert health.ok


@pytest.mark.asyncio
async def test_local_only_auto_route_is_not_treated_as_a_fault():
    """v0.8.105 — the inverse of what v0.8.104 asserted, deliberately.

    v0.8.104 flagged "auto-route on, no cloud model" as an issue. Because
    health.add() sets ok=False, that pushed the whole runtime snapshot to
    "degraded" and raised an alert in the status panel for a configuration that
    is not merely valid but is the EXPECTED one: this product's governing
    constraint is that it works with the network cable unplugged, so a
    local-only install has no cloud model by design.

    Since v0.8.100 auto-route degrades cleanly to the configured default here,
    so nothing is broken. A panel that cries degraded at a correct setup trains
    people to ignore it — which costs more than the note was worth.
    """
    health = await _evaluate(
        _defaults(auto_route_enabled=True), _model(), _credential()
    )
    assert health.ok
    assert health.issues == []


@pytest.mark.asyncio
async def test_unreadable_defaults_degrade_rather_than_raise():
    async def boom():
        raise RuntimeError("db down")

    health = await evaluate_model_config_health(
        defaults_loader=boom, model_loader=None, credential_loader=None
    )
    assert "model_defaults_unreadable" in [i.code for i in health.issues]


# --- the surfacing seam -------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_surfaces_issues_and_flags_the_run_degraded():
    """A health check nobody can see is worth nothing — assert it reaches the API."""

    async def unhealthy():
        return {
            "ok": False,
            "issues": [
                {
                    "code": "chat_default_dangling",
                    "detail": "The configured chat model (model:gone) no longer exists.",
                    "remedy": "Settings → Models → pick a different default chat model.",
                }
            ],
        }

    snapshot = await build_runtime_snapshot(
        RuntimeSnapshotProviders(model_config_health=unhealthy)
    )

    assert snapshot.model_config_health.state == "degraded"
    assert snapshot.model_config_health.issues[0].code == "chat_default_dangling"
    assert "model_config_degraded" in snapshot.reasons


@pytest.mark.asyncio
async def test_snapshot_stays_ready_when_configuration_is_healthy():
    async def healthy():
        return {"ok": True, "issues": []}

    snapshot = await build_runtime_snapshot(
        RuntimeSnapshotProviders(model_config_health=healthy)
    )
    assert snapshot.model_config_health.state == "ready"
    assert "model_config_degraded" not in snapshot.reasons


@pytest.mark.asyncio
async def test_a_provider_that_explodes_yields_unknown_not_a_500():
    async def boom():
        raise RuntimeError("nope")

    snapshot = await build_runtime_snapshot(
        RuntimeSnapshotProviders(model_config_health=boom)
    )
    assert snapshot.model_config_health.state == "unknown"
    assert "model_config_unknown" in snapshot.reasons
