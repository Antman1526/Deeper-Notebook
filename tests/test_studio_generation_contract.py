"""Contract tests for the Evidence Studio generation service boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.studio import artifact_generation
from deeper_notebook.studio.generation import ArtifactGenerationRequest
from deeper_notebook.studio.generation import service as generation_service
from deeper_notebook.studio.generation.context import (
    artifact_context,
    artifact_not_ready_sources,
)
from deeper_notebook.studio.generation.prompts import (
    artifact_instruction,
    artifact_model_role,
    study_unit_prompt,
)


def test_prompt_helpers_preserve_artifact_steering_and_model_roles() -> None:
    artifact = SimpleNamespace(
        artifact_type="flashcards",
        prompt="Keep each answer compact.",
    )

    assert artifact_model_role("flashcards") == "study_fast"
    assert "source-grounded flashcards" in artifact_instruction(artifact)
    assert "Keep each answer compact." in artifact_instruction(artifact)


def test_study_unit_prompt_is_metadata_bound_and_bounded_by_caller() -> None:
    prompt = study_unit_prompt(
        "study_guide",
        plan_goal="Learn mechanics",
        unit_title="Foundations",
        objectives=("Explain the core idea",),
        prerequisite_unit_ids=("intro",),
        source_ids=("source:one",),
        context="Prefer short examples.",
    )

    assert "Unit: Foundations" in prompt
    assert "source:one" in prompt
    assert "Prefer short examples." in prompt
    assert "Provider secret" not in prompt


def test_context_helpers_keep_stable_citation_markers_and_readiness_shape() -> None:
    ready = SimpleNamespace(
        id="source:ready",
        title="Ready source",
        full_text="Evidence that is ready to cite.",
        command=None,
    )
    waiting = SimpleNamespace(
        id="source:waiting",
        title="Waiting source",
        full_text="",
        command="command:extract",
    )

    context, citations = artifact_context([ready])

    assert "## Source [S1]: Ready source" in context
    assert citations == [
        {
            "source_id": "source:ready",
            "title": "Ready source",
            "marker": "[S1]",
            "location": "Source [S1]",
            "preview": "Evidence that is ready to cite.",
        }
    ]
    assert artifact_not_ready_sources([ready, waiting]) == [
        {
            "source_id": "source:waiting",
            "title": "Waiting source",
            "command_id": "command:extract",
        }
    ]


@pytest.mark.asyncio
async def test_legacy_adapter_delegates_to_the_request_service(monkeypatch) -> None:
    generated = SimpleNamespace(id="studio_artifact:report")
    generate = AsyncMock(return_value=generated)
    monkeypatch.setattr(artifact_generation, "generate_artifact", generate)

    result = await artifact_generation.generate_studio_artifact(
        "studio_artifact:report"
    )

    assert result is generated
    assert generate.await_args.args == (
        ArtifactGenerationRequest(
            artifact_id="studio_artifact:report",
            source_ids=[],
        ),
    )


@pytest.mark.asyncio
async def test_additive_persistence_callback_accepts_async_result() -> None:
    artifact = generation_service.StudioArtifact(
        notebook_id="notebook:study_callback",
        artifact_type="quiz",
        title="Callback quiz",
    )
    persist = AsyncMock(return_value=artifact)
    request = ArtifactGenerationRequest(
        artifact_id="studio_artifact:callback",
        source_ids=[],
        persist_artifact=persist,
    )

    result = await generation_service._persist_artifact(request, artifact)

    assert result is artifact
    persist.assert_awaited_once_with(artifact)
