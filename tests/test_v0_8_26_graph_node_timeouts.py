"""v0.8.26 — Per-node LLM timeout for the transformation + prompt graphs.

Background: v0.7.138 added per-node `asyncio.wait_for` timeouts to the
ask graph after the audit found that a wedged local LLM could pin the
ask SSE stream indefinitely. The same audit family was not applied to
the transformation or prompt graphs — both call `chain.ainvoke(payload)`
directly without a timeout.

Why this matters specifically for the transformation graph: it's
invoked from `source_graph` (deeper_notebook/graphs/source.py:180) which
runs inside the `process_source` surreal-commands worker. With the
worker's retry config (`max_attempts=15`, `wait_max=120s`), a single
wedged transformation could keep the worker slot unavailable for
roughly half an hour before surreal_commands gives up — backing up
the entire ingest queue. The /transformations/execute endpoint has
an outer timeout (v0.7.95), but the graph-internal invocation does
not — that's the gap this fix closes.

The prompt graph (used by notes router for title generation) had the
same shape and shares the same env knob now (DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC).

Tests:
1. transformation graph times out and surfaces ExternalServiceError
2. prompt graph times out and surfaces ExternalServiceError
3. _transform_node_timeout_sec parses DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC
4. invalid env values fall back to 180s default with a warning
"""
from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.exceptions import ExternalServiceError

# ---------------------------------------------------------------------------
# Timeout-knob parsing
# ---------------------------------------------------------------------------


def test_v0826_timeout_default_is_180_seconds(monkeypatch):
    """Default is 180s — more generous than the v0.7.138 ask graph's
    120s because transformations run over capped source content
    (~3000 tokens), not just a short query."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC", raising=False)

    from deeper_notebook.graphs.transformation import _transform_node_timeout_sec

    assert _transform_node_timeout_sec() == 180.0


def test_v0826_timeout_respects_env_var(monkeypatch):
    """Setting DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC overrides the default."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC", "30.5")

    from deeper_notebook.graphs.transformation import _transform_node_timeout_sec

    assert _transform_node_timeout_sec() == 30.5


def test_v0826_timeout_falls_back_on_garbage_value(monkeypatch, caplog):
    """Malformed env value (e.g. 'fast') must fall back to the default
    with a logged warning — not crash the graph at module import."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC", "fast")

    from deeper_notebook.graphs.transformation import _transform_node_timeout_sec

    assert _transform_node_timeout_sec() == 180.0


def test_v0826_timeout_falls_back_on_negative_value(monkeypatch):
    """Negative timeouts make no sense — fall back to default."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC", "-5")

    from deeper_notebook.graphs.transformation import _transform_node_timeout_sec

    assert _transform_node_timeout_sec() == 180.0


# ---------------------------------------------------------------------------
# Transformation graph timeout behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v0826_transformation_graph_times_out(monkeypatch):
    """v0.8.26 — A wedged chain.ainvoke must surface as
    ExternalServiceError (not hang the worker forever).

    We tighten the timeout to ~0.1s and substitute a chain whose
    ainvoke sleeps for 5s, longer than the timeout, asserting the
    wait_for fires.
    """
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC", "0.1")

    from deeper_notebook.graphs import transformation as tg_mod

    # Build a fake "chain" that takes 5 seconds — far longer than 0.1s.
    class _SlowChain:
        async def ainvoke(self, payload):
            await asyncio.sleep(5)
            return type("R", (), {"content": "never reached"})()

    async def _fake_provision(*_args, **_kwargs):
        return _SlowChain()

    monkeypatch.setattr(tg_mod, "provision_langchain_model", _fake_provision)

    # Minimal stubs for the rest of the run_transformation pipeline so
    # the node reaches the ainvoke call.
    from langchain_core.runnables import RunnableConfig

    class _FakeTransformation:
        title = "Test transform"
        description = "test"
        prompt = "Test prompt"

    state = {
        "transformation": _FakeTransformation(),
        "content": "small content to transform",
        "input_text": "small content to transform",
        "source": None,
        "output": "",
    }

    with pytest.raises(ExternalServiceError) as exc_info:
        await tg_mod.run_transformation(
            state, RunnableConfig(configurable={}),
        )

    msg = str(exc_info.value)
    assert "timed out" in msg.lower(), (
        f"Expected timeout message; got {msg!r}"
    )
    assert "DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC" in msg, (
        f"Timeout message must name the env knob so the operator "
        f"knows how to raise it; got {msg!r}"
    )


# ---------------------------------------------------------------------------
# Prompt graph timeout behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v0826_prompt_graph_times_out(monkeypatch):
    """v0.8.26 — prompt graph shares the same timeout knob as
    transformation graph. A wedged chain.ainvoke here pins whatever
    invoked the prompt graph (e.g. notes router title generation)."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC", "0.1")

    from deeper_notebook.graphs import prompt as pg_mod

    class _SlowChain:
        async def ainvoke(self, payload):
            await asyncio.sleep(5)
            return type("R", (), {"content": "never reached"})()

    async def _fake_provision(*_args, **_kwargs):
        return _SlowChain()

    monkeypatch.setattr(pg_mod, "provision_langchain_model", _fake_provision)

    from langchain_core.runnables import RunnableConfig

    state = {
        "prompt": "Test prompt template",
        "parser": None,
        "input_text": "tiny",
        "output": "",
    }

    with pytest.raises(ExternalServiceError) as exc_info:
        await pg_mod.call_model(state, RunnableConfig(configurable={}))

    msg = str(exc_info.value)
    assert "timed out" in msg.lower()
    assert "DEEPER_NOTEBOOK_TRANSFORM_NODE_TIMEOUT_SEC" in msg
    # And it identifies which graph timed out so the operator can
    # debug — distinguishes transformation vs prompt failures.
    assert "Prompt graph" in msg, (
        f"Prompt graph timeout must identify itself in the message; "
        f"got {msg!r}"
    )


# ---------------------------------------------------------------------------
# Source-text contract pins
# ---------------------------------------------------------------------------


def test_v0826_transformation_uses_wait_for():
    """Pin the wait_for wrap so a future refactor doesn't drop it."""
    from pathlib import Path

    src = Path("deeper_notebook/graphs/transformation.py").read_text(
        encoding="utf-8",
    )
    assert "asyncio.wait_for(" in src and "chain.ainvoke" in src, (
        "v0.8.26: transformation graph must wrap chain.ainvoke in "
        "asyncio.wait_for. A refactor that drops the wrap reintroduces "
        "the worker-pinning bug — a wedged local LLM holds the "
        "surreal_commands worker for hours via the max_attempts=15 "
        "retry config."
    )


def test_v0826_prompt_uses_wait_for():
    """Pin the wait_for wrap on the prompt graph too."""
    from pathlib import Path

    src = Path("deeper_notebook/graphs/prompt.py").read_text(encoding="utf-8")
    assert "asyncio.wait_for(" in src and "chain.ainvoke" in src
    assert "_transform_node_timeout_sec" in src, (
        "v0.8.26: prompt graph imports _transform_node_timeout_sec "
        "from transformation.py to share the env knob."
    )
