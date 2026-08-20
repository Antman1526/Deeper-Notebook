"""Approval-gated, source-grounded syllabus proposal service.

The service is deliberately narrower than the Evidence Studio artifact
pipeline: it produces one immutable, typed ``StudySyllabus`` version and does
not create downstream artifacts or approve the result.  Source records remain
the authority for both evidence and content fingerprints.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from collections.abc import Iterable, Mapping
from types import SimpleNamespace
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from deeper_notebook.domain.notebook import Source
from deeper_notebook.studio.generation.context import artifact_context
from deeper_notebook.studio.schemas import ArtifactDocumentBase
from deeper_notebook.studio.structured_generation import (
    StructuredArtifactGenerationError,
    generate_structured_document,
)
from deeper_notebook.study.plan_repository import (
    StudyPlanConflictError,
    StudyPlanNotFoundError,
    StudyPlanRepository,
    StudyPlanRepositoryError,
)
from deeper_notebook.study.plans import (
    StudyActivity,
    StudyPlan,
    StudySyllabus,
    StudySyllabusUnit,
)
from deeper_notebook.study.source_service import (
    StudySourceNotFoundError,
    StudySourceService,
    StudySourceUnavailableError,
    normalize_source_id,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_CONTEXT_CHARS = 64_000
_MAX_SOURCE_LINKS = 100
_GENERATION_TIMEOUT_SECONDS = 120
_MODEL_MAX_TOKENS = 3_072


class StudySyllabusError(RuntimeError):
    """Base class for safe, typed syllabus-domain failures."""

    code = "syllabus_error"

    def __init__(self, reason: str | None = None):
        self.reason = reason or self.code
        super().__init__(self.reason)


class StudySyllabusNotFound(StudySyllabusError):
    code = "syllabus_not_found"


class StudySyllabusConflict(StudySyllabusError):
    code = "syllabus_conflict"


class StudySyllabusNotReady(StudySyllabusConflict):
    code = "sources_not_ready"


class StudySyllabusNoEvidence(StudySyllabusConflict):
    code = "no_evidence"


class StudySyllabusGenerationError(StudySyllabusError):
    code = "generation_unavailable"


class StudySyllabusTimeout(StudySyllabusGenerationError):
    code = "generation_timeout"


class StudySyllabusMalformedOutput(StudySyllabusError):
    code = "malformed_output"


class StudySyllabusValidationError(StudySyllabusMalformedOutput):
    code = "malformed_output"


class StudySyllabusBounds(StudySyllabusMalformedOutput):
    code = "syllabus_bounds"


class StudySyllabusUnavailable(StudySyllabusError):
    code = "syllabus_unavailable"


class StudySyllabusActivityDocument(BaseModel):
    """Bounded model-facing activity shape."""

    model_config = ConfigDict(extra="forbid", strict=True)

    activity_id: StrictStr = Field(
        min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$"
    )
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
    title: StrictStr = Field(min_length=1, max_length=200)
    estimated_minutes: StrictInt = Field(ge=5, le=10_080)
    source_ids: list[StrictStr] = Field(default_factory=list, max_length=100)

    @field_validator("activity_id", "title")
    @classmethod
    def text_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("activity text must not be blank")
        return value


class StudySyllabusUnitDocument(BaseModel):
    """Bounded model-facing syllabus unit shape."""

    model_config = ConfigDict(extra="forbid", strict=True)

    unit_id: StrictStr = Field(
        min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$"
    )
    title: StrictStr = Field(min_length=1, max_length=200)
    objectives: list[StrictStr] = Field(min_length=1, max_length=20)
    prerequisite_unit_ids: list[StrictStr] = Field(default_factory=list, max_length=20)
    estimated_minutes: StrictInt = Field(ge=5, le=10_080)
    source_ids: list[StrictStr] = Field(min_length=1, max_length=100)
    activities: list[StudySyllabusActivityDocument] = Field(
        default_factory=list, max_length=50
    )

    @field_validator("unit_id", "title")
    @classmethod
    def text_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("unit text must not be blank")
        return value

    @field_validator("objectives", "prerequisite_unit_ids", "source_ids")
    @classmethod
    def collection_text_is_nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("unit collection text must not be blank")
        return values


class StudySyllabusDocument(ArtifactDocumentBase):
    """Typed structured-generation document for a proposed syllabus."""

    model_config = ConfigDict(extra="forbid", strict=True)

    artifact_type: Literal["study_syllabus"] = "study_syllabus"
    title: StrictStr = Field(min_length=1, max_length=200)
    units: list[StudySyllabusUnitDocument] = Field(min_length=1, max_length=64)
    knowledge_gaps: list[StrictStr] = Field(default_factory=list, max_length=32)

    @field_validator("title")
    @classmethod
    def title_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("syllabus title must not be blank")
        return value

    @field_validator("knowledge_gaps")
    @classmethod
    def gaps_are_bounded(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("knowledge gaps must not be blank")
        return values

    @model_validator(mode="after")
    def unit_ids_are_unique(self) -> "StudySyllabusDocument":
        unit_ids = [unit.unit_id for unit in self.units]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("syllabus unit IDs must be unique")
        return self


def _value(source: object, key: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _canonical_source_id(source: object) -> str:
    raw = _value(source, "source_id", _value(source, "id"))
    if not isinstance(raw, str):
        raise StudySyllabusNoEvidence("source_id_missing")
    try:
        return normalize_source_id(raw).canonical
    except StudySourceNotFoundError as exc:
        raise StudySyllabusNoEvidence("source_id_invalid") from exc


def _fingerprint(source: object) -> str:
    provenance = _value(source, "provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    for key in ("content_fingerprint", "fingerprint", "source_fingerprint"):
        candidate = _value(source, key, None)
        if candidate is None:
            candidate = provenance.get(key)
        if isinstance(candidate, str) and _SHA256.fullmatch(candidate.lower()):
            return candidate.lower()

    text = _value(source, "full_text", None)
    if isinstance(text, str) and text.strip():
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    raise StudySyllabusNoEvidence("source_fingerprint_missing")


def source_manifest(sources: Iterable[object]) -> str:
    """Return a deterministic SHA-256 manifest for canonical source evidence."""

    entries: list[str] = []
    seen: set[str] = set()
    for source in sources:
        source_id = _canonical_source_id(source)
        if source_id in seen:
            raise StudySyllabusValidationError("duplicate_sources")
        seen.add(source_id)
        entries.append(f"{source_id}\x00{_fingerprint(source)}")
    if not entries:
        raise StudySyllabusNoEvidence("no_evidence")
    return hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()


def detect_drift(syllabus: StudySyllabus, sources: Iterable[object]) -> bool:
    """Compare an immutable syllabus manifest with current source evidence."""

    return source_manifest(sources) != syllabus.source_manifest_sha256


async def _maybe_await(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


def _safe_error(
    exc: BaseException, fallback: type[StudySyllabusError], reason: str
) -> StudySyllabusError:
    if isinstance(exc, StudySyllabusError):
        return exc
    if isinstance(exc, (StudyPlanNotFoundError,)):
        return StudySyllabusNotFound("syllabus_not_found")
    if isinstance(exc, (StudyPlanConflictError,)):
        return StudySyllabusConflict("revision_conflict")
    if isinstance(exc, StudyPlanRepositoryError):
        return StudySyllabusUnavailable("syllabus_unavailable")
    return fallback(reason)


class StudySyllabusService:
    """Generate immutable proposed syllabi and perform drift-guarded approval."""

    source_manifest = staticmethod(source_manifest)

    def __init__(
        self,
        *,
        repository: object | None = None,
        source_service: object | None = None,
        model_resolver: object | None = None,
        source_loader: object | None = None,
    ) -> None:
        self.repository = repository or StudyPlanRepository()
        self.source_service = source_service or StudySourceService()
        self.model_resolver = model_resolver
        self.source_loader = source_loader or Source.get

    async def propose(self, plan_id: str, *, expected_revision: int) -> StudySyllabus:
        (
            plan,
            sources,
            manifest,
            context_text,
            citations,
        ) = await self._load_ready_plan_sources(
            plan_id, expected_revision=expected_revision
        )
        try:
            model = await self._resolve_model(plan, context_text)
            result = await generate_structured_document(
                model=model,
                schema=StudySyllabusDocument,
                messages=self._messages(plan, context_text, citations),
                timeout_seconds=_GENERATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise StudySyllabusTimeout("generation_timeout") from exc
        except StructuredArtifactGenerationError as exc:
            raise StudySyllabusMalformedOutput("malformed_output") from exc
        except StudySyllabusError:
            raise
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc

        try:
            document = (
                result.document
                if isinstance(result.document, StudySyllabusDocument)
                else StudySyllabusDocument.model_validate(result.document)
            )
            syllabus = self._to_syllabus(
                plan,
                document,
                manifest=manifest,
                selected_source_ids={
                    _canonical_source_id(source) for source in sources
                },
            )
        except StudySyllabusError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StudySyllabusMalformedOutput("malformed_output") from exc

        try:
            latest = await self.repository.get_syllabus(plan.plan_id)
            version = (latest.version + 1) if latest is not None else 1
            syllabus = syllabus.model_copy(update={"version": version})
            return await self.repository.save_syllabus(
                syllabus,
                expected_revision=expected_revision,
                lifecycle_action="propose",
            )
        except StudySyllabusError:
            raise
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc

    async def approve(
        self,
        plan_id: str,
        *,
        syllabus_version: int,
        expected_revision: int,
    ) -> StudyPlan:
        try:
            plan = await self.repository.get(plan_id)
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc
        if plan is None:
            raise StudySyllabusNotFound("syllabus_not_found")
        if plan.version != expected_revision:
            raise StudySyllabusConflict("revision_conflict")
        if plan.state != "editing":
            raise StudySyllabusConflict("invalid_lifecycle")

        try:
            syllabus = await self.repository.get_syllabus(
                plan_id, version=syllabus_version
            )
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc
        if syllabus is None:
            raise StudySyllabusNotFound("syllabus_not_found")
        if syllabus.approved_at is not None:
            raise StudySyllabusConflict("already_approved")

        _, sources, current_manifest, _, _ = await self._load_ready_plan_sources(
            plan_id, expected_revision=expected_revision
        )
        if current_manifest != syllabus.source_manifest_sha256:
            raise StudySyllabusConflict("sources_changed")
        try:
            return await self.repository.approve_syllabus(
                plan_id,
                syllabus_version=syllabus_version,
                expected_revision=expected_revision,
            )
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc

    async def detect_drift(
        self,
        plan_id: str,
        *,
        syllabus_version: int | None = None,
    ) -> bool:
        """Read current source evidence and compare it to a stored version."""

        try:
            plan = await self.repository.get(plan_id)
            if plan is None:
                raise StudySyllabusNotFound("syllabus_not_found")
            syllabus = await self.repository.get_syllabus(
                plan_id, version=syllabus_version
            )
        except StudySyllabusError:
            raise
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc
        if syllabus is None:
            raise StudySyllabusNotFound("syllabus_not_found")
        _, sources, _, _, _ = await self._load_ready_plan_sources(
            plan_id, expected_revision=plan.version
        )
        return detect_drift(syllabus, sources)

    async def _load_ready_plan_sources(
        self,
        plan_id: str,
        *,
        expected_revision: int,
    ) -> tuple[StudyPlan, list[object], str, str, list[dict[str, str]]]:
        try:
            plan = await self.repository.get(plan_id)
        except Exception as exc:
            raise _safe_error(
                exc, StudySyllabusUnavailable, "syllabus_unavailable"
            ) from exc
        if plan is None:
            raise StudySyllabusNotFound("syllabus_not_found")
        if plan.version != expected_revision:
            raise StudySyllabusConflict("revision_conflict")
        if not plan.source_links:
            raise StudySyllabusNoEvidence("no_evidence")
        try:
            readiness = await self.source_service.readiness(plan)
        except (StudySourceNotFoundError, StudySourceUnavailableError) as exc:
            raise StudySyllabusNotReady("sources_not_ready") from exc
        except Exception as exc:
            raise StudySyllabusUnavailable("source_authority_unavailable") from exc
        if not getattr(readiness, "ready", False):
            raise StudySyllabusNotReady("sources_not_ready")

        sources: list[object] = []
        seen: set[str] = set()
        for link in plan.source_links:
            try:
                canonical_id = normalize_source_id(link.source_id).canonical
            except StudySourceNotFoundError as exc:
                raise StudySyllabusNotReady("source_not_found") from exc
            if canonical_id in seen:
                raise StudySyllabusValidationError("duplicate_sources")
            seen.add(canonical_id)
            try:
                source = await _maybe_await(self.source_loader(canonical_id))
            except Exception as exc:
                raise StudySyllabusNotReady("source_not_ready") from exc
            if source is None:
                raise StudySyllabusNotReady("source_not_ready")
            text = _value(source, "full_text", None)
            if not isinstance(text, str) or not text.strip():
                raise StudySyllabusNoEvidence("no_evidence")
            sources.append(source)

        try:
            manifest = source_manifest(sources)
        except StudySyllabusError:
            raise
        except Exception as exc:
            raise StudySyllabusNoEvidence("no_evidence") from exc
        context_text, citations = artifact_context(sources)
        bounded_context = context_text[:_MAX_CONTEXT_CHARS]
        if not bounded_context.strip() or not citations:
            raise StudySyllabusNoEvidence("no_evidence")
        return plan, sources, manifest, bounded_context, citations

    async def _resolve_model(self, plan: StudyPlan, context_text: str) -> object:
        if self.model_resolver is not None:
            try:
                return await _maybe_await(self.model_resolver(plan))
            except asyncio.TimeoutError as exc:
                raise StudySyllabusTimeout("generation_timeout") from exc
            except Exception as exc:
                raise StudySyllabusUnavailable("model_unavailable") from exc

        try:
            from deeper_notebook.ai.provision import provision_langchain_model
            from deeper_notebook.studio.generation.context import (
                resolve_artifact_model_route,
            )

            route = await resolve_artifact_model_route(
                SimpleNamespace(
                    artifact_type="flashcards", model_id=None, provider=None
                )
            )
            model_id = route[0] if isinstance(route, tuple) else None
            return await provision_langchain_model(
                context_text,
                model_id,
                "study_fast",
                max_tokens=_MODEL_MAX_TOKENS,
            )
        except asyncio.TimeoutError as exc:
            raise StudySyllabusTimeout("generation_timeout") from exc
        except Exception as exc:
            raise StudySyllabusUnavailable("model_unavailable") from exc

    @staticmethod
    def _messages(
        plan: StudyPlan,
        context_text: str,
        citations: list[dict[str, str]],
    ) -> list[object]:
        source_ids = ", ".join(citation["source_id"] for citation in citations)
        system = (
            "You are the local Curriculum Architect. Propose an editable, "
            "source-grounded syllabus for the study plan below. Return only the "
            "typed JSON object requested by the structured-output schema. Every "
            "unit must cite one or more selected source IDs in source_ids; do not "
            "invent source IDs. Use concise bounded objectives and activities. "
            "Prerequisites must refer to unit_id values in this response.\n\n"
            f"Study goal: {plan.goal}\n"
            f"Starting level: {plan.starting_level}\n"
            f"Selected source IDs: {source_ids}"
        )
        return [SystemMessage(content=system), HumanMessage(content=context_text)]

    @staticmethod
    def _to_syllabus(
        plan: StudyPlan,
        document: StudySyllabusDocument,
        *,
        manifest: str,
        selected_source_ids: set[str],
    ) -> StudySyllabus:
        units: list[StudySyllabusUnit] = []
        unit_ids = {unit.unit_id for unit in document.units}
        for unit in document.units:
            prerequisites = tuple(unit.prerequisite_unit_ids)
            if len(set(prerequisites)) != len(prerequisites):
                raise StudySyllabusValidationError("duplicate_prerequisites")
            if any(prerequisite not in unit_ids for prerequisite in prerequisites):
                raise StudySyllabusValidationError("unknown_prerequisite")
            source_ids = StudySyllabusService._canonicalize_output_sources(
                unit.source_ids,
                selected_source_ids,
            )
            activities: list[StudyActivity] = []
            activity_ids: set[str] = set()
            for activity in unit.activities:
                if activity.activity_id in activity_ids:
                    raise StudySyllabusValidationError("duplicate_activities")
                activity_ids.add(activity.activity_id)
                activity_source_ids = StudySyllabusService._canonicalize_output_sources(
                    activity.source_ids,
                    selected_source_ids,
                    allow_empty=True,
                )
                activities.append(
                    StudyActivity(
                        activity_id=activity.activity_id,
                        kind=activity.kind,
                        title=activity.title,
                        estimated_minutes=activity.estimated_minutes,
                        source_ids=activity_source_ids,
                    )
                )
            units.append(
                StudySyllabusUnit(
                    unit_id=unit.unit_id,
                    title=unit.title,
                    objectives=tuple(unit.objectives),
                    prerequisite_unit_ids=prerequisites,
                    estimated_minutes=unit.estimated_minutes,
                    source_ids=source_ids,
                    activities=tuple(activities),
                )
            )
        StudySyllabusService._validate_prerequisite_graph(units)
        try:
            return StudySyllabus(
                plan_id=plan.plan_id,
                version=1,
                source_manifest_sha256=manifest,
                units=tuple(units),
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise StudySyllabusBounds("syllabus_bounds") from exc

    @staticmethod
    def _canonicalize_output_sources(
        source_ids: Iterable[str],
        selected_source_ids: set[str],
        *,
        allow_empty: bool = False,
    ) -> tuple[str, ...]:
        values: list[str] = []
        seen: set[str] = set()
        for source_id in source_ids:
            try:
                canonical = normalize_source_id(source_id).canonical
            except StudySourceNotFoundError as exc:
                raise StudySyllabusValidationError("source_id_invalid") from exc
            if canonical in seen:
                raise StudySyllabusValidationError("duplicate_source_citations")
            if canonical not in selected_source_ids:
                raise StudySyllabusValidationError("source_id_not_selected")
            seen.add(canonical)
            values.append(canonical)
        if not values and not allow_empty:
            raise StudySyllabusNoEvidence("unit_without_evidence")
        return tuple(values)

    @staticmethod
    def _validate_prerequisite_graph(units: Iterable[StudySyllabusUnit]) -> None:
        graph = {unit.unit_id: tuple(unit.prerequisite_unit_ids) for unit in units}
        state: dict[str, int] = {}

        def visit(unit_id: str) -> None:
            mark = state.get(unit_id, 0)
            if mark == 1:
                raise StudySyllabusValidationError("cyclic_prerequisites")
            if mark == 2:
                return
            state[unit_id] = 1
            for prerequisite in graph[unit_id]:
                visit(prerequisite)
            state[unit_id] = 2

        for unit_id in graph:
            visit(unit_id)


__all__ = [
    "StudySyllabusActivityDocument",
    "StudySyllabusBounds",
    "StudySyllabusConflict",
    "StudySyllabusDocument",
    "StudySyllabusError",
    "StudySyllabusGenerationError",
    "StudySyllabusMalformedOutput",
    "StudySyllabusNoEvidence",
    "StudySyllabusNotFound",
    "StudySyllabusNotReady",
    "StudySyllabusService",
    "StudySyllabusTimeout",
    "StudySyllabusUnavailable",
    "StudySyllabusUnitDocument",
    "StudySyllabusValidationError",
    "detect_drift",
    "source_manifest",
]
