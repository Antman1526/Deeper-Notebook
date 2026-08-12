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
from collections.abc import Awaitable, Callable, Iterable, Mapping

from deeper_notebook.domain.notebook import Source, StudioArtifact
from deeper_notebook.studio.generation import (
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
_UNIT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_PLAN_ID = re.compile(r"^study_plan:.{1,511}$")


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


def _artifact_notebook_id(plan_id: str) -> str:
    """Use a stable, plan-scoped notebook-shaped owner for Studio's schema.

    ``studio_artifact.notebook_id`` predates Study Workbench and is typed as a
    ``record<notebook>``.  Study ownership is represented by the explicit
    ``study_plan_artifact`` link; this synthetic owner is never read, created,
    mutated, or used as a source authority.
    """
    token = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:40]
    return f"notebook:study_{token}"


class StudyArtifactService:
    """Validate and generate one approved syllabus unit through Evidence Studio."""

    def __init__(
        self,
        *,
        repository: StudyPlanRepository | object | None = None,
        source_service: StudySourceService | object | None = None,
        source_loader: SourceLoader | None = None,
    ) -> None:
        self.repository = repository or StudyPlanRepository()
        self.source_service = source_service or StudySourceService()
        self.source_loader = source_loader or Source.get

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
        unit_sources = _unit_source_ids(unit)
        if not unit_sources:
            raise StudyArtifactConflict("unit_sources_missing")
        if not set(unit_sources).issubset(linked_ids):
            raise StudyArtifactConflict("unit_source_not_linked")

        # A unit can request several types, but each one receives the exact
        # same readiness/fingerprint guard immediately before its generation.
        receipts: list[dict[str, str]] = []
        for artifact_type in types:
            existing = await self._existing_link(
                plan_key,
                unit_id=unit.unit_id,
                artifact_kind=artifact_type,
                syllabus_version=syllabus.version,
            )
            if existing is not None:
                artifact_id = _value(existing, "artifact_id")
                if isinstance(artifact_id, str) and artifact_id:
                    receipts.append(
                        {
                            "artifact_id": artifact_id,
                            "artifact_type": artifact_type,
                            "status": "completed",
                            "unit_id": unit.unit_id,
                        }
                    )
                    continue

            sources = await self._ready_sources(plan, syllabus, unit_sources)
            prompt = study_unit_prompt(
                artifact_type,
                plan_goal=plan.goal,
                unit_title=unit.title,
                objectives=unit.objectives,
                prerequisite_unit_ids=unit.prerequisite_unit_ids,
                source_ids=unit_sources,
                context=bounded_context,
            )
            prompt = prompt[:MAX_PROMPT_CHARS]
            # Calling artifact_context here is deliberate: it is the existing
            # bounded context/citation adapter, not a second generator.  The
            # generation service loads the same sources again by IDs.
            combined_context, _ = artifact_context(sources)
            if not combined_context.strip():
                raise StudyArtifactNotReady("no_evidence")
            provisional = await self._create_provisional(
                plan,
                artifact_type=artifact_type,
                unit=unit,
                source_ids=unit_sources,
                prompt=prompt,
            )
            artifact_id = str(getattr(provisional, "id", "") or "")
            if not artifact_id:
                raise StudyArtifactGenerationError("artifact_generation_failed")
            request = ArtifactGenerationRequest(
                artifact_id=artifact_id,
                source_ids=list(unit_sources),
            )
            try:
                generated = await generate_artifact(request)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                if isinstance(exc, asyncio.CancelledError):
                    await self._mark(provisional, "cancelled")
                    raise StudyArtifactCancelled("generation_cancelled") from exc
                await self._mark(provisional, "failed")
                raise StudyArtifactGenerationError("artifact_generation_failed") from exc
            if str(getattr(generated, "status", "")) != "completed":
                await self._mark(provisional, str(getattr(generated, "status", "failed")))
                raise StudyArtifactGenerationError("artifact_generation_failed")
            completed_id = str(getattr(generated, "id", "") or artifact_id)
            metadata = {
                "unit_id": unit.unit_id,
                "syllabus_version": syllabus.version,
                "source_manifest_sha256": syllabus.source_manifest_sha256,
                "expected_revision": revision,
            }
            try:
                await self._link(
                    plan_key,
                    completed_id,
                    artifact_kind=artifact_type,
                    metadata=metadata,
                )
            except StudyArtifactError:
                raise
            except Exception as exc:
                raise StudyArtifactUnavailable("artifact_link_unavailable") from exc
            receipts.append(
                {
                    "artifact_id": completed_id,
                    "artifact_type": artifact_type,
                    "status": "completed",
                    "unit_id": unit.unit_id,
                }
            )
        return receipts

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

    async def _load_syllabus(self, plan_id: str, version: int) -> StudySyllabus:
        try:
            syllabus = await self.repository.get_syllabus(plan_id, version=version)
        except Exception as exc:
            raise StudyArtifactUnavailable("syllabus_unavailable") from exc
        if syllabus is None:
            raise StudyArtifactNotFound("syllabus_not_found")
        return syllabus

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
    ) -> StudioArtifact:
        try:
            artifact = StudioArtifact(
                notebook_id=_artifact_notebook_id(plan.plan_id),
                artifact_type=artifact_type,
                title=f"{unit.title} — {artifact_type.replace('_', ' ')}",
                status="pending",
                source_ids=list(source_ids),
                prompt=prompt,
            )
            await artifact.save()
            return artifact
        except Exception as exc:
            raise StudyArtifactUnavailable("artifact_persistence_unavailable") from exc

    async def _mark(self, artifact: object, status: str) -> None:
        try:
            setattr(artifact, "status", status if status in {"failed", "cancelled"} else "failed")
            for field_name, empty_value in (
                ("output_payload", {}),
                ("citations", []),
                ("export_paths", {}),
            ):
                if hasattr(artifact, field_name):
                    setattr(artifact, field_name, empty_value)
            save = getattr(artifact, "save", None)
            if callable(save):
                result = save()
                if inspect.isawaitable(result):
                    await result
        except Exception:
            # A failed/cancelled provisional record must never become a plan
            # link; inability to persist its terminal status is non-authorizing.
            return

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
