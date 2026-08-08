"""Versioned state for restart-safe, source-approved research runs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeper_notebook.tools.web_evidence import WebEvidence

ResearchStage = Literal[
    "plan",
    "discover",
    "await_source_approval",
    "ingest",
    "extract",
    "compare",
    "synthesize",
    "validate",
    "complete",
]

RESEARCH_STAGES: tuple[ResearchStage, ...] = (
    "plan",
    "discover",
    "await_source_approval",
    "ingest",
    "extract",
    "compare",
    "synthesize",
    "validate",
    "complete",
)

_NEXT_STAGE: dict[ResearchStage, ResearchStage] = dict(
    zip(RESEARCH_STAGES, RESEARCH_STAGES[1:])
)


def next_stage(stage: ResearchStage) -> ResearchStage:
    """Return the sole forward transition; `complete` is terminal."""
    return _NEXT_STAGE.get(stage, "complete")


def unique_strings(values: Iterable[str]) -> list[str]:
    """Preserve first-seen ordering while making resume writes idempotent."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class ResearchCandidate(BaseModel):
    """A discovered source awaiting an explicit approve or reject decision."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=256)
    url: str = Field(min_length=1, max_length=4096)
    title: str | None = Field(default=None, max_length=1000)
    summary: str | None = Field(default=None, max_length=2000)
    evidence: WebEvidence | None = None


class ResearchStageResult(BaseModel):
    """The only shape accepted from an idempotent stage handler."""

    model_config = ConfigDict(extra="forbid")

    checkpoint: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any] | None = None
    hypotheses: list[str] | None = None
    search_queries: list[str] | None = None
    candidates: list[ResearchCandidate] | None = None
    approval_decisions: dict[str, bool] | None = None
    source_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ResearchRun(BaseModel):
    """All durable state necessary to stop and later resume a research run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str | None = None
    notebook_id: str | None = None
    objective: str = Field(min_length=1, max_length=4000)
    stage: ResearchStage = "plan"
    plan: dict[str, Any] = Field(default_factory=dict)
    hypotheses: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    candidates: list[ResearchCandidate] = Field(default_factory=list)
    approval_decisions: dict[str, bool] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    checkpoints: dict[str, dict[str, Any]] = Field(default_factory=dict)
    completed_stages: list[ResearchStage] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    cancelled: bool = False
    command_id: str | None = None

    @field_validator("source_ids", "hypotheses", "search_queries", "errors")
    @classmethod
    def de_duplicate_strings(cls, values: list[str]) -> list[str]:
        return unique_strings(values)

    def pending_candidate_ids(self) -> set[str]:
        """Return discovered candidates that have no explicit decision yet."""
        return {
            candidate.candidate_id
            for candidate in self.candidates
            if candidate.candidate_id not in self.approval_decisions
        }

    def approved_candidate_ids(self) -> set[str]:
        """Return only explicitly approved candidates in discovery order."""
        return {
            candidate.candidate_id
            for candidate in self.candidates
            if self.approval_decisions.get(candidate.candidate_id) is True
        }

    def has_completed(self, stage: ResearchStage) -> bool:
        return stage in self.completed_stages

    def with_approval_decisions(
        self,
        decisions: dict[str, bool],
    ) -> "ResearchRun":
        """Persist only decisions for candidates discovered by this run."""
        candidate_ids = {candidate.candidate_id for candidate in self.candidates}
        unknown_ids = set(decisions) - candidate_ids
        if unknown_ids:
            raise ValueError("approval decisions include unknown research candidates")
        return self.model_copy(
            update={"approval_decisions": {**self.approval_decisions, **decisions}}
        )

    def with_stage_result(
        self,
        stage: ResearchStage,
        result: ResearchStageResult,
    ) -> "ResearchRun":
        """Merge one checkpoint without replaying sources on a retry."""
        if self.has_completed(stage):
            return self

        data = self.model_dump()
        data["completed_stages"] = [*self.completed_stages, stage]
        data["stage"] = next_stage(stage)
        data["checkpoints"] = {
            **self.checkpoints,
            stage: result.checkpoint,
        }
        data["source_ids"] = unique_strings([*self.source_ids, *result.source_ids])
        data["errors"] = unique_strings([*self.errors, *result.errors])
        for field in (
            "plan",
            "hypotheses",
            "search_queries",
            "candidates",
            "approval_decisions",
        ):
            value = getattr(result, field)
            if value is not None:
                data[field] = value
        return ResearchRun.model_validate(data)
