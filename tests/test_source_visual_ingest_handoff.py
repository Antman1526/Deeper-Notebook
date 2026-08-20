from __future__ import annotations

from types import SimpleNamespace

import pytest

NOW = __import__("datetime").datetime(2026, 8, 15)
HASH = "a" * 64


def _input():
    from commands.source_commands import SourceProcessingInput

    return SourceProcessingInput(
        source_id="source:one",
        content_state={"title": "Source one", "full_text": "text"},
        notebook_ids=[],
        transformations=[],
        embed=False,
    )


@pytest.fixture
def source_processing_context(monkeypatch):
    import commands.source_commands as source_commands

    processed = SimpleNamespace(
        id="source:one",
        full_text="source content remains authoritative",
        title="Source one",
        topics=[],
        async_save_calls=0,
    )

    async def save():
        processed.async_save_calls += 1

    async def get_insights():
        return []

    processed.save = save
    processed.get_insights = get_insights
    source = SimpleNamespace(
        id="source:one",
        command=None,
        full_text="source content remains authoritative",
        title="Source one",
        async_save_calls=0,
    )

    async def source_save():
        source.async_save_calls += 1

    source.save = source_save
    monkeypatch.setattr(
        source_commands, "Transformation", SimpleNamespace(get=lambda _id: None)
    )
    monkeypatch.setattr(
        source_commands,
        "Source",
        SimpleNamespace(get=lambda _id: source),
    )
    monkeypatch.setattr(
        source_commands,
        "ContentSettings",
        SimpleNamespace(get_instance=lambda: SimpleNamespace()),
    )
    monkeypatch.setattr(
        source_commands,
        "source_graph",
        SimpleNamespace(ainvoke=lambda _state: {"source": processed}),
    )
    monkeypatch.setattr(
        source_commands,
        "compute_source_visual_authority",
        lambda _source: SimpleNamespace(content_sha256=HASH),
    )
    return source_commands, processed, source


@pytest.mark.asyncio
async def test_ingest_visual_handoff_is_disabled_without_backend_flag(
    source_processing_context, monkeypatch
):
    source_commands, _processed, _source = source_processing_context
    called = []
    monkeypatch.setattr(source_commands, "source_visuals_enabled", lambda: False)
    monkeypatch.setattr(
        source_commands,
        "submit_source_visual",
        lambda *args, **kwargs: called.append((args, kwargs)),
    )

    result = await source_commands.process_source_command(_input())

    assert result.success is True
    assert called == []


@pytest.mark.asyncio
async def test_ingest_visual_handoff_uses_deterministic_request_and_is_best_effort(
    source_processing_context, monkeypatch
):
    source_commands, processed, _source = source_processing_context
    called = []

    async def fail_handoff(*args, **kwargs):
        called.append((args, kwargs))
        raise RuntimeError("private source path must not alter ingest")

    monkeypatch.setattr(source_commands, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(source_commands, "submit_source_visual", fail_handoff)

    result = await source_commands.process_source_command(_input())

    assert result.success is True
    assert called == [(("source:one", f"ingest:{HASH}"), {"explicit": False})]
    assert processed.full_text == "source content remains authoritative"


@pytest.mark.asyncio
async def test_ingest_handoff_success_does_not_change_existing_processing_result(
    source_processing_context, monkeypatch
):
    source_commands, processed, _source = source_processing_context
    called = []

    async def submit(*args, **kwargs):
        called.append((args, kwargs))
        return SimpleNamespace(outcome="queued")

    monkeypatch.setattr(source_commands, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(source_commands, "submit_source_visual", submit)

    result = await source_commands.process_source_command(_input())

    assert result.success is True
    assert result.source_id == "source:one"
    assert result.insights_created == 0
    assert processed.full_text == "source content remains authoritative"
