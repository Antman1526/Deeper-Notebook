"""Immutable domain contracts for Study Workbench plans and syllabi."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, Mapping, Self

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
_PROTECTED_PLAN_COPY_FIELDS = frozenset(
    {
        "plan_id",
        "source_links",
        "source_manifest_sha256",
        "approved_syllabus_version",
        "state",
        "version",
        "created_at",
        "updated_at",
    }
)

_UnitId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$"),
]
_Objective = Annotated[str, Field(min_length=1, max_length=2_000)]
_SourceId = Annotated[str, Field(min_length=1, max_length=512)]


def _require_nonblank(value: str, *, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _require_timezone_aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _list_to_tuple(value: object) -> object:
    """Accept documented list inputs while storing immutable tuples."""
    return tuple(value) if isinstance(value, list) else value


class _FrozenContract(BaseModel):
    """Strict immutable contract base that cannot skip validators on copies."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Return a revalidated copy, preserving Pydantic's deep-copy option."""
        values = dict(self.__dict__)
        if deep:
            values = deepcopy(values)
        if update:
            values.update(dict(update))
        return type(self).model_validate(values)


class StudyActivity(_FrozenContract):
    """One bounded planned learning activity within a syllabus unit."""

    activity_id: _UnitId
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
    source_ids: tuple[_SourceId, ...] = Field(default_factory=tuple, max_length=100)

    @field_validator("activity_id", "title")
    @classmethod
    def text_is_not_blank(cls, value: str, info: object) -> str:
        return _require_nonblank(value, field_name=str(info.field_name))

    @field_validator("source_ids", mode="before")
    @classmethod
    def source_ids_use_immutable_storage(cls, value: object) -> object:
        return _list_to_tuple(value)

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_not_blank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_require_nonblank(value, field_name="source_id") for value in values)


class StudyPlanPreferences(_FrozenContract):
    """User-confirmed time and model/network policy for a study plan."""

    weekly_minutes: int = Field(ge=5, le=10_080)
    session_minutes: int = Field(ge=5, le=480)
    model_route: Literal["local", "cloud"] = "local"
    network_allowed: bool = False
    approved_network_scope: tuple[str, ...] = Field(default_factory=tuple, max_length=8)

    @field_validator("approved_network_scope", mode="before")
    @classmethod
    def network_scope_uses_immutable_storage(cls, value: object) -> object:
        return _list_to_tuple(value)

    @field_validator("approved_network_scope")
    @classmethod
    def network_scope_is_bounded_https(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("approved network scope entries must be unique")
        for value in values:
            if not value.strip() or len(value) > 512 or not value.startswith("https://"):
                raise ValueError("approved network scope must contain bounded HTTPS origins")
        return values

    @model_validator(mode="after")
    def remote_authority_is_explicit(self) -> "StudyPlanPreferences":
        if self.network_allowed != bool(self.approved_network_scope):
            raise ValueError("network authority and approved scope must be supplied together")
        if self.model_route == "cloud" and not self.network_allowed:
            raise ValueError("cloud model route requires network authority")
        return self


class StudyPlanSourceLink(_FrozenContract):
    """A read-only link from a plan to an existing source record."""

    source_id: str = Field(min_length=1, max_length=512)

    @field_validator("source_id")
    @classmethod
    def source_id_is_not_blank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="source_id")


class StudySyllabusUnit(_FrozenContract):
    """An immutable, evidence-linked unit in a proposed syllabus."""

    unit_id: _UnitId
    title: str = Field(min_length=1, max_length=200)
    objectives: tuple[_Objective, ...] = Field(min_length=1, max_length=20)
    prerequisite_unit_ids: tuple[_UnitId, ...] = Field(default_factory=tuple, max_length=20)
    estimated_minutes: int = Field(ge=5, le=10_080)
    source_ids: tuple[_SourceId, ...] = Field(default_factory=tuple, max_length=100)
    activities: tuple[StudyActivity, ...] = Field(default_factory=tuple, max_length=50)

    @field_validator("unit_id", "title")
    @classmethod
    def text_is_not_blank(cls, value: str, info: object) -> str:
        return _require_nonblank(value, field_name=str(info.field_name))

    @field_validator(
        "objectives",
        "prerequisite_unit_ids",
        "source_ids",
        "activities",
        mode="before",
    )
    @classmethod
    def collections_use_immutable_storage(cls, value: object) -> object:
        return _list_to_tuple(value)

    @field_validator("objectives", "prerequisite_unit_ids", "source_ids")
    @classmethod
    def list_text_is_not_blank(
        cls, values: tuple[str, ...], info: object
    ) -> tuple[str, ...]:
        field_name = str(info.field_name).removesuffix("s")
        return tuple(_require_nonblank(value, field_name=field_name) for value in values)


class StudySyllabus(_FrozenContract):
    """A versioned immutable syllabus snapshot bound to its source manifest."""

    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=512)
    version: int = Field(ge=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    units: tuple[StudySyllabusUnit, ...] = Field(min_length=1, max_length=64)
    approved_at: datetime | None = None

    @field_validator("plan_id")
    @classmethod
    def plan_id_is_not_blank(cls, value: str) -> str:
        return _require_nonblank(value, field_name="plan_id")

    @field_validator("units", mode="before")
    @classmethod
    def units_use_immutable_storage(cls, value: object) -> object:
        return _list_to_tuple(value)

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


class StudyPlan(_FrozenContract):
    """An immutable plan whose lifecycle advances only through ``transition``."""

    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=512)
    goal: str = Field(min_length=1, max_length=2_000)
    starting_level: str = Field(min_length=1, max_length=200)
    target_date: date | None = None
    preferences: StudyPlanPreferences | None = None
    source_links: tuple[StudyPlanSourceLink, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    source_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    approved_syllabus_version: int | None = Field(default=None, ge=1)
    state: StudyPlanState = "draft"
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def default_timestamps_from_one_clock_sample(cls, value: object) -> object:
        """Capture creation/update defaults together at the precision boundary.

        SurrealDB persists nanoseconds while the Python driver commonly
        decodes microseconds.  Two adjacent ``now()`` calls can therefore
        round-trip in the opposite order.  A newly-created plan has one
        authoritative timestamp; later lifecycle mutations explicitly set
        only ``updated_at``.
        """
        if not isinstance(value, Mapping):
            return value
        values = dict(value)
        if "created_at" not in values and "updated_at" not in values:
            now = datetime.now(UTC)
            values["created_at"] = now
            values["updated_at"] = now
        elif "created_at" in values and "updated_at" not in values:
            values["updated_at"] = values["created_at"]
        elif "updated_at" in values and "created_at" not in values:
            values["created_at"] = values["updated_at"]
        return values

    @field_validator("plan_id", "goal", "starting_level")
    @classmethod
    def text_is_not_blank(cls, value: str, info: object) -> str:
        return _require_nonblank(value, field_name=str(info.field_name))

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_timezone_aware(cls, value: datetime, info: object) -> datetime:
        return _require_timezone_aware(value, field_name=str(info.field_name))

    @field_validator("source_links", mode="before")
    @classmethod
    def source_links_use_immutable_storage(cls, value: object) -> object:
        return _list_to_tuple(value)

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

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Revalidate non-lifecycle revisions without bypassing plan authority."""
        update = update or {}
        protected_fields = sorted(set(update) & _PROTECTED_PLAN_COPY_FIELDS)
        if protected_fields:
            raise ValueError(
                "model_copy cannot change protected plan fields; "
                "use transition for lifecycle changes"
            )
        return super().model_copy(update=update, deep=deep)

    def _require_approval_binding(self) -> None:
        if self.source_manifest_sha256 is None:
            raise ValueError("approval requires a source manifest")
        if self.approved_syllabus_version is None:
            raise ValueError("approval requires an approved syllabus version")
