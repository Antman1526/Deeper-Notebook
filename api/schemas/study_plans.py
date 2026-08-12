"""Strict HTTP contracts for feature-gated Study Workbench plans."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Self
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from deeper_notebook.study.plans import (
    StudyPlan,
    StudyPlanPreferences,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)
from deeper_notebook.study.source_service import (
    StudySourceReadiness,
    StudySourceReadinessItem,
)


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _nonblank(value: str, *, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


class CreateStudyPlanRequest(_StrictRequest):
    goal: StrictStr = Field(min_length=1, max_length=2_000)
    starting_level: StrictStr = Field(min_length=1, max_length=200)
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None

    @field_validator("goal", "starting_level")
    @classmethod
    def text_is_nonblank(cls, value: str, info: object) -> str:
        return _nonblank(value, field_name=str(info.field_name))

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
    goal: StrictStr | None = Field(default=None, min_length=1, max_length=2_000)
    starting_level: StrictStr | None = Field(default=None, min_length=1, max_length=200)
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None

    @field_validator("goal", "starting_level")
    @classmethod
    def text_is_nonblank(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return value
        return _nonblank(value, field_name=str(info.field_name))

    @model_validator(mode="after")
    def has_changes(self) -> Self:
        changes = self.model_fields_set - {"expected_revision"}
        if not changes:
            raise ValueError("study plan patch must contain a change")
        forbidden_nulls = changes & {"goal", "starting_level", "preferences"}
        if any(getattr(self, field_name) is None for field_name in forbidden_nulls):
            raise ValueError("study plan patch field must not be null")
        return self

    def changes(self) -> dict[str, object]:
        return self.model_dump(exclude={"expected_revision"}, exclude_unset=True)


class SourceLinkRequest(_StrictRequest):
    source_id: StrictStr = Field(min_length=1, max_length=512)
    expected_revision: StrictInt = Field(ge=1)

    @field_validator("source_id")
    @classmethod
    def source_id_is_nonblank(cls, value: str) -> str:
        return _nonblank(value, field_name="source_id")


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


class ProposeSyllabusRequest(_StrictRequest):
    """Optimistic revision guard for source-grounded syllabus proposals."""

    expected_revision: StrictInt = Field(ge=1)


class ApproveSyllabusRequest(_StrictRequest):
    syllabus_version: StrictInt = Field(ge=1)
    expected_revision: StrictInt = Field(ge=1)


StudyArtifactType = Literal[
    "study_guide",
    "course_pack",
    "flashcards",
    "quiz",
    "mind_map",
]


class GenerateStudyArtifactsRequest(_StrictRequest):
    """Bounded request for one exact approved syllabus unit."""

    unit_id: StrictStr = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
    )
    artifact_types: tuple[StudyArtifactType, ...] = Field(
        min_length=1,
        max_length=5,
    )
    expected_revision: StrictInt = Field(ge=1)
    context: StrictStr | None = Field(default=None, max_length=8_000)

    @model_validator(mode="after")
    def artifact_types_are_unique(self) -> "GenerateStudyArtifactsRequest":
        if len(set(self.artifact_types)) != len(self.artifact_types):
            raise ValueError("artifact_types must not contain duplicates")
        return self


class StudyArtifactReceiptResponse(BaseModel):
    """Metadata-only receipt; generated payloads remain in Evidence Studio."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=512)
    artifact_type: StudyArtifactType
    status: Literal["completed"]
    unit_id: str = Field(min_length=1, max_length=64)


class GenerateStudyArtifactsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1, max_length=512)
    unit_id: str = Field(min_length=1, max_length=64)
    artifacts: tuple[StudyArtifactReceiptResponse, ...] = Field(max_length=5)


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


class StudySourceReadinessItemResponse(BaseModel):
    """Bounded source projection for the Study Workbench picker."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal[
        "link",
        "upload",
        "text",
        "web_import",
        "deep_research_report",
    ]
    ready: bool
    command_id: str | None = Field(default=None, max_length=512)
    fingerprint_status: Literal["available", "unknown"]
    reason: Literal["ready", "processing", "processing_failed", "missing", "unavailable"]

    @classmethod
    def from_item(cls, item: StudySourceReadinessItem) -> "StudySourceReadinessItemResponse":
        return cls.model_validate(item.model_dump())


class StudySourceReadinessResponse(BaseModel):
    """Readiness summary without source paths, bodies, or driver errors."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    items: tuple[StudySourceReadinessItemResponse, ...] = Field(max_length=100)

    @classmethod
    def from_readiness(cls, readiness: StudySourceReadiness) -> "StudySourceReadinessResponse":
        return cls(
            ready=readiness.ready,
            items=tuple(
                StudySourceReadinessItemResponse.from_item(item)
                for item in readiness.items
            ),
        )


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
