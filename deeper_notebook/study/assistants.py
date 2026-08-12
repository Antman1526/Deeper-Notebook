"""Strict, plan-local contracts for the Study assistant team.

The assistant boundary intentionally contains no model/provider object.  It is
the small wire-independent seam shared by a future assistant service,
repositories, and HTTP adapters.  All collections are tuples of frozen
submodels so a provider response cannot be mutated after validation.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StudyAssistantRole = Literal[
    "study_director",
    "curriculum_architect",
    "socratic_tutor",
    "concept_explainer",
    "source_guide",
    "practice_coach",
    "exam_coach",
    "memory_coach",
    "research_scout",
    "project_mentor",
    "writing_coach",
    "progress_coach",
]
StudyAuthority = Literal["ask", "coach", "plan", "create"]
StudySessionStatus = Literal[
    "queued", "running", "completed", "failed", "cancelled"
]
StudyDecision = Literal["pending", "accepted", "rejected", "deferred"]
StudyMemoryProvenance = Literal[
    "user_confirmed",
    "assistant_observation",
    "assistant_inference",
    "source_evidence",
    "system_receipt",
]
StudyMemoryStatus = Literal[
    "inferred", "confirmed", "rejected", "superseded", "active", "cleared"
]
StudyProgressEvent = Literal[
    "started",
    "completed",
    "assessed",
    "mastery_updated",
    "intervention_proposed",
    "schedule_changed",
    "decision",
    "failed",
    "cancelled",
]

STUDY_ASSISTANT_ROLES: tuple[StudyAssistantRole, ...] = (
    "study_director",
    "curriculum_architect",
    "socratic_tutor",
    "concept_explainer",
    "source_guide",
    "practice_coach",
    "exam_coach",
    "memory_coach",
    "research_scout",
    "project_mentor",
    "writing_coach",
    "progress_coach",
)
STUDY_AUTHORITIES: tuple[StudyAuthority, ...] = ("ask", "coach", "plan", "create")

_MAX_PROMPT_BYTES = 16 * 1024
_MAX_CITATIONS = 32
_MAX_ACTIONS = 20
_MAX_HANDOFFS_PAGE = 50
_MAX_SOURCE_IDS = 100
_MAX_NETWORK_SCOPE = 8
_MAX_ERROR_CODE = 96

_RecordID = Annotated[str, Field(min_length=1, max_length=512)]
_UnitID = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]


def _nonblank(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _tuplize(value: object) -> object:
    if isinstance(value, list):
        return tuple(value)
    return value


def _utf8_bounded(value: str, *, field_name: str, limit: int) -> str:
    _nonblank(value, field_name=field_name)
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{field_name} exceeds its bounded size")
    return value


def _record_id_text(value: str, *, field_name: str, table: str) -> str:
    """Validate a public ID without interpolating it into a query.

    Surreal's RecordID parser is intentionally not used here: its escaping
    details differ between driver versions.  Repository methods perform the
    final table-bound ``RecordID`` conversion immediately before binding.
    """
    _nonblank(value, field_name=field_name)
    if len(value) > 512 or not value.startswith(f"{table}:"):
        raise ValueError(f"{field_name} must be an exact {table} record ID")
    token = value[len(table) + 1 :]
    if not token.strip() or "\n" in token or "\r" in token:
        raise ValueError(f"{field_name} must be an exact {table} record ID")
    return value


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        values = dict(self.__dict__)
        if deep:
            values = deepcopy(values)
        if update:
            values.update(dict(update))
        return type(self).model_validate(values)


class StudyCitation(_FrozenContract):
    """One bounded source citation; never a source body or provider payload."""

    source_id: _RecordID
    locator: str | None = Field(default=None, max_length=256)
    quote: str | None = Field(default=None, max_length=2_000)
    title: str | None = Field(default=None, max_length=200)

    @field_validator("source_id")
    @classmethod
    def source_id_is_not_blank(cls, value: str) -> str:
        return _nonblank(value, field_name="source_id")

    @field_validator("locator", "quote", "title")
    @classmethod
    def optional_text_is_bounded(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _nonblank(value, field_name=str(getattr(info, "field_name", "text")))


class StudyProposedAction(_FrozenContract):
    """A visible, inert action proposal awaiting an explicit user decision."""

    action: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_.-]{0,95}$")
    label: str = Field(min_length=1, max_length=200)
    unit_id: _UnitID | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("action", "label")
    @classmethod
    def action_text_is_not_blank(cls, value: str, info: object) -> str:
        return _nonblank(value, field_name=str(getattr(info, "field_name", "text")))


class StudyRetrievalReceipt(_FrozenContract):
    """Metadata-only retrieval receipt used in assistant responses."""

    source_ids: tuple[_RecordID, ...] = Field(default_factory=tuple, max_length=_MAX_SOURCE_IDS)
    citation_count: int = Field(default=0, ge=0, le=_MAX_CITATIONS)

    @field_validator("source_ids", mode="before")
    @classmethod
    def source_ids_are_immutable(cls, value: object) -> object:
        return _tuplize(value)

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_not_blank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_nonblank(value, field_name="source_id") for value in values)


class StudyAssistantInvocation(_FrozenContract):
    """A bounded request to one foreground assistant."""

    schema_version: Literal[1] = 1
    invocation_id: str | None = Field(default=None, max_length=256)
    request_id: str | None = Field(default=None, max_length=256)
    plan_id: _RecordID
    unit_id: _UnitID | None = None
    role: StudyAssistantRole
    authority: StudyAuthority
    prompt: str = Field(min_length=1)
    selected_source_ids: tuple[_RecordID, ...] = Field(
        default_factory=tuple, max_length=_MAX_SOURCE_IDS
    )
    citations: tuple[StudyCitation, ...] = Field(
        default_factory=tuple, max_length=_MAX_CITATIONS
    )
    proposed_actions: tuple[StudyProposedAction, ...] = Field(
        default_factory=tuple, max_length=_MAX_ACTIONS
    )
    network_allowed: bool = False
    approved_network_scope: tuple[str, ...] = Field(
        default_factory=tuple, max_length=_MAX_NETWORK_SCOPE
    )
    model_route: Literal["local", "cloud"] = "local"
    # ``plan`` authority can only describe a proposal.  Applying an edit is a
    # separate, user-authorized plan mutation owned by the plan repository.
    syllabus_mutation: Literal["none", "propose"] = "none"
    mutates_syllabus: bool = False
    mutates_sources: bool = False
    publishes_cards: bool = False
    changes_schedule: bool = False
    timeout_seconds: int = Field(default=120, ge=1, le=120)
    created_at: datetime

    @field_validator("plan_id")
    @classmethod
    def plan_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="plan_id", table="study_plan")

    @field_validator("invocation_id", "request_id")
    @classmethod
    def optional_ids_are_not_blank(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _nonblank(value, field_name=str(getattr(info, "field_name", "id")))

    @field_validator("prompt")
    @classmethod
    def prompt_is_utf8_bounded(cls, value: str) -> str:
        return _utf8_bounded(value, field_name="prompt", limit=_MAX_PROMPT_BYTES)

    @field_validator("selected_source_ids", mode="before")
    @classmethod
    def selected_sources_are_immutable(cls, value: object) -> object:
        return _tuplize(value)

    @field_validator("selected_source_ids")
    @classmethod
    def selected_sources_are_not_blank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_nonblank(value, field_name="source_id") for value in values)

    @field_validator("citations", "proposed_actions", mode="before")
    @classmethod
    def lists_are_immutable(cls, value: object) -> object:
        return _tuplize(value)

    @field_validator("approved_network_scope", mode="before")
    @classmethod
    def scope_is_immutable(cls, value: object) -> object:
        return _tuplize(value)

    @field_validator("approved_network_scope")
    @classmethod
    def scope_is_explicit_https(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        result: list[str] = []
        for value in values:
            _nonblank(value, field_name="approved_network_scope")
            if len(value) > 512 or not value.startswith("https://"):
                raise ValueError("approved network scope must contain bounded HTTPS origins")
            result.append(value)
        if len(set(result)) != len(result):
            raise ValueError("approved network scope entries must be unique")
        return tuple(result)

    @field_validator("created_at")
    @classmethod
    def created_at_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, field_name="created_at")

    @model_validator(mode="after")
    def authority_cannot_expand(self) -> "StudyAssistantInvocation":
        if self.network_allowed and not self.approved_network_scope:
            raise ValueError("network access requires an approved network scope")
        if not self.network_allowed and self.approved_network_scope:
            raise ValueError("network scope requires network_allowed")
        if self.model_route == "cloud" and not self.network_allowed:
            raise ValueError("cloud model route requires explicit network authority")
        protected = (
            self.mutates_sources
            or self.publishes_cards
            or self.changes_schedule
            or self.mutates_syllabus
        )
        if self.mutates_syllabus:
            raise ValueError("assistant invocations cannot mutate the syllabus directly")
        if self.syllabus_mutation not in {"none", "propose"}:
            raise ValueError("assistant invocations can only propose syllabus changes")
        if self.authority != "plan" and self.syllabus_mutation != "none":
            raise ValueError("syllabus mutations require plan authority")
        if self.authority == "plan" and protected:
            raise ValueError(
                "plan authority can only propose syllabus, source, card, and schedule changes"
            )
        if self.authority == "create" and (self.network_allowed or protected):
            raise ValueError("create authority cannot expand network or mutate Study state")
        if self.authority in {"ask", "coach"} and protected:
            raise ValueError("ask and coach authority are read-only")
        return self


class StudyAssistantResponse(_FrozenContract):
    """Public assistant result; provider payloads and hidden reasoning are absent."""

    schema_version: Literal[1] = 1
    response_id: str | None = Field(default=None, max_length=512)
    session_id: str | None = Field(default=None, max_length=512)
    plan_id: _RecordID
    role: StudyAssistantRole
    authority: StudyAuthority
    status: Literal["completed", "failed", "cancelled"] = "completed"
    answer: str = Field(min_length=1, max_length=64_000)
    citations: tuple[StudyCitation, ...] = Field(
        default_factory=tuple, max_length=_MAX_CITATIONS
    )
    proposed_actions: tuple[StudyProposedAction, ...] = Field(
        default_factory=tuple, max_length=_MAX_ACTIONS
    )
    retrieval_receipt: StudyRetrievalReceipt = Field(default_factory=StudyRetrievalReceipt)
    error_code: str | None = Field(default=None, max_length=_MAX_ERROR_CODE)
    created_at: datetime
    completed_at: datetime | None = None

    @field_validator("plan_id")
    @classmethod
    def response_plan_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="plan_id", table="study_plan")

    @field_validator("response_id", "session_id", "error_code")
    @classmethod
    def response_optional_text_is_safe(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _nonblank(value, field_name=str(getattr(info, "field_name", "value")))

    @field_validator("citations", "proposed_actions", mode="before")
    @classmethod
    def response_lists_are_immutable(cls, value: object) -> object:
        return _tuplize(value)

    @field_validator("created_at", "completed_at")
    @classmethod
    def response_timestamps_are_aware(
        cls, value: datetime | None, info: object
    ) -> datetime | None:
        if value is None:
            return None
        return _aware(value, field_name=str(getattr(info, "field_name", "timestamp")))

    @model_validator(mode="after")
    def response_status_is_consistent(self) -> "StudyAssistantResponse":
        if self.status != "completed" and not self.error_code:
            raise ValueError("failed or cancelled responses require a safe error code")
        return self


class StudyAssistantSession(_FrozenContract):
    """Durable session metadata, intentionally without prompt/provider bytes."""

    schema_version: Literal[1] = 1
    session_id: str
    plan_id: _RecordID
    role: StudyAssistantRole
    authority: StudyAuthority
    request_id: str | None = Field(default=None, max_length=256)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_source_ids: tuple[_RecordID, ...] = Field(
        default_factory=tuple, max_length=_MAX_SOURCE_IDS
    )
    status: StudySessionStatus = "queued"
    response_id: str | None = Field(default=None, max_length=512)
    error_code: str | None = Field(default=None, max_length=_MAX_ERROR_CODE)
    revision: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="session_id", table="study_assistant_session")

    @field_validator("plan_id")
    @classmethod
    def session_plan_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="plan_id", table="study_plan")

    @field_validator("created_at", "updated_at", "completed_at")
    @classmethod
    def session_times_are_aware(
        cls, value: datetime | None, info: object
    ) -> datetime | None:
        if value is None:
            return None
        return _aware(value, field_name=str(getattr(info, "field_name", "timestamp")))

    @model_validator(mode="after")
    def session_time_order(self) -> "StudyAssistantSession":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self


class StudyAssistantHandoff(_FrozenContract):
    """A concise assistant-to-assistant receipt, never an unrestricted transcript."""

    schema_version: Literal[1] = 1
    handoff_id: str | None = Field(default=None, max_length=512)
    request_id: str | None = Field(default=None, max_length=256)
    plan_id: _RecordID
    session_id: str
    role: StudyAssistantRole
    observation: str = Field(min_length=1, max_length=16_384)
    evidence: tuple[StudyCitation, ...] = Field(default_factory=tuple, max_length=_MAX_CITATIONS)
    proposed_action: str | None = Field(default=None, max_length=2_000)
    origin: StudyAssistantRole
    user_decision: StudyDecision = "pending"
    created_at: datetime
    decided_at: datetime | None = None

    @field_validator("handoff_id")
    @classmethod
    def handoff_id_is_exact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _record_id_text(value, field_name="handoff_id", table="study_assistant_handoff")

    @field_validator("plan_id")
    @classmethod
    def handoff_plan_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="plan_id", table="study_plan")

    @field_validator("session_id")
    @classmethod
    def handoff_session_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="session_id", table="study_assistant_session")

    @field_validator("request_id", "proposed_action")
    @classmethod
    def handoff_text_is_bounded(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _nonblank(value, field_name=str(getattr(info, "field_name", "text")))

    @field_validator("evidence", mode="before")
    @classmethod
    def evidence_is_immutable(cls, value: object) -> object:
        return _tuplize(value)

    @field_validator("created_at", "decided_at")
    @classmethod
    def handoff_times_are_aware(
        cls, value: datetime | None, info: object
    ) -> datetime | None:
        if value is None:
            return None
        return _aware(value, field_name=str(getattr(info, "field_name", "timestamp")))

    @model_validator(mode="after")
    def decision_has_receipt(self) -> "StudyAssistantHandoff":
        if self.user_decision != "pending" and self.decided_at is None:
            raise ValueError("a decided handoff requires decided_at")
        if self.decided_at is not None and self.decided_at < self.created_at:
            raise ValueError("decided_at must not precede created_at")
        return self


class StudyPlanMemory(_FrozenContract):
    """Editable plan-local memory with explicit provenance and confirmation."""

    schema_version: Literal[1] = 1
    memory_id: str | None = Field(default=None, max_length=512)
    plan_id: _RecordID
    memory_key: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}$")
    value: str = Field(min_length=1, max_length=4_000)
    provenance: StudyMemoryProvenance
    status: StudyMemoryStatus
    confirmation_required: bool
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    revision: int = Field(default=1, ge=1)

    @field_validator("memory_id")
    @classmethod
    def memory_id_is_exact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _record_id_text(value, field_name="memory_id", table="study_plan_memory")

    @field_validator("plan_id")
    @classmethod
    def memory_plan_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="plan_id", table="study_plan")

    @field_validator("memory_key", "value")
    @classmethod
    def memory_text_is_not_blank(cls, value: str, info: object) -> str:
        return _nonblank(value, field_name=str(getattr(info, "field_name", "memory")))

    @field_validator("confirmed_at", "created_at", "updated_at")
    @classmethod
    def memory_times_are_aware(
        cls, value: datetime | None, info: object
    ) -> datetime | None:
        if value is None:
            return None
        return _aware(value, field_name=str(getattr(info, "field_name", "timestamp")))

    @model_validator(mode="after")
    def confirmation_is_explicit(self) -> "StudyPlanMemory":
        if self.provenance == "assistant_inference":
            if (
                self.status != "inferred"
                or not self.confirmation_required
                or self.confirmed_at is not None
            ):
                raise ValueError(
                    "assistant inference must remain inferred until user confirmation"
                )
        if self.status == "inferred" and not self.confirmation_required:
            raise ValueError("inferred memory requires user confirmation")
        if self.status == "confirmed" and self.confirmation_required:
            raise ValueError("confirmed memory cannot still require confirmation")
        if self.status == "confirmed" and self.confirmed_at is None:
            raise ValueError("confirmed memory requires confirmed_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        return self

    def confirm(self, *, now: datetime | None = None) -> "StudyPlanMemory":
        confirmed_at = _aware(now or datetime.now(UTC), field_name="confirmed_at")
        return self.model_copy(
            update={
                "provenance": "user_confirmed"
                if self.provenance == "assistant_inference"
                else self.provenance,
                "status": "confirmed",
                "confirmation_required": False,
                "confirmed_at": confirmed_at,
                "updated_at": confirmed_at,
                "revision": self.revision + 1,
            }
        )


class StudyProgressReceipt(_FrozenContract):
    """Small append-only progress receipt owned by the assistant migration."""

    schema_version: Literal[1] = 1
    receipt_id: str | None = Field(default=None, max_length=512)
    request_id: str = Field(min_length=1, max_length=256)
    plan_id: _RecordID
    unit_id: _UnitID | None = None
    event: StudyProgressEvent
    details: str | None = Field(default=None, max_length=2_000)
    created_at: datetime

    @field_validator("receipt_id")
    @classmethod
    def receipt_id_is_exact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _record_id_text(value, field_name="receipt_id", table="study_progress")

    @field_validator("request_id", "event", "details")
    @classmethod
    def receipt_text_is_safe(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _nonblank(value, field_name=str(getattr(info, "field_name", "text")))

    @field_validator("plan_id")
    @classmethod
    def receipt_plan_id_is_exact(cls, value: str) -> str:
        return _record_id_text(value, field_name="plan_id", table="study_plan")

    @field_validator("created_at")
    @classmethod
    def receipt_created_at_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, field_name="created_at")


def prompt_sha256(prompt: str) -> str:
    """Return the only prompt representation safe for durable receipts."""
    _utf8_bounded(prompt, field_name="prompt", limit=_MAX_PROMPT_BYTES)
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


__all__ = [
    "STUDY_ASSISTANT_ROLES",
    "STUDY_AUTHORITIES",
    "StudyAssistantHandoff",
    "StudyAssistantInvocation",
    "StudyAssistantResponse",
    "StudyAssistantRole",
    "StudyAssistantSession",
    "StudyAuthority",
    "StudyCitation",
    "StudyPlanMemory",
    "StudyProgressEvent",
    "StudyProgressReceipt",
    "StudyProposedAction",
    "StudyRetrievalReceipt",
    "prompt_sha256",
]
