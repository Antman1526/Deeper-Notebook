"""API response contracts for persisted evidence evaluations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from open_notebook.evaluation.schemas import ClaimVerdict


class SourceContentHashResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    sha256: str


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    notebook_id: str
    artifact_id: str | None = None
    message_id: str | None = None
    evaluator_version: str
    model_id: str | None = None
    source_content_hashes: list[SourceContentHashResponse] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created: str | None = None
    updated: str | None = None


class ClaimVerdictResponse(ClaimVerdict):
    id: str
    evaluation_run_id: str
