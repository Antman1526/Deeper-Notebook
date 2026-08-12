"""RED-to-GREEN contracts for Study Workbench syllabus generation and approval."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)
from deeper_notebook.study.source_service import (
    StudySourceReadiness,
    StudySourceReadinessItem,
)
from deeper_notebook.study.syllabus_service import (
    StudySyllabusConflict,
    StudySyllabusMalformedOutput,
    StudySyllabusNoEvidence,
    StudySyllabusNotReady,
    StudySyllabusService,
    StudySyllabusTimeout,
    source_manifest,
)

NOW = datetime(2026, 8, 12, tzinfo=UTC)


def _plan(*, version: int = 2, state: str = "editing") -> StudyPlan:
    return StudyPlan(
        plan_id="study_plan:one",
        goal="Learn mechanics",
        starting_level="Beginner",
        source_links=(StudyPlanSourceLink(source_id="source:one"),),
        version=version,
        state=state,
        created_at=NOW,
        updated_at=NOW,
    )


def _source(*, text: str = "Velocity is displacement over time.", fingerprint: str | None = None):
    return SimpleNamespace(
        id="source:one",
        title="Mechanics notes",
        source_type="text",
        full_text=text,
        command=None,
        provenance={"content_fingerprint": fingerprint} if fingerprint else {},
    )


def _ready() -> StudySourceReadiness:
    return StudySourceReadiness(
        ready=True,
        items=(
            StudySourceReadinessItem(
                source_id="source:one",
                title="Mechanics notes",
                kind="text",
                ready=True,
                command_id=None,
                fingerprint_status="available",
                reason="ready",
            ),
        ),
    )


def _document(*, unit_id: str = "foundations", source_ids: list[str] | None = None) -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "study_syllabus",
        "title": "Mechanics syllabus",
        "units": [
            {
                "unit_id": unit_id,
                "title": "Foundations",
                "objectives": ["Explain velocity"],
                "prerequisite_unit_ids": [],
                "estimated_minutes": 30,
                "source_ids": source_ids if source_ids is not None else ["source:one"],
                "activities": [],
            }
        ],
        "knowledge_gaps": [],
    }


class FakeModel:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[list[object]] = []

    def with_structured_output(self, schema, *, include_raw):
        raise NotImplementedError

    async def ainvoke(self, messages):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return SimpleNamespace(content=json.dumps(response) if isinstance(response, dict) else response)


class FakeRepository:
    def __init__(self, *, plan: StudyPlan | None = None, syllabi: tuple[StudySyllabus, ...] = ()):
        self.plan = plan or _plan()
        self.syllabi = {syllabus.version: syllabus for syllabus in syllabi}
        self.saved_artifacts: list[object] = []
        self.saved: list[StudySyllabus] = []
        self.approved: list[tuple[str, int, int]] = []

    async def get(self, plan_id: str) -> StudyPlan | None:
        return self.plan if plan_id == self.plan.plan_id else None

    async def get_syllabus(self, plan_id: str, *, version: int | None = None) -> StudySyllabus | None:
        if plan_id != self.plan.plan_id:
            return None
        if version is None:
            return self.syllabi[max(self.syllabi)] if self.syllabi else None
        return self.syllabi.get(version)

    async def save_syllabus(self, syllabus: StudySyllabus, *, expected_revision: int) -> StudySyllabus:
        if expected_revision != self.plan.version:
            raise StudySyllabusConflict("revision_conflict")
        if syllabus.version in self.syllabi:
            raise StudySyllabusConflict("version_exists")
        self.syllabi[syllabus.version] = syllabus
        self.saved.append(syllabus)
        return syllabus

    async def approve_syllabus(self, plan_id: str, *, syllabus_version: int, expected_revision: int) -> StudyPlan:
        if expected_revision != self.plan.version:
            raise StudySyllabusConflict("revision_conflict")
        syllabus = self.syllabi[syllabus_version]
        self.plan = StudyPlan.model_validate(
            self.plan.model_dump()
            | {
                "state": "approved",
                "source_manifest_sha256": syllabus.source_manifest_sha256,
                "approved_syllabus_version": syllabus_version,
                "version": self.plan.version + 1,
            }
        )
        self.approved.append((plan_id, syllabus_version, expected_revision))
        return self.plan


class FakeSourceService:
    def __init__(self, source: object | None = None, readiness: StudySourceReadiness | None = None):
        self.source = source or _source()
        self.receipt = readiness or _ready()

    async def readiness(self, plan):
        return self.receipt


@pytest.mark.asyncio
async def test_proposal_is_typed_and_does_not_approve_or_generate_artifacts():
    repository = FakeRepository()
    service = StudySyllabusService(
        repository=repository,
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(),
        model_resolver=lambda _: FakeModel([_document()]),
    )

    syllabus = await service.propose("study_plan:one", expected_revision=2)

    assert isinstance(syllabus, StudySyllabus)
    assert syllabus.version == 1
    assert syllabus.approved_at is None
    assert repository.saved_artifacts == []
    assert repository.approved == []
    assert syllabus.units[0].source_ids == ("source:one",)


@pytest.mark.asyncio
async def test_proposal_requires_current_revision_before_reading_sources():
    source_service = FakeSourceService()
    service = StudySyllabusService(
        repository=FakeRepository(),
        source_service=source_service,
        source_loader=lambda _source_id: _source(),
        model_resolver=lambda _: FakeModel([_document()]),
    )

    with pytest.raises(StudySyllabusConflict, match="revision_conflict"):
        await service.propose("study_plan:one", expected_revision=7)


@pytest.mark.asyncio
async def test_proposal_rejects_not_ready_sources_and_no_evidence():
    not_ready = StudySourceReadiness(
        ready=False,
        items=(_ready().items[0].model_copy(update={"ready": False, "reason": "processing"}),),
    )
    service = StudySyllabusService(
        repository=FakeRepository(),
        source_service=FakeSourceService(readiness=not_ready),
        source_loader=lambda _source_id: _source(text=""),
        model_resolver=lambda _: FakeModel([_document()]),
    )

    with pytest.raises(StudySyllabusNotReady, match="sources_not_ready"):
        await service.propose("study_plan:one", expected_revision=2)

    service = StudySyllabusService(
        repository=FakeRepository(),
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(text=""),
        model_resolver=lambda _: FakeModel([_document()]),
    )
    with pytest.raises(StudySyllabusNoEvidence, match="no_evidence"):
        await service.propose("study_plan:one", expected_revision=2)


@pytest.mark.asyncio
async def test_generation_uses_bounded_context_120_second_timeout_and_one_repair():
    model = FakeModel(["not json", _document()])
    repository = FakeRepository()
    service = StudySyllabusService(
        repository=repository,
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(text="Evidence " * 50_000),
        model_resolver=lambda _: model,
    )

    syllabus = await service.propose("study_plan:one", expected_revision=2)

    assert syllabus.units
    assert len(model.calls) == 2
    assert all(isinstance(message, HumanMessage) for call in model.calls for message in call[-1:])
    assert all(len(str(message.content)) <= 70_000 for call in model.calls for message in call)


@pytest.mark.asyncio
async def test_generation_timeout_and_malformed_output_are_typed():
    timeout_service = StudySyllabusService(
        repository=FakeRepository(),
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(),
        model_resolver=lambda _: FakeModel([asyncio.TimeoutError()]),
    )
    with pytest.raises(StudySyllabusTimeout, match="generation_timeout"):
        await timeout_service.propose("study_plan:one", expected_revision=2)

    malformed_service = StudySyllabusService(
        repository=FakeRepository(),
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(),
        model_resolver=lambda _: FakeModel(["bad", "still bad"]),
    )
    with pytest.raises(StudySyllabusMalformedOutput, match="malformed_output"):
        await malformed_service.propose("study_plan:one", expected_revision=2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document",
    [
        _document(unit_id="foundations"),
        {
            **_document(),
            "units": [
                {**_document()["units"][0], "unit_id": "a", "prerequisite_unit_ids": ["b"]},
                {**_document()["units"][0], "unit_id": "b", "prerequisite_unit_ids": ["a"]},
            ],
        },
    ],
)
async def test_generation_rejects_duplicate_or_cyclic_prerequisites(document):
    if document["units"][0]["unit_id"] == "foundations":
        document = {
            **document,
            "units": [{**document["units"][0], "prerequisite_unit_ids": ["a", "a"]}],
        }
    service = StudySyllabusService(
        repository=FakeRepository(),
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(),
        model_resolver=lambda _: FakeModel([document]),
    )

    with pytest.raises(StudySyllabusMalformedOutput):
        await service.propose("study_plan:one", expected_revision=2)


def test_source_manifest_is_deterministic_over_sorted_ids_and_fingerprints():
    first = [
        _source(fingerprint="b" * 64),
        SimpleNamespace(id="source:two", full_text="Second", provenance={"content_fingerprint": "a" * 64}),
    ]
    second = list(reversed(first))

    assert source_manifest(first) == source_manifest(second)
    expected_payload = "source:one\x00" + "b" * 64 + "\n" + "source:two\x00" + "a" * 64
    assert source_manifest(first) == hashlib.sha256(expected_payload.encode()).hexdigest()


@pytest.mark.asyncio
async def test_approval_rejects_source_manifest_drift_without_mutation():
    source = _source(fingerprint="a" * 64)
    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256=source_manifest([source]),
        units=(
            StudySyllabusUnit(
                unit_id="foundations",
                title="Foundations",
                objectives=("Explain velocity",),
                estimated_minutes=30,
                source_ids=("source:one",),
            ),
        ),
    )
    repository = FakeRepository(syllabi=(syllabus,))
    service = StudySyllabusService(
        repository=repository,
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: _source(fingerprint="c" * 64),
    )

    with pytest.raises(StudySyllabusConflict, match="sources_changed"):
        await service.approve("study_plan:one", syllabus_version=1, expected_revision=2)
    assert repository.approved == []


@pytest.mark.asyncio
async def test_approval_is_explicit_and_binds_exact_version():
    source = _source(fingerprint="a" * 64)
    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256=source_manifest([source]),
        units=(
            StudySyllabusUnit(
                unit_id="foundations",
                title="Foundations",
                objectives=("Explain velocity",),
                estimated_minutes=30,
                source_ids=("source:one",),
            ),
        ),
    )
    repository = FakeRepository(syllabi=(syllabus,))
    service = StudySyllabusService(
        repository=repository,
        source_service=FakeSourceService(),
        source_loader=lambda _source_id: source,
    )

    approved = await service.approve("study_plan:one", syllabus_version=1, expected_revision=2)

    assert approved.state == "approved"
    assert approved.approved_syllabus_version == 1
    assert repository.approved == [("study_plan:one", 1, 2)]
