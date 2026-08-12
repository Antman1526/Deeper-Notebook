"""RED contract tests for Study Workbench unit artifact generation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.study.artifact_service import (
    CLAIM_LEASE_SECONDS,
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


def _unit(
    *,
    source_ids: tuple[str, ...] = ("source:one",),
    title: str = "Foundations",
) -> StudySyllabusUnit:
    return StudySyllabusUnit(
        unit_id="foundations",
        title=title,
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

    async def claim(
        self,
        *,
        owner: str | None = None,
        started_at: datetime | None = None,
        lease_until: datetime | None = None,
        now: datetime | None = None,
    ) -> bool:
        incumbent = self.records.get(self.id)
        if incumbent is not self:
            return False
        expiry = getattr(self, "generation_claim_lease_until", None)
        expired = (
            self.status == "running"
            and isinstance(expiry, datetime)
            and isinstance(now, datetime)
            and expiry <= now
        )
        if self.status != "pending" and not expired:
            return False
        self.status = "running"
        self.generation_claim_owner = owner
        self.generation_claim_started_at = started_at
        self.generation_claim_lease_until = lease_until
        return True


class LeasedArtifact:
    """Small object authority used to exercise expired-claim recovery."""

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)
        self.id = str(values["id"])
        self.status = values.get("status", "pending")
        self.artifact_type = values.get("artifact_type", "quiz")
        self.source_ids = values.get("source_ids", [])

    async def save(self) -> None:
        return None


class FencedRaceArtifact:
    """Detached objects with an unconditional legacy save and owner fence."""

    records: dict[str, "FencedRaceArtifact"] = {}

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)
        self.id = str(values["id"])
        self.status = values.get("status", "pending")
        self.output_payload = values.get("output_payload", {})
        self.citations = values.get("citations", [])
        self.export_paths = values.get("export_paths", {})

    def _copy(self) -> "FencedRaceArtifact":
        values = dict(self.__dict__)
        values["output_payload"] = dict(self.output_payload)
        values["citations"] = list(self.citations)
        values["export_paths"] = dict(self.export_paths)
        return type(self)(**values)

    @classmethod
    async def get(cls, artifact_id: str) -> "FencedRaceArtifact | None":
        current = cls.records.get(artifact_id)
        return current._copy() if current is not None else None

    async def save(self) -> None:
        # This models the pre-repair Studio save: a stale detached worker can
        # overwrite a reclaimed row after a newer owner completes.
        self.__class__.records[self.id] = self._copy()

    async def claim(
        self,
        *,
        owner: str | None = None,
        started_at: datetime | None = None,
        lease_until: datetime | None = None,
        now: datetime | None = None,
    ) -> bool:
        current = self.__class__.records.get(self.id)
        if current is None:
            return False
        expiry = getattr(current, "generation_claim_lease_until", None)
        expired = (
            current.status == "running"
            and isinstance(expiry, datetime)
            and isinstance(now, datetime)
            and expiry <= now
        )
        if current.status != "pending" and not expired:
            return False
        self.status = "running"
        self.generation_claim_owner = owner
        self.generation_claim_started_at = started_at
        self.generation_claim_lease_until = lease_until
        self.__class__.records[self.id] = self._copy()
        return True

    async def persist_if_owner(self, owner: str | None) -> bool:
        current = self.__class__.records.get(self.id)
        if owner is None or current is None or current.generation_claim_owner != owner:
            return False
        self.__class__.records[self.id] = self._copy()
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
    FencedRaceArtifact.records.clear()


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


@pytest.mark.asyncio
async def test_source_drift_after_durable_claim_aborts_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    generated = AsyncMock(side_effect=lambda request: _complete(request.artifact_id))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generated)
    service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
    )
    original_claim = service._claim_provisional

    async def claim_then_mutate(*args: object, **kwargs: object) -> tuple[object, str]:
        claimed = await original_claim(*args, **kwargs)
        source.full_text = "changed after the durable claim"
        return claimed

    service._claim_provisional = claim_then_mutate  # type: ignore[method-assign]

    with pytest.raises(StudyArtifactConflict, match="sources_changed"):
        await service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)

    generated.assert_not_awaited()
    assert repository.links == []
    assert FakeArtifact.created[0].status == "pending"


@pytest.mark.asyncio
async def test_reclaimed_owner_cannot_overwrite_completed_output_or_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FencedRaceArtifact)
    old_started = asyncio.Event()
    release_old = asyncio.Event()
    generation_calls = 0
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    current_time = [now]

    async def generate(request: object) -> FencedRaceArtifact:
        nonlocal generation_calls
        generation_calls += 1
        artifact_id = str(request.artifact_id)
        artifact = FencedRaceArtifact.records[artifact_id]._copy()
        if generation_calls == 1:
            old_started.set()
            await release_old.wait()
            artifact.output_payload = {"markdown": "old owner"}
            artifact.status = "completed"
        else:
            artifact.output_payload = {"markdown": "fresh owner"}
            artifact.status = "completed"
        before = getattr(request, "before_persist", None)
        if before is not None:
            await before(artifact)
        persist = getattr(request, "persist_artifact", None)
        if persist is None:
            await artifact.save()
        else:
            persisted = persist(artifact)
            if asyncio.iscoroutine(persisted):
                await persisted
        current = await FencedRaceArtifact.get(artifact_id)
        assert current is not None
        return current

    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generate)
    old_service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        clock=lambda: current_time[0],
        owner_token_factory=lambda: "old-owner",
        lock_store={},
    )
    fresh_service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        clock=lambda: current_time[0],
        owner_token_factory=lambda: "fresh-owner",
        lock_store={},
    )
    old_task = asyncio.create_task(
        old_service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    )
    await old_started.wait()
    current_time[0] = now + timedelta(seconds=241)
    fresh_result = await fresh_service.generate_unit(
        "study_plan:one", "foundations", ["quiz"], expected_revision=3
    )
    release_old.set()
    with pytest.raises(StudyArtifactConflict, match="generation_claim_lost"):
        await old_task

    # The stale owner must not have been able to publish after takeover; the
    # fresh owner remains reusable through the idempotent plan link.
    operation_id = _artifact_identity(
        "study_plan:one", 1, source_manifest([source]), "foundations", "quiz"
    )
    stored = FencedRaceArtifact.records[operation_id]
    assert generation_calls == 2
    assert stored.output_payload == {"markdown": "fresh owner"}
    assert len(repository.links) == 1

    reused = await fresh_service.generate_unit(
        "study_plan:one", "foundations", ["quiz"], expected_revision=3
    )
    assert reused == fresh_result
    assert generation_calls == 2


@pytest.mark.asyncio
async def test_expired_owner_cannot_publish_before_takeover_and_fresh_retry_is_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    repository = FakeRepository(
        plan=_plan(manifest=source_manifest([source])),
        syllabus=_syllabus(source),
    )
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FencedRaceArtifact)
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    current_time = [now]
    generation_calls = 0

    async def generate(request: object) -> FencedRaceArtifact:
        nonlocal generation_calls
        generation_calls += 1
        artifact_id = str(request.artifact_id)
        artifact = FencedRaceArtifact.records[artifact_id]._copy()
        if generation_calls == 1:
            # The owner token is unchanged, but its durable lease has expired
            # before the shared generator tries to publish its result.
            current_time[0] = now + timedelta(seconds=CLAIM_LEASE_SECONDS)
            artifact.output_payload = {"markdown": "expired owner"}
        else:
            artifact.output_payload = {"markdown": "fresh owner"}
        artifact.status = "completed"
        before = getattr(request, "before_persist", None)
        if before is not None:
            await before(artifact)
        persist = getattr(request, "persist_artifact", None)
        if persist is None:
            await artifact.save()
        else:
            result = persist(artifact)
            if asyncio.iscoroutine(result):
                await result
        current = await FencedRaceArtifact.get(artifact_id)
        assert current is not None
        return current

    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generate)
    stale_service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        clock=lambda: current_time[0],
        owner_token_factory=lambda: "same-owner",
        lock_store={},
    )
    fresh_service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        clock=lambda: current_time[0],
        owner_token_factory=lambda: "fresh-owner",
        lock_store={},
    )

    with pytest.raises(StudyArtifactConflict, match="generation_claim_lost"):
        await stale_service.generate_unit(
            "study_plan:one", "foundations", ["quiz"], expected_revision=3
        )

    operation_id = _artifact_identity(
        "study_plan:one", 1, source_manifest([source]), "foundations", "quiz"
    )
    stored = FencedRaceArtifact.records[operation_id]
    assert generation_calls == 1
    assert stored.status == "running"
    assert stored.output_payload == {}
    assert stored.generation_claim_owner == "same-owner"
    assert repository.links == []

    retry = await fresh_service.generate_unit(
        "study_plan:one", "foundations", ["quiz"], expected_revision=3
    )
    assert generation_calls == 2
    assert retry[0]["status"] == "completed"
    assert repository.links == [
        {
            "plan_id": "study_plan:one",
            "artifact_id": operation_id,
            "artifact_kind": "quiz",
            "metadata": {
                "unit_id": "foundations",
                "syllabus_version": 1,
                "source_manifest_sha256": source_manifest([source]),
                "expected_revision": 3,
            },
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lease_until",
    [None, "not-a-timestamp", datetime(2026, 8, 12, 12, 4)],
)
async def test_owner_fence_rejects_missing_malformed_or_naive_lease(
    monkeypatch: pytest.MonkeyPatch,
    lease_until: object,
) -> None:
    operation_id = "studio_artifact:invalid-lease"
    artifact = FencedRaceArtifact(
        id=operation_id,
        status="running",
        generation_claim_owner="worker",
        generation_claim_lease_until=lease_until,
    )
    FencedRaceArtifact.records[operation_id] = artifact
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FencedRaceArtifact)
    service = StudyArtifactService(
        clock=lambda: datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(StudyArtifactConflict, match="generation_claim_lost"):
        await service._assert_claim_owner(artifact, operation_id, "worker")


@pytest.mark.asyncio
async def test_plan_authority_drift_after_claim_aborts_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    generated = AsyncMock(side_effect=lambda request: _complete(request.artifact_id))
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generated)
    service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
    )
    original_claim = service._claim_provisional

    async def claim_then_revise(*args: object, **kwargs: object) -> tuple[object, str]:
        claimed = await original_claim(*args, **kwargs)
        repository.plan = StudyPlan.model_validate(
            repository.plan.model_dump(mode="python") | {"version": 4}
        )
        repository.syllabus = repository.syllabus.model_copy(
            update={"units": (_unit(title="Changed foundations"),)}
        )
        return claimed

    service._claim_provisional = claim_then_revise  # type: ignore[method-assign]

    with pytest.raises(StudyArtifactConflict, match="study_authority_changed"):
        await service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    generated.assert_not_awaited()
    assert repository.links == []


@pytest.mark.asyncio
async def test_plan_authority_drift_during_generation_cannot_link_stale_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    generation_started = asyncio.Event()
    release_generation = asyncio.Event()
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", FakeArtifact)

    async def generate(request: object) -> FakeArtifact:
        generation_started.set()
        await release_generation.wait()
        return _complete(request.artifact_id)

    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generate)
    service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
    )
    task = asyncio.create_task(
        service.generate_unit("study_plan:one", "foundations", ["quiz"], expected_revision=3)
    )
    await generation_started.wait()
    repository.plan = StudyPlan.model_validate(
        repository.plan.model_dump(mode="python") | {"state": "editing"}
    )
    release_generation.set()

    with pytest.raises(StudyArtifactConflict, match="study_authority_changed"):
        await task
    assert repository.links == []


@pytest.mark.asyncio
async def test_expired_running_claim_is_reclaimed_with_bounded_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", LeasedArtifact)
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    stale = LeasedArtifact(
        id="studio_artifact:stale",
        artifact_type="quiz",
        source_ids=["source:one"],
        status="running",
        generation_claim_owner="dead-worker",
        generation_claim_started_at=now - timedelta(seconds=300),
        generation_claim_lease_until=now - timedelta(seconds=1),
    )
    service = StudyArtifactService(
        repository=object(),
        source_service=object(),
        clock=lambda: now,
        owner_token_factory=lambda: "new-owner",
    )

    claimed, owner = await service._claim_provisional(
        stale,
        stale.id,
        "quiz",
        ("source:one",),
    )

    assert claimed is stale
    assert owner == "new-owner"
    assert stale.status == "running"
    assert stale.generation_claim_owner == "new-owner"
    assert stale.generation_claim_lease_until == now + timedelta(seconds=240)


@pytest.mark.asyncio
async def test_two_independent_expired_claimers_converge_on_one_owner() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    operation_id = "studio_artifact:stale-race"
    artifact = PersistentRaceArtifact(
        id=operation_id,
        artifact_type="quiz",
        source_ids=["source:one"],
        status="running",
        generation_claim_owner="dead-worker",
        generation_claim_started_at=now - timedelta(seconds=300),
        generation_claim_lease_until=now - timedelta(seconds=1),
    )
    PersistentRaceArtifact.records[operation_id] = artifact
    first_service = StudyArtifactService(
        repository=object(),
        source_service=object(),
        clock=lambda: now,
        owner_token_factory=lambda: "worker-one",
    )
    second_service = StudyArtifactService(
        repository=object(),
        source_service=object(),
        clock=lambda: now,
        owner_token_factory=lambda: "worker-two",
    )

    async def claim(service: StudyArtifactService) -> object:
        current = await PersistentRaceArtifact.get(operation_id)
        assert current is not None
        return await service._claim_provisional(current, operation_id, "quiz", ("source:one",))

    results = await asyncio.gather(claim(first_service), claim(second_service), return_exceptions=True)

    assert sum(isinstance(result, StudyArtifactConflict) for result in results) == 1
    successes = [result for result in results if isinstance(result, tuple)]
    assert len(successes) == 1
    assert artifact.generation_claim_owner in {"worker-one", "worker-two"}


@pytest.mark.asyncio
async def test_expired_claim_retry_generates_and_links_once(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source()
    repository = FakeRepository(plan=_plan(manifest=source_manifest([source])), syllabus=_syllabus(source))
    operation_id = _artifact_identity(
        "study_plan:one", 1, source_manifest([source]), "foundations", "quiz"
    )
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    stale = PersistentRaceArtifact(
        id=operation_id,
        artifact_type="quiz",
        source_ids=["source:one"],
        status="running",
        generation_claim_owner="dead-worker",
        generation_claim_started_at=now - timedelta(seconds=300),
        generation_claim_lease_until=now - timedelta(seconds=1),
    )
    PersistentRaceArtifact.records[operation_id] = stale
    generated = AsyncMock()

    async def complete(request: object) -> PersistentRaceArtifact:
        artifact = PersistentRaceArtifact.records[str(request.artifact_id)]
        artifact.status = "completed"
        artifact.output_payload = {"markdown": "completed"}
        return artifact

    generated.side_effect = complete
    monkeypatch.setattr("deeper_notebook.study.artifact_service.StudioArtifact", PersistentRaceArtifact)
    monkeypatch.setattr("deeper_notebook.study.artifact_service.generate_artifact", generated)
    service = StudyArtifactService(
        repository=repository,
        source_service=FakeSourceService(source),
        source_loader=lambda _: source,
        clock=lambda: now,
        owner_token_factory=lambda: "retry-owner",
    )

    result = await service.generate_unit(
        "study_plan:one", "foundations", ["quiz"], expected_revision=3
    )

    assert result[0]["artifact_id"] == operation_id
    assert generated.await_count == 1
    assert len(repository.links) == 1
    assert stale.status == "completed"
    assert stale.generation_claim_owner is None


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
