"""Fail-closed local transcription and notebook-routing suggestions."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from .contracts import CaptureInboxItem
from .fingerprints import CaptureFingerprintError, fingerprint_file

CaptureRoutingState = Literal["ready", "no_model", "unavailable"]
_MEDIA_SUFFIXES = frozenset(
    {".aac", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm"}
)
_WORDS = re.compile(r"[a-z0-9]{2,}")


class CaptureRoutingError(ValueError):
    """The selected file does not satisfy the local capture safety boundary."""


class CaptureNotebook(BaseModel):
    """The small, read-only notebook shape needed for suggestions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class CaptureNotebookSuggestion(CaptureNotebook):
    score: float = Field(ge=0)
    reason: str = Field(min_length=1)


class CaptureRouteSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root_path: str
    relative_path: str
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=0)
    modified_ns: int = Field(ge=0)


class CaptureRouteResult(BaseModel):
    """A transcription result that cannot itself trigger an import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: CaptureRoutingState
    source: CaptureRouteSource
    transcript: str | None = None
    notebook_suggestions: list[CaptureNotebookSuggestion] = Field(
        default_factory=list, max_length=3
    )
    approval_required: Literal[True] = True
    reason: str | None = None


SpeechToTextGetter = Callable[[], Awaitable[Any | None]]
NotebookSuggester = Callable[
    [str, CaptureRouteSource, tuple[CaptureNotebook, ...]],
    Awaitable[list[CaptureNotebookSuggestion]],
]


class CaptureRoutingService:
    """Route only a stable, approved local capture through one STT model."""

    def __init__(
        self,
        *,
        approved_roots: Iterable[Path | str],
        capture_items: Iterable[CaptureInboxItem],
        notebooks: Iterable[CaptureNotebook],
        get_speech_to_text: SpeechToTextGetter,
        semantic_suggester: NotebookSuggester | None = None,
    ) -> None:
        self._roots = tuple(
            Path(root).expanduser().resolve() for root in approved_roots
        )
        self._items = tuple(capture_items)
        self._notebooks = tuple(notebooks)
        self._get_speech_to_text = get_speech_to_text
        self._semantic_suggester = semantic_suggester

    async def route(self, media_path: Path | str) -> CaptureRouteResult:
        source = self._validated_source(Path(media_path))
        try:
            model = await self._get_speech_to_text()
        except Exception:
            logger.warning("Capture routing could not acquire the configured STT model")
            return CaptureRouteResult(
                state="unavailable",
                source=source,
                reason="configured_speech_to_text_unavailable",
            )
        if model is None:
            return CaptureRouteResult(
                state="no_model",
                source=source,
                reason="no_default_speech_to_text_model",
            )
        try:
            result = await model.atranscribe(audio_file=Path(source.path))
        except Exception:
            logger.warning(
                "Capture routing transcription unavailable from configured STT model"
            )
            return CaptureRouteResult(
                state="unavailable",
                source=source,
                reason="configured_speech_to_text_unavailable",
            )

        transcript = self._transcript_text(result)
        return CaptureRouteResult(
            state="ready",
            source=source,
            transcript=transcript,
            notebook_suggestions=await self._suggest_notebooks(transcript, source),
        )

    def _validated_source(self, requested_path: Path) -> CaptureRouteSource:
        try:
            if requested_path.is_symlink():
                raise CaptureRoutingError("capture media must not be a symlink")
            candidate = requested_path.expanduser().resolve(strict=True)
        except OSError as exc:
            raise CaptureRoutingError(
                "capture media must be an existing local file"
            ) from exc
        if not candidate.is_file() or candidate.suffix.lower() not in _MEDIA_SUFFIXES:
            raise CaptureRoutingError("capture media must be a supported regular file")

        root, relative_path = self._approved_location(candidate)
        item = self._ready_item(root, relative_path)
        try:
            fingerprint = fingerprint_file(candidate)
            stat = candidate.stat()
        except (CaptureFingerprintError, OSError) as exc:
            raise CaptureRoutingError(
                "capture media changed or became unavailable"
            ) from exc
        if (
            item.sha256 != fingerprint.sha256
            or item.byte_size != fingerprint.byte_size
            or item.modified_ns != stat.st_mtime_ns
        ):
            raise CaptureRoutingError("capture media is not stable since its last scan")

        return CaptureRouteSource(
            root_path=str(root),
            relative_path=relative_path,
            path=str(candidate),
            sha256=fingerprint.sha256,
            byte_size=fingerprint.byte_size,
            modified_ns=stat.st_mtime_ns,
        )

    def _approved_location(self, candidate: Path) -> tuple[Path, str]:
        for root in self._roots:
            try:
                return root, candidate.relative_to(root).as_posix()
            except ValueError:
                continue
        raise CaptureRoutingError("capture media is outside an approved root")

    def _ready_item(self, root: Path, relative_path: str) -> CaptureInboxItem:
        for item in self._items:
            if (
                item.root_path == str(root)
                and item.relative_path == relative_path
                and item.state in {"ready", "duplicate"}
                and item.sha256 is not None
                and item.byte_size is not None
                and item.modified_ns is not None
            ):
                return item
        raise CaptureRoutingError("capture media has not passed the stability scan")

    @staticmethod
    def _transcript_text(result: object) -> str:
        text = getattr(result, "text", result)
        return str(text).strip()

    async def _suggest_notebooks(
        self, transcript: str, source: CaptureRouteSource
    ) -> list[CaptureNotebookSuggestion]:
        if self._semantic_suggester is not None and transcript:
            try:
                suggestions = await self._semantic_suggester(
                    transcript, source, self._notebooks
                )
                if suggestions:
                    return suggestions[:3]
            except Exception:
                logger.warning("Local semantic capture routing was unavailable")

        search_terms = set(
            _WORDS.findall(f"{transcript} {source.relative_path}".lower())
        )
        scored: list[CaptureNotebookSuggestion] = []
        for notebook in self._notebooks:
            matches = sorted(search_terms & set(_WORDS.findall(notebook.name.lower())))
            if matches:
                scored.append(
                    CaptureNotebookSuggestion(
                        **notebook.model_dump(),
                        score=float(len(matches)),
                        reason=f"Matched {', '.join(matches)}",
                    )
                )
        return sorted(scored, key=lambda item: (-item.score, item.name.lower()))[:3]
