"""RED contract tests for Study Workbench unit artifact generation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.study.artifact_service import (
    StudyArtifactCancelled,
    StudyArtifactConflict,
    StudyArtifactGenerationError,
    StudyArtifactService,
    _artifact_identity,
)
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
from deeper_notebook.study.syllabus_service import source_manifest


def _plan(*, state: str = "approved", version: int = 3, manifest: str | None = None) -> StudyPlan:
    return StudyPlan(
        plan_id="study_plan:one",
        goal="Learn mechanics",
        starting_level="beginner",
        source_links=(StudyPlanSourceLink(source_id="source:one"),),
        source_manifest_sha256=manifest,
        approved_syllabus_version=1 if state == "approved" else None,
        state=state,
        version=version,
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        updated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


def _unit(*, source_ids: tuple[str, ...] = ("source:one",)) -> StudySyllabusUnit:
    return StudySyllabusUnit(
        unit_id="foundations",
        title="Foundations",
        objectives=("Explain the core idea",),
        estimated_minutes=30,
        source_ids=source_ids,
    )


def _source(text: str = "Evidence about mechanics") -> SimpleNamespace:
    return SimpleNamespace(
        id="source:one",
        title="Mechanics notes",
        full_text=text,
        provenance={},
        command=None,
    )


def _readiness(*, ready: bool = True) -> StudySourceReadiness:
    return StudySourceReadiness(
        ready=ready,
        items=(
            StudySourceReadinessItem(
                source_id="source:one",
                title="Mechanics notes",
                kind="text",
                ready=ready,
                command_id=None,
                fingerprint_status="available" if ready else "unknown",
                reason="ready" if ready else "processing",
            ),
        ),
    )


def _syllabus(source: object | None = None) -> StudySyllabus:
    evidence = source or _source()
    return StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256=source_manifest([evidence]),
        units=(_unit(),),
        approved_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


class FakeArtifact:
    created: list["FakeArtifact"] = []

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)
        self.id = values.get("id") or f"studio_artifact:{len(self.created) + 1}"
        self.status = values.get("status", "pending")
        self.output_payload = values.get("output_payload", {})
        self.citations = values.get("citations", [])
        self.export_paths = values.get("export_paths", {})
        self.created.append(self)

    async def save(self) -> None:
        return None


class PersistentRaceArtifact:
    """Tiny persistent-authority double for independent service instances."""

    records: dict[str, "PersistentRaceArtifact"] = {}

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)
        self.id = str(values["id"])
        self.status = values.get("status", "pending")
        self.output_payload = values.get("output_payload", {})
        self.citations = values.get("citations", [])
        self.export_paths = values.get("export_paths", {})

    @classmethod
    async def get(cls, artifact_id: str) -> "PersistentRaceArtifact | None":
        return cls.records.get(artifact_id)

    async def save(self) -> None:
        await asyncio.sleep(0)
        incumbent = self.records.get(self.id)
        if incumbent is not None and incumbent is not self:
            raise RuntimeError("duplicate deterministic artifact")
        self.records[self.id] = self

    async def claim(self) -> bool:
        incumbent = self.records.get(self.id)
        if incumbent is not self or self.status != "pending":
            return False
        self.status = "running"
        return True


class FakeRepository:
    def __init__(self, *, plan: StudyPlan, syllabus: StudySyllabus) -> None:
        self.plan = plan
        self.syllabus = syllabus
        self.links: list[dict[str, object]] = []

    async def get(self, plan_id: str) -> StudyPlan | None:
        return self.plan if plan_id == self.plan.plan_id else None

    async def get_syllabus(self, plan_id: str, *, version: int | None = None) -> StudySyllabus | None:
        if plan_id != self.plan.plan_id or version not in (None, self.syllabus.version):
            return None
        return self.syllabus

    async def link_artifact(self, plan_id: str, artifact_id: str, *, artifact_kind: str, metadata: dict[str, object]) -> dict[str, object]:
        existing = next((item for item in self.links if item["plan_id"] == plan_id and item["artifact_id"] == artifact_id), None)
        if existing is not None:
            return existing
        link = {"plan_id": plan_id, "artifact_id": artifact_id, "artifact_kind": artifact_kind, "metadata": metadata}
        self.links.append(link)
        return link


class FakeSourceService:
    def __init__(self, source: object | None = None) -> None:
        self.source = source or _source()
        self.readiness_calls = 0

    async def readiness(self, _plan: StudyPlan) -> StudySourceReadiness:
        self.readiness_calls += 1
        return _readiness()


@pytest.fixture(autouse=True)
def reset_artifacts() -> None:
    FakeArtifact.created.clear()
    PersistentRaceArtifact.records.clear()


@pytest.mark.asyncio
async def test_unit_generation_requires_approved_matching_manifest() -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(state="editing", version=2), syllabus=_syllabus(source))
    service = StudyArtifactService(repository=repository, source_service=FakeSourceService(source))

    with pytest.raises(StudyArtifactConflict, match="syllabus_not_approved"):
        await service.generate_unit("study_plan:one", "foundations", ["study_guide"], expected_revision=2)


@pytest.mark.asyncio
async def test_unit_generation_allowlist_bounds_and_exact_unit_source_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    source_service = FakeSourceService(source)
    generated = AsyncMock(side_effect=lambda request: _complete(request.artifact_id))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generated)
    service = StudyArtifactService(repository=repository, source_service=source_service, source_loader=lambda _: source)

    with pytest.raises(StudyArtifactConflict, match="unsupported_artifact_type"):
        await service.generate_unit("study_plan:one", "foundations", ["report"], expected_revision=3)
    with pytest.raises(StudyArtifactConflict, match="unit_source_not_linked"):
        bad_syllabus = repository.syllabus.model_copy(update={"units": (_unit(source_ids=("source:other",)),)})
        repository.syllabus = bad_syllabus
        await service.generate_unit("study_plan:one", "foundations", ["study_guide"], expected_revision=3)


@pytest.mark.asyncio
async def test_completed_artifacts_link_idempotently_and_retry_does_not_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", AsyncMock(side_effect=lambda request: _complete(request.artifact_id)))
    service = StudyArtifactService(repository=repository, source_service=FakeSourceService(source), source_loader=lambda _: source)

    first = await service.generate_unit("study_plan:one", "foundations", ["study_guide"], expected_revision=3)
    second = await service.generate_unit("study_plan:one", "foundations", ["study_guide"], expected_revision=3)

    assert len(first) == len(second) == 1
    assert len(repository.links) == 1
    assert len(FakeArtifact.created) == 1


@pytest.mark.asyncio
async def test_failed_generation_never_creates_a_plan_link_and_hides_raw_error(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", AsyncMock(side_effect=RuntimeError("provider secret/path")))
    service = StudyArtifactService(repository=repository, source_service=FakeSourceService(source), source_loader=lambda _: source)

    with pytest.raises(StudyArtifactGenerationError, match="artifact_generation_failed") as error:
        await service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    assert "provider secret/path" not in str(error.value)
    assert repository.links == []


@pytest.mark.asyncio
async def test_cancellation_marks_provisional_artifact_cancelled_without_link(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", AsyncMock(side_effect=asyncio.CancelledError()))
    service = StudyArtifactService(repository=repository, source_service=FakeSourceService(source), source_loader=lambda _: source)

    with pytest.raises(StudyArtifactCancelled, match="generation_cancelled"):
        await service.generate_unit("study_plan:one", "foundations", ["mind_map"], expected_revision=3)
    assert repository.links == []
    assert FakeArtifact.created[0].status == "cancelled"


@pytest.mark.asyncio
async def test_concurrent_identical_generation_serializes_to_one_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    started = asyncio.Event()
    release = asyncio.Event()
    generation_calls = 0

    async def generate(request: object) -> FakeArtifact:
        nonlocal generation_calls
        generation_calls += 1
        started.set()
        await release.wait()
        return _complete(request.artifact_id)

    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generate)
    service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
    )
    first = asyncio.create_task(
        service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    )
    await started.wait()
    second = asyncio.create_task(
        service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    )
    await asyncio.sleep(0)
    release.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert generation_calls == 1
    assert len(FakeArtifact.created) == 1
    assert len(repository.links) == 1
    assert first_result == second_result


@pytest.mark.asyncio
async def test_independent_services_converge_on_persistent_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", PersistentRaceArtifact)
    started = asyncio.Event()
    release = asyncio.Event()
    generation_calls = 0

    async def generate(request: object) -> PersistentRaceArtifact:
        nonlocal generation_calls
        generation_calls += 1
        started.set()
        await release.wait()
        artifact = PersistentRaceArtifact.records[str(request.artifact_id)]
        artifact.status = "completed"
        artifact.output_payload = {"markdown": "completed"}
        return artifact

    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generate)
    first_service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        lock_store={},
    )
    second_service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        lock_store={},
    )
    first = asyncio.create_task(
        first_service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    )
    await started.wait()
    second = asyncio.create_task(
        second_service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    )
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert generation_calls == 1
    assert len(PersistentRaceArtifact.records) == 1
    assert len(repository.links) == 1
    assert sum(isinstance(result, StudyArtifactConflict) for result in results) == 1
    assert sum(isinstance(result, list) for result in results) == 1


def test_artifact_identity_changes_for_every_authority_dimension() -> None:
    base = _artifact_identity("study_plan:one", 1, "a" * 64, "foundations", "quiz")
    assert _artifact_identity("study_plan:one", 2, "a" * 64, "foundations", "quiz") != base
    assert _artifact_identity("study_plan:one", 1, "b" * 64, "foundations", "quiz") != base
    assert _artifact_identity("study_plan:one", 1, "a" * 64, "advanced", "quiz") != base
    assert _artifact_identity("study_plan:one", 1, "a" * 64, "foundations", "flashcards") != base


def _complete(artifact_id: str) -> FakeArtifact:
    artifact = next(item for item in FakeArtifact.created if item.id == artifact_id)
    artifact.status = "completed"
    artifact.output_payload = {"markdown": "completed"}
    return artifact
