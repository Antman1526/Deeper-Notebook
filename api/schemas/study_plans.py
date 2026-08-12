"""Strict HTTP contracts for feature-gated Study Workbench plans."""

from __future__ import annotations

from datetime import date, datetime
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanPreferences,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateStudyPlanRequest(_StrictRequest):
    goal: str = Field(min_length=1, max_length=2_000)
    starting_level: str = Field(min_length=1, max_length=200)
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None

    def to_plan(self) -> StudyPlan:
        return StudyPlan(
            plan_id=f"study_plan:{uuid4().hex}",
            goal=self.goal,
            starting_level=self.starting_level,
            target_date=self.target_date,
            preferences=self.preferences,
        )


class PatchStudyPlanRequest(_StrictRequest):
    expected_revision: StrictInt = Field(ge=1)
    goal: str | None = Field(default=None, min_length=1, max_length=2_000)
    starting_level: str | None = Field(default=None, min_length=1, max_length=200)
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None

    @model_validator(mode="after")
    def has_changes(self) -> Self:
        if not self.model_fields_set - {"expected_revision"}:
            raise ValueError("study plan patch must contain a change")
        return self

    def changes(self) -> dict[str, object]:
        return self.model_dump(exclude={"expected_revision"}, exclude_unset=True)


class SourceLinkRequest(_StrictRequest):
    source_id: str = Field(min_length=1, max_length=512)
    expected_revision: StrictInt = Field(ge=1)


class RemoveSourceLinkRequest(_StrictRequest):
    expected_revision: StrictInt = Field(ge=1)


class SaveSyllabusRequest(_StrictRequest):
    expected_revision: StrictInt = Field(ge=1)
    version: StrictInt = Field(ge=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    units: tuple[StudySyllabusUnit, ...] = Field(min_length=1, max_length=64)

    def to_syllabus(self, plan_id: str) -> StudySyllabus:
        return StudySyllabus(
            plan_id=plan_id,
            version=self.version,
            source_manifest_sha256=self.source_manifest_sha256,
            units=self.units,
        )


class ApproveSyllabusRequest(_StrictRequest):
    syllabus_version: StrictInt = Field(ge=1)
    expected_revision: StrictInt = Field(ge=1)


class StudyPlanResponse(BaseModel):
    """Safe plan projection; no persisted database metadata is exposed."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    goal: str
    starting_level: str
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None
    source_links: tuple[StudyPlanSourceLink, ...]
    approved_syllabus_version: int | None = None
    state: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_plan(cls, plan: StudyPlan) -> "StudyPlanResponse":
        return cls(
            plan_id=plan.plan_id,
            goal=plan.goal,
            starting_level=plan.starting_level,
            target_date=plan.target_date,
            preferences=plan.preferences,
            source_links=plan.source_links,
            approved_syllabus_version=plan.approved_syllabus_version,
            state=plan.state,
            version=plan.version,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )


class StudyPlanSourceLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str

    @classmethod
    def from_link(cls, link: StudyPlanSourceLink) -> "StudyPlanSourceLinkResponse":
        return cls(source_id=link.source_id)


class RemoveSourceLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removed: bool


class StudySyllabusResponse(BaseModel):
    """Safe immutable syllabus projection with no record or source-body fields."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    version: int
    source_manifest_sha256: str
    units: tuple[StudySyllabusUnit, ...]
    approved_at: datetime | None = None

    @classmethod
    def from_syllabus(cls, syllabus: StudySyllabus) -> "StudySyllabusResponse":
        return cls(
            plan_id=syllabus.plan_id,
            version=syllabus.version,
            source_manifest_sha256=syllabus.source_manifest_sha256,
            units=syllabus.units,
            approved_at=syllabus.approved_at,
        )
