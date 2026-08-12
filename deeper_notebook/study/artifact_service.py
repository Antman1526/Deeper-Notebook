"""Approval-gated adapter from Study units to Evidence Studio artifacts.

This module intentionally does not implement a second model/generation path.
It validates the immutable study authority, creates a provisional
``StudioArtifact``, delegates generation/evaluation to Evidence Studio, and
only then persists the plan-owned link.  Returned receipts contain metadata
only; generated payloads and provider exceptions never cross this boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping, MutableMapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from weakref import WeakValueDictionary

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Source, StudioArtifact
from deeper_notebook.exceptions import NotFoundError
from deeper_notebook.studio.generation import (
    ArtifactGenerationOwnershipLost,
    ArtifactGenerationRequest,
    generate_artifact,
)
from deeper_notebook.studio.generation.context import artifact_context
from deeper_notebook.studio.generation.prompts import study_unit_prompt
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import StudyPlan, StudySyllabus, StudySyllabusUnit
from deeper_notebook.study.source_service import (
    StudySourceReadiness,
    StudySourceService,
)
from deeper_notebook.study.syllabus_service import source_manifest

SUPPORTED_ARTIFACT_TYPES = frozenset(
    {"study_guide", "course_pack", "flashcards", "quiz", "mind_map"}
)
MAX_ARTIFACT_TYPES = 5
MAX_CONTEXT_CHARS = 8_000
MAX_PROMPT_CHARS = 16_000
# Evidence Studio's generation timeout is currently 180 seconds.  Keep the
# durable lease longer than that timeout plus a bounded recovery margin so an
# active worker is not stolen merely because generation is slow.
CLAIM_LEASE_SECONDS = 240
CLAIM_OWNER_MAX_CHARS = 128
_UNIT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_PLAN_ID = re.compile(r"^study_plan:.{1,511}$")
_GENERATION_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_REAL_STUDIO_ARTIFACT = StudioArtifact


class StudyArtifactError(RuntimeError):
    """Base class for safe, typed study-artifact failures."""

    code = "study_artifact_error"

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or self.code
        super().__init__(self.reason)


class StudyArtifactNotFound(StudyArtifactError):
    code = "artifact_not_found"


class StudyArtifactConflict(StudyArtifactError):
    code = "artifact_conflict"


class StudyArtifactNotReady(StudyArtifactConflict):
    code = "sources_not_ready"


class StudyArtifactGenerationError(StudyArtifactError):
    code = "artifact_generation_failed"


class StudyArtifactCancelled(StudyArtifactError):
    code = "generation_cancelled"


class StudyArtifactUnavailable(StudyArtifactError):
    code = "artifact_unavailable"


SourceLoader = Callable[[str], object | Awaitable[object]]
ClaimClock = Callable[[], datetime]
ClaimOwnerFactory = Callable[[], str]


def _safe_id(value: object, *, field_name: str, pattern: re.Pattern[str], limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or pattern.fullmatch(value) is None:
        raise StudyArtifactConflict(f"invalid_{field_name}")
    return value


def _validate_request(
    plan_id: object,
    unit_id: object,
    artifact_types: object,
    expected_revision: object,
    context: object,
) -> tuple[str, str, tuple[str, ...], int, str | None]:
    plan = _safe_id(plan_id, field_name="plan_id", pattern=_PLAN_ID, limit=512)
    unit = _safe_id(unit_id, field_name="unit_id", pattern=_UNIT_ID, limit=64)
    if isinstance(artifact_types, (str, bytes)) or not isinstance(artifact_types, (list, tuple)):
        raise StudyArtifactConflict("invalid_artifact_types")
    if not artifact_types or len(artifact_types) > MAX_ARTIFACT_TYPES:
        raise StudyArtifactConflict("artifact_type_bounds")
    normalized: list[str] = []
    for item in artifact_types:
        if not isinstance(item, str) or item not in SUPPORTED_ARTIFACT_TYPES:
            raise StudyArtifactConflict("unsupported_artifact_type")
        if item in normalized:
            raise StudyArtifactConflict("duplicate_artifact_type")
        normalized.append(item)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
        raise StudyArtifactConflict("invalid_expected_revision")
    if context is not None:
        if not isinstance(context, str) or len(context) > MAX_CONTEXT_CHARS:
            raise StudyArtifactConflict("context_bounds")
        bounded_context = context.strip() or None
    else:
        bounded_context = None
    return plan, unit, tuple(normalized), expected_revision, bounded_context


def _value(item: object, name: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _canonical_source_id(item: object) -> str | None:
    value = _value(item, "source_id", _value(item, "id"))
    return value if isinstance(value, str) and value else None


def _unit_source_ids(unit: StudySyllabusUnit) -> tuple[str, ...]:
    values: list[str] = list(unit.source_ids)
    for activity in unit.activities:
        values.extend(activity.source_ids)
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return tuple(unique)


def _canonical_linked_source_ids(plan: StudyPlan) -> tuple[str, ...]:
    """Return the exact bounded source-link set used by the Study authority."""
    values = tuple(link.source_id for link in plan.source_links)
    if len(set(values)) != len(values):
        raise StudyArtifactConflict("source_links_not_canonical")
    return tuple(sorted(values))


def _artifact_notebook_id(plan_id: str) -> str:
    """Use a stable, plan-scoped notebook-shaped owner for Studio's schema.

    ``studio_artifact.notebook_id`` predates Study Workbench and is typed as a
    ``record<notebook>``.  Study ownership is represented by the explicit
    ``study_plan_artifact`` link; this synthetic owner is never read, created,
    mutated, or used as a source authority.
    """
    token = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:40]
    return f"notebook:study_{token}"


def _artifact_identity(
    plan_id: str,
    syllabus_version: int,
    source_manifest_sha256: str,
    unit_id: str,
    artifact_type: str,
) -> str:
    """Return one stable operation/artifact ID for the approved unit request."""
    token = hashlib.sha256(
        "\x1f".join(
            (
                plan_id,
                str(syllabus_version),
                source_manifest_sha256,
                unit_id,
                artifact_type,
            )
        ).encode("utf-8")
    ).hexdigest()[:40]
    return f"studio_artifact:study_{token}"


@asynccontextmanager
async def _generation_lock(
    operation_id: str,
    lock_store: MutableMapping[str, asyncio.Lock] | None = None,
):
    """Serialize identical work in this process without retaining unbounded keys."""
    store = _GENERATION_LOCKS if lock_store is None else lock_store
    lock = store.get(operation_id)
    if lock is None:
        lock = asyncio.Lock()
        store[operation_id] = lock
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


class StudyArtifactService:
    """Validate and generate one approved syllabus unit through Evidence Studio."""

    def __init__(
        self,
        *,
        repository: StudyPlanRepository | object | None = None,
        source_service: StudySourceService | object | None = None,
        source_loader: SourceLoader | None = None,
        lock_store: MutableMapping[str, asyncio.Lock] | None = None,
        clock: ClaimClock | None = None,
        owner_token_factory: ClaimOwnerFactory | None = None,
    ) -> None:
        self.repository = repository or StudyPlanRepository()
        self.source_service = source_service or StudySourceService()
        self.source_loader = source_loader or Source.get
        self.lock_store = lock_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._owner_token_factory = owner_token_factory or (lambda: uuid4().hex)

    async def generate_unit(
        self,
        plan_id: str,
        unit_id: str,
        artifact_types: Iterable[str],
        expected_revision: int,
        *,
        context: str | None = None,
    ) -> list[dict[str, str]]:
        """Generate requested artifact types for one exact syllabus unit."""
        plan_key, requested_unit, types, revision, bounded_context = _validate_request(
            plan_id, unit_id, artifact_types, expected_revision, context
        )
        plan = await self._load_plan(plan_key)
        if plan.version != revision:
            raise StudyArtifactConflict("revision_conflict")
        if plan.state != "approved":
            raise StudyArtifactConflict("syllabus_not_approved")
        if plan.approved_syllabus_version is None or plan.source_manifest_sha256 is None:
            raise StudyArtifactConflict("syllabus_not_approved")
        syllabus = await self._load_syllabus(plan_key, plan.approved_syllabus_version)
        if syllabus.approved_at is None:
            raise StudyArtifactConflict("syllabus_not_approved")
        if syllabus.source_manifest_sha256 != plan.source_manifest_sha256:
            raise StudyArtifactConflict("manifest_mismatch")
        unit = next((candidate for candidate in syllabus.units if candidate.unit_id == requested_unit), None)
        if unit is None:
            raise StudyArtifactNotFound("unit_not_found")

        linked_ids = {link.source_id for link in plan.source_links}
        linked_source_set = _canonical_linked_source_ids(plan)
        unit_sources = _unit_source_ids(unit)
        if not unit_sources:
            raise StudyArtifactConflict("unit_sources_missing")
        if not set(unit_sources).issubset(linked_ids):
            raise StudyArtifactConflict("unit_source_not_linked")

        # A unit can request several types, but each one receives the exact
        # same readiness/fingerprint guard immediately before its generation.
        receipts: list[dict[str, str]] = []
        for artifact_type in types:
            operation_id = _artifact_identity(
                plan_key,
                syllabus.version,
                syllabus.source_manifest_sha256,
                unit.unit_id,
                artifact_type,
            )
            async with _generation_lock(operation_id, self.lock_store):
                receipts.append(
                    await self._generate_one(
                        plan,
                        syllabus,
                        unit,
                        unit_sources,
                        artifact_type,
                        revision,
                        bounded_context,
                        operation_id,
                        linked_source_set,
                    )
                )
        return receipts

    async def _generate_one(
        self,
        plan: StudyPlan,
        syllabus: StudySyllabus,
        unit: StudySyllabusUnit,
        unit_sources: tuple[str, ...],
        artifact_type: str,
        revision: int,
        bounded_context: str | None,
        operation_id: str,
        linked_source_set: tuple[str, ...],
    ) -> dict[str, str]:
        existing = await self._existing_link(
            plan.plan_id,
            unit_id=unit.unit_id,
            artifact_kind=artifact_type,
            syllabus_version=syllabus.version,
        )
        if existing is not None:
            artifact_id = _value(existing, "artifact_id")
            if isinstance(artifact_id, str) and artifact_id:
                if artifact_id != operation_id:
                    raise StudyArtifactConflict("artifact_identity_mismatch")
                await self._revalidate_claim_authority(
                    plan,
                    syllabus,
                    unit,
                    unit_sources,
                    revision,
                    linked_source_set,
                    require_sources=True,
                )
                return {
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "status": "completed",
                    "unit_id": unit.unit_id,
                }

        sources = await self._ready_sources(plan, syllabus, unit_sources)
        prompt = study_unit_prompt(
            artifact_type,
            plan_goal=plan.goal,
            unit_title=unit.title,
            objectives=unit.objectives,
            prerequisite_unit_ids=unit.prerequisite_unit_ids,
            source_ids=unit_sources,
            context=bounded_context,
        )[:MAX_PROMPT_CHARS]
        # Calling artifact_context here is deliberate: it is the existing
        # bounded context/citation adapter, not a second generator.
        combined_context, _ = artifact_context(sources)
        if not combined_context.strip():
            raise StudyArtifactNotReady("no_evidence")
        provisional = await self._get_or_create_provisional(
            plan,
            syllabus,
            unit,
            artifact_type,
            unit_sources,
            prompt,
            operation_id,
        )
        if str(getattr(provisional, "status", "pending")) == "completed":
            completed_id = str(getattr(provisional, "id", "") or operation_id)
            await self._revalidate_claim_authority(
                plan,
                syllabus,
                unit,
                unit_sources,
                revision,
                linked_source_set,
                require_sources=True,
            )
            await self._link_completed(
                plan.plan_id,
                completed_id,
                unit,
                syllabus,
                artifact_type,
                revision,
                expected_plan=plan,
                expected_unit_sources=unit_sources,
                expected_linked_source_set=linked_source_set,
            )
            return {
                "artifact_id": completed_id,
                "artifact_type": artifact_type,
                "status": "completed",
                "unit_id": unit.unit_id,
            }
        claim_result = await self._claim_provisional(
            provisional,
            operation_id,
            artifact_type,
            unit_sources,
        )
        if (
            isinstance(claim_result, tuple)
            and len(claim_result) == 2
            and isinstance(claim_result[1], (str, type(None)))
        ):
            provisional, claim_owner = claim_result
        else:  # Compatibility for alternate test authorities from Task 9.
            provisional, claim_owner = claim_result, None
        if str(getattr(provisional, "status", "pending")) == "completed":
            completed_id = str(getattr(provisional, "id", "") or operation_id)
            await self._link_completed(
                plan.plan_id,
                completed_id,
                unit,
                syllabus,
                artifact_type,
                revision,
                artifact=provisional,
                owner_token=claim_owner,
                expected_plan=plan,
                expected_unit_sources=unit_sources,
                expected_linked_source_set=linked_source_set,
            )
            return {
                "artifact_id": completed_id,
                "artifact_type": artifact_type,
                "status": "completed",
                "unit_id": unit.unit_id,
            }

        # Re-read every linked source after the durable claim and immediately
        # before handing the request to Evidence Studio.  A source mutation
        # between the first guard and this point releases the claim and never
        # enters generation.
        try:
            plan, syllabus, unit, unit_sources = await self._revalidate_claim_authority(
                plan,
                syllabus,
                unit,
                unit_sources,
                revision,
                linked_source_set,
                require_sources=True,
            )
            await self._assert_claim_owner(provisional, operation_id, claim_owner)
            sources = await self._ready_sources(plan, syllabus, unit_sources)
            combined_context, _ = artifact_context(sources)
            if not combined_context.strip():
                raise StudyArtifactNotReady("no_evidence")
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            await self._release_claim(provisional, operation_id, claim_owner)
            raise

        artifact_id = str(getattr(provisional, "id", "") or "")
        if not artifact_id:
            raise StudyArtifactGenerationError("artifact_generation_failed")
        request = ArtifactGenerationRequest(
            artifact_id=artifact_id,
            source_ids=list(unit_sources),
            before_persist=lambda _artifact: self._assert_generation_owner(
                provisional, operation_id, claim_owner
            ),
            persist_artifact=lambda artifact: self._persist_claimed_artifact(
                artifact, operation_id, claim_owner
            ),
        )
        try:
            generated = await generate_artifact(request)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(exc, asyncio.CancelledError):
                await self._mark(provisional, "cancelled", owner_token=claim_owner)
                raise StudyArtifactCancelled("generation_cancelled") from exc
            if isinstance(exc, ArtifactGenerationOwnershipLost):
                raise StudyArtifactConflict("generation_claim_lost") from exc
            await self._mark(provisional, "failed", owner_token=claim_owner)
            raise StudyArtifactGenerationError("artifact_generation_failed") from exc
        await self._assert_claim_owner(
            provisional,
            operation_id,
            claim_owner,
            require_status="completed",
        )
        if str(getattr(generated, "status", "")) != "completed":
            await self._mark(
                provisional,
                str(getattr(generated, "status", "failed")),
                owner_token=claim_owner,
            )
            raise StudyArtifactGenerationError("artifact_generation_failed")
        completed_id = str(getattr(generated, "id", "") or artifact_id)
        if completed_id != operation_id:
            await self._mark(provisional, "failed", owner_token=claim_owner)
            raise StudyArtifactGenerationError("artifact_identity_mismatch")
        try:
            plan, syllabus, unit, unit_sources = await self._revalidate_claim_authority(
                plan,
                syllabus,
                unit,
                unit_sources,
                revision,
                linked_source_set,
                require_sources=True,
            )
            await self._assert_claim_owner(
                provisional,
                operation_id,
                claim_owner,
                require_status="completed",
            )
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            await self._release_claim(provisional, operation_id, claim_owner)
            raise
        try:
            await self._link_completed(
                plan.plan_id,
                completed_id,
                unit,
                syllabus,
                artifact_type,
                revision,
                artifact=provisional,
                owner_token=claim_owner,
                expected_plan=plan,
                expected_unit_sources=unit_sources,
                expected_linked_source_set=linked_source_set,
            )
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            await self._release_claim(provisional, operation_id, claim_owner)
            raise
        await self._clear_claim(provisional, operation_id, claim_owner)
        return {
            "artifact_id": completed_id,
            "artifact_type": artifact_type,
            "status": "completed",
            "unit_id": unit.unit_id,
        }

    async def _get_or_create_provisional(
        self,
        plan: StudyPlan,
        syllabus: StudySyllabus,
        unit: StudySyllabusUnit,
        artifact_type: str,
        source_ids: tuple[str, ...],
        prompt: str,
        operation_id: str,
    ) -> object:
        existing = await self._existing_artifact(operation_id)
        if existing is not None:
            self._validate_artifact_identity(existing, artifact_type, source_ids)
            current_status = str(getattr(existing, "status", "pending"))
            if current_status in {"failed", "cancelled"}:
                await self._reset_for_retry(existing)
            return existing
        try:
            return await self._create_provisional(
                plan,
                artifact_type=artifact_type,
                unit=unit,
                source_ids=source_ids,
                prompt=prompt,
                operation_id=operation_id,
            )
        except Exception as exc:
            # Another process may have won the deterministic CREATE. Re-read
            # that record and converge on its state rather than creating a
            # second artifact or leaking a driver conflict.
            existing = await self._existing_artifact(operation_id)
            if existing is not None:
                self._validate_artifact_identity(existing, artifact_type, source_ids)
                return existing
            if isinstance(exc, StudyArtifactError):
                raise
            raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc

    async def _existing_artifact(self, artifact_id: str) -> object | None:
        getter = getattr(StudioArtifact, "get", None)
        if not callable(getter):
            return None
        try:
            result = getter(artifact_id)
            return await result if inspect.isawaitable(result) else result
        except NotFoundError:
            return None
        except Exception as exc:
            raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc

    @staticmethod
    def _validate_artifact_identity(
        artifact: object,
        artifact_type: str,
        source_ids: tuple[str, ...],
    ) -> None:
        if str(getattr(artifact, "artifact_type", artifact_type)) != artifact_type:
            raise StudyArtifactConflict("artifact_identity_mismatch")
        existing_sources = tuple(str(item) for item in getattr(artifact, "source_ids", ()))
        if existing_sources and existing_sources != source_ids:
            raise StudyArtifactConflict("artifact_identity_mismatch")

    async def _reset_for_retry(self, artifact: object) -> None:
        await self._mark(artifact, "pending")

    def _claim_now(self) -> datetime:
        try:
            now = self._clock()
        except Exception as exc:
            raise StudyArtifactUnavailable("claim_clock_unavailable") from exc
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise StudyArtifactUnavailable("claim_clock_unavailable")
        try:
            now = now.astimezone(UTC)
        except Exception as exc:
            raise StudyArtifactUnavailable("claim_clock_unavailable") from exc
        return now

    def _claim_metadata(self) -> tuple[str, datetime, datetime]:
        now = self._claim_now()
        try:
            owner = self._owner_token_factory()
        except Exception as exc:
            raise StudyArtifactUnavailable("claim_owner_unavailable") from exc
        if not isinstance(owner, str):
            raise StudyArtifactUnavailable("claim_owner_unavailable")
        owner = owner.strip()
        if not owner or len(owner) > CLAIM_OWNER_MAX_CHARS:
            raise StudyArtifactUnavailable("claim_owner_unavailable")
        return owner, now, now + timedelta(seconds=CLAIM_LEASE_SECONDS)

    @staticmethod
    def _claim_expiry(artifact: object) -> datetime | None:
        value = getattr(artifact, "generation_claim_lease_until", None)
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if not isinstance(value, datetime) or value.tzinfo is None:
            return None
        try:
            return value.astimezone(UTC)
        except Exception:
            return None

    @staticmethod
    def _set_claim_metadata(
        artifact: object,
        *,
        owner: str | None,
        started_at: datetime | None,
        lease_until: datetime | None,
    ) -> None:
        setattr(artifact, "generation_claim_owner", owner)
        setattr(artifact, "generation_claim_started_at", started_at)
        setattr(artifact, "generation_claim_lease_until", lease_until)

    async def _assert_claim_owner(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str | None,
        *,
        require_status: str | None = None,
    ) -> object:
        if owner_token is None:
            if require_status is not None and str(getattr(artifact, "status", "")) != require_status:
                raise StudyArtifactConflict("generation_claim_lost")
            return artifact
        current = artifact
        if callable(getattr(StudioArtifact, "get", None)):
            loaded = await self._existing_artifact(operation_id)
            if loaded is None:
                raise StudyArtifactConflict("generation_claim_lost")
            current = loaded
        if getattr(current, "generation_claim_owner", None) != owner_token:
            raise StudyArtifactConflict("generation_claim_lost")
        if require_status is not None and str(getattr(current, "status", "")) != require_status:
            raise StudyArtifactConflict("generation_claim_lost")
        return current

    async def _claim_provisional(
        self,
        artifact: object,
        operation_id: str,
        artifact_type: str,
        source_ids: tuple[str, ...],
    ) -> tuple[object, str | None]:
        """Atomically claim pending work before invoking Evidence Studio.

        The in-process lock is only a fast path.  Real Studio records use a
        conditional persistent status transition plus a bounded durable lease,
        so separate workers and process restarts converge on one owner. Test
        and alternate authorities may expose a small ``claim`` method;
        otherwise the object mutation remains protected by the caller's local
        lock.
        """
        status = str(getattr(artifact, "status", "pending"))
        if status == "completed":
            return artifact, None
        if status in {"failed", "cancelled"}:
            await self._reset_for_retry(artifact)
            status = "pending"
        if status == "running":
            now = self._claim_now()
            expiry = self._claim_expiry(artifact)
            if expiry is None or expiry > now:
                raise StudyArtifactConflict("generation_in_progress")
        if status not in {"pending", "running"}:
            raise StudyArtifactConflict("generation_in_progress")

        owner, started_at, lease_until = self._claim_metadata()

        claim = getattr(artifact, "claim", None)
        if callable(claim):
            try:
                result = claim(
                    owner=owner,
                    started_at=started_at,
                    lease_until=lease_until,
                    now=started_at,
                )
            except TypeError:
                # Preserve compatibility with the tiny Task 9 alternate
                # authority seam while still attaching the durable metadata.
                result = claim()
            claimed = await result if inspect.isawaitable(result) else result
            if claimed:
                self._set_claim_metadata(
                    artifact,
                    owner=owner,
                    started_at=started_at,
                    lease_until=lease_until,
                )
                save = getattr(artifact, "save", None)
                if callable(save):
                    saved = save()
                    if inspect.isawaitable(saved):
                        await saved
                return artifact, owner
            current = await self._existing_artifact(operation_id)
            if current is not None and str(getattr(current, "status", "")) == "completed":
                return current, None
            raise StudyArtifactConflict("generation_in_progress")

        if StudioArtifact is _REAL_STUDIO_ARTIFACT:
            try:
                rows = await repo_query(
                    "UPDATE $artifact SET status = 'running', "
                    "generation_claim_owner = $owner, "
                    "generation_claim_started_at = $started_at, "
                    "generation_claim_lease_until = $lease_until "
                    "WHERE status = 'pending' OR "
                    "(status = 'running' AND generation_claim_lease_until < $now) "
                    "RETURN AFTER;",
                    {
                        "artifact": ensure_record_id(operation_id),
                        "owner": owner,
                        "started_at": started_at,
                        "lease_until": lease_until,
                        "now": started_at,
                    },
                )
            except Exception as exc:
                raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                claimed = StudioArtifact(**rows[0])
                self._validate_artifact_identity(claimed, artifact_type, source_ids)
                return claimed, owner
            current = await self._existing_artifact(operation_id)
            if current is not None and str(getattr(current, "status", "")) == "completed":
                return current, None
            raise StudyArtifactConflict("generation_in_progress")

        setattr(artifact, "status", "running")
        self._set_claim_metadata(
            artifact,
            owner=owner,
            started_at=started_at,
            lease_until=lease_until,
        )
        save = getattr(artifact, "save", None)
        if callable(save):
            result = save()
            if inspect.isawaitable(result):
                await result
        return artifact, owner

    async def _load_plan(self, plan_id: str) -> StudyPlan:
        try:
            plan = await self.repository.get(plan_id)
        except StudyArtifactError:
            raise
        except Exception as exc:
            raise StudyArtifactUnavailable("study_plan_unavailable") from exc
        if plan is None:
            raise StudyArtifactNotFound("study_plan_not_found")
        return plan

    async def _persist_claimed_artifact(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str | None,
    ) -> object:
        """Persist Studio mutations only while this worker still owns the lease."""
        if owner_token is None:
            save = getattr(artifact, "save", None)
            if callable(save):
                result = save()
                if inspect.isawaitable(result):
                    await result
            return artifact
        await self._assert_generation_owner(artifact, operation_id, owner_token)
        conditional = getattr(artifact, "persist_if_owner", None)
        if callable(conditional):
            result = conditional(owner_token)
            persisted = await result if inspect.isawaitable(result) else result
            if not persisted:
                raise ArtifactGenerationOwnershipLost("generation claim lost")
            return artifact
        if StudioArtifact is _REAL_STUDIO_ARTIFACT:
            prepare = getattr(artifact, "_prepare_save_data", None)
            if not callable(prepare):
                raise ArtifactGenerationOwnershipLost("generation claim lost")
            data = dict(prepare())
            data.pop("id", None)
            try:
                rows = await repo_query(
                    "UPDATE $artifact MERGE $data "
                    "WHERE generation_claim_owner = $owner RETURN AFTER;",
                    {
                        "artifact": ensure_record_id(operation_id),
                        "data": data,
                        "owner": owner_token,
                    },
                )
            except Exception as exc:
                raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc
            if not isinstance(rows, list) or not rows:
                raise ArtifactGenerationOwnershipLost("generation claim lost")
            return StudioArtifact(**rows[0])
        current_owner = getattr(artifact, "generation_claim_owner", None)
        if current_owner != owner_token:
            raise ArtifactGenerationOwnershipLost("generation claim lost")
        save = getattr(artifact, "save", None)
        if callable(save):
            result = save()
            if inspect.isawaitable(result):
                await result
        return artifact

    async def _assert_generation_owner(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str | None,
    ) -> object:
        try:
            return await self._assert_claim_owner(artifact, operation_id, owner_token)
        except StudyArtifactConflict as exc:
            raise ArtifactGenerationOwnershipLost("generation claim lost") from exc

    async def _owned_artifact_for_update(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str,
    ) -> object:
        current = artifact
        if callable(getattr(StudioArtifact, "get", None)):
            loaded = await self._existing_artifact(operation_id)
            if loaded is None:
                raise StudyArtifactConflict("generation_claim_lost")
            current = loaded
        if getattr(current, "generation_claim_owner", None) != owner_token:
            raise StudyArtifactConflict("generation_claim_lost")
        return current

    async def _save_owned_state(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str,
    ) -> object:
        conditional = getattr(artifact, "persist_if_owner", None)
        if callable(conditional):
            result = conditional(owner_token)
            persisted = await result if inspect.isawaitable(result) else result
            if not persisted:
                raise StudyArtifactConflict("generation_claim_lost")
            return artifact
        if StudioArtifact is _REAL_STUDIO_ARTIFACT:
            prepare = getattr(artifact, "_prepare_save_data", None)
            if not callable(prepare):
                raise StudyArtifactConflict("generation_claim_lost")
            data = dict(prepare())
            data.pop("id", None)
            try:
                rows = await repo_query(
                    "UPDATE $artifact MERGE $data "
                    "WHERE generation_claim_owner = $owner RETURN AFTER;",
                    {
                        "artifact": ensure_record_id(operation_id),
                        "data": data,
                        "owner": owner_token,
                    },
                )
            except Exception as exc:
                raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc
            if not isinstance(rows, list) or not rows:
                raise StudyArtifactConflict("generation_claim_lost")
            return StudioArtifact(**rows[0])
        save = getattr(artifact, "save", None)
        if callable(save):
            result = save()
            if inspect.isawaitable(result):
                await result
        return artifact

    async def _load_syllabus(self, plan_id: str, version: int) -> StudySyllabus:
        try:
            syllabus = await self.repository.get_syllabus(plan_id, version=version)
        except Exception as exc:
            raise StudyArtifactUnavailable("syllabus_unavailable") from exc
        if syllabus is None:
            raise StudyArtifactNotFound("syllabus_not_found")
        return syllabus

    async def _revalidate_claim_authority(
        self,
        plan: StudyPlan,
        syllabus: StudySyllabus,
        unit: StudySyllabusUnit,
        unit_sources: tuple[str, ...],
        revision: int,
        linked_source_set: tuple[str, ...],
        *,
        require_sources: bool,
    ) -> tuple[StudyPlan, StudySyllabus, StudySyllabusUnit, tuple[str, ...]]:
        """Re-read the exact Study authority at every publication boundary."""
        current_plan = await self._load_plan(plan.plan_id)
        if (
            current_plan.version != revision
            or current_plan.state != "approved"
            or current_plan.approved_syllabus_version != syllabus.version
            or current_plan.source_manifest_sha256 != syllabus.source_manifest_sha256
            or _canonical_linked_source_ids(current_plan) != linked_source_set
        ):
            raise StudyArtifactConflict("study_authority_changed")
        current_syllabus = await self._load_syllabus(
            current_plan.plan_id, current_plan.approved_syllabus_version or 0
        )
        if (
            current_syllabus.version != syllabus.version
            or current_syllabus.approved_at is None
            or current_syllabus.approved_at != syllabus.approved_at
            or current_syllabus.source_manifest_sha256 != syllabus.source_manifest_sha256
        ):
            raise StudyArtifactConflict("study_authority_changed")
        current_unit = next(
            (candidate for candidate in current_syllabus.units if candidate.unit_id == unit.unit_id),
            None,
        )
        if current_unit is None:
            raise StudyArtifactConflict("study_authority_changed")
        current_unit_sources = _unit_source_ids(current_unit)
        if (
            current_unit != unit
            or current_unit_sources != unit_sources
            or not set(current_unit_sources).issubset(set(linked_source_set))
        ):
            raise StudyArtifactConflict("study_authority_changed")
        if require_sources:
            await self._ready_sources(current_plan, current_syllabus, current_unit_sources)
        return current_plan, current_syllabus, current_unit, current_unit_sources

    async def _ready_sources(
        self,
        plan: StudyPlan,
        syllabus: StudySyllabus,
        source_ids: tuple[str, ...],
    ) -> list[object]:
        try:
            readiness = await self.source_service.readiness(plan)
        except Exception as exc:
            raise StudyArtifactUnavailable("source_readiness_unavailable") from exc
        if not isinstance(readiness, StudySourceReadiness):
            raise StudyArtifactNotReady("sources_not_ready")
        if not readiness.ready:
            raise StudyArtifactNotReady("sources_not_ready")
        readiness_by_id = {
            item.source_id: item
            for item in readiness.items
            if isinstance(item.source_id, str)
        }
        if any(
            source_id not in readiness_by_id
            or not readiness_by_id[source_id].ready
            or readiness_by_id[source_id].fingerprint_status != "available"
            or readiness_by_id[source_id].reason != "ready"
            for source_id in {link.source_id for link in plan.source_links}
        ):
            raise StudyArtifactNotReady("sources_not_ready")
        sources_by_id: dict[str, object] = {}
        all_source_ids = tuple(link.source_id for link in plan.source_links)
        try:
            for source_id in all_source_ids:
                loaded = self.source_loader(source_id)
                source = await loaded if inspect.isawaitable(loaded) else loaded
                if source is None:
                    raise StudyArtifactNotReady("source_not_found")
                canonical = _canonical_source_id(source)
                if canonical != source_id:
                    raise StudyArtifactConflict("source_identity_mismatch")
                if not isinstance(_value(source, "full_text"), str) or not _value(source, "full_text").strip():
                    raise StudyArtifactNotReady("sources_not_ready")
                sources_by_id[source_id] = source
        except StudyArtifactError:
            raise
        except Exception as exc:
            raise StudyArtifactUnavailable("source_unavailable") from exc
        try:
            if source_manifest(sources_by_id.values()) != syllabus.source_manifest_sha256:
                raise StudyArtifactConflict("sources_changed")
        except StudyArtifactError:
            raise
        except Exception as exc:
            raise StudyArtifactNotReady("source_fingerprint_missing") from exc
        return [sources_by_id[source_id] for source_id in source_ids]

    async def _create_provisional(
        self,
        plan: StudyPlan,
        *,
        artifact_type: str,
        unit: StudySyllabusUnit,
        source_ids: tuple[str, ...],
        prompt: str,
        operation_id: str,
    ) -> object:
        try:
            values = {
                "id": operation_id,
                "notebook_id": _artifact_notebook_id(plan.plan_id),
                "artifact_type": artifact_type,
                "title": f"{unit.title} — {artifact_type.replace('_', ' ')}",
                "status": "pending",
                "source_ids": list(source_ids),
                "prompt": prompt,
            }
            if StudioArtifact is _REAL_STUDIO_ARTIFACT:
                draft = StudioArtifact(**values)
                data = draft._prepare_save_data()
                data.pop("id", None)
                rows = await repo_query(
                    "CREATE $artifact CONTENT $data RETURN AFTER;",
                    {"artifact": ensure_record_id(operation_id), "data": data},
                )
                if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                    return StudioArtifact(**rows[0])
                loaded = await self._existing_artifact(operation_id)
                if loaded is not None:
                    return loaded
                raise StudyArtifactUnavailable("artifact_persistence_unavailable")
            artifact = StudioArtifact(**values)
            await artifact.save()
            return artifact
        except Exception as exc:
            raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc

    async def _release_claim(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str | None,
    ) -> None:
        """Return a claimed row to pending only when this worker owns it."""
        if owner_token is None:
            return
        if StudioArtifact is _REAL_STUDIO_ARTIFACT:
            try:
                await repo_query(
                    "UPDATE $artifact SET status = 'pending', "
                    "generation_claim_owner = NONE, "
                    "generation_claim_started_at = NONE, "
                    "generation_claim_lease_until = NONE, "
                    "output_payload = {}, citations = [], export_paths = {} "
                    "WHERE generation_claim_owner = $owner RETURN AFTER;",
                    {
                        "artifact": ensure_record_id(operation_id),
                        "owner": owner_token,
                    },
                )
            except Exception:
                return
            return
        try:
            current = await self._owned_artifact_for_update(
                artifact, operation_id, owner_token
            )
        except StudyArtifactConflict:
            return
        setattr(current, "status", "pending")
        self._set_claim_metadata(current, owner=None, started_at=None, lease_until=None)
        for field_name, empty_value in (
            ("output_payload", {}),
            ("citations", []),
            ("export_paths", {}),
        ):
            if hasattr(current, field_name):
                setattr(current, field_name, empty_value)
        await self._save_owned_state(current, operation_id, owner_token)

    async def _clear_claim(
        self,
        artifact: object,
        operation_id: str,
        owner_token: str | None,
    ) -> None:
        """Clear a completed claim without allowing a reclaimed owner overwrite."""
        if owner_token is None:
            return
        if StudioArtifact is _REAL_STUDIO_ARTIFACT:
            try:
                rows = await repo_query(
                    "UPDATE $artifact SET generation_claim_owner = NONE, "
                    "generation_claim_started_at = NONE, "
                    "generation_claim_lease_until = NONE "
                    "WHERE generation_claim_owner = $owner RETURN AFTER;",
                    {
                        "artifact": ensure_record_id(operation_id),
                        "owner": owner_token,
                    },
                )
            except Exception as exc:
                raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc
            if not isinstance(rows, list) or not rows:
                raise StudyArtifactConflict("generation_claim_lost")
            return
        current = await self._owned_artifact_for_update(artifact, operation_id, owner_token)
        self._set_claim_metadata(current, owner=None, started_at=None, lease_until=None)
        await self._save_owned_state(current, operation_id, owner_token)

    async def _mark(
        self,
        artifact: object,
        status: str,
        *,
        owner_token: str | None = None,
    ) -> None:
        try:
            bounded_status = status if status in {"failed", "cancelled", "pending"} else "failed"
            if owner_token is not None and StudioArtifact is _REAL_STUDIO_ARTIFACT:
                await repo_query(
                    "UPDATE $artifact SET status = $status, "
                    "output_payload = {}, citations = [], export_paths = {}, "
                    "generation_claim_owner = NONE, "
                    "generation_claim_started_at = NONE, "
                    "generation_claim_lease_until = NONE "
                    "WHERE generation_claim_owner = $owner RETURN AFTER;",
                    {
                        "artifact": ensure_record_id(str(getattr(artifact, "id", ""))),
                        "owner": owner_token,
                        "status": bounded_status,
                    },
                )
                return
            if owner_token is not None:
                try:
                    artifact = await self._owned_artifact_for_update(
                        artifact, str(getattr(artifact, "id", "")), owner_token
                    )
                except StudyArtifactConflict:
                    return
            setattr(artifact, "status", bounded_status)
            self._set_claim_metadata(artifact, owner=None, started_at=None, lease_until=None)
            for field_name, empty_value in (
                ("output_payload", {}),
                ("citations", []),
                ("export_paths", {}),
            ):
                if hasattr(artifact, field_name):
                    setattr(artifact, field_name, empty_value)
            if owner_token is not None:
                await self._save_owned_state(
                    artifact, str(getattr(artifact, "id", "")), owner_token
                )
            else:
                save = getattr(artifact, "save", None)
                if callable(save):
                    result = save()
                    if inspect.isawaitable(result):
                        await result
        except Exception:
            # A failed/cancelled provisional record must never become a plan
            # link; inability to persist its terminal status is non-authorizing.
            return

    async def _link_completed(
        self,
        plan_id: str,
        artifact_id: str,
        unit: StudySyllabusUnit,
        syllabus: StudySyllabus,
        artifact_type: str,
        revision: int,
        *,
        artifact: object | None = None,
        owner_token: str | None = None,
        expected_plan: StudyPlan | None = None,
        expected_unit_sources: tuple[str, ...] | None = None,
        expected_linked_source_set: tuple[str, ...] | None = None,
    ) -> object:
        if (
            expected_plan is not None
            and expected_unit_sources is not None
            and expected_linked_source_set is not None
        ):
            await self._revalidate_claim_authority(
                expected_plan,
                syllabus,
                unit,
                expected_unit_sources,
                revision,
                expected_linked_source_set,
                require_sources=True,
            )
        if owner_token is not None and artifact is not None:
            await self._assert_claim_owner(
                artifact,
                artifact_id,
                owner_token,
            )
        metadata = {
            "unit_id": unit.unit_id,
            "syllabus_version": syllabus.version,
            "source_manifest_sha256": syllabus.source_manifest_sha256,
            "expected_revision": revision,
        }
        try:
            return await self._link(
                plan_id,
                artifact_id,
                artifact_kind=artifact_type,
                metadata=metadata,
            )
        except StudyArtifactError:
            raise
        except Exception as exc:
            raise StudyArtifactUnavailable("artifact_link_unavailable") from exc

    async def _existing_link(
        self,
        plan_id: str,
        *,
        unit_id: str,
        artifact_kind: str,
        syllabus_version: int,
    ) -> object | None:
        finder = getattr(self.repository, "find_artifact_link", None)
        if callable(finder):
            try:
                result = finder(
                    plan_id,
                    unit_id=unit_id,
                    artifact_kind=artifact_kind,
                    syllabus_version=syllabus_version,
                )
                return await result if inspect.isawaitable(result) else result
            except Exception as exc:
                raise StudyArtifactUnavailable("artifact_link_unavailable") from exc
        links = getattr(self.repository, "links", None)
        if isinstance(links, list):
            for link in links:
                metadata = _value(link, "metadata", {})
                if (
                    _value(link, "plan_id") == plan_id
                    and _value(link, "artifact_kind") == artifact_kind
                    and _value(metadata, "unit_id") == unit_id
                    and _value(metadata, "syllabus_version") == syllabus_version
                ):
                    return link
        return None

    async def _link(
        self,
        plan_id: str,
        artifact_id: str,
        *,
        artifact_kind: str,
        metadata: dict[str, object],
    ) -> object:
        linker = getattr(self.repository, "link_artifact", None)
        if not callable(linker):
            raise StudyArtifactUnavailable("artifact_link_unavailable")
        result = linker(
            plan_id,
            artifact_id,
            artifact_kind=artifact_kind,
            metadata=metadata,
        )
        return await result if inspect.isawaitable(result) else result


__all__ = [
    "CLAIM_LEASE_SECONDS",
    "CLAIM_OWNER_MAX_CHARS",
    "MAX_ARTIFACT_TYPES",
    "MAX_CONTEXT_CHARS",
    "SUPPORTED_ARTIFACT_TYPES",
    "StudyArtifactCancelled",
    "StudyArtifactConflict",
    "StudyArtifactError",
    "StudyArtifactGenerationError",
    "StudyArtifactNotFound",
    "StudyArtifactNotReady",
    "StudyArtifactService",
    "StudyArtifactUnavailable",
]
