"""Owner-fenced worker flow for one source-derived visual command."""

from __future__ import annotations

import asyncio
import inspect
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Literal, TypeVar

from pydantic import ConfigDict, Field
from surreal_commands import CommandInput, CommandOutput

from deeper_notebook.domain.notebook import Source
from deeper_notebook.source_visuals.authority import (
    SourceVisualAuthorityError,
    compute_source_visual_authority,
)
from deeper_notebook.source_visuals.cleanup import SourceVisualCleanup
from deeper_notebook.source_visuals.contracts import SourceVisualRecord
from deeper_notebook.source_visuals.extractors import (
    extract_audio_artwork,
    extract_pdf_candidates,
    extract_video_candidates,
)
from deeper_notebook.source_visuals.media import (
    SourceVisualMediaError,
    build_alt_text,
    prepare_webp,
    select_candidate,
)
from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepository,
    SourceVisualRepositoryError,
)
from deeper_notebook.source_visuals.storage import (
    SourceVisualStorageError,
    SourceVisualStore,
)

_AwaitableValue = TypeVar("_AwaitableValue")
_CLAIM_LEASE_SECONDS = 90
_GLOBAL_MEDIA_SEMAPHORE = asyncio.Semaphore(2)
_FINGERPRINT_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
_FINGERPRINT_LOCKS_GUARD = asyncio.Lock()


class ExtractSourceVisualInput(CommandInput):
    """Strict command input with the durable claim owner fence."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^source:[A-Za-z0-9_-]+$", max_length=512)
    request_id: str = Field(min_length=1, max_length=256)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_version: str = Field(min_length=1, max_length=64)
    claim_owner_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExtractSourceVisualOutput(CommandOutput):
    """Public-safe worker receipt, deliberately excluding errors, text, and paths."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    origin: Literal["embedded", "video_frame", "audio_artwork"] | None = None
    width: int | None = Field(default=None, ge=1, le=1280)
    height: int | None = Field(default=None, ge=1, le=720)
    duration_ms: int = Field(ge=0, le=60_000)
    outcome: Literal["ready", "failed"]
    error_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$",
        max_length=64,
    )


async def _await_if_needed(value: _AwaitableValue | Awaitable[_AwaitableValue]) -> _AwaitableValue:
    if inspect.isawaitable(value):
        return await value
    return value


async def _run_boundary(function, *args):
    """Use a worker thread for sync decoder/storage boundaries, not async seams."""

    if inspect.iscoroutinefunction(function):
        return await function(*args)
    value = await asyncio.to_thread(function, *args)
    return await _await_if_needed(value)


async def _fingerprint_lock(identity: str) -> asyncio.Lock:
    async with _FINGERPRINT_LOCKS_GUARD:
        lock = _FINGERPRINT_LOCKS.get(identity)
        if lock is None:
            lock = asyncio.Lock()
            _FINGERPRINT_LOCKS[identity] = lock
        return lock


def _safe_error_code(value: object, *, fallback: str = "extraction_failed") -> str:
    raw = str(getattr(value, "code", fallback)).strip().lower()
    safe = "".join(character if character.isalnum() else "_" for character in raw)
    safe = safe.strip("_")[:64]
    return safe or fallback


def _source_locator(candidate: object) -> dict[str, int | str]:
    locator = dict(getattr(candidate, "locator", {}))
    origin = getattr(candidate, "origin", None)
    if origin == "video_frame":
        return {"timestamp_ms": int(locator["timestamp_ms"])}
    if origin == "audio_artwork":
        return {"resource_id": str(locator["resource_id"])}
    # Contracts permit exactly one embedded locator.  The extractor supplies
    # page + resource ID for ranking; persist the more specific opaque ID.
    if "resource_id" in locator:
        return {"resource_id": str(locator["resource_id"])}
    return {"page": int(locator["page"])}


class SourceVisualService:
    def __init__(
        self,
        *,
        repository: SourceVisualRepository | object | None = None,
        store: SourceVisualStore | object | None = None,
        cleanup: SourceVisualCleanup | object | None = None,
    ) -> None:
        self._repository = repository or SourceVisualRepository()
        self._store = store or SourceVisualStore()
        self._cleanup = cleanup or SourceVisualCleanup(self._store, self._repository)

    async def _renew(self, authority: object, owner_token: str) -> None:
        await _await_if_needed(
            self._repository.renew_claim(
                source_id=authority.source_id,
                content_sha256=authority.content_sha256,
                extractor_version=authority.extractor_version,
                owner_token=owner_token,
                lease_seconds=_CLAIM_LEASE_SECONDS,
            )
        )

    async def _candidates(self, authority: object) -> list[object]:
        path = getattr(authority, "controlled_file_path", None)
        if not isinstance(path, str) or not path:
            raise SourceVisualMediaError("SOURCE_MEDIA_UNAVAILABLE")
        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            return list(await _run_boundary(extract_pdf_candidates, path))
        if suffix in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}:
            return list(await _run_boundary(extract_video_candidates, path))
        if suffix in {".m4a", ".mp3", ".aac", ".flac", ".ogg", ".wav"}:
            candidate = await _run_boundary(extract_audio_artwork, path)
            return [candidate] if candidate is not None else []
        raise SourceVisualMediaError("SOURCE_MEDIA_UNSUPPORTED")

    async def _cleanup_task_temp(self) -> None:
        cleanup = getattr(self._store, "reconcile_staged_files", None)
        if callable(cleanup):
            try:
                await _run_boundary(lambda: cleanup(limit=100))
            except TypeError:
                await _run_boundary(cleanup)
            except SourceVisualStorageError:
                pass

    async def _release(self, authority: object, owner_token: str) -> None:
        try:
            await _await_if_needed(
                self._repository.release_claim(
                    source_id=authority.source_id,
                    content_sha256=authority.content_sha256,
                    extractor_version=authority.extractor_version,
                    owner_token=owner_token,
                )
            )
        except Exception:
            pass

    async def execute(self, input_data: ExtractSourceVisualInput) -> ExtractSourceVisualOutput:
        """Execute bounded extraction without changing source content or paths."""

        started = time.monotonic()
        authority = None

        def failed(error_code: str) -> ExtractSourceVisualOutput:
            return ExtractSourceVisualOutput(
                source_id=input_data.source_id,
                content_sha256=input_data.expected_content_sha256,
                duration_ms=min(60_000, int((time.monotonic() - started) * 1_000)),
                outcome="failed",
                error_code=error_code,
            )

        try:
            source = await _await_if_needed(Source.get(input_data.source_id))
            if source is None:
                return failed("source_missing")
            authority = await _await_if_needed(compute_source_visual_authority(source))
            if (
                authority.content_sha256 != input_data.expected_content_sha256
                or authority.extractor_version != input_data.extractor_version
            ):
                return failed("source_stale")

            lock = await _fingerprint_lock(
                f"{authority.source_id}\0{authority.content_sha256}\0{authority.extractor_version}"
            )
            async with _GLOBAL_MEDIA_SEMAPHORE:
                async with lock:
                    await self._renew(authority, input_data.claim_owner_token)
                    candidates = await self._candidates(authority)
                    await self._renew(authority, input_data.claim_owner_token)
                    candidate = await _run_boundary(select_candidate, candidates)
                    if candidate is None:
                        raise SourceVisualMediaError("NO_ELIGIBLE_CANDIDATE")
                    prepared = await _run_boundary(prepare_webp, candidate.encoded_bytes)
                    staged = await _run_boundary(
                        self._store.stage,
                        authority.source_id,
                        authority.content_sha256,
                        prepared,
                    )
                    stored = await _run_boundary(self._store.publish, staged)
                    await self._renew(authority, input_data.claim_owner_token)
                    now = datetime.now(timezone.utc)
                    record = SourceVisualRecord(
                        source_id=authority.source_id,
                        source_updated_at=authority.source_updated_at,
                        source_file_sha256=authority.source_file_sha256,
                        content_sha256=authority.content_sha256,
                        asset_sha256=stored.asset_sha256,
                        asset_relpath=stored.asset_relpath,
                        origin=candidate.origin,
                        source_locator=_source_locator(candidate),
                        extractor_version=authority.extractor_version,
                        alt_text=await _run_boundary(
                            build_alt_text,
                            str(getattr(source, "title", "") or "Source"),
                            authority.normalized_source_type,
                            candidate,
                        ),
                        width=stored.width,
                        height=stored.height,
                        mime_type=stored.mime_type,
                        created_at=now,
                        updated_at=now,
                    )
                    await _await_if_needed(
                        self._repository.publish_ready(
                            record,
                            source_id=authority.source_id,
                            content_sha256=authority.content_sha256,
                            extractor_version=authority.extractor_version,
                            owner_token=input_data.claim_owner_token,
                            source_updated_at=authority.source_updated_at,
                        )
                    )
                    await _await_if_needed(
                        self._repository.complete_claim(
                            source_id=authority.source_id,
                            content_sha256=authority.content_sha256,
                            extractor_version=authority.extractor_version,
                            owner_token=input_data.claim_owner_token,
                        )
                    )
                    try:
                        await _await_if_needed(self._cleanup.evict_to_budget())
                    except SourceVisualStorageError:
                        pass
                    return ExtractSourceVisualOutput(
                        source_id=authority.source_id,
                        content_sha256=authority.content_sha256,
                        asset_sha256=stored.asset_sha256,
                        origin=candidate.origin,
                        width=stored.width,
                        height=stored.height,
                        duration_ms=min(60_000, int((time.monotonic() - started) * 1_000)),
                        outcome="ready",
                    )
        except asyncio.CancelledError:
            if authority is not None:
                await self._cleanup_task_temp()
                await self._release(authority, input_data.claim_owner_token)
            return failed("cancelled")
        except (
            SourceVisualAuthorityError,
            SourceVisualMediaError,
            SourceVisualRepositoryError,
            SourceVisualStorageError,
        ) as exc:
            if authority is not None:
                await self._cleanup_task_temp()
                await self._release(authority, input_data.claim_owner_token)
            return failed(_safe_error_code(exc))
        except Exception:
            if authority is not None:
                await self._cleanup_task_temp()
                await self._release(authority, input_data.claim_owner_token)
            return failed("extraction_failed")


__all__ = [
    "ExtractSourceVisualInput",
    "ExtractSourceVisualOutput",
    "SourceVisualService",
]
