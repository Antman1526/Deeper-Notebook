"""Real-SurrealDB contracts for persisted Research Runs."""

from __future__ import annotations

import pytest

from open_notebook.domain.notebook import Notebook
from open_notebook.research.repository import ResearchRunRepository
from open_notebook.research.state import (
    ResearchCandidate,
    ResearchRun,
    ResearchStageResult,
)

pytestmark = pytest.mark.integration_surreal


async def test_repository_persists_stage_checkpoint_and_deduplicates_sources(
    clean_namespace,
):
    notebook = Notebook(name="Research run", description="Research persistence test")
    await notebook.save()
    repository = ResearchRunRepository()
    created = await repository.create(
        ResearchRun(objective="Compare evidence", notebook_id=str(notebook.id))
    )

    saved = await repository.save_stage_result(
        created,
        "plan",
        ResearchStageResult(
            checkpoint={"plan_version": 1},
            hypotheses=["Evidence is reproducible"],
            source_ids=["source:one", "source:one", "source:two"],
        ),
    )
    replayed = await repository.save_stage_result(
        saved,
        "plan",
        ResearchStageResult(source_ids=["source:three"]),
    )

    assert saved.stage == "discover"
    assert saved.source_ids == ["source:one", "source:two"]
    assert replayed.source_ids == ["source:one", "source:two"]
    assert replayed.checkpoints["plan"] == {"plan_version": 1}


async def test_repository_persists_cancellation(clean_namespace):
    repository = ResearchRunRepository()
    created = await repository.create(ResearchRun(objective="Stop research"))

    cancelled = await repository.request_cancellation(created.id or "")
    reloaded = await repository.get(created.id or "")

    assert cancelled is not None and cancelled.cancelled is True
    assert reloaded is not None and reloaded.cancelled is True


async def test_repository_persists_explicit_candidate_decisions(clean_namespace):
    repository = ResearchRunRepository()
    created = await repository.create(
        ResearchRun(
            objective="Approve trusted source",
            candidates=[
                ResearchCandidate(
                    candidate_id="candidate:trusted",
                    url="https://example.test/trusted",
                )
            ],
        )
    )

    saved = await repository.save_approval_decisions(
        created,
        {"candidate:trusted": True},
    )

    assert saved.approval_decisions == {"candidate:trusted": True}
