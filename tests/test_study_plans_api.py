"""HTTP-contract tests for the feature-gated Study Plan workbench API."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import study_plans
from api.schemas.study_plans import ProposeSyllabusRequest
from deeper_notebook.study import source_service
from deeper_notebook.study.artifact_service import (
    StudyArtifactConflict,
    StudyArtifactGenerationError,
)
from deeper_notebook.study.plan_repository import (
    StudyPlanConflictError,
    StudyPlanNotFoundError,
    StudyPlanRepositoryError,
)
from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanPreferences,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)
from deeper_notebook.study.syllabus_service import (
    StudySyllabusConflict,
    StudySyllabusMalformedOutput,
    StudySyllabusTimeout,
)


def _plan(
    *,
    plan_id: str = "study_plan:one",
    version: int = 1,
    state: str = "draft",
    source_links: tuple[StudyPlanSourceLink, ...] = (),
    approved_syllabus_version: int | None = None,
) -> StudyPlan:
    values: dict[str, Any] = {
        "plan_id": plan_id,
        "goal": "Learn mechanics",
        "starting_level": "Beginner",
        "source_links": source_links,
        "version": version,
        "state": state,
        "created_at": datetime(2026, 8, 12, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 12, tzinfo=UTC),
    }
    if approved_syllabus_version is not None:
        values.update(
            source_manifest_sha256="a" * 64,
            approved_syllabus_version=approved_syllabus_version,
        )
    return StudyPlan.model_validate(values)


def _syllabus(*, plan_id: str = "study_plan:one", version: int = 1) -> StudySyllabus:
    return StudySyllabus(
        plan_id=plan_id,
        version=version,
        source_manifest_sha256="a" * 64,
        units=(
            StudySyllabusUnit(
                unit_id="motion",
                title="Motion",
                objectives=("Explain velocity",),
                estimated_minutes=30,
            ),
        ),
    )


class FakeRepository:
    def __init__(self) -> None:
        self.plans: dict[str, StudyPlan] = {"study_plan:one": _plan()}
        self.syllabi: dict[tuple[str, int], StudySyllabus] = {
            ("study_plan:one", 1): _syllabus()
        }
        self.last_get: str | None = None
        self.calls = 0

    async def create(self, plan: StudyPlan) -> StudyPlan:
        self.calls += 1
        self.plans[plan.plan_id] = plan
        return plan

    async def list(self, *, limit: int, offset: int) -> list[StudyPlan]:
        self.calls += 1
        return list(self.plans.values())[offset : offset + limit]

    async def get(self, plan_id: str) -> StudyPlan | None:
        self.calls += 1
        self.last_get = plan_id
        return self.plans.get(plan_id)

    async def update(
        self, plan_id: str, changes: dict[str, Any], *, expected_revision: int
    ) -> StudyPlan:
        self.calls += 1
        current = self.plans.get(plan_id)
        if current is None:
            raise StudyPlanNotFoundError("study plan not found")
        if current.version != expected_revision:
            raise StudyPlanConflictError("study plan revision conflict")
        updated = StudyPlan.model_validate(
            current.model_dump() | changes | {"version": current.version + 1}
        )
        self.plans[plan_id] = updated
        return updated

    async def add_source(
        self, plan_id: str, source_id: str, *, expected_revision: int
    ) -> StudyPlanSourceLink:
        self.calls += 1
        current = self.plans.get(plan_id)
        if current is None or current.version != expected_revision:
            raise StudyPlanConflictError("study plan revision conflict")
        link = StudyPlanSourceLink(source_id=source_id)
        self.plans[plan_id] = StudyPlan.model_validate(
            current.model_dump()
            | {
                "source_links": current.source_links + (link,),
                "state": "analyzing_sources" if current.state == "draft" else current.state,
                "version": current.version + 1,
            }
        )
        return link

    async def remove_source(
        self, plan_id: str, source_id: str, *, expected_revision: int
    ) -> bool:
        self.calls += 1
        current = self.plans.get(plan_id)
        if current is None or current.version != expected_revision:
            raise StudyPlanConflictError("study plan revision conflict")
        links = tuple(link for link in current.source_links if link.source_id != source_id)
        removed = len(links) != len(current.source_links)
        if removed:
            self.plans[plan_id] = StudyPlan.model_validate(
                current.model_dump() | {"source_links": links, "version": current.version + 1}
            )
        return removed

    async def get_syllabus(self, plan_id: str, *, version: int | None = None) -> StudySyllabus | None:
        self.calls += 1
        if version is None:
            versions = [key[1] for key in self.syllabi if key[0] == plan_id]
            version = max(versions) if versions else None
        return self.syllabi.get((plan_id, version)) if version is not None else None

    async def save_syllabus(
        self,
        syllabus: StudySyllabus,
        *,
        expected_revision: int,
        lifecycle_action: str | None = None,
    ) -> StudySyllabus:
        self.calls += 1
        current = self.plans.get(syllabus.plan_id)
        if current is None or current.version != expected_revision:
            raise StudyPlanConflictError("study plan revision conflict")
        if lifecycle_action == "propose" and current.state != "analyzing_sources":
            raise StudyPlanConflictError("study plan lifecycle conflict")
        if lifecycle_action == "edit" and current.state not in {"syllabus_proposed", "editing"}:
            raise StudyPlanConflictError("study plan lifecycle conflict")
        self.syllabi[(syllabus.plan_id, syllabus.version)] = syllabus
        if lifecycle_action == "propose":
            self.plans[syllabus.plan_id] = StudyPlan.model_validate(
                current.model_dump()
                | {"state": "syllabus_proposed", "version": current.version + 1}
            )
        elif lifecycle_action == "edit":
            self.plans[syllabus.plan_id] = StudyPlan.model_validate(
                current.model_dump()
                | {"state": "editing", "version": current.version + 1}
            )
        return syllabus

    async def approve_syllabus(
        self, plan_id: str, *, syllabus_version: int, expected_revision: int
    ) -> StudyPlan:
        self.calls += 1
        current = self.plans.get(plan_id)
        syllabus = self.syllabi.get((plan_id, syllabus_version))
        if current is None or current.version != expected_revision or syllabus is None:
            raise StudyPlanConflictError("study plan revision conflict")
        approved = StudyPlan.model_validate(
            current.model_dump()
            | {
                "state": "approved",
                "source_manifest_sha256": syllabus.source_manifest_sha256,
                "approved_syllabus_version": syllabus_version,
                "version": current.version + 1,
            }
        )
        self.plans[plan_id] = approved
        return approved


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, repository: FakeRepository) -> TestClient:
    monkeypatch.setattr(study_plans, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_plans, "_repository", lambda: repository)
    # These route-contract tests use an in-memory plan repository.  Keep the
    # production source-authority validation enabled, while making the
    # explicit seam deterministic so happy-path link requests can reach the
    # fake repository instead of opening the local database.
    monkeypatch.setattr(
        study_plans.StudySourceService,
        "validate_source",
        AsyncMock(return_value=SimpleNamespace(id="source:one")),
    )
    app = FastAPI()
    app.include_router(study_plans.router, prefix="/api")
    return TestClient(app)


def test_create_plan_projects_only_public_fields_and_forbids_unknown_fields(client: TestClient) -> None:
    invalid = client.post(
        "/api/study/plans",
        json={"goal": "Learn mechanics", "starting_level": "Beginner", "unexpected": True},
    )
    created = client.post(
        "/api/study/plans",
        json={"goal": "Learn mechanics", "starting_level": "Beginner"},
    )

    assert invalid.status_code == 422
    assert created.status_code == 201
    assert created.json()["plan_id"].startswith("study_plan:")
    assert "schema_version" not in created.json()


def test_list_caps_pagination_and_get_decodes_encoded_colon_id(
    client: TestClient, repository: FakeRepository
) -> None:
    listed = client.get("/api/study/plans?limit=500&offset=0")
    fetched = client.get("/api/study/plans/study_plan%3Aone")

    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == "study_plan:one"
    assert repository.last_get == "study_plan:one"


def test_get_missing_or_invalid_plan_is_non_disclosing_404(client: TestClient) -> None:
    missing = client.get("/api/study/plans/study_plan%3Amissing")
    invalid = client.get("/api/study/plans/not-a-plan")

    assert missing.status_code == invalid.status_code == 404
    assert missing.json() == invalid.json() == {"detail": "Study plan not found"}


def test_patch_requires_strict_payload_and_exact_revision(client: TestClient) -> None:
    invalid = client.patch(
        "/api/study/plans/study_plan%3Aone",
        json={"expected_revision": 1, "goal": "Updated", "state": "approved"},
    )
    stale = client.patch(
        "/api/study/plans/study_plan%3Aone",
        json={"expected_revision": 7, "goal": "Updated"},
    )
    updated = client.patch(
        "/api/study/plans/study_plan%3Aone",
        json={"expected_revision": 1, "goal": "Updated"},
    )

    assert invalid.status_code == 422
    assert stale.status_code == 409
    assert updated.status_code == 200
    assert updated.json()["goal"] == "Updated"
    assert updated.json()["version"] == 2


def test_source_links_require_exact_revision_and_only_project_source_id(client: TestClient) -> None:
    stale = client.post(
        "/api/study/plans/study_plan%3Aone/sources",
        json={"source_id": "source:one", "expected_revision": 7},
    )
    added = client.post(
        "/api/study/plans/study_plan%3Aone/sources",
        json={"source_id": "source:one", "expected_revision": 1},
    )
    removed = client.request(
        "DELETE",
        "/api/study/plans/study_plan%3Aone/sources/source%3Aone",
        json={"expected_revision": 2},
    )

    assert stale.status_code == 409
    assert added.status_code == 201
    assert added.json() == {"source_id": "source:one"}
    assert removed.status_code == 200
    assert removed.json() == {"removed": True}


def test_syllabus_read_and_update_require_exact_plan_revision(
    client: TestClient, repository: FakeRepository
) -> None:
    fetched = client.get("/api/study/plans/study_plan%3Aone/syllabus?version=1")
    forbidden_schema_version = client.put(
        "/api/study/plans/study_plan%3Aone/syllabus",
        json={"expected_revision": 1, **_syllabus().model_dump(mode="json", exclude={"plan_id", "approved_at"})},
    )
    stale = client.put(
        "/api/study/plans/study_plan%3Aone/syllabus",
        json={
            "expected_revision": 7,
            **_syllabus().model_dump(
                mode="json", exclude={"plan_id", "schema_version", "approved_at"}
            ),
        },
    )
    repository.plans["study_plan:one"] = _plan(state="syllabus_proposed")
    saved = client.put(
        "/api/study/plans/study_plan%3Aone/syllabus",
        json={
            "expected_revision": 1,
            **_syllabus().model_dump(
                mode="json", exclude={"plan_id", "schema_version", "approved_at"}
            ),
        },
    )

    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == "study_plan:one"
    assert forbidden_schema_version.status_code == 422
    assert stale.status_code == 409
    assert saved.status_code == 200


def test_approve_syllabus_rejects_illegal_lifecycle_and_stale_revision(
    client: TestClient, repository: FakeRepository
) -> None:
    illegal = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:approve",
        json={"syllabus_version": 1, "expected_revision": 1},
    )
    repository.plans["study_plan:one"] = _plan(
        state="editing", source_links=(StudyPlanSourceLink(source_id="source:one"),)
    )
    stale = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:approve",
        json={"syllabus_version": 1, "expected_revision": 7},
    )

    assert illegal.status_code == 409
    assert stale.status_code == 409


def test_feature_off_returns_404_before_constructing_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(study_plans.router, prefix="/api")
    calls = 0

    def forbidden_repository() -> FakeRepository:
        nonlocal calls
        calls += 1
        raise AssertionError("feature-off request touched the repository")

    monkeypatch.setattr(study_plans, "study_workbench_enabled", lambda: False)
    monkeypatch.setattr(study_plans, "_repository", forbidden_repository)

    with TestClient(app) as client:
        responses = [
            client.get("/api/study/plans?limit=not-an-integer"),
            client.post("/api/study/plans", json={"goal": 7}),
            client.get("/api/study/plans/not-a-plan"),
            client.patch("/api/study/plans/not-a-plan", json={"expected_revision": 0}),
            client.post(
                "/api/study/plans/not-a-plan/sources",
                json={"source_id": "   ", "expected_revision": "wrong"},
            ),
            client.request(
                "DELETE",
                "/api/study/plans/not-a-plan/sources/not-a-source",
                json={"expected_revision": 0},
            ),
            client.get("/api/study/plans/not-a-plan/syllabus?version=wrong"),
            client.put("/api/study/plans/not-a-plan/syllabus", json={}),
            client.post("/api/study/plans/not-a-plan/syllabus:approve", json={}),
            client.post("/api/study/plans/not-a-plan/generate", json={}),
        ]

    assert {response.status_code for response in responses} == {404}
    assert calls == 0


def test_unit_artifact_generation_returns_metadata_only_and_rejects_bad_request(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Service:
        async def generate_unit(
            self,
            plan_id: str,
            unit_id: str,
            artifact_types: tuple[str, ...],
            expected_revision: int,
            *,
            context: str | None,
        ) -> list[dict[str, str]]:
            assert (plan_id, unit_id, artifact_types, expected_revision, context) == (
                "study_plan:one",
                "motion",
                ("quiz",),
                3,
                None,
            )
            return [
                {
                    "artifact_id": "studio_artifact:quiz",
                    "artifact_type": "quiz",
                    "status": "completed",
                    "unit_id": "motion",
                }
            ]

    monkeypatch.setattr(study_plans, "StudyArtifactService", Service)
    response = client.post(
        "/api/study/plans/study_plan%3Aone/generate",
        json={"unit_id": "motion", "artifact_types": ["quiz"], "expected_revision": 3},
    )
    malformed = client.post(
        "/api/study/plans/study_plan%3Aone/generate",
        json={"unit_id": "motion", "artifact_types": ["report"], "expected_revision": 3},
    )

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": "study_plan:one",
        "unit_id": "motion",
        "artifacts": [
            {
                "artifact_id": "studio_artifact:quiz",
                "artifact_type": "quiz",
                "status": "completed",
                "unit_id": "motion",
            }
        ],
    }
    assert "output_payload" not in response.text
    assert malformed.status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (StudyArtifactConflict("sources_changed"), 409),
        (StudyArtifactGenerationError("provider password=secret"), 503),
    ],
)
def test_unit_artifact_domain_errors_are_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    class Service:
        async def generate_unit(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
            del args, kwargs
            raise error

    monkeypatch.setattr(study_plans, "StudyArtifactService", Service)
    response = client.post(
        "/api/study/plans/study_plan%3Aone/generate",
        json={"unit_id": "motion", "artifact_types": ["quiz"], "expected_revision": 1},
    )

    assert response.status_code == status_code
    assert "password=secret" not in response.text


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/api/study/plans", {"goal": "   ", "starting_level": "Beginner"}),
        ("POST", "/api/study/plans", {"goal": "Learn", "starting_level": "\t"}),
        (
            "PATCH",
            "/api/study/plans/study_plan%3Aone",
            {"expected_revision": 1, "goal": "  "},
        ),
        (
            "PATCH",
            "/api/study/plans/study_plan%3Aone",
            {"expected_revision": 1, "goal": None},
        ),
        (
            "PATCH",
            "/api/study/plans/study_plan%3Aone",
            {"expected_revision": 1, "starting_level": None},
        ),
        (
            "PATCH",
            "/api/study/plans/study_plan%3Aone",
            {"expected_revision": 1, "preferences": None},
        ),
        (
            "POST",
            "/api/study/plans/study_plan%3Aone/sources",
            {"source_id": " \n ", "expected_revision": 1},
        ),
    ],
)
def test_invalid_text_and_explicit_null_updates_fail_before_repository(
    client: TestClient,
    repository: FakeRepository,
    method: str,
    path: str,
    payload: dict[str, object],
) -> None:
    calls_before = repository.calls

    response = client.request(method, path, json=payload)

    assert response.status_code == 422
    assert repository.calls == calls_before


def test_patch_allows_explicit_null_target_date_to_clear_it(client: TestClient) -> None:
    response = client.patch(
        "/api/study/plans/study_plan%3Aone",
        json={"expected_revision": 1, "target_date": None},
    )

    assert response.status_code == 200
    assert response.json()["target_date"] is None


def test_syllabus_nested_text_is_strictly_nonblank_before_repository(
    client: TestClient, repository: FakeRepository
) -> None:
    payload = {
        "expected_revision": 1,
        **_syllabus().model_dump(
            mode="json", exclude={"plan_id", "schema_version", "approved_at"}
        ),
    }
    payload["units"][0]["title"] = "   "
    calls_before = repository.calls

    response = client.put("/api/study/plans/study_plan%3Aone/syllabus", json=payload)

    assert response.status_code == 422
    assert repository.calls == calls_before


def test_repository_failure_returns_generic_safe_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingRepository:
        async def list(self, *, limit: int, offset: int) -> list[StudyPlan]:
            raise StudyPlanRepositoryError("driver password=do-not-disclose")

    monkeypatch.setattr(study_plans, "_repository", FailingRepository)

    response = client.get("/api/study/plans")

    assert response.status_code == 503
    assert response.json() == {"detail": "Study plans are unavailable"}


@pytest.mark.parametrize("operation", ["add_source", "save_syllabus"])
def test_conflict_like_driver_failures_remain_safe_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    class FailingRepository(FakeRepository):
        async def add_source(
            self, plan_id: str, source_id: str, *, expected_revision: int
        ) -> StudyPlanSourceLink:
            raise StudyPlanRepositoryError(
                "Study source link already exists or plan is unavailable"
            )

        async def save_syllabus(
            self,
            syllabus: StudySyllabus,
            *,
            expected_revision: int,
            lifecycle_action: str | None = None,
        ) -> StudySyllabus:
            del lifecycle_action
            raise StudyPlanRepositoryError(
                "study syllabus version already exists or is unavailable"
            )

    monkeypatch.setattr(study_plans, "_repository", FailingRepository)
    if operation == "add_source":
        response = client.post(
            "/api/study/plans/study_plan%3Aone/sources",
            json={"source_id": "source:one", "expected_revision": 1},
        )
    else:
        response = client.put(
            "/api/study/plans/study_plan%3Aone/syllabus",
            json={
                "expected_revision": 1,
                **_syllabus().model_dump(
                    mode="json", exclude={"plan_id", "schema_version", "approved_at"}
                ),
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Study plans are unavailable"}


def test_readiness_with_legacy_wrong_table_link_returns_safe_bounded_items(
    client: TestClient,
    repository: FakeRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository.plans["study_plan:one"] = _plan(
        source_links=(
            StudyPlanSourceLink(source_id="note:legacy"),
            StudyPlanSourceLink(source_id="source:one"),
        )
    )
    query = AsyncMock(
        return_value=[
            {
                "id": "source:one",
                "title": "Valid source",
                "source_type": "text",
                "command": None,
                "has_text": True,
                "text_length": 12,
                "fingerprint": None,
                "content_fingerprint": None,
                "source_fingerprint": None,
            }
        ]
    )
    monkeypatch.setattr(source_service, "repo_query", query)

    response = client.get(
        "/api/study/plans/study_plan%3Aone/sources/readiness"
    )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["items"] == [
        {
            "source_id": "note:legacy",
            "title": "Source unavailable",
            "kind": "text",
            "ready": False,
            "command_id": None,
            "fingerprint_status": "unknown",
            "reason": "missing",
        },
        {
            "source_id": "source:one",
            "title": "Valid source",
            "kind": "text",
            "ready": True,
            "command_id": None,
            "fingerprint_status": "unknown",
            "reason": "ready",
        },
    ]
    query.assert_awaited_once()


def test_propose_syllabus_returns_typed_version_without_approval(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Service:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def propose(self, plan_id: str, *, expected_revision: int) -> StudySyllabus:
            assert plan_id == "study_plan:one"
            assert expected_revision == 1
            return _syllabus()

    monkeypatch.setattr(study_plans, "StudySyllabusService", Service)
    response = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:propose",
        json={"expected_revision": 1},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert response.json()["approved_at"] is None


def test_manifestless_api_plan_can_complete_explicit_syllabus_lifecycle(
    client: TestClient,
    repository: FakeRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LifecycleService:
        def __init__(self, *, repository: FakeRepository) -> None:
            self.repository = repository

        async def propose(self, plan_id: str, *, expected_revision: int) -> StudySyllabus:
            syllabus = _syllabus(plan_id=plan_id, version=2)
            return await self.repository.save_syllabus(
                syllabus,
                expected_revision=expected_revision,
                lifecycle_action="propose",
            )

        async def approve(
            self,
            plan_id: str,
            *,
            syllabus_version: int,
            expected_revision: int,
        ) -> StudyPlan:
            return await self.repository.approve_syllabus(
                plan_id,
                syllabus_version=syllabus_version,
                expected_revision=expected_revision,
            )

    monkeypatch.setattr(study_plans, "StudySyllabusService", LifecycleService)
    assert repository.plans["study_plan:one"].source_manifest_sha256 is None

    linked = client.post(
        "/api/study/plans/study_plan%3Aone/sources",
        json={"source_id": "source:one", "expected_revision": 1},
    )
    proposed = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:propose",
        json={"expected_revision": 2},
    )
    edited = client.put(
        "/api/study/plans/study_plan%3Aone/syllabus",
        json={
            "expected_revision": 3,
            **_syllabus(version=3).model_dump(
                mode="json", exclude={"plan_id", "schema_version", "approved_at"}
            ),
        },
    )
    approved = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:approve",
        json={"syllabus_version": 3, "expected_revision": 4},
    )

    assert linked.status_code == 201
    assert proposed.status_code == 200
    assert edited.status_code == 200
    assert approved.status_code == 200
    final = repository.plans["study_plan:one"]
    assert final.state == "approved"
    assert final.version == 5
    assert final.approved_syllabus_version == 3
    assert final.source_manifest_sha256 == "a" * 64

    stale = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:approve",
        json={"syllabus_version": 3, "expected_revision": 4},
    )
    assert stale.status_code == 409
    assert repository.plans["study_plan:one"] == final


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (StudySyllabusConflict("sources_changed"), 409),
        (StudySyllabusMalformedOutput("malformed_output"), 422),
        (StudySyllabusTimeout("generation_timeout"), 503),
    ],
)
def test_syllabus_domain_errors_are_safe_and_typed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    class Service:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def propose(self, plan_id: str, *, expected_revision: int) -> StudySyllabus:
            del plan_id, expected_revision
            raise error

    monkeypatch.setattr(study_plans, "StudySyllabusService", Service)
    response = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:propose",
        json={"expected_revision": 1},
    )

    assert response.status_code == status_code
    assert "sources_changed" not in response.text or status_code == 409
    assert "raw" not in response.text
