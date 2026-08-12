"""Read-only Source authority for the Study Workbench.

Study plans link existing ``source`` records.  The workbench must not load a
whole Source object (which contains bodies, paths, and provenance), so this
module owns one fixed, bounded projection used for both validation and
readiness.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.study.plans import StudyPlan, StudyPlanSourceLink

SourceKind = Literal[
    "link",
    "upload",
    "text",
    "web_import",
    "deep_research_report",
]
SourceReason = Literal[
    "ready",
    "processing",
    "processing_failed",
    "missing",
    "unavailable",
]
FingerprintStatus = Literal["available", "unknown"]

_SOURCE_KINDS: frozenset[str] = frozenset(
    {"link", "upload", "text", "web_import", "deep_research_report"}
)
_PROCESSING_STATUSES: frozenset[str] = frozenset({"new", "queued", "running"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_LINKS = 100

# This is intentionally the only Source query in the Study authority.  It
# excludes asset paths, source bodies, and the rest of provenance while still
# allowing the UI to report bounded readiness and fingerprint availability.
SOURCE_PROJECTION = """
SELECT id, title, source_type, command,
    string::len(full_text) AS text_length,
    string::len(string::trim(full_text)) > 0 AS has_text,
    provenance.fingerprint AS fingerprint,
    provenance.content_fingerprint AS content_fingerprint,
    provenance.source_fingerprint AS source_fingerprint
FROM $source_id LIMIT 1;
"""


class StudySourceError(RuntimeError):
    """Base class for safe source-service failures."""


class StudySourceNotFoundError(StudySourceError):
    """The requested source record does not exist."""


class StudySourceUnavailableError(StudySourceError):
    """The source authority could not be read."""


class StudySourceInputLimitError(StudySourceError):
    """The caller supplied more than the bounded source-link limit."""


class StudySourceReadinessItem(BaseModel):
    """Bounded source readiness projection safe for study-plan callers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=200)
    kind: SourceKind
    ready: bool
    command_id: str | None = Field(default=None, max_length=512)
    fingerprint_status: FingerprintStatus
    reason: SourceReason


class StudySourceReadiness(BaseModel):
    """Readiness for the unique source links attached to a study plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ready: bool
    items: tuple[StudySourceReadinessItem, ...] = Field(max_length=_MAX_LINKS)


class StudySourceService:
    """Resolve existing source records through a fixed projection only."""

    async def validate_source(self, source_id: str) -> dict[str, Any]:
        """Require one existing source before a plan link is persisted."""
        normalized_id = self._normalize_source_id(source_id)
        projection = await self._read_projection(normalized_id)
        if projection is None:
            raise StudySourceNotFoundError("source not found")
        return projection

    async def readiness(
        self,
        plan_or_links: StudyPlan | Iterable[StudyPlanSourceLink | str],
    ) -> StudySourceReadiness:
        """Return one safe readiness item per unique linked source.

        Inputs are consumed and bounded before the first database call.  This
        both protects an accidental infinite iterable and prevents a caller
        from causing a partial fan-out before an over-limit request fails.
        """
        source_ids = self._collect_source_ids(self._links(plan_or_links))
        items = [await self._readiness_item(source_id) for source_id in source_ids]
        return StudySourceReadiness(
            ready=bool(items) and all(item.ready for item in items),
            items=tuple(items),
        )

    async def _readiness_item(self, source_id: str) -> StudySourceReadinessItem:
        try:
            projection = await self._read_projection(source_id)
        except StudySourceUnavailableError:
            return self._unavailable_item(source_id)
        if projection is None:
            return self._missing_item(source_id)

        title = self._title(projection)
        kind = self._kind(projection)
        command_id = self._command_id(projection.get("command"))
        fingerprint_status = self._fingerprint_status(projection)
        status = await self._status(command_id)
        has_text = self._has_text(projection)

        if status == "failed":
            ready = False
            reason: SourceReason = "processing_failed"
        elif status in _PROCESSING_STATUSES or status == "unknown":
            ready = False
            reason = "processing"
        elif not has_text:
            ready = False
            reason = "processing"
        else:
            ready = True
            reason = "ready"

        return StudySourceReadinessItem(
            source_id=source_id,
            title=title,
            kind=kind,
            ready=ready,
            command_id=command_id,
            fingerprint_status=fingerprint_status,
            reason=reason,
        )

    async def _read_projection(self, source_id: str) -> dict[str, Any] | None:
        normalized_id = self._normalize_source_id(source_id)
        try:
            rows = await repo_query(
                SOURCE_PROJECTION,
                {"source_id": ensure_record_id(normalized_id)},
            )
        except Exception as exc:
            raise StudySourceUnavailableError("source authority unavailable") from exc
        if not rows:
            return None
        first = rows[0]
        if not isinstance(first, dict):
            raise StudySourceUnavailableError("source authority unavailable")
        return first

    @staticmethod
    async def _status(command_id: str | None) -> str | None:
        if not command_id:
            return None
        try:
            from surreal_commands import get_command_status

            result = await get_command_status(command_id)
            status = getattr(result, "status", None)
            return status if isinstance(status, str) else None
        except Exception:
            return "unknown"

    @staticmethod
    def _title(projection: dict[str, Any]) -> str:
        title = projection.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()[:200]
        return "Untitled source"

    @classmethod
    def _kind(cls, projection: dict[str, Any]) -> SourceKind:
        source_type = projection.get("source_type")
        if isinstance(source_type, str) and source_type in _SOURCE_KINDS:
            return source_type  # type: ignore[return-value]
        return "text"

    @staticmethod
    def _command_id(command: Any) -> str | None:
        if command is None:
            return None
        value = str(command).strip()
        return value[:512] if value else None

    @classmethod
    def _fingerprint_status(cls, projection: dict[str, Any]) -> FingerprintStatus:
        for key in ("fingerprint", "content_fingerprint", "source_fingerprint"):
            value = projection.get(key)
            if isinstance(value, str) and _SHA256.fullmatch(value):
                return "available"
        return "unknown"

    @staticmethod
    def _has_text(projection: dict[str, Any]) -> bool:
        value = projection.get("has_text")
        if isinstance(value, bool):
            return value
        length = projection.get("text_length")
        return isinstance(length, (int, float)) and not isinstance(length, bool) and length > 0

    @staticmethod
    def _missing_item(source_id: str) -> StudySourceReadinessItem:
        return StudySourceReadinessItem(
            source_id=source_id,
            title="Source unavailable",
            kind="text",
            ready=False,
            command_id=None,
            fingerprint_status="unknown",
            reason="missing",
        )

    @staticmethod
    def _unavailable_item(source_id: str) -> StudySourceReadinessItem:
        return StudySourceReadinessItem(
            source_id=source_id,
            title="Source unavailable",
            kind="text",
            ready=False,
            command_id=None,
            fingerprint_status="unknown",
            reason="unavailable",
        )

    @staticmethod
    def _normalize_source_id(source_id: str) -> str:
        if not isinstance(source_id, str):
            raise StudySourceNotFoundError("source not found")
        normalized = source_id.strip()
        if not normalized or len(normalized) > 512:
            raise StudySourceNotFoundError("source not found")
        try:
            record = ensure_record_id(normalized)
        except Exception as exc:
            raise StudySourceNotFoundError("source not found") from exc
        if getattr(record, "table_name", None) != "source":
            raise StudySourceNotFoundError("source not found")
        record_token = getattr(record, "id", None)
        if not isinstance(record_token, str) or not record_token.strip():
            raise StudySourceNotFoundError("source not found")
        if len(str(record)) > 512:
            raise StudySourceNotFoundError("source not found")
        return normalized

    @classmethod
    def _links(
        cls,
        plan_or_links: StudyPlan | Iterable[StudyPlanSourceLink | str],
    ) -> Iterable[StudyPlanSourceLink | str]:
        if isinstance(plan_or_links, StudyPlan):
            return plan_or_links.source_links
        return plan_or_links

    @classmethod
    def _collect_source_ids(
        cls,
        links: Iterable[StudyPlanSourceLink | str],
    ) -> tuple[str, ...]:
        source_ids: list[str] = []
        seen: set[str] = set()
        for index, link in enumerate(links):
            if index >= _MAX_LINKS:
                raise StudySourceInputLimitError("too many source links")
            source_id = cls._link_source_id(link)
            if source_id not in seen:
                seen.add(source_id)
                source_ids.append(source_id)
        return tuple(source_ids)

    @classmethod
    def _link_source_id(cls, link: StudyPlanSourceLink | str) -> str:
        raw_id = link.source_id if isinstance(link, StudyPlanSourceLink) else link
        return cls._normalize_source_id(raw_id)
