"""Immutable domain contracts for Study Workbench plans and syllabi."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StudyPlanState = Literal[
    "draft",
    "analyzing_sources",
    "syllabus_proposed",
    "editing",
    "approved",
    "generating",
    "active",
    "completed",
    "archived",
]

_APPROVAL_BOUND_STATES: frozenset[StudyPlanState] = frozenset(
    {"approved", "generating", "active", "completed", "archived"}
)
_ALLOWED_TRANSITIONS: dict[StudyPlanState, frozenset[StudyPlanState]] = {
    "draft": frozenset({"analyzing_sources"}),
    "analyzing_sources": frozenset({"syllabus_proposed"}),
    "syllabus_proposed": frozenset({"editing"}),
    "editing": frozenset({"approved"}),
    "approved": frozenset({"generating"}),
    "generating": frozenset({"active"}),
    "active": frozenset({"completed", "archived"}),
    "completed": frozenset(),
    "archived": frozenset(),
}


def _require_nonblank(value: str, *, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _require_timezone_aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class StudyActivity(BaseModel):
    """One bounded planned learning activity within a syllabus unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    activity_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    kind: Literal[
        "reading",
        "lesson",
        "tutor_session",
        "quiz",
        "recall",
        "exam",
        "project",
        "review",
        "custom",
    ]
    title: str = Field(min_length=1, max_length=200)
    estimated_minutes: int = Field(ge=5, le=10_080)
    source_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("activity_id", "title")
    @classmethod
    def text_is_not_blank(cls, value: str, info: object) -> str:
        return _require_nonblank(value, field_name=str(info.field_name))

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_not_blank(cls, values: list[str]) -> list[str]:
        return [_require_nonblank(value, field_name="source_id") for value in values]


class StudyPlanPreferences(BaseModel):
    """User-confirmed time budget for a study plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    weekly_minutes: int = Field(ge=5, le=10_080)
    session_minutes: int = Field(ge=5, le=480)


class StudyPlanSourceLink(BaseModel):
    """A read-only link from a plan to an existing source record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=512)

    @field_validator("source_id")
    @classmethod
    def source_id_is_not_blank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="source_id")


class StudySyllabusUnit(BaseModel):
    """An immutable, evidence-linked unit in a proposed syllabus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    objectives: list[str] = Field(min_length=1, max_length=20)
    prerequisite_unit_ids: list[str] = Field(default_factory=list, max_length=20)
    estimated_minutes: int = Field(ge=5, le=10_080)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    activities: list[StudyActivity] = Field(default_factory=list, max_length=50)

    @field_validator("unit_id", "title")
    @classmethod
    def text_is_not_blank(cls, value: str, info: object) -> str:
        return _require_nonblank(value, field_name=str(info.field_name))

    @field_validator("objectives", "prerequisite_unit_ids", "source_ids")
    @classmethod
    def list_text_is_not_blank(cls, values: list[str], info: object) -> list[str]:
        field_name = str(info.field_name).removesuffix("s")
        return [_require_nonblank(value, field_name=field_name) for value in values]


class StudySyllabus(BaseModel):
    """A versioned immutable syllabus snapshot bound to its source manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=512)
    version: int = Field(ge=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    units: list[StudySyllabusUnit] = Field(min_length=1, max_length=64)
    approved_at: datetime | None = None

    @field_validator("plan_id")
    @classmethod
    def plan_id_is_not_blank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="plan_id")

    @field_validator("approved_at")
    @classmethod
    def approved_at_is_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_timezone_aware(value, field_name="approved_at")

    @model_validator(mode="after")
    def units_are_unique(self) -> "StudySyllabus":
        if len({unit.unit_id for unit in self.units}) != len(self.units):
            raise ValueError("syllabus unit IDs must be unique")
        return self


class StudyPlan(BaseModel):
    """An immutable plan whose lifecycle advances only through ``transition``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=512)
    goal: str = Field(min_length=1, max_length=2_000)
    starting_level: str = Field(min_length=1, max_length=200)
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None
    source_links: list[StudyPlanSourceLink] = Field(default_factory=list, max_length=100)
    source_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    approved_syllabus_version: int | None = Field(default=None, ge=1)
    state: StudyPlanState = "draft"
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("plan_id", "goal", "starting_level")
    @classmethod
    def text_is_not_blank(cls, value: str, info: object) -> str:
        return _require_nonblank(value, field_name=str(info.field_name))

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_timezone_aware(cls, value: datetime, info: object) -> datetime:
        return _require_timezone_aware(value, field_name=str(info.field_name))

    @model_validator(mode="after")
    def validate_plan_contract(self) -> "StudyPlan":
        source_ids = [link.source_id for link in self.source_links]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("plan source links must be unique")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        if self.state in _APPROVAL_BOUND_STATES:
            self._require_approval_binding()
        return self

    def transition(
        self,
        next_state: StudyPlanState,
        *,
        expected_version: int,
    ) -> "StudyPlan":
        """Advance one allowlisted lifecycle edge using optimistic concurrency."""
        if expected_version != self.version:
            raise ValueError(
                f"Expected plan version {expected_version}, current version is {self.version}"
            )
        if next_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Transition from {self.state} to {next_state} is not allowed")
        if next_state in _APPROVAL_BOUND_STATES:
            self._require_approval_binding()
        return StudyPlan.model_validate(
            self.model_dump()
            | {
                "state": next_state,
                "version": self.version + 1,
                "updated_at": datetime.now(UTC),
            }
        )

    def _require_approval_binding(self) -> None:
        if self.source_manifest_sha256 is None:
            raise ValueError("approval requires a source manifest")
        if self.approved_syllabus_version is None:
            raise ValueError("approval requires an approved syllabus version")
