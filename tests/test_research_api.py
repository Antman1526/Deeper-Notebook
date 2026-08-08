"""API contracts for approval-first, notebook-owned Research Runs."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import research as research_router
from deeper_notebook.research.state import ResearchCandidate, ResearchRun
from deeper_notebook.security.outbound_url import OutboundURLPolicyError
from deeper_notebook.tools.web_evidence import normalize_web_results


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

    async def fake_search_with_evidence(query: str, *, max_results: int):
        return normalize_web_results(
            [
                {
                    "url": "https://Example.com/a#ignored",
                    "title": "One",
                    "snippet": "First",
                },
                {
                    "url": "https://example.com/a",
                    "title": "Duplicate",
                    "snippet": "x",
                },
                {
                    "url": "file:///etc/passwd",
                    "title": "Unsafe",
                    "snippet": "x",
                },
            ],
            query=query,
            provider="tavily",
            degraded=True,
            max_results=max_results,
        )

    monkeypatch.setattr(
        "deeper_notebook.research.discovery.web_search_enabled", lambda: True
    )
    monkeypatch.setattr(
        "deeper_notebook.research.discovery.run_web_search_with_evidence",
        fake_search_with_evidence,
    )
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
            "evidence": {
                "query": "secure research",
                "provider": "tavily",
                "title": "One",
                "url": "https://example.com/a",
                "snippet": "First",
                "retrieved_at": body["candidates"][0]["evidence"]["retrieved_at"],
                "freshness": "fresh",
                "degraded": True,
                "source_fingerprint": body["candidates"][0]["evidence"][
                    "source_fingerprint"
                ],
                "evidence_id": body["candidates"][0]["evidence"]["evidence_id"],
            },
        }
    ]

    evidence = body["candidates"][0]["evidence"]
    assert evidence["provider"] == "tavily"
    assert len(evidence["source_fingerprint"]) == 64
    assert len(evidence["evidence_id"]) == 64
    assert evidence["freshness"] == "fresh"
    assert evidence["degraded"] is True


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

    async def source_get(source_id: str):
        assert source_id == "source:one"
        return SimpleNamespace(
            id=source_id,
            full_text="The archive retains audit receipts.",
        )

    monkeypatch.setattr(research_router, "validate_outbound_url", validated)
    monkeypatch.setattr(research_router, "ingest_approved_sources", imported)
    monkeypatch.setattr("deeper_notebook.research.analysis.Source.get", source_get)
    with _client(monkeypatch, store) as client:
        response = client.post(
            "/api/notebooks/notebook:one/research-runs/research_run:one/approve",
            json={"accepted_candidate_ids": ["candidate:ok"]},
        )

    assert response.status_code == 200
    assert response.json()["stage"] == "complete"
    assert store.run is not None
    assert store.run.approval_decisions == {"candidate:ok": True}
    assert store.run.source_ids == ["source:one"]
    assert store.run.checkpoints["validate"]["comparison"]["verdicts"]


def test_approve_with_evidence_still_requires_outbound_url_validation(monkeypatch) -> None:
    evidence = normalize_web_results(
        [{"title": "T", "url": "https://example.com/a", "snippet": "S"}],
        query="q",
        provider="tavily",
    )[0]
    candidate = ResearchCandidate(
        candidate_id="candidate:unsafe",
        url="https://example.com/a",
        evidence=evidence,
    )
    store = MemoryRepository(
        ResearchRun(
            id="research_run:one",
            notebook_id="notebook:one",
            objective="Reject unsafe source",
            stage="await_source_approval",
            candidates=[candidate],
        )
    )

    async def blocked(url: str):
        raise OutboundURLPolicyError("blocked")

    monkeypatch.setattr(research_router, "validate_outbound_url", blocked)
    with _client(monkeypatch, store) as client:
        response = client.post(
            "/api/notebooks/notebook:one/research-runs/research_run:one/approve",
            json={"accepted_candidate_ids": ["candidate:unsafe"]},
        )

    assert response.status_code == 409
    assert store.run.approval_decisions == {}


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
