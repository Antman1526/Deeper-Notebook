"""v0.7.10 — regression tests for transformation input cap.

`deeper_notebook.graphs.transformation.run_transformation` used to pass
`source.full_text` (or `input_text`) into the LLM prompt with no upper
bound. Combined with `max_tokens=8192`, a modest 50 KB source already
overflowed a 16k-context local server (the v0.7.8 default), throwing
opaque context-overflow errors mid-transform.

These tests pin the new `_truncate_transformation_input` contract.
"""

from __future__ import annotations

import pytest

from deeper_notebook.graphs import transformation

# ---------------------------------------------------------------------------
# _truncate_transformation_input — pure function tests
# ---------------------------------------------------------------------------


def test_short_input_passes_through(monkeypatch):
    """Input under the cap is returned unchanged — no marker, no warning."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", raising=False)
    text = "A short article body."
    out = transformation._truncate_transformation_input(text)
    assert out == text
    assert transformation._TRUNCATION_MARKER not in out


def test_oversize_input_is_truncated_with_marker(monkeypatch):
    """Default cap is 12_000 chars. A 30 KB input gets sliced and marked."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", raising=False)
    text = "X" * 30_000
    out = transformation._truncate_transformation_input(text)
    assert len(out) == 12_000 + len(transformation._TRUNCATION_MARKER)
    assert out.endswith(transformation._TRUNCATION_MARKER)
    # Original content preserved up to cap — not replaced with anything
    assert out.startswith("X" * 100)


def test_env_var_raises_cap(monkeypatch):
    """DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP lets capable-hardware users raise the cap."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", "50000")
    text = "Y" * 30_000
    # 30k now fits under 50k cap → no truncation
    out = transformation._truncate_transformation_input(text)
    assert out == text


def test_env_var_lowers_cap(monkeypatch):
    """Low-RAM users can shrink the cap."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", "1000")
    text = "Z" * 5000
    out = transformation._truncate_transformation_input(text)
    assert len(out) == 1000 + len(transformation._TRUNCATION_MARKER)
    assert out.endswith(transformation._TRUNCATION_MARKER)


def test_invalid_env_var_falls_back(monkeypatch):
    """Garbage value falls back to default (12_000) with a warning."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", "not-an-int")
    text = "Q" * 30_000
    out = transformation._truncate_transformation_input(text)
    # Default applied
    assert len(out) == 12_000 + len(transformation._TRUNCATION_MARKER)


def test_too_low_env_var_falls_back(monkeypatch):
    """Below 500 chars is almost certainly a typo — fall back to default
    rather than ship a useless one-paragraph input."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", "100")
    text = "Q" * 30_000
    out = transformation._truncate_transformation_input(text)
    assert len(out) == 12_000 + len(transformation._TRUNCATION_MARKER)


def test_exact_cap_size_not_truncated(monkeypatch):
    """Input at exactly the cap boundary is not truncated — `<=`, not `<`."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", raising=False)
    text = "A" * 12_000
    out = transformation._truncate_transformation_input(text)
    assert out == text
    assert transformation._TRUNCATION_MARKER not in out


def test_empty_input_is_unchanged(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", raising=False)
    assert transformation._truncate_transformation_input("") == ""


# ---------------------------------------------------------------------------
# run_transformation integration — ensure the cap is actually wired in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_transformation_applies_cap_to_input_text(monkeypatch):
    """When state["input_text"] is oversized, the LLM payload's
    HumanMessage gets the truncated version, not the raw text."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", raising=False)

    sent_payloads: list = []

    class _FakeResp:
        content = "result"

    class _FakeModel:
        async def ainvoke(self, payload):
            sent_payloads.append(payload)
            return _FakeResp()

    async def fake_provision(*args, **kw):
        return _FakeModel()

    class _FakePrompter:
        def __init__(self, *args, **kw):
            pass

        def render(self, data):
            return "system prompt"

    # Stub out DefaultPrompts to skip DB access entirely
    class _FakeDefaultPrompts:
        def __init__(self, *args, **kw):
            self.transformation_instructions = None

    class _FakeTransformation:
        title = "T"
        prompt = "transform this:"

    monkeypatch.setattr(transformation, "provision_langchain_model", fake_provision)
    monkeypatch.setattr(transformation, "Prompter", _FakePrompter)
    monkeypatch.setattr(transformation, "DefaultPrompts", _FakeDefaultPrompts)

    big_input = "B" * 30_000
    out = await transformation.run_transformation(
        {
            "input_text": big_input,
            "source": None,
            "transformation": _FakeTransformation(),
        },
        {"configurable": {}},
    )
    assert out == {"output": "result"}
    assert len(sent_payloads) == 1
    payload = sent_payloads[0]
    # payload[1] is the HumanMessage
    human_msg = payload[1]
    truncated = human_msg.content
    assert len(truncated) == 12_000 + len(transformation._TRUNCATION_MARKER)
    assert truncated.endswith(transformation._TRUNCATION_MARKER)


@pytest.mark.asyncio
async def test_run_transformation_applies_cap_to_source_full_text(monkeypatch):
    """When input_text isn't provided, source.full_text takes the same
    truncation path — this is the more common production case (running
    transformations on uploaded PDFs etc)."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_TRANSFORMATION_INPUT_CAP", raising=False)

    sent_payloads: list = []
    insights_added: list = []

    class _FakeSource:
        full_text = "S" * 50_000

        async def add_insight(self, title, content):
            insights_added.append((title, content))

    # Make isinstance(source, Source) true by patching Source itself
    monkeypatch.setattr(transformation, "Source", _FakeSource)

    class _FakeResp:
        content = "insight body"

    class _FakeModel:
        async def ainvoke(self, payload):
            sent_payloads.append(payload)
            return _FakeResp()

    async def fake_provision(*args, **kw):
        return _FakeModel()

    class _FakePrompter:
        def __init__(self, *args, **kw):
            pass

        def render(self, data):
            return "system prompt"

    class _FakeDefaultPrompts:
        def __init__(self, *args, **kw):
            self.transformation_instructions = None

    class _FakeTransformation:
        title = "My Transform"
        prompt = "do the thing"

    monkeypatch.setattr(transformation, "provision_langchain_model", fake_provision)
    monkeypatch.setattr(transformation, "Prompter", _FakePrompter)
    monkeypatch.setattr(transformation, "DefaultPrompts", _FakeDefaultPrompts)

    src = _FakeSource()
    out = await transformation.run_transformation(
        {
            "source": src,
            "transformation": _FakeTransformation(),
        },
        {"configurable": {}},
    )

    assert out == {"output": "insight body"}
    assert insights_added == [("My Transform", "insight body")]
    payload = sent_payloads[0]
    human_msg = payload[1]
    assert len(human_msg.content) == 12_000 + len(transformation._TRUNCATION_MARKER)
    assert human_msg.content.startswith("S" * 100)
