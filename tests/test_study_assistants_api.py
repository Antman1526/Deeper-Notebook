from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import study_assistants
from deeper_notebook.study.assistants import StudyAssistantResponse


class FakeService:
    async def invoke(self, plan_id, role, invocation):
        return StudyAssistantResponse(
            invocation_id=invocation.request_id or invocation.invocation_id,
            response_id="response-one",
            session_id="study_assistant_session:one",
            plan_id=plan_id,
            role=role,
            authority=invocation.authority,
            answer="Use the selected evidence.",
            created_at=datetime(2026, 8, 12, tzinfo=UTC),
            completed_at=datetime(2026, 8, 12, tzinfo=UTC),
        )


def client(monkeypatch, *, enabled: bool = True) -> TestClient:
    monkeypatch.setattr(study_assistants, "study_workbench_enabled", lambda: enabled)
    monkeypatch.setattr(study_assistants, "_service", lambda: FakeService())
    app = FastAPI()
    app.include_router(study_assistants.router, prefix="/api")
    return TestClient(app)


def payload() -> dict[str, object]:
    return {
        "authority": "ask",
        "prompt": "Explain this source",
        "unit_id": "unit-one",
        "selected_source_ids": ["source:allowed"],
        "model_route": "local",
        "network_allowed": False,
        "approved_network_scope": [],
        "timeout_seconds": 30,
        "request_id": "assistant-request",
        "created_at": "2026-08-12T00:00:00Z",
    }


def test_invocation_route_is_additive_and_strict(monkeypatch) -> None:
    response = client(monkeypatch).post(
        "/api/study/plans/study_plan:one/assistants/source_guide:invoke",
        json=payload(),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "source_guide"
    assert response.json()["invocation_id"] == "assistant-request"
    bad = payload() | {"provider_payload": "secret"}
    assert (
        client(monkeypatch)
        .post(
            "/api/study/plans/study_plan:one/assistants/source_guide:invoke", json=bad
        )
        .status_code
        == 422
    )


def test_feature_off_is_uniform_404_before_validation(monkeypatch) -> None:
    response = client(monkeypatch, enabled=False).post(
        "/api/study/plans/study_plan:one/assistants/source_guide:invoke",
        json={"bad": "payload"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Study plan not found"}


def test_policy_failure_is_safe(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise study_assistants.StudyAssistantPolicyError("network_not_approved")

    fake = FakeService()
    fake.invoke = fail
    monkeypatch.setattr(study_assistants, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_assistants, "_service", lambda: fake)
    app = FastAPI()
    app.include_router(study_assistants.router, prefix="/api")
    response = TestClient(app).post(
        "/api/study/plans/study_plan:one/assistants/research_scout:invoke",
        json=payload(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "network_not_approved"
    assert "secret" not in response.text.lower()


def test_changed_body_request_id_is_reported_as_conflict(monkeypatch) -> None:
    async def fail(*_args, **_kwargs):
        raise study_assistants.StudyAssistantPolicyError(
            "assistant_request_conflict"
        )

    fake = FakeService()
    fake.invoke = fail
    monkeypatch.setattr(study_assistants, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_assistants, "_service", lambda: fake)
    app = FastAPI()
    app.include_router(study_assistants.router, prefix="/api")
    response = TestClient(app).post(
        "/api/study/plans/study_plan:one/assistants/source_guide:invoke",
        json=payload() | {"request_id": "already-used"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assistant_request_conflict"


def test_domain_conversion_failures_are_stable_422s(monkeypatch) -> None:
    api = client(monkeypatch)
    malformed_plan = api.post(
        "/api/study/plans/not-a-plan/assistants/source_guide:invoke",
        json=payload(),
    )
    assert malformed_plan.status_code == 422
    assert malformed_plan.json()["detail"]["code"] == "invalid_assistant_request"

    malformed_scope = api.post(
        "/api/study/plans/study_plan:one/assistants/research_scout:invoke",
        json=payload()
        | {
            "network_allowed": True,
            "approved_network_scope": ["https://example.edu/", "https://example.edu/"],
        },
    )
    assert malformed_scope.status_code == 422
    assert malformed_scope.json()["detail"]["code"] == "invalid_assistant_request"

    naive_time = api.post(
        "/api/study/plans/study_plan:one/assistants/source_guide:invoke",
        json=payload() | {"created_at": "2026-08-12T00:00:00"},
    )
    assert naive_time.status_code == 422
    assert naive_time.json()["detail"]["code"] == "invalid_assistant_request"
