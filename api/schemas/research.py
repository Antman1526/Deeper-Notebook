"""Public API contracts for owner-approved Research Runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeper_notebook.tools.web_evidence import WebEvidence


class CreateResearchRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=4_000)
    query: str | None = Field(default=None, max_length=1_000)

    @field_validator("objective", "query")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class ApproveResearchSourcesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_candidate_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("accepted_candidate_ids")
    @classmethod
    def unique_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value and value.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("candidate ids must be unique")
        return cleaned


class ResearchCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    url: str
    title: str | None = None
    domain: str
    snippet: str | None = None
    search_query: str | None = None
    decision: Literal["accepted", "rejected", "pending"]
    evidence: WebEvidence | None = None


class ResearchComparisonResponse(BaseModel):
    """Read-only comparison receipt; payloads remain structured, never HTML."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    agreements: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdicts: list[dict[str, Any]] = Field(default_factory=list)


class ResearchRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    notebook_id: str
    objective: str
    stage: str
    plan: dict[str, Any] = Field(default_factory=dict)
    hypotheses: list[str] = Field(default_factory=list)
    search_query: str | None = None
    candidates: list[ResearchCandidateResponse] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    comparison: ResearchComparisonResponse = Field(
        default_factory=ResearchComparisonResponse
    )
    cancelled: bool = False


class ResearchEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["status"] = "status"
    run: ResearchRunResponse
