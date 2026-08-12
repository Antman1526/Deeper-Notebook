"""Read-only source authority for the Study Workbench.

Study plans link existing ``Source`` records.  This module deliberately keeps
the projection small: callers can learn whether a source is usable without
receiving its body, local path, processing error, or other ingestion details.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.domain.notebook import Source
from deeper_notebook.exceptions import NotFoundError
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


class StudySourceError(RuntimeError):
    """Base class for safe source-service failures."""


class StudySourceNotFoundError(StudySourceError):
    """The requested source record does not exist."""


class StudySourceUnavailableError(StudySourceError):
    """The source authority could not be read."""


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
    items: tuple[StudySourceReadinessItem, ...] = Field(max_length=100)


class StudySourceService:
    """Resolve existing Source records without duplicating ingestion logic."""

    async def validate_source(self, source_id: str) -> Source:
        """Require one existing source before a plan link is persisted."""
        normalized_id = self._normalize_source_id(source_id)
        try:
            source = await Source.get(normalized_id)
        except NotFoundError as exc:
            if self._looks_unavailable(exc):
                raise StudySourceUnavailableError("source authority unavailable") from exc
            raise StudySourceNotFoundError("source not found") from exc
        except Exception as exc:
            raise StudySourceUnavailableError("source authority unavailable") from exc
        if source is None:
            raise StudySourceNotFoundError("source not found")
        return source

    async def readiness(
        self,
        plan_or_links: StudyPlan | Iterable[StudyPlanSourceLink | str],
    ) -> StudySourceReadiness:
        """Return one safe readiness item per unique linked source.

        Missing records are represented as a bounded ``missing`` item.  A
        transient authority failure is represented as ``unavailable`` so this
        read-only projection never leaks driver details to an API caller.
        """
        links = self._links(plan_or_links)
        items: list[StudySourceReadinessItem] = []
        seen: set[str] = set()
        for raw_link in links:
            source_id = self._link_source_id(raw_link)
            if source_id in seen:
                continue
            seen.add(source_id)
            items.append(await self._readiness_item(source_id))
        return StudySourceReadiness(
            ready=bool(items) and all(item.ready for item in items),
            items=tuple(items),
        )

    async def _readiness_item(self, source_id: str) -> StudySourceReadinessItem:
        try:
            source = await Source.get(source_id)
        except NotFoundError as exc:
            if self._looks_unavailable(exc):
                return self._unavailable_item(source_id)
            return self._missing_item(source_id)
        except Exception:
            return self._unavailable_item(source_id)
        if source is None:
            return self._missing_item(source_id)

        title = self._title(source)
        kind = self._kind(source)
        command_id = self._command_id(source)
        fingerprint_status = self._fingerprint_status(source)
        status = await self._status(source)
        full_text = getattr(source, "full_text", None)
        has_text = isinstance(full_text, str) and bool(full_text.strip())
        extraction_quality = getattr(source, "extraction_quality", None)

        if status == "failed":
            ready = False
            reason: SourceReason = "processing_failed"
        elif status in _PROCESSING_STATUSES or status == "unknown":
            ready = False
            reason = "processing"
        elif extraction_quality in {"pending", "no_text", "low_text"} or not has_text:
            # Source processing owns extraction.  The study service only
            # observes the existing text/status fields; it never re-ingests.
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

    @staticmethod
    async def _status(source: Any) -> str | None:
        get_status = getattr(source, "get_status", None)
        if not callable(get_status):
            return None
        try:
            status = await get_status()
        except Exception:
            return "unknown"
        return status if isinstance(status, str) else None

    @staticmethod
    def _title(source: Any) -> str:
        title = getattr(source, "title", None)
        if isinstance(title, str) and title.strip():
            return title.strip()[:200]
        return "Untitled source"

    @classmethod
    def _kind(cls, source: Any) -> SourceKind:
        source_type = getattr(source, "source_type", None)
        if isinstance(source_type, str) and source_type in _SOURCE_KINDS:
            return source_type  # type: ignore[return-value]
        asset = getattr(source, "asset", None)
        if getattr(asset, "url", None):
            return "link"
        if getattr(asset, "file_path", None):
            return "upload"
        return "text"

    @staticmethod
    def _command_id(source: Any) -> str | None:
        command = getattr(source, "command", None)
        if command is None:
            return None
        value = str(command).strip()
        return value[:512] if value else None

    @classmethod
    def _fingerprint_status(cls, source: Any) -> FingerprintStatus:
        for attribute in ("fingerprint", "content_fingerprint", "source_fingerprint"):
            value = getattr(source, attribute, None)
            if isinstance(value, str) and _SHA256.fullmatch(value):
                return "available"
        provenance = getattr(source, "provenance", None)
        if isinstance(provenance, dict):
            for key in ("fingerprint", "content_fingerprint", "source_fingerprint"):
                value = provenance.get(key)
                if isinstance(value, str) and _SHA256.fullmatch(value):
                    return "available"
        return "unknown"

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
        return normalized

    @staticmethod
    def _looks_unavailable(exc: Exception) -> bool:
        # ObjectModel.get wraps driver failures in NotFoundError.  Preserve a
        # safe distinction between a genuine missing record and an unavailable
        # source authority without returning the wrapped driver message.
        message = str(exc).lower()
        return any(
            marker in message
            for marker in ("authentication", "connection", "database", "timeout")
        )

    @classmethod
    def _links(
        cls,
        plan_or_links: StudyPlan | Iterable[StudyPlanSourceLink | str],
    ) -> Iterable[StudyPlanSourceLink | str]:
        if isinstance(plan_or_links, StudyPlan):
            return plan_or_links.source_links
        return plan_or_links

    @classmethod
    def _link_source_id(cls, link: StudyPlanSourceLink | str) -> str:
        raw_id = link.source_id if isinstance(link, StudyPlanSourceLink) else link
        return cls._normalize_source_id(raw_id)
