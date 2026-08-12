"""Feature-gated, projection-only HTTP endpoints for Study Workbench plans."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.schemas.study_plans import (
    ApproveSyllabusRequest,
    CreateStudyPlanRequest,
    GenerateStudyArtifactsRequest,
    GenerateStudyArtifactsResponse,
    PatchStudyPlanRequest,
    ProposeSyllabusRequest,
    RemoveSourceLinkRequest,
    RemoveSourceLinkResponse,
    SaveSyllabusRequest,
    SourceLinkRequest,
    StudyPlanResponse,
    StudyPlanSourceLinkResponse,
    StudyProgressDecisionRequest,
    StudyProgressDecisionResponse,
    StudySourceReadinessResponse,
    StudySyllabusResponse,
)
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.artifact_service import (
    StudyArtifactCancelled,
    StudyArtifactConflict,
    StudyArtifactError,
    StudyArtifactGenerationError,
    StudyArtifactNotFound,
    StudyArtifactService,
    StudyArtifactUnavailable,
)
from deeper_notebook.study.assistant_repository import (
    StudyAssistantConflictError,
    StudyAssistantNotFoundError,
    StudyAssistantRepositoryError,
    StudyAssistantUnavailableError,
)
from deeper_notebook.study.plan_repository import (
    StudyPlanConflictError,
    StudyPlanNotFoundError,
    StudyPlanRepository,
    StudyPlanRepositoryError,
)
from deeper_notebook.study.plans import StudyPlan, StudyPlanPreferences
from deeper_notebook.study.progress import (
    StudyMasteryProjection,
    decision_claim_request_id,
    decision_terminal_request_id,
    make_progress_receipt,
)
from deeper_notebook.study.progress_repository import (
    StudyProgressRepository,
    StudyProgressRepositoryError,
)
from deeper_notebook.study.source_service import (
    StudySourceNotFoundError,
    StudySourceService,
    StudySourceUnavailableError,
    normalize_source_id,
)
from deeper_notebook.study.syllabus_service import (
    StudySyllabusConflict,
    StudySyllabusError,
    StudySyllabusGenerationError,
    StudySyllabusMalformedOutput,
    StudySyllabusNotFound,
    StudySyllabusService,
)


def _repository() -> StudyPlanRepository:
    return StudyPlanRepository()


def _progress_repository() -> StudyProgressRepository:
    return StudyProgressRepository()


def _require_study_workbench() -> None:
    if not study_workbench_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found"
        )


router = APIRouter(
    prefix="/study/plans",
    tags=["study-plans"],
    dependencies=[Depends(_require_study_workbench)],
)


def _not_found(detail: str = "Study plan not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _repository_error(exc: StudyPlanRepositoryError) -> HTTPException:
    """Project only safe, action-relevant persistence failures to HTTP."""
    if isinstance(exc, StudyPlanNotFoundError):
        return _not_found()
    if isinstance(exc, StudyPlanConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Study plan changed"
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Study plans are unavailable",
    )


async def _existing_plan(plan_id: str) -> StudyPlanResponse:
    plan = await _load_plan(plan_id)
    return StudyPlanResponse.from_plan(plan)


async def _load_plan(plan_id: str) -> StudyPlan:
    try:
        plan = await _repository().get(plan_id)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if plan is None:
        raise _not_found()
    return plan


def _source_error(
    exc: StudySourceNotFoundError | StudySourceUnavailableError,
) -> HTTPException:
    if isinstance(exc, StudySourceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Sources are unavailable",
    )


def _syllabus_error(exc: StudySyllabusError) -> HTTPException:
    """Map typed syllabus failures to bounded, non-disclosing HTTP details."""
    if isinstance(exc, StudySyllabusNotFound):
        return _not_found("Study syllabus not found")
    if isinstance(exc, StudySyllabusMalformedOutput):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.reason, "message": "Generated syllabus is invalid"},
        )
    if isinstance(exc, StudySyllabusConflict):
        message = {
            "sources_changed": "Study sources changed; review the syllabus again",
            "sources_not_ready": "Study sources are not ready",
            "no_evidence": "Study syllabus requires source evidence",
            "invalid_lifecycle": "Study plan cannot approve this syllabus",
            "already_approved": "Study syllabus is already approved",
            "revision_conflict": "Study plan changed",
        }.get(exc.reason, "Study syllabus changed")
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.reason, "message": message},
        )
    if isinstance(exc, StudySyllabusGenerationError) or exc.code in {
        "syllabus_unavailable",
        "model_unavailable",
        "source_authority_unavailable",
    }:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.reason,
                "message": "Syllabus generation is unavailable",
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "syllabus_unavailable",
            "message": "Syllabus generation is unavailable",
        },
    )


def _artifact_error(exc: StudyArtifactError) -> HTTPException:
    """Map study-artifact domain failures without exposing provider details."""
    if isinstance(exc, StudyArtifactNotFound):
        return _not_found("Study artifact or unit not found")
    if isinstance(exc, StudyArtifactConflict):
        allowed_reasons = {
            "syllabus_not_approved",
            "revision_conflict",
            "sources_not_ready",
            "sources_changed",
            "manifest_mismatch",
            "unit_source_not_linked",
        }
        reason = exc.reason if exc.reason in allowed_reasons else exc.code
        if reason.startswith("invalid_") or reason.endswith("_bounds"):
            return HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": reason, "message": "Invalid study artifact request"},
            )
        message = {
            "syllabus_not_approved": "Study syllabus is not approved",
            "revision_conflict": "Study plan changed",
            "sources_not_ready": "Study sources are not ready",
            "sources_changed": "Study sources changed; review the syllabus again",
            "manifest_mismatch": "Study syllabus evidence binding is invalid",
            "unit_source_not_linked": "Study unit source coverage is invalid",
        }.get(reason, "Study artifact generation is not currently allowed")
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": reason, "message": message},
        )
    if isinstance(exc, StudyArtifactCancelled):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.reason,
                "message": "Study artifact generation was cancelled",
            },
        )
    if isinstance(exc, (StudyArtifactGenerationError, StudyArtifactUnavailable)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": exc.code,
                "message": "Study artifact generation is unavailable",
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "artifact_unavailable",
            "message": "Study artifact generation is unavailable",
        },
    )


def _progress_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (StudyPlanNotFoundError, StudyAssistantNotFoundError)):
        return _not_found()
    if isinstance(exc, (StudyPlanConflictError, StudyAssistantConflictError)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "progress_conflict", "message": "Study progress changed"},
        )
    if isinstance(exc, StudyProgressRepositoryError) and "invalid" in str(exc).lower():
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_progress_request",
                "message": "Invalid study progress request",
            },
        )
    if isinstance(exc, StudyAssistantRepositoryError) and isinstance(
        exc, StudyAssistantUnavailableError
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "progress_unavailable",
                "message": "Study progress is unavailable",
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "progress_unavailable",
            "message": "Study progress is unavailable",
        },
    )


def _progress_now(value: datetime | None) -> datetime:
    now = value or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_progress_timestamp",
                "message": "Progress time must include a timezone",
            },
        )
    return now


def _projection_for_plan(projection: StudyMasteryProjection, plan: StudyPlan):
    """Expose only the one bounded proposal backed by an existing mutation."""
    preferences = plan.preferences
    can_add_practice = (
        preferences is not None
        and plan.state in {"approved", "generating", "active", "completed"}
        and preferences.weekly_minutes + preferences.session_minutes <= 10_080
    )
    return projection.model_copy(
        update={
            "proposals": tuple(
                proposal.model_copy(
                    update={
                        "available": proposal.action == "extra_practice"
                        and proposal.status == "proposed"
                        and can_add_practice
                    }
                )
                for proposal in projection.proposals
            )
        }
    )


def _plan_fingerprint(
    plan: StudyPlan,
    *,
    preferences: StudyPlanPreferences | None = None,
) -> str:
    """Hash mutation-relevant plan authority, excluding volatile timestamps/version."""
    payload = {
        "goal": plan.goal,
        "starting_level": plan.starting_level,
        "target_date": plan.target_date.isoformat() if plan.target_date else None,
        "preferences": (preferences or plan.preferences).model_dump(mode="json")
        if (preferences or plan.preferences) is not None
        else None,
        "source_links": [link.model_dump(mode="json") for link in plan.source_links],
        "source_manifest_sha256": plan.source_manifest_sha256,
        "approved_syllabus_version": plan.approved_syllabus_version,
        "state": plan.state,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _completion_request_id(plan_id: str, request_id: str) -> str:
    token = hashlib.sha256(f"{plan_id}|{request_id}|completion".encode()).hexdigest()
    return f"study_decision_completion:{token}"


def _intent_payload(
    *,
    proposal_id: str,
    base_revision: int,
    base_plan_sha256: str,
    target_plan_sha256: str,
    target_weekly_minutes: int,
) -> dict[str, object]:
    return {
        "base_revision": base_revision,
        "base_plan_sha256": base_plan_sha256,
        "decision": "accepted",
        "phase": "intent",
        "proposal_id": proposal_id,
        "target_plan_sha256": target_plan_sha256,
        "target_weekly_minutes": target_weekly_minutes,
    }


def _completion_payload(
    *,
    proposal_id: str,
    base_revision: int,
    base_plan_sha256: str,
    target_plan_sha256: str,
    intent_request_id: str,
) -> dict[str, object]:
    return {
        "base_revision": base_revision,
        "base_plan_sha256": base_plan_sha256,
        "decision": "accepted",
        "intent_request_id": intent_request_id,
        "phase": "completion",
        "proposal_id": proposal_id,
        "target_plan_sha256": target_plan_sha256,
    }


def _claim_payload(
    *,
    client_request_id: str,
    decision: str,
    proposal_id: str,
    base_revision: int | None = None,
    base_plan_sha256: str | None = None,
    target_plan_sha256: str | None = None,
    target_weekly_minutes: int | None = None,
) -> dict[str, object]:
    if decision == "dismissed":
        return {
            "client_request_id": client_request_id,
            "decision": decision,
            "phase": "claim",
            "proposal_id": proposal_id,
        }
    return {
        "base_plan_sha256": base_plan_sha256,
        "base_revision": base_revision,
        "client_request_id": client_request_id,
        "decision": "accepted",
        "phase": "claim",
        "proposal_id": proposal_id,
        "target_plan_sha256": target_plan_sha256,
        "target_weekly_minutes": target_weekly_minutes,
    }


def _terminal_payload(
    *,
    claim_request_id: str,
    client_request_id: str,
    decision: str,
    proposal_id: str,
    base_revision: int | None = None,
    target_plan_sha256: str | None = None,
) -> dict[str, object]:
    if decision == "dismissed":
        return {
            "claim_request_id": claim_request_id,
            "client_request_id": client_request_id,
            "decision": decision,
            "phase": "terminal",
            "proposal_id": proposal_id,
        }
    return {
        "base_revision": base_revision,
        "claim_request_id": claim_request_id,
        "client_request_id": client_request_id,
        "decision": "accepted",
        "phase": "terminal",
        "proposal_id": proposal_id,
        "target_plan_sha256": target_plan_sha256,
    }


def _progress_details(receipt: object) -> dict[str, object] | None:
    from deeper_notebook.study.progress import decode_progress_event_details

    return decode_progress_event_details(getattr(receipt, "details", None))


def _receipt_envelope_matches(
    receipt: object,
    *,
    plan_id: str,
    request_id: str,
    now: datetime,
) -> bool:
    """Require a deterministic decision receipt envelope before its details."""

    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return False
    if getattr(receipt, "event", None) != "decision":
        return False
    if str(getattr(receipt, "plan_id", "")) != plan_id:
        return False
    if getattr(receipt, "request_id", None) != request_id:
        return False
    created_at = getattr(receipt, "created_at", None)
    return bool(
        isinstance(created_at, datetime)
        and created_at.tzinfo is not None
        and created_at.utcoffset() is not None
        and created_at <= now
    )


def _strict_decision_details(
    receipt: object,
    *,
    phase: str,
    plan_id: str,
    request_id: str,
    now: datetime,
) -> dict[str, object] | None:
    if not _receipt_envelope_matches(
        receipt, plan_id=plan_id, request_id=request_id, now=now
    ):
        return None
    details = _progress_details(receipt)
    if details is None:
        return None
    expected = {
        "intent": {
            "base_plan_sha256",
            "base_revision",
            "decision",
            "phase",
            "proposal_id",
            "target_plan_sha256",
            "target_weekly_minutes",
        },
        "completion": {
            "base_plan_sha256",
            "base_revision",
            "decision",
            "intent_request_id",
            "phase",
            "proposal_id",
            "target_plan_sha256",
        },
    }[phase]
    if set(details) != expected or details.get("phase") != phase or details.get("decision") != "accepted":
        return None
    base_revision = details.get("base_revision")
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) or not 1 <= base_revision <= 100_000:
        return None
    proposal_id = details.get("proposal_id")
    if not isinstance(proposal_id, str) or not 1 <= len(proposal_id) <= 512 or any(ord(char) < 32 for char in proposal_id):
        return None
    for key in ("base_plan_sha256", "target_plan_sha256"):
        value = details.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            return None
    if phase == "intent":
        target_weekly = details.get("target_weekly_minutes")
        if isinstance(target_weekly, bool) or not isinstance(target_weekly, int) or not 5 <= target_weekly <= 10_080:
            return None
    else:
        intent_request_id = details.get("intent_request_id")
        if not isinstance(intent_request_id, str) or not 1 <= len(intent_request_id) <= 256 or any(ord(char) < 32 for char in intent_request_id):
            return None
    return details


def _strict_dismiss_details(receipt: object, *, proposal_id: str) -> bool:
    details = _progress_details(receipt)
    return bool(
        details is not None
        and set(details) == {"decision", "phase", "proposal_id"}
        and details.get("decision") == "dismissed"
        and details.get("phase") == "completion"
        and details.get("proposal_id") == proposal_id
    )


def _strict_claim_details(
    receipt: object,
    *,
    plan_id: str,
    request_id: str,
    proposal_id: str,
    client_request_id: str,
    decision: str,
    now: datetime,
) -> dict[str, object] | None:
    if not _receipt_envelope_matches(
        receipt, plan_id=plan_id, request_id=request_id, now=now
    ):
        return None
    details = _progress_details(receipt)
    if details is None or details.get("phase") != "claim":
        return None
    expected = (
        {"client_request_id", "decision", "phase", "proposal_id"}
        if decision == "dismissed"
        else {
            "base_plan_sha256",
            "base_revision",
            "client_request_id",
            "decision",
            "phase",
            "proposal_id",
            "target_plan_sha256",
            "target_weekly_minutes",
        }
    )
    if decision not in {"accepted", "dismissed"} or set(details) != expected:
        return None
    if (
        details.get("decision") != decision
        or details.get("proposal_id") != proposal_id
        or details.get("client_request_id") != client_request_id
    ):
        return None
    if decision == "accepted":
        base_revision = details.get("base_revision")
        target_weekly = details.get("target_weekly_minutes")
        if (
            isinstance(base_revision, bool)
            or not isinstance(base_revision, int)
            or not 1 <= base_revision <= 100_000
            or isinstance(target_weekly, bool)
            or not isinstance(target_weekly, int)
            or not 5 <= target_weekly <= 10_080
        ):
            return None
        for key in ("base_plan_sha256", "target_plan_sha256"):
            value = details.get(key)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                return None
    return details


def _strict_terminal_details(
    receipt: object,
    *,
    plan_id: str,
    request_id: str,
    proposal_id: str,
    client_request_id: str,
    decision: str,
    claim_request_id: str,
    now: datetime,
) -> dict[str, object] | None:
    if not _receipt_envelope_matches(
        receipt, plan_id=plan_id, request_id=request_id, now=now
    ):
        return None
    details = _progress_details(receipt)
    if details is None or details.get("phase") != "terminal":
        return None
    expected = (
        {"claim_request_id", "client_request_id", "decision", "phase", "proposal_id"}
        if decision == "dismissed"
        else {
            "base_revision",
            "claim_request_id",
            "client_request_id",
            "decision",
            "phase",
            "proposal_id",
            "target_plan_sha256",
        }
    )
    if decision not in {"accepted", "dismissed"} or set(details) != expected:
        return None
    if (
        details.get("decision") != decision
        or details.get("proposal_id") != proposal_id
        or details.get("client_request_id") != client_request_id
        or details.get("claim_request_id") != claim_request_id
    ):
        return None
    if decision == "accepted":
        base_revision = details.get("base_revision")
        if (
            isinstance(base_revision, bool)
            or not isinstance(base_revision, int)
            or not 1 <= base_revision <= 100_000
        ):
            return None
        for key in ("target_plan_sha256",):
            value = details.get(key)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                return None
    return details


def _terminal_matches_claim(
    terminal_details: dict[str, object],
    claim_details: dict[str, object],
    *,
    decision: str,
) -> bool:
    """Bind the terminal receipt to the exact earlier proposal claim."""

    shared = ("client_request_id", "decision", "proposal_id")
    if any(terminal_details.get(key) != claim_details.get(key) for key in shared):
        return False
    if decision == "accepted":
        return all(
            terminal_details.get(key) == claim_details.get(key)
            for key in ("base_revision", "target_plan_sha256")
        )
    return True


async def _accept_study_plan_progress(
    *,
    plan_id: str,
    plan: StudyPlan,
    selected_id: str,
    payload: StudyProgressDecisionRequest,
    repository: StudyProgressRepository,
    projection: StudyMasteryProjection,
    visible_projection: StudyMasteryProjection,
    now: datetime,
) -> StudyProgressDecisionResponse:
    """Serialize one proposal decision before any plan mutation."""

    claim_id = decision_claim_request_id(plan_id, selected_id)
    terminal_id = decision_terminal_request_id(plan_id, selected_id)

    # A deterministic terminal is checked first so retries remain valid even
    # when the proposal has aged out of the ordinary projection page.
    existing_terminal = await repository.get_progress_by_request(plan_id, terminal_id)
    if existing_terminal is not None:
        terminal_details = _strict_terminal_details(
            existing_terminal,
            plan_id=plan_id,
            request_id=terminal_id,
            proposal_id=selected_id,
            client_request_id=payload.request_id,
            decision="accepted",
            claim_request_id=claim_id,
            now=now,
        )
        terminal_claim = await repository.get_progress_by_request(plan_id, claim_id)
        terminal_claim_details = (
            _strict_claim_details(
                terminal_claim,
                plan_id=plan_id,
                request_id=claim_id,
                proposal_id=selected_id,
                client_request_id=payload.request_id,
                decision="accepted",
                now=now,
            )
            if terminal_claim is not None
            else None
        )
        if (
            terminal_details is None
            or terminal_claim_details is None
            or not _terminal_matches_claim(
                terminal_details, terminal_claim_details, decision="accepted"
            )
            or payload.expected_revision != terminal_claim_details.get("base_revision")
            or getattr(existing_terminal, "created_at", None)
            < getattr(terminal_claim, "created_at", None)
        ):
            raise StudyAssistantConflictError("proposal decision was already used")
        current_plan = await _load_plan(plan_id)
        base_revision = terminal_claim_details.get("base_revision")
        target_plan_sha256 = terminal_claim_details.get("target_plan_sha256")
        if (
            current_plan.version != base_revision + 1
            or _plan_fingerprint(current_plan) != target_plan_sha256
        ):
            raise StudyAssistantConflictError("study plan authority changed")
        return StudyProgressDecisionResponse(
            proposal_id=selected_id,
            decision="accepted",
            projection=_projection_for_plan(
                await repository.project(plan_id, now=now), current_plan
            ),
        )

    claim = await repository.get_progress_by_request(plan_id, claim_id)
    claim_details = (
        _strict_claim_details(
            claim,
            plan_id=plan_id,
            request_id=claim_id,
            proposal_id=selected_id,
            client_request_id=payload.request_id,
            decision="accepted",
            now=now,
        )
        if claim is not None
        else None
    )
    if claim is not None and claim_details is None:
        raise StudyAssistantConflictError("proposal decision claim was already used")

    # Legacy client-keyed intent/completion records are retained for safe
    # migration and corruption detection, but never bypass the deterministic
    # claim identity.
    completion_id = _completion_request_id(plan_id, payload.request_id)
    legacy_completion = await repository.get_progress_by_request(plan_id, completion_id)
    if legacy_completion is not None:
        legacy_details = _strict_decision_details(
            legacy_completion,
            phase="completion",
            plan_id=plan_id,
            request_id=completion_id,
            now=now,
        )
        legacy_intent = await repository.get_progress_by_request(plan_id, payload.request_id)
        legacy_intent_details = (
            _strict_decision_details(
                legacy_intent,
                phase="intent",
                plan_id=plan_id,
                request_id=payload.request_id,
                now=now,
            )
            if legacy_intent is not None
            else None
        )
        if (
            legacy_details is None
            or legacy_intent_details is None
            or legacy_details.get("proposal_id") != selected_id
            or legacy_details.get("intent_request_id") != payload.request_id
            or legacy_intent_details.get("proposal_id") != selected_id
            or payload.expected_revision != legacy_intent_details.get("base_revision")
        ):
            raise StudyAssistantConflictError("progress request ID was already used")
        raise StudyAssistantConflictError("legacy proposal decision requires retry")

    existing_intent = await repository.get_progress_by_request(plan_id, payload.request_id)
    intent_details = (
        _strict_decision_details(
            existing_intent,
            phase="intent",
            plan_id=plan_id,
            request_id=payload.request_id,
            now=now,
        )
        if existing_intent is not None
        else None
    )
    if existing_intent is not None and (
        intent_details is None or intent_details.get("proposal_id") != selected_id
    ):
        raise StudyAssistantConflictError("progress request ID was already used")

    if claim_details is not None:
        base_revision = claim_details.get("base_revision")
        base_plan_sha256 = claim_details.get("base_plan_sha256")
        target_plan_sha256 = claim_details.get("target_plan_sha256")
        target_weekly_minutes = claim_details.get("target_weekly_minutes")
    elif intent_details is not None:
        base_revision = intent_details.get("base_revision")
        base_plan_sha256 = intent_details.get("base_plan_sha256")
        target_plan_sha256 = intent_details.get("target_plan_sha256")
        target_weekly_minutes = intent_details.get("target_weekly_minutes")
    else:
        proposal = next(
            (item for item in visible_projection.proposals if item.proposal_id == selected_id),
            None,
        )
        if proposal is None:
            raise StudyAssistantNotFoundError("study adaptation proposal not found")
        if (
            not proposal.available
            or proposal.action != "extra_practice"
            or plan.preferences is None
            or payload.expected_revision is None
            or plan.version != payload.expected_revision
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "adaptation_unavailable", "message": "This study adaptation is unavailable"},
            )
        base_revision = payload.expected_revision
        base_plan_sha256 = _plan_fingerprint(plan)
        target_preferences = plan.preferences.model_copy(
            update={
                "weekly_minutes": plan.preferences.weekly_minutes
                + plan.preferences.session_minutes
            }
        )
        target_weekly_minutes = target_preferences.weekly_minutes
        target_plan_sha256 = _plan_fingerprint(plan, preferences=target_preferences)

    if (
        not isinstance(base_revision, int)
        or not isinstance(base_plan_sha256, str)
        or not isinstance(target_plan_sha256, str)
        or not isinstance(target_weekly_minutes, int)
        or plan.preferences is None
        or payload.expected_revision != base_revision
    ):
        raise StudyAssistantConflictError("proposal decision authority mismatch")
    target_preferences = plan.preferences.model_copy(
        update={"weekly_minutes": target_weekly_minutes}
    )
    if claim_details is not None:
        if _plan_fingerprint(plan) not in {base_plan_sha256, target_plan_sha256}:
            # The only permitted post-mutation state is the exact target.
            if plan.version != base_revision + 1 or _plan_fingerprint(plan) != target_plan_sha256:
                raise StudyAssistantConflictError("study plan authority changed")
    else:
        # The claim is the shared serialization point.  It is appended before
        # intent and before update so a competing decision cannot mutate.
        claim_receipt = make_progress_receipt(
            plan_id=plan_id,
            request_id=claim_id,
            event="decision",
            created_at=now,
            details=_claim_payload(
                client_request_id=payload.request_id,
                decision="accepted",
                proposal_id=selected_id,
                base_revision=base_revision,
                base_plan_sha256=base_plan_sha256,
                target_plan_sha256=target_plan_sha256,
                target_weekly_minutes=target_weekly_minutes,
            ),
        )
        await repository.append_progress(claim_receipt)

    if existing_intent is None:
        intent = make_progress_receipt(
            plan_id=plan_id,
            request_id=payload.request_id,
            event="decision",
            created_at=now,
            details=_intent_payload(
                proposal_id=selected_id,
                base_revision=base_revision,
                base_plan_sha256=base_plan_sha256,
                target_plan_sha256=target_plan_sha256,
                target_weekly_minutes=target_weekly_minutes,
            ),
        )
        await repository.append_progress(intent)

    if plan.version == base_revision:
        if (
            _plan_fingerprint(plan) != base_plan_sha256
            or _plan_fingerprint(plan, preferences=target_preferences) != target_plan_sha256
        ):
            raise StudyAssistantConflictError("study plan authority changed")
        try:
            current = await _repository().update(
                plan_id,
                {"preferences": target_preferences},
                expected_revision=base_revision,
            )
        except StudyPlanRepositoryError as exc:
            raise _repository_error(exc) from None
    elif plan.version == base_revision + 1:
        if _plan_fingerprint(plan) != target_plan_sha256:
            raise StudyAssistantConflictError("study plan authority changed")
        current = plan
    else:
        raise StudyAssistantConflictError("study plan authority changed")

    terminal = make_progress_receipt(
        plan_id=plan_id,
        request_id=terminal_id,
        event="decision",
        created_at=now,
        details=_terminal_payload(
            claim_request_id=claim_id,
            client_request_id=payload.request_id,
            decision="accepted",
            proposal_id=selected_id,
            base_revision=base_revision,
            target_plan_sha256=target_plan_sha256,
        ),
    )
    await repository.append_progress(terminal)
    refreshed = await repository.project(plan_id, now=now)
    current_plan = await _load_plan(plan_id)
    return StudyProgressDecisionResponse(
        proposal_id=selected_id,
        decision="accepted",
        projection=_projection_for_plan(refreshed, current_plan),
    )


@router.post("", response_model=StudyPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_study_plan(payload: CreateStudyPlanRequest) -> StudyPlanResponse:
    try:
        return StudyPlanResponse.from_plan(
            await _repository().create(payload.to_plan())
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None


@router.get("", response_model=list[StudyPlanResponse])
async def list_study_plans(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100_000),
) -> list[StudyPlanResponse]:
    try:
        plans = await _repository().list(limit=limit, offset=offset)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return [StudyPlanResponse.from_plan(plan) for plan in plans]


@router.get("/{plan_id}/progress", response_model=StudyMasteryProjection)
async def get_study_plan_progress(
    plan_id: str,
    limit: int = Query(default=50, ge=1, le=50),
    now: datetime | None = Query(default=None),
):
    """Return a deterministic mastery projection over bounded progress/reviews."""
    plan = await _load_plan(plan_id)
    try:
        projection = await _progress_repository().project(
            plan_id,
            now=_progress_now(now),
            limit=limit,
        )
    except (StudyProgressRepositoryError, StudyAssistantRepositoryError) as exc:
        raise _progress_error(exc) from None
    return _projection_for_plan(projection, plan)


async def _decide_study_plan_progress(
    plan_id: str,
    payload: StudyProgressDecisionRequest,
    *,
    proposal_id: str | None = None,
) -> StudyProgressDecisionResponse:
    plan = await _load_plan(plan_id)
    selected_id = proposal_id or payload.proposal_id
    if proposal_id is not None and payload.proposal_id != proposal_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "proposal_id_mismatch",
                "message": "Invalid study progress request",
            },
        )
    try:
        now = datetime.now(UTC)
        repository = _progress_repository()
        projection = await repository.project(plan_id, now=now)
        visible_projection = _projection_for_plan(projection, plan)
        if payload.decision == "accepted":
            return await _accept_study_plan_progress(
                plan_id=plan_id,
                plan=plan,
                selected_id=selected_id,
                payload=payload,
                repository=repository,
                projection=projection,
                visible_projection=visible_projection,
                now=now,
            )
        claim_id = decision_claim_request_id(plan_id, selected_id)
        terminal_id = decision_terminal_request_id(plan_id, selected_id)
        existing_terminal = await repository.get_progress_by_request(plan_id, terminal_id)
        if existing_terminal is not None:
            terminal_details = _strict_terminal_details(
                existing_terminal,
                plan_id=plan_id,
                request_id=terminal_id,
                proposal_id=selected_id,
                client_request_id=payload.request_id,
                decision="dismissed",
                claim_request_id=claim_id,
                now=now,
            )
            terminal_claim = await repository.get_progress_by_request(plan_id, claim_id)
            terminal_claim_details = (
                _strict_claim_details(
                    terminal_claim,
                    plan_id=plan_id,
                    request_id=claim_id,
                    proposal_id=selected_id,
                    client_request_id=payload.request_id,
                    decision="dismissed",
                    now=now,
                )
                if terminal_claim is not None
                else None
            )
            if (
                terminal_details is None
                or terminal_claim_details is None
                or not _terminal_matches_claim(
                    terminal_details, terminal_claim_details, decision="dismissed"
                )
                or getattr(existing_terminal, "created_at", None)
                < getattr(terminal_claim, "created_at", None)
            ):
                raise StudyAssistantConflictError("proposal decision was already used")
            current_plan = await _load_plan(plan_id)
            refreshed = await repository.project(plan_id, now=now)
            return StudyProgressDecisionResponse(
                proposal_id=selected_id,
                decision="dismissed",
                projection=_projection_for_plan(refreshed, current_plan),
            )

        existing_claim = await repository.get_progress_by_request(plan_id, claim_id)
        if existing_claim is not None:
            if (
                _strict_claim_details(
                    existing_claim,
                    plan_id=plan_id,
                    request_id=claim_id,
                    proposal_id=selected_id,
                    client_request_id=payload.request_id,
                    decision="dismissed",
                    now=now,
                )
                is None
            ):
                raise StudyAssistantConflictError("proposal decision claim was already used")
        else:
            proposal = next(
                (
                    item
                    for item in visible_projection.proposals
                    if item.proposal_id == selected_id
                ),
                None,
            )
            if proposal is None:
                raise StudyAssistantNotFoundError("study adaptation proposal not found")
            if proposal.status != "proposed":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "adaptation_unavailable",
                        "message": "This study adaptation is no longer proposed",
                    },
                )
            claim = make_progress_receipt(
                plan_id=plan_id,
                request_id=claim_id,
                event="decision",
                created_at=now,
                details=_claim_payload(
                    client_request_id=payload.request_id,
                    decision="dismissed",
                    proposal_id=selected_id,
                ),
            )
            await repository.append_progress(claim)

        terminal = make_progress_receipt(
            plan_id=plan_id,
            request_id=terminal_id,
            event="decision",
            created_at=now,
            details=_terminal_payload(
                claim_request_id=claim_id,
                client_request_id=payload.request_id,
                decision="dismissed",
                proposal_id=selected_id,
            ),
        )
        await repository.append_progress(terminal)
        refreshed = await repository.project(plan_id, now=now)
        current_plan = await _load_plan(plan_id)
        return StudyProgressDecisionResponse(
            proposal_id=selected_id,
            decision="dismissed",
            projection=_projection_for_plan(refreshed, current_plan),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_progress_request",
                "message": "Invalid study progress request",
            },
        ) from exc
    except (StudyProgressRepositoryError, StudyAssistantRepositoryError) as exc:
        raise _progress_error(exc) from None


@router.post(
    "/{plan_id}/progress:decision",
    response_model=StudyProgressDecisionResponse,
)
async def decide_study_plan_progress(
    plan_id: str,
    payload: StudyProgressDecisionRequest,
) -> StudyProgressDecisionResponse:
    return await _decide_study_plan_progress(plan_id, payload)


@router.post(
    "/{plan_id}/progress/{proposal_id}:decision",
    response_model=StudyProgressDecisionResponse,
)
async def decide_study_plan_progress_by_id(
    plan_id: str,
    proposal_id: str,
    payload: StudyProgressDecisionRequest,
) -> StudyProgressDecisionResponse:
    return await _decide_study_plan_progress(plan_id, payload, proposal_id=proposal_id)


@router.get("/{plan_id}", response_model=StudyPlanResponse)
async def get_study_plan(plan_id: str) -> StudyPlanResponse:
    return await _existing_plan(plan_id)


@router.patch("/{plan_id}", response_model=StudyPlanResponse)
async def patch_study_plan(
    plan_id: str, payload: PatchStudyPlanRequest
) -> StudyPlanResponse:
    try:
        plan = await _repository().update(
            plan_id,
            payload.changes(),
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudyPlanResponse.from_plan(plan)


@router.post(
    "/{plan_id}/sources",
    response_model=StudyPlanSourceLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_study_plan_source(
    plan_id: str, payload: SourceLinkRequest
) -> StudyPlanSourceLinkResponse:
    try:
        source_id = normalize_source_id(payload.source_id).canonical
    except StudySourceNotFoundError as exc:
        raise _source_error(exc) from None

    repository = _repository()
    try:
        current = await repository.get(plan_id)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if current is None:
        raise _not_found()
    existing_source_ids: set[str] = set()
    for link in current.source_links:
        try:
            existing_source_ids.add(normalize_source_id(link.source_id).canonical)
        except StudySourceNotFoundError:
            # A legacy malformed link must not make a valid retry unsafe.
            continue
    if source_id in existing_source_ids:
        # A retry of an already-persisted link is idempotent even when the
        # caller retained a stale revision.  Do this before source authority
        # access or revision checks so retries remain mutation-free.
        return StudyPlanSourceLinkResponse(source_id=source_id)

    if current.version != payload.expected_revision:
        raise _repository_error(StudyPlanConflictError("study plan revision conflict"))

    try:
        await StudySourceService().validate_source(source_id)
    except (StudySourceNotFoundError, StudySourceUnavailableError) as exc:
        raise _source_error(exc) from None

    try:
        await repository.add_source(
            plan_id,
            source_id,
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudyPlanSourceLinkResponse(source_id=source_id)


@router.get(
    "/{plan_id}/sources/readiness",
    response_model=StudySourceReadinessResponse,
)
async def get_study_plan_source_readiness(plan_id: str) -> StudySourceReadinessResponse:
    plan = await _load_plan(plan_id)
    readiness = await StudySourceService().readiness(plan)
    return StudySourceReadinessResponse.from_readiness(readiness)


@router.delete(
    "/{plan_id}/sources/{source_id}", response_model=RemoveSourceLinkResponse
)
async def remove_study_plan_source(
    plan_id: str,
    source_id: str,
    payload: RemoveSourceLinkRequest,
) -> RemoveSourceLinkResponse:
    try:
        removed = await _repository().remove_source(
            plan_id,
            source_id,
            expected_revision=payload.expected_revision,
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return RemoveSourceLinkResponse(removed=removed)


@router.get("/{plan_id}/syllabus", response_model=StudySyllabusResponse)
async def get_study_syllabus(
    plan_id: str,
    version: int | None = Query(default=None, ge=1),
) -> StudySyllabusResponse:
    try:
        syllabus = await _repository().get_syllabus(plan_id, version=version)
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    if syllabus is None:
        raise _not_found("Study syllabus not found")
    return StudySyllabusResponse.from_syllabus(syllabus)


@router.post("/{plan_id}/syllabus:propose", response_model=StudySyllabusResponse)
async def propose_study_syllabus(
    plan_id: str,
    payload: ProposeSyllabusRequest,
) -> StudySyllabusResponse:
    try:
        syllabus = await StudySyllabusService(repository=_repository()).propose(
            plan_id,
            expected_revision=payload.expected_revision,
        )
    except StudySyllabusError as exc:
        raise _syllabus_error(exc) from None
    return StudySyllabusResponse.from_syllabus(syllabus)


@router.put("/{plan_id}/syllabus", response_model=StudySyllabusResponse)
async def save_study_syllabus(
    plan_id: str,
    payload: SaveSyllabusRequest,
) -> StudySyllabusResponse:
    try:
        syllabus = await _repository().save_syllabus(
            payload.to_syllabus(plan_id),
            expected_revision=payload.expected_revision,
            lifecycle_action="edit",
        )
    except StudyPlanRepositoryError as exc:
        raise _repository_error(exc) from None
    return StudySyllabusResponse.from_syllabus(syllabus)


@router.post("/{plan_id}/syllabus:approve", response_model=StudyPlanResponse)
async def approve_study_syllabus(
    plan_id: str,
    payload: ApproveSyllabusRequest,
) -> StudyPlanResponse:
    current = await _existing_plan(plan_id)
    if current.state != "editing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Study plan cannot approve syllabus",
        )
    try:
        plan = await StudySyllabusService(repository=_repository()).approve(
            plan_id,
            syllabus_version=payload.syllabus_version,
            expected_revision=payload.expected_revision,
        )
    except StudySyllabusError as exc:
        raise _syllabus_error(exc) from None
    return StudyPlanResponse.from_plan(plan)


@router.post(
    "/{plan_id}/generate",
    response_model=GenerateStudyArtifactsResponse,
)
async def generate_study_plan_artifacts(
    plan_id: str,
    payload: GenerateStudyArtifactsRequest,
) -> GenerateStudyArtifactsResponse:
    """Generate unit-scoped Evidence Studio artifacts after approval only."""
    try:
        artifacts = await StudyArtifactService().generate_unit(
            plan_id,
            payload.unit_id,
            payload.artifact_types,
            payload.expected_revision,
            context=payload.context,
        )
    except StudyArtifactError as exc:
        raise _artifact_error(exc) from None
    return GenerateStudyArtifactsResponse(
        plan_id=plan_id,
        unit_id=payload.unit_id,
        artifacts=tuple(artifacts),
    )
