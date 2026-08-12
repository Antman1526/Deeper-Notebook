"""Pure, bounded Study progress codecs and mastery projections.

The assistant work in Task 10 already owns the append-only ``study_progress``
table and its ``StudyProgressReceipt`` contract.  This module deliberately
does not add another persistence authority.  It encodes the richer Task 14
assessment payload into the existing bounded ``details`` field and projects
mastery from those receipts plus native immutable ``StudyReview`` receipts.
Projection is deterministic for an explicit ``now`` and never writes inferred
memory or FSRS scheduling state.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .assistants import StudyProgressReceipt
from .contracts import StudyRating, StudyReview

MAX_PROGRESS_DETAILS_BYTES = 2_000
MAX_PROJECTION_RECEIPTS = 500
MAX_CONCEPTS = 500
MAX_PROPOSALS = 100

ProgressAction = Literal[
    "prerequisite_detour",
    "schedule_review",
    "extra_practice",
    "slow_pacing",
]
MasteryStatus = Literal["needs_review", "developing", "mastered"]
ProposalStatus = Literal["proposed", "accepted", "dismissed"]


def _nonblank(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} contains control characters")
    return value


def _visible_id(value: str, *, field_name: str, limit: int = 128) -> str:
    value = _nonblank(value, field_name=field_name)
    if len(value) > limit:
        raise ValueError(f"{field_name} exceeds its bounded size")
    return value


def _aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
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
            from copy import deepcopy

            values = deepcopy(values)
        if update:
            values.update(dict(update))
        return type(self).model_validate(values)


class StudyProgressAssessment(_FrozenContract):
    """A bounded quiz/assessment observation stored inside a progress receipt."""

    schema_version: Literal[1] = 1
    concept_id: str = Field(min_length=1, max_length=128)
    unit_id: str | None = Field(default=None, min_length=1, max_length=64)
    score: float = Field(ge=0.0, le=1.0)
    correct: bool | None = None
    weight: float = Field(default=1.0, ge=0.25, le=4.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    prerequisite_concept_ids: tuple[str, ...] = Field(
        default_factory=tuple, max_length=20
    )

    @field_validator("concept_id", "unit_id")
    @classmethod
    def ids_are_visible(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _visible_id(value, field_name=str(getattr(info, "field_name", "id")))

    @field_validator("prerequisite_concept_ids", mode="before")
    @classmethod
    def prerequisites_are_immutable(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("prerequisite_concept_ids")
    @classmethod
    def prerequisites_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("prerequisite concepts must be unique")
        return tuple(
            _visible_id(item, field_name="prerequisite_concept_id") for item in value
        )

    @model_validator(mode="after")
    def correct_matches_score_when_known(self) -> "StudyProgressAssessment":
        if self.correct is not None and self.correct != (self.score >= 0.5):
            raise ValueError("correct must agree with the assessment score")
        return self


class StudyMasteryConcept(_FrozenContract):
    """Deterministic, non-persistent projection for one concept."""

    concept_id: str = Field(min_length=1, max_length=128)
    unit_id: str | None = Field(default=None, max_length=64)
    score: float = Field(ge=0.0, le=1.0)
    status: MasteryStatus
    attempts: int = Field(ge=0, le=MAX_PROJECTION_RECEIPTS)
    last_activity_at: datetime | None = None
    lapses: int = Field(default=0, ge=0, le=MAX_PROJECTION_RECEIPTS)

    @field_validator("concept_id", "unit_id")
    @classmethod
    def concept_ids_are_visible(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _visible_id(value, field_name=str(getattr(info, "field_name", "id")))

    @field_validator("last_activity_at")
    @classmethod
    def activity_time_is_aware(cls, value: datetime | None) -> datetime | None:
        return (
            _aware(value, field_name="last_activity_at") if value is not None else None
        )


class StudyReviewConsistency(_FrozenContract):
    """Review-only counters; the native FSRS state remains untouched."""

    reviews: int = Field(ge=0, le=MAX_PROJECTION_RECEIPTS)
    lapses: int = Field(ge=0, le=MAX_PROJECTION_RECEIPTS)
    due_reviews: int = Field(ge=0, le=MAX_PROJECTION_RECEIPTS)
    on_time_rate: float = Field(ge=0.0, le=1.0)


class StudyAdaptationProposal(_FrozenContract):
    """An inert adaptation suggestion awaiting an explicit user decision."""

    schema_version: Literal[1] = 1
    proposal_id: str = Field(min_length=1, max_length=512)
    concept_id: str | None = Field(default=None, max_length=128)
    unit_id: str | None = Field(default=None, max_length=64)
    action: ProgressAction
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2_000)
    status: ProposalStatus = "proposed"
    available: bool = True

    @field_validator("proposal_id", "concept_id", "unit_id", "title", "rationale")
    @classmethod
    def proposal_text_is_visible(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _visible_id(
            value,
            field_name=str(getattr(info, "field_name", "proposal_text")),
            limit=2_000 if str(getattr(info, "field_name", "")) == "rationale" else 512,
        )


class StudyMasteryProjection(_FrozenContract):
    """Complete deterministic progress response for a single explicit instant."""

    schema_version: Literal[1] = 1
    concepts: tuple[StudyMasteryConcept, ...] = Field(max_length=MAX_CONCEPTS)
    review_consistency: StudyReviewConsistency
    proposals: tuple[StudyAdaptationProposal, ...] = Field(max_length=MAX_PROPOSALS)
    generated_at: datetime
    # Inferred difficulty is intentionally not durable memory.
    memory_writes: tuple[str, ...] = Field(default_factory=tuple, max_length=0)

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_aware(cls, value: datetime) -> datetime:
        return _aware(value, field_name="generated_at")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    details = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(details.encode("utf-8")) > MAX_PROGRESS_DETAILS_BYTES:
        raise ValueError("progress details exceed their bounded UTF-8 size")
    return details


def make_progress_receipt(
    *,
    plan_id: str,
    request_id: str,
    event: Literal[
        "started",
        "completed",
        "assessed",
        "mastery_updated",
        "intervention_proposed",
        "schedule_changed",
        "decision",
        "failed",
        "cancelled",
    ],
    created_at: datetime,
    assessment: StudyProgressAssessment | None = None,
    details: Mapping[str, Any] | None = None,
) -> StudyProgressReceipt:
    """Build a Task 10 receipt with a canonical, versioned Task 14 payload."""

    if assessment is not None and details is not None:
        raise ValueError("supply assessment or details, not both")
    _aware(created_at, field_name="created_at")
    payload: dict[str, Any]
    if assessment is not None:
        payload = {
            "assessment": assessment.model_dump(mode="json"),
            "kind": "assessment",
            "schema_version": 1,
        }
    elif details is not None:
        payload = {
            "details": dict(details),
            "kind": "event",
            "schema_version": 1,
        }
    else:
        payload = {"kind": "event", "schema_version": 1}
    encoded = _canonical_json(payload)
    return StudyProgressReceipt(
        request_id=_nonblank(request_id, field_name="request_id"),
        plan_id=_nonblank(plan_id, field_name="plan_id"),
        event=event,
        details=encoded,
        unit_id=assessment.unit_id if assessment is not None else None,
        created_at=created_at,
    )


def _decode_assessment_strict(details: str) -> StudyProgressAssessment:
    if len(details.encode("utf-8")) > MAX_PROGRESS_DETAILS_BYTES:
        raise ValueError("progress details exceed their bounded UTF-8 size")
    raw = json.loads(details)
    if not isinstance(raw, dict) or set(raw) != {
        "assessment",
        "kind",
        "schema_version",
    }:
        raise ValueError("unsupported progress detail payload")
    if raw.get("schema_version") != 1 or raw.get("kind") != "assessment":
        raise ValueError("unsupported progress detail payload")
    assessment = raw.get("assessment")
    if not isinstance(assessment, dict):
        raise ValueError("assessment payload must be an object")
    return StudyProgressAssessment.model_validate(assessment)


def decode_progress_details(details: str | None) -> StudyProgressAssessment | None:
    """Safely decode current assessments; legacy/malformed details are ignored."""

    if not isinstance(details, str) or not details.startswith("{"):
        return None
    try:
        return _decode_assessment_strict(details)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def decode_progress_event_details(details: str | None) -> dict[str, Any] | None:
    """Decode the small canonical event payload used for decision receipts."""

    if not isinstance(details, str) or not details.startswith("{"):
        return None
    try:
        if len(details.encode("utf-8")) > MAX_PROGRESS_DETAILS_BYTES:
            return None
        raw = json.loads(details)
        if not isinstance(raw, dict) or set(raw) != {
            "details",
            "kind",
            "schema_version",
        }:
            return None
        if raw.get("schema_version") != 1 or raw.get("kind") != "event":
            return None
        values = raw.get("details")
        if not isinstance(values, dict) or len(values) > 8:
            return None
        if any(not isinstance(key, str) or len(key) > 64 for key in values):
            return None
        for value in values.values():
            if isinstance(value, dict):
                if len(value) > 16 or any(
                    not isinstance(key, str) or len(key) > 64 for key in value
                ):
                    return None
                for item in value.values():
                    if isinstance(item, list):
                        if len(item) > 8 or any(
                            not isinstance(entry, str) or len(entry) > 512
                            for entry in item
                        ):
                            return None
                    elif not isinstance(item, (str, int, float, bool)) and item is not None:
                        return None
            elif not isinstance(value, (str, int, float, bool)) and value is not None:
                return None
            if isinstance(value, str) and len(value.encode("utf-8")) > 512:
                return None
        phase = values.get("phase")
        if phase == "intent":
            if set(values) != {
                "base_plan_sha256",
                "base_revision",
                "decision",
                "phase",
                "proposal_id",
                "target_plan_sha256",
                "target_weekly_minutes",
            } or values.get("decision") != "accepted":
                return None
            base_revision = values.get("base_revision")
            proposal_id = values.get("proposal_id")
            target_weekly = values.get("target_weekly_minutes")
            if (
                isinstance(base_revision, bool)
                or not isinstance(base_revision, int)
                or not 1 <= base_revision <= 100_000
                or not isinstance(proposal_id, str)
                or not 1 <= len(proposal_id) <= 512
                or any(ord(char) < 32 or ord(char) == 127 for char in proposal_id)
                or isinstance(target_weekly, bool)
                or not isinstance(target_weekly, int)
                or not 5 <= target_weekly <= 10_080
            ):
                return None
            hashes = (values.get("base_plan_sha256"), values.get("target_plan_sha256"))
            if any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in hashes
            ):
                return None
        elif phase == "completion":
            if values.get("decision") == "dismissed":
                if set(values) != {"decision", "phase", "proposal_id"}:
                    return None
                proposal_id = values.get("proposal_id")
                if (
                    not isinstance(proposal_id, str)
                    or not 1 <= len(proposal_id) <= 512
                    or any(ord(char) < 32 or ord(char) == 127 for char in proposal_id)
                ):
                    return None
            else:
                if set(values) != {
                    "base_plan_sha256",
                    "base_revision",
                    "decision",
                    "intent_request_id",
                    "phase",
                    "proposal_id",
                    "target_plan_sha256",
                } or values.get("decision") != "accepted":
                    return None
                base_revision = values.get("base_revision")
                proposal_id = values.get("proposal_id")
                intent_request_id = values.get("intent_request_id")
                if (
                    isinstance(base_revision, bool)
                    or not isinstance(base_revision, int)
                    or not 1 <= base_revision <= 100_000
                    or not isinstance(proposal_id, str)
                    or not 1 <= len(proposal_id) <= 512
                    or any(ord(char) < 32 or ord(char) == 127 for char in proposal_id)
                    or not isinstance(intent_request_id, str)
                    or not 1 <= len(intent_request_id) <= 256
                    or any(ord(char) < 32 or ord(char) == 127 for char in intent_request_id)
                ):
                    return None
                hashes = (values.get("base_plan_sha256"), values.get("target_plan_sha256"))
                if any(
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value)
                    for value in hashes
                ):
                    return None
        elif phase == "claim":
            decision = values.get("decision")
            if decision == "dismissed":
                expected = {"client_request_id", "decision", "phase", "proposal_id"}
            elif decision == "accepted":
                expected = {
                    "base_plan_sha256",
                    "base_revision",
                    "client_request_id",
                    "decision",
                    "phase",
                    "proposal_id",
                    "target_plan_sha256",
                    "target_weekly_minutes",
                }
            else:
                return None
            if set(values) != expected:
                return None
            proposal_id = values.get("proposal_id")
            client_request_id = values.get("client_request_id")
            if (
                not isinstance(proposal_id, str)
                or not 1 <= len(proposal_id) <= 512
                or any(ord(char) < 32 or ord(char) == 127 for char in proposal_id)
                or not isinstance(client_request_id, str)
                or not 1 <= len(client_request_id) <= 256
                or any(
                    ord(char) < 32 or ord(char) == 127 for char in client_request_id
                )
            ):
                return None
            if decision == "accepted":
                base_revision = values.get("base_revision")
                target_weekly = values.get("target_weekly_minutes")
                if (
                    isinstance(base_revision, bool)
                    or not isinstance(base_revision, int)
                    or not 1 <= base_revision <= 100_000
                    or isinstance(target_weekly, bool)
                    or not isinstance(target_weekly, int)
                    or not 5 <= target_weekly <= 10_080
                ):
                    return None
                hashes = (
                    values.get("base_plan_sha256"),
                    values.get("target_plan_sha256"),
                )
                if any(
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value)
                    for value in hashes
                ):
                    return None
        elif phase == "terminal":
            decision = values.get("decision")
            expected = {
                "claim_request_id",
                "client_request_id",
                "decision",
                "phase",
                "proposal_id",
            }
            if decision == "accepted":
                expected |= {
                    "base_revision",
                    "target_plan_sha256",
                }
            elif decision != "dismissed":
                return None
            if set(values) != expected:
                return None
            proposal_id = values.get("proposal_id")
            client_request_id = values.get("client_request_id")
            claim_request_id = values.get("claim_request_id")
            if (
                not isinstance(proposal_id, str)
                or not 1 <= len(proposal_id) <= 512
                or any(ord(char) < 32 or ord(char) == 127 for char in proposal_id)
                or not isinstance(client_request_id, str)
                or not 1 <= len(client_request_id) <= 256
                or any(
                    ord(char) < 32 or ord(char) == 127 for char in client_request_id
                )
                or not isinstance(claim_request_id, str)
                or not 1 <= len(claim_request_id) <= 256
                or any(
                    ord(char) < 32 or ord(char) == 127 for char in claim_request_id
                )
            ):
                return None
            if decision == "accepted":
                base_revision = values.get("base_revision")
                target_plan_sha256 = values.get("target_plan_sha256")
                if (
                    isinstance(base_revision, bool)
                    or not isinstance(base_revision, int)
                    or not 1 <= base_revision <= 100_000
                    or not isinstance(target_plan_sha256, str)
                    or len(target_plan_sha256) != 64
                    or any(
                        char not in "0123456789abcdef"
                        for char in target_plan_sha256
                    )
                ):
                    return None
        return dict(values)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
def _receipt(value: object) -> StudyProgressReceipt | None:
    if isinstance(value, StudyProgressReceipt):
        return value
    if not isinstance(value, Mapping):
        return None
    try:
        return StudyProgressReceipt.model_validate(dict(value))
    except Exception:
        return None


def _review(value: object) -> tuple[StudyReview, str | None, str | None] | None:
    if isinstance(value, StudyReview):
        return value, None, None
    if not isinstance(value, Mapping):
        return None
    concept_id = value.get("concept_id")
    unit_id = value.get("unit_id")
    try:
        review = StudyReview.model_validate(
            {key: value[key] for key in StudyReview.model_fields if key in value}
        )
    except Exception:
        return None
    return (
        review,
        concept_id if isinstance(concept_id, str) else None,
        unit_id if isinstance(unit_id, str) else None,
    )


def _recency(activity_at: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - activity_at).total_seconds() / 86_400)
    # A bounded hyperbolic decay is stable, simple to explain, and never zeroes
    # out older evidence entirely.
    return 1.0 / (1.0 + min(age_days, 365.0) / 30.0)


def _proposal_id(concept_id: str, action: str) -> str:
    token = hashlib.sha256(f"{concept_id}|{action}".encode("utf-8")).hexdigest()[:24]
    return f"study_adaptation:{token}"


def _decision_request_id(kind: str, plan_id: str, proposal_id: str) -> str:
    """Return a bounded, deterministic receipt identity for a proposal decision."""

    plan_id = _visible_id(plan_id, field_name="plan_id", limit=256)
    proposal_id = _visible_id(proposal_id, field_name="proposal_id", limit=512)
    token = hashlib.sha256(
        f"study-progress|{kind}|{plan_id}|{proposal_id}".encode("utf-8")
    ).hexdigest()
    return f"study_decision_{kind}:{token}"


def decision_claim_request_id(plan_id: str, proposal_id: str) -> str:
    return _decision_request_id("claim", plan_id, proposal_id)


def decision_terminal_request_id(plan_id: str, proposal_id: str) -> str:
    return _decision_request_id("completion", plan_id, proposal_id)


def project_mastery(
    receipts: Iterable[StudyProgressReceipt | Mapping[str, Any]],
    review_receipts: Iterable[StudyReview | Mapping[str, Any]],
    *,
    now: datetime,
) -> StudyMasteryProjection:
    """Project quiz/progress and native review observations without mutation."""

    now = _aware(now, field_name="now")
    normalized_receipts: list[StudyProgressReceipt] = []
    for value in itertools.islice(receipts, MAX_PROJECTION_RECEIPTS):
        item = _receipt(value)
        if item is not None:
            normalized_receipts.append(item)
    # Request IDs are the receipt identity.  Choosing a canonical minimum for
    # malformed duplicate payloads makes projections independent of input order.
    by_request: dict[str, StudyProgressReceipt] = {}
    for item in normalized_receipts:
        existing = by_request.get(item.request_id)
        item_key = json.dumps(
            item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        existing_key = (
            json.dumps(
                existing.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )
            if existing is not None
            else None
        )
        if existing is None or item_key < existing_key:
            by_request[item.request_id] = item

    decision_status: dict[str, ProposalStatus] = {}
    for item in sorted(
        by_request.values(), key=lambda value: (value.created_at, value.request_id)
    ):
        if item.created_at > now:
            continue
        if item.event != "decision":
            continue
        details = decode_progress_event_details(item.details)
        if details is None or details.get("phase", "completion") not in {
            "completion",
            "terminal",
        }:
            continue
        proposal_id = details.get("proposal_id")
        decision = details.get("decision")
        if isinstance(proposal_id, str) and decision in {"accepted", "dismissed"}:
            decision_status[proposal_id] = decision  # type: ignore[assignment]

    observations: dict[
        str, list[tuple[float, float, datetime, str | None, tuple[str, ...]]]
    ] = {}
    for item in sorted(
        by_request.values(), key=lambda value: (value.created_at, value.request_id)
    ):
        if item.created_at > now:
            continue
        assessment = decode_progress_details(item.details)
        if assessment is None:
            continue
        bucket = observations.setdefault(assessment.concept_id, [])
        bucket.append(
            (
                assessment.score,
                assessment.weight * _recency(item.created_at, now),
                item.created_at,
                assessment.unit_id,
                assessment.prerequisite_concept_ids,
            )
        )

    review_stats: dict[str, list[tuple[float, float, datetime, int, bool]]] = {}
    review_count = 0
    lapses = 0
    on_time = 0
    latest_card_state: dict[str, tuple[datetime, str, str, bool]] = {}
    for raw in itertools.islice(review_receipts, MAX_PROJECTION_RECEIPTS):
        normalized = _review(raw)
        if normalized is None:
            continue
        review, explicit_concept_id, explicit_unit_id = normalized
        if review.reviewed_at > now:
            continue
        review_count += 1
        # ``lapse_count_after`` is cumulative card state, not an event count;
        # only the current Again rating represents a new lapse.
        is_lapse = review.rating == StudyRating.AGAIN
        lapses += int(is_lapse)
        due = review.fsrs_state_after.due <= now
        on_time += int(review.reviewed_at <= review.fsrs_state_before.due)
        concept_id = explicit_concept_id or review.card_id
        review_key = review.request_id or review.id or ""
        previous_state = latest_card_state.get(review.card_id)
        if previous_state is None or (review.reviewed_at, review_key) > (
            previous_state[0],
            previous_state[1],
        ):
            latest_card_state[review.card_id] = (
                review.reviewed_at,
                review_key,
                concept_id,
                due,
            )
        rating_score = {
            StudyRating.AGAIN: 0.0,
            StudyRating.HARD: 0.45,
            StudyRating.GOOD: 0.8,
            StudyRating.EASY: 1.0,
        }[review.rating]
        review_stats.setdefault(concept_id, []).append(
            (
                rating_score,
                _recency(review.reviewed_at, now),
                review.reviewed_at,
                int(is_lapse),
                due,
            )
        )
        if (
            explicit_concept_id
            and explicit_unit_id
            and explicit_concept_id not in observations
        ):
            observations[explicit_concept_id] = []

    due_reviews = sum(int(state[3]) for state in latest_card_state.values())
    latest_due_concepts = {
        state[2] for state in latest_card_state.values() if state[3]
    }

    concepts: list[StudyMasteryConcept] = []
    prerequisite_by_concept: dict[str, tuple[str, ...]] = {}
    all_concept_ids = sorted(set(observations) | set(review_stats))[:MAX_CONCEPTS]
    for concept_id in all_concept_ids:
        assessment_values = observations.get(concept_id, [])
        review_values = review_stats.get(concept_id, [])
        weighted = [(score, weight) for score, weight, *_rest in assessment_values]
        weighted.extend((score, weight) for score, weight, *_rest in review_values)
        total_weight = sum(weight for _score, weight in weighted)
        score = (
            sum(value * weight for value, weight in weighted) / total_weight
            if total_weight
            else 0.0
        )
        attempts = min(
            MAX_PROJECTION_RECEIPTS, len(assessment_values) + len(review_values)
        )
        times = [entry[2] for entry in assessment_values] + [
            entry[2] for entry in review_values
        ]
        unit_id = next((entry[3] for entry in assessment_values if entry[3]), None)
        lapses_for_concept = sum(entry[3] for entry in review_values)
        status: MasteryStatus = (
            "mastered"
            if score >= 0.8
            else "developing"
            if score >= 0.6
            else "needs_review"
        )
        concepts.append(
            StudyMasteryConcept(
                concept_id=concept_id,
                unit_id=unit_id,
                score=max(0.0, min(1.0, score)),
                status=status,
                attempts=attempts,
                last_activity_at=max(times) if times else None,
                lapses=lapses_for_concept,
            )
        )
        if assessment_values:
            prerequisite_by_concept[concept_id] = assessment_values[-1][4]

    proposals: list[tuple[int, str, str, StudyAdaptationProposal]] = []
    for concept in concepts:
        prerequisites = prerequisite_by_concept.get(concept.concept_id, ())
        if concept.status == "needs_review" and prerequisites:
            proposals.append(
                (
                    0,
                    concept.concept_id,
                    "prerequisite_detour",
                    StudyAdaptationProposal(
                        proposal_id=_proposal_id(
                            concept.concept_id, "prerequisite_detour"
                        ),
                        concept_id=concept.concept_id,
                        unit_id=concept.unit_id,
                        action="prerequisite_detour",
                        title="Review the prerequisite first",
                        rationale="A prerequisite concept is still weak; detour before advancing.",
                        status=decision_status.get(
                            _proposal_id(concept.concept_id, "prerequisite_detour"),
                            "proposed",
                        ),
                    ),
                )
            )
        if concept.concept_id in latest_due_concepts:
            proposals.append(
                (
                    1,
                    concept.concept_id,
                    "schedule_review",
                    StudyAdaptationProposal(
                        proposal_id=_proposal_id(concept.concept_id, "schedule_review"),
                        concept_id=concept.concept_id,
                        unit_id=concept.unit_id,
                        action="schedule_review",
                        title="Schedule another review",
                        rationale="A native FSRS review is due; schedule it through the existing review flow.",
                        status=decision_status.get(
                            _proposal_id(concept.concept_id, "schedule_review"),
                            "proposed",
                        ),
                    ),
                )
            )
        elif concept.status == "developing":
            proposals.append(
                (
                    2,
                    concept.concept_id,
                    "extra_practice",
                    StudyAdaptationProposal(
                        proposal_id=_proposal_id(concept.concept_id, "extra_practice"),
                        concept_id=concept.concept_id,
                        unit_id=concept.unit_id,
                        action="extra_practice",
                        title="Add a short practice block",
                        rationale="Recent evidence is developing; another bounded practice block may help.",
                        status=decision_status.get(
                            _proposal_id(concept.concept_id, "extra_practice"),
                            "proposed",
                        ),
                    ),
                )
            )

    proposals = sorted(proposals, key=lambda row: row[:3])[:MAX_PROPOSALS]
    return StudyMasteryProjection(
        concepts=tuple(concept for concept in concepts),
        review_consistency=StudyReviewConsistency(
            reviews=review_count,
            lapses=lapses,
            due_reviews=due_reviews,
            on_time_rate=on_time / review_count if review_count else 0.0,
        ),
        proposals=tuple(item[3] for item in proposals),
        generated_at=now,
        memory_writes=(),
    )


__all__ = [
    "MAX_PROGRESS_DETAILS_BYTES",
    "MasteryStatus",
    "ProgressAction",
    "StudyAdaptationProposal",
    "StudyMasteryConcept",
    "StudyMasteryProjection",
    "StudyProgressAssessment",
    "StudyProgressReceipt",
    "StudyReviewConsistency",
    "decode_progress_details",
    "decode_progress_event_details",
    "decision_claim_request_id",
    "decision_terminal_request_id",
    "make_progress_receipt",
    "project_mastery",
]
