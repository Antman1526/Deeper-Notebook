"""API contracts for approval-first, notebook-owned Research Runs."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import research as research_router
from open_notebook.research.state import ResearchCandidate, ResearchRun


@dataclass
class MemoryRepository:
    run: ResearchRun | None = None

    async def create(self, run: ResearchRun) -> ResearchRun:
        self.run = run.model_copy(update={"id": "research_run:one"})
        return self.run

    async def get(self, run_id: str) -> ResearchRun | None:
        return self.run if self.run and self.run.id == run_id else None

    async def save_stage_result(self, run, stage, result):
        self.run = run.with_stage_result(stage, result)
        return self.run

    async def save_approval_decisions(self, run, decisions):
        self.run = run.with_approval_decisions(decisions)
        return self.run

    async def request_cancellation(self, run_id: str):
        if self.run is None or self.run.id != run_id:
            return None
        self.run = self.run.model_copy(update={"cancelled": True})
        return self.run

    async def set_command_id(self, run_id, command_id):
        assert self.run is not None
        self.run = self.run.model_copy(update={"command_id": command_id})
        return self.run


class _Notebook:
    id = "notebook:one"


def _client(monkeypatch, store: MemoryRepository) -> TestClient:
    async def get_notebook(notebook_id: str):
        return _Notebook() if notebook_id == "notebook:one" else None

    monkeypatch.setattr(research_router.Notebook, "get", get_notebook)
    monkeypatch.setattr(research_router, "_repository", lambda: store)
    app = FastAPI()
    app.include_router(research_router.router, prefix="/api")
    return TestClient(app)


def test_create_discovers_normalized_candidates_then_pauses(monkeypatch) -> None:
    store = MemoryRepository()

    async def fake_search(query: str, *, max_results: int):
        return [
            {
                "url": "https://Example.com/a#ignored",
                "title": "One",
                "snippet": "First",
            },
            {"url": "https://example.com/a", "title": "Duplicate", "snippet": "x"},
            {"url": "file:///etc/passwd", "title": "Unsafe", "snippet": "x"},
        ]

    monkeypatch.setattr(
        "open_notebook.research.discovery.web_search_enabled", lambda: True
    )
    monkeypatch.setattr("open_notebook.research.discovery.run_web_search", fake_search)
    with _client(monkeypatch, store) as client:
        response = client.post(
            "/api/notebooks/notebook:one/research-runs",
            json={"objective": "Compare sources", "query": "secure research"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["stage"] == "await_source_approval"
    assert body["candidates"] == [
        {
            "candidate_id": body["candidates"][0]["candidate_id"],
            "url": "https://example.com/a",
            "title": "One",
            "domain": "example.com",
            "snippet": "First",
            "search_query": "secure research",
            "decision": "pending",
        }
    ]


def test_approve_records_rejected_candidates_before_resume(monkeypatch) -> None:
    candidate = ResearchCandidate(
        candidate_id="candidate:ok", url="https://example.com/a"
    )
    store = MemoryRepository(
        ResearchRun(
            id="research_run:one",
            notebook_id="notebook:one",
            objective="Compare sources",
            stage="await_source_approval",
            candidates=[candidate],
        )
    )

    async def validated(url: str):
        return object()

    async def imported(run: ResearchRun):
        return research_router.ResearchStageResult(source_ids=["source:one"])

    monkeypatch.setattr(research_router, "validate_outbound_url", validated)
    monkeypatch.setattr(research_router, "ingest_approved_sources", imported)
    with _client(monkeypatch, store) as client:
        response = client.post(
            "/api/notebooks/notebook:one/research-runs/research_run:one/approve",
            json={"accepted_candidate_ids": ["candidate:ok"]},
        )

    assert response.status_code == 200
    assert response.json()["stage"] == "extract"
    assert store.run is not None
    assert store.run.approval_decisions == {"candidate:ok": True}
    assert store.run.source_ids == ["source:one"]


def test_rejects_cross_notebook_access_and_streams_current_status(monkeypatch) -> None:
    store = MemoryRepository(
        ResearchRun(
            id="research_run:one",
            notebook_id="notebook:other",
            objective="Private run",
        )
    )
    with _client(monkeypatch, store) as client:
        missing = client.get(
            "/api/notebooks/notebook:one/research-runs/research_run:one"
        )
        events = client.get(
            "/api/notebooks/notebook:other/research-runs/research_run:one/events"
        )

    assert missing.status_code == 404
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in events.text


def test_cancel_is_durable_and_resume_does_not_restart_it(monkeypatch) -> None:
    store = MemoryRepository(
        ResearchRun(
            id="research_run:one",
            notebook_id="notebook:one",
            objective="Stop work",
            stage="discover",
        )
    )
    with _client(monkeypatch, store) as client:
        cancelled = client.post(
            "/api/notebooks/notebook:one/research-runs/research_run:one/cancel"
        )
        resumed = client.post(
            "/api/notebooks/notebook:one/research-runs/research_run:one/resume"
        )

    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] is True
    assert resumed.status_code == 200
    assert resumed.json()["cancelled"] is True
    assert resumed.json()["stage"] == "discover"
