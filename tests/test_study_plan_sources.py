"""RED-to-GREEN coverage for Study Workbench source readiness and linking."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routers import study_plans
from api.schemas.study_plans import SourceLinkRequest
from deeper_notebook.study import source_service
from deeper_notebook.study.plans import StudyPlan, StudyPlanSourceLink

LINK = StudyPlanSourceLink(source_id="source:one")


@pytest.mark.asyncio
async def test_readiness_marks_missing_text_without_reading_or_copying_source(monkeypatch):
    """A source without extracted text is bounded as processing, not exposed."""

    get_source = AsyncMock(
        return_value=SimpleNamespace(
            id="source:one",
            title="Lecture",
            full_text="",
            command="command:one",
            source_type="upload",
            asset=SimpleNamespace(file_path="/private/lecture.pdf"),
        )
    )
    monkeypatch.setattr(source_service.Source, "get", get_source)

    receipt = await source_service.StudySourceService().readiness([LINK])

    assert receipt.ready is False
    assert receipt.items[0].source_id == "source:one"
    assert receipt.items[0].title == "Lecture"
    assert receipt.items[0].kind == "upload"
    assert receipt.items[0].reason == "processing"
    assert receipt.items[0].command_id == "command:one"
    assert receipt.items[0].fingerprint_status == "unknown"
    assert "full_text" not in receipt.items[0].model_dump()
    assert "file_path" not in receipt.items[0].model_dump()
    get_source.assert_awaited_once_with("source:one")


@pytest.mark.asyncio
async def test_readiness_deduplicates_links_and_exposes_only_bounded_projection(monkeypatch):
    source = SimpleNamespace(
        id="source:one",
        title="Lecture",
        full_text="A complete extracted lecture.",
        command=None,
        source_type="text",
        provenance={"fingerprint": "a" * 64},
        asset=SimpleNamespace(file_path="/private/lecture.txt"),
    )
    get_source = AsyncMock(return_value=source)
    monkeypatch.setattr(source_service.Source, "get", get_source)

    receipt = await source_service.StudySourceService().readiness([LINK, LINK])

    assert receipt.ready is True
    assert len(receipt.items) == 1
    assert receipt.items[0].fingerprint_status == "available"
    assert set(receipt.items[0].model_dump()) == {
        "source_id",
        "title",
        "kind",
        "ready",
        "command_id",
        "fingerprint_status",
        "reason",
    }
    get_source.assert_awaited_once_with("source:one")


@pytest.mark.asyncio
async def test_validate_source_rejects_missing_source_before_linking(monkeypatch):
    monkeypatch.setattr(source_service.Source, "get", AsyncMock(return_value=None))

    with pytest.raises(source_service.StudySourceNotFoundError):
        await source_service.StudySourceService().validate_source("source:missing")


def _plan(*links: StudyPlanSourceLink) -> StudyPlan:
    from datetime import UTC, datetime

    now = datetime(2026, 8, 12, tzinfo=UTC)
    return StudyPlan(
        plan_id="study_plan:one",
        goal="Learn mechanics",
        starting_level="Beginner",
        source_links=links,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_link_validates_source_before_repository_mutation(monkeypatch):
    plan = _plan()
    add_source = AsyncMock()

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await add_source(*args, **kwargs)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(source_service.Source, "get", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as raised:
        await study_plans.add_study_plan_source(
            "study_plan:one",
            SourceLinkRequest(source_id="source:missing", expected_revision=1),
        )

    assert raised.value.status_code == 404
    add_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_link_deduplicates_existing_source_without_revision_bump(monkeypatch):
    plan = _plan(LINK)
    add_source = AsyncMock()

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await add_source(*args, **kwargs)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(
        source_service.Source,
        "get",
        AsyncMock(return_value=SimpleNamespace(full_text="existing source")),
    )

    result = await study_plans.add_study_plan_source(
        "study_plan:one",
        SourceLinkRequest(source_id="source:one", expected_revision=1),
    )

    assert result.source_id == "source:one"
    add_source.assert_not_awaited()
