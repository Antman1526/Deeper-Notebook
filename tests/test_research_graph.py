"""Hermetic contracts for the persisted Research Run state machine."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from open_notebook.research.graph import ResearchWorkflow
from open_notebook.research.state import (
    ResearchCandidate,
    ResearchRun,
    ResearchStageResult,
)


@dataclass
class MemoryResearchStore:
    run: ResearchRun
    saved_stages: list[str]

    async def get(self, run_id: str) -> ResearchRun | None:
        return self.run if self.run.id == run_id else None

    async def save_stage_result(self, run, stage, result):
        self.saved_stages.append(stage)
        self.run = run.with_stage_result(stage, result)
        return self.run

    async def request_cancellation(self, run_id: str):
        self.run = self.run.model_copy(update={"cancelled": True})
        return self.run

    async def set_command_id(self, run_id: str, command_id: str):
        self.run = self.run.model_copy(update={"command_id": command_id})
        return self.run


def test_stage_result_deduplicates_source_ids_and_refuses_replay() -> None:
    run = ResearchRun(id="research_run:one", objective="Compare approaches")
    first = run.with_stage_result(
        "plan",
        ResearchStageResult(source_ids=["source:a", "source:a", "source:b"]),
    )

    replayed = first.with_stage_result(
        "plan", ResearchStageResult(source_ids=["source:c"])
    )

    assert first.source_ids == ["source:a", "source:b"]
    assert replayed == first
    assert replayed.stage == "discover"


def test_approval_decisions_must_belong_to_discovered_candidates() -> None:
    run = ResearchRun(
        id="research_run:decisions",
        objective="Approve sources",
        candidates=[
            ResearchCandidate(candidate_id="candidate:one", url="https://example.test")
        ],
    )

    decided = run.with_approval_decisions({"candidate:one": True})

    assert decided.approval_decisions == {"candidate:one": True}
    with pytest.raises(ValueError, match="unknown research candidates"):
        run.with_approval_decisions({"candidate:other": True})


@pytest.mark.asyncio
async def test_resume_pauses_for_explicit_source_approval_then_continues() -> None:
    run = ResearchRun(
        id="research_run:approval",
        objective="Find trusted sources",
        stage="await_source_approval",
        candidates=[
            ResearchCandidate(candidate_id="candidate:one", url="https://example.test")
        ],
    )
    store = MemoryResearchStore(run, [])
    workflow = ResearchWorkflow(store)

    paused = await workflow.resume(run.id)
    assert paused.stage == "await_source_approval"
    assert store.saved_stages == []

    store.run = store.run.model_copy(
        update={"approval_decisions": {"candidate:one": True}}
    )
    resumed = await workflow.resume(run.id)
    assert resumed.stage == "ingest"
    assert resumed.checkpoints["await_source_approval"] == {
        "approved_candidate_ids": ["candidate:one"]
    }


@pytest.mark.asyncio
async def test_resume_uses_persisted_checkpoint_without_replaying_stage() -> None:
    run = ResearchRun(
        id="research_run:resume",
        objective="Restart safely",
        stage="discover",
        completed_stages=["plan"],
        checkpoints={"plan": {"version": 1}},
    )
    store = MemoryResearchStore(run, [])
    calls: list[str] = []

    async def discover(current: ResearchRun) -> ResearchStageResult:
        calls.append(current.stage)
        return ResearchStageResult(
            candidates=[
                ResearchCandidate(
                    candidate_id="candidate:accepted",
                    url="https://example.test/evidence",
                )
            ],
            source_ids=["source:accepted", "source:accepted"],
        )

    resumed = await ResearchWorkflow(store, {"discover": discover}).resume(run.id)

    assert calls == ["discover"]
    assert resumed.stage == "await_source_approval"
    assert resumed.source_ids == ["source:accepted"]
    assert store.saved_stages == ["discover"]


@pytest.mark.asyncio
async def test_cancelled_command_stops_before_next_stage() -> None:
    run = ResearchRun(
        id="research_run:cancelled",
        objective="Stop safely",
        stage="discover",
        command_id="command:one",
    )
    store = MemoryResearchStore(run, [])
    called = False

    async def discover(current: ResearchRun) -> ResearchStageResult:
        nonlocal called
        called = True
        return ResearchStageResult()

    async def command_status(command_id: str):
        return SimpleNamespace(status="canceled")

    cancelled = await ResearchWorkflow(
        store,
        {"discover": discover},
        command_status_getter=command_status,
    ).resume(run.id)

    assert cancelled.cancelled is True
    assert called is False


@pytest.mark.asyncio
async def test_submit_attaches_surreal_command_id() -> None:
    run = ResearchRun(id="research_run:submit", objective="Run in the background")
    store = MemoryResearchStore(run, [])
    submitted: list[tuple[object, ...]] = []

    def submit(*args):
        submitted.append(args)
        return "command:research"

    queued = await ResearchWorkflow(store, command_submitter=submit).submit(run.id)

    assert queued.command_id == "command:research"
    assert submitted == [("open_notebook", "run_research", {"research_run_id": run.id})]
