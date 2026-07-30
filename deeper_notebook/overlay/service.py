"""Orchestration boundary for canonical app-owned Markdown."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayNote,
    OverlayPage,
    UpdateOverlayNote,
)
from deeper_notebook.overlay.paths import (
    daily_relative_path,
    overlay_frontmatter,
    unique_relative_path,
)
from deeper_notebook.overlay.repository import (
    OverlayConflictError,
    OverlayRepository,
    OverlayRepositoryError,
    OverlayReservation,
)
from deeper_notebook.overlay.storage import (
    OverlayConflictError as OverlayStorageConflictError,
)
from deeper_notebook.overlay.storage import (
    OverlayStorage,
    OverlayStorageError,
    StoredOverlayBytes,
)
from deeper_notebook.vault.parsers import parse_document


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class OverlayService:
    """Coordinate idempotent database reservations and canonical storage."""

    def __init__(
        self,
        repository: OverlayRepository,
        storage: OverlayStorage,
        *,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.clock = clock

    async def create_daily(self, request: CreateDailyNote) -> OverlayPage:
        relative_path = daily_relative_path(request.date_key)
        reservation = await self.repository.reserve_create(
            operation="create-daily",
            idempotency_key=f"daily:{request.date_key}",
            kind="daily",
            date_key=request.date_key,
            relative_path=relative_path,
            title=request.date_key,
        )
        return await self._create(
            reservation,
            body=f"# {request.date_key}\n",
        )

    async def create_unique(self, request: CreateUniqueNote) -> OverlayPage:
        blocked_paths: set[str] = set()
        local_time = _aware(self.clock())
        while True:
            relative_path = unique_relative_path(
                local_time,
                request.title,
                exists=blocked_paths.__contains__,
            )
            try:
                reservation = await self.repository.reserve_create(
                    operation="create-unique",
                    idempotency_key=request.idempotency_key,
                    kind="unique",
                    date_key=None,
                    relative_path=relative_path,
                    title=request.title,
                )
                break
            except OverlayConflictError as error:
                if str(error) != "overlay_path_conflict":
                    raise
                blocked_paths.add(relative_path)
        return await self._create(
            reservation,
            body=f"# {request.title}\n",
        )

    async def _create(
        self,
        reservation: OverlayReservation,
        *,
        body: str,
    ) -> OverlayPage:
        replay = await self.repository.get_replay(reservation)
        if replay is not None:
            return replay
        note = await self.repository.get_note(reservation.overlay_note_id)
        markdown = overlay_frontmatter(note, body)
        try:
            stored = self.storage.create(
                reservation.relative_path,
                markdown,
                operation_id=reservation.operation_id,
            )
        except OverlayStorageConflictError:
            replay = await self.repository.get_replay(reservation)
            if replay is not None:
                return replay
            try:
                stored = self.storage.read(reservation.relative_path)
            except OverlayStorageError as error:
                await self._record_failure(reservation, error.code)
                raise
        except OverlayStorageError as error:
            await self._record_failure(reservation, error.code)
            raise
        return await self._parse_commit_or_mark_pending(
            reservation,
            stored,
            relative_snapshot=None,
        )

    async def get_page(self, note_id: str) -> OverlayPage:
        page = await self.repository.get_page(note_id)
        try:
            stored = self.storage.read(page.overlay.relative_path)
        except OverlayStorageError as error:
            raise OverlayRepositoryError(error.code) from None
        if stored.content_hash != page.overlay.content_hash:
            raise OverlayRepositoryError("overlay_projection_pending")
        return page

    async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]:
        return await self.repository.list_notes(limit, offset)

    async def update(
        self,
        note_id: str,
        request: UpdateOverlayNote,
    ) -> OverlayPage:
        reservation = await self.repository.reserve_update(
            note_id=note_id,
            expected_revision=request.expected_revision,
            idempotency_key=request.idempotency_key,
        )
        replay = await self.repository.get_replay(reservation)
        if replay is not None:
            return replay

        current = await self.repository.get_note(note_id)
        try:
            stored = self.storage.read(current.relative_path)
        except OverlayStorageError as error:
            await self._record_failure(reservation, error.code)
            raise
        receipt = await self.repository.get_receipt(reservation)
        reconciling = bool(
            receipt is not None
            and receipt.status == "failed"
            and receipt.after_hash == stored.content_hash
            and stored.content_hash != current.content_hash
        )
        if stored.content_hash != current.content_hash and not reconciling:
            self.repository.stage_failure_hash(reservation, stored.content_hash)
            await self._record_failure(
                reservation,
                "overlay_revision_conflict",
            )
            raise OverlayConflictError("overlay_revision_conflict")

        updated_reservation = replace(reservation, title=request.title)
        if reconciling:
            published = stored
            relative_snapshot = None
        else:
            try:
                snapshot = self.storage.snapshot(
                    current.id,
                    current.revision,
                    stored,
                )
                candidate = current.model_copy(
                    update={
                        "title": request.title,
                        "updated_at": _aware(self.clock()),
                    }
                )
                markdown = overlay_frontmatter(candidate, request.markdown)
                published = self.storage.replace(
                    current.relative_path,
                    markdown,
                    expected_hash=current.content_hash,
                    revision=current.revision + 1,
                    operation_id=reservation.operation_id,
                )
            except OverlayStorageError as error:
                await self._record_failure(reservation, error.code)
                raise
            relative_snapshot = snapshot.relative_snapshot

        return await self._parse_commit_or_mark_pending(
            updated_reservation,
            published,
            relative_snapshot=relative_snapshot,
        )

    async def _parse_commit_or_mark_pending(
        self,
        reservation: OverlayReservation,
        stored: StoredOverlayBytes,
        *,
        relative_snapshot: str | None,
    ) -> OverlayPage:
        self.repository.stage_failure_hash(reservation, stored.content_hash)
        try:
            parsed = parse_document(
                stored.relative_path,
                stored.markdown.encode("utf-8"),
                format_mode="markdown",
                max_markdown_bytes=self.storage.max_markdown_bytes,
            )
        except Exception:
            await self._record_failure(reservation, "overlay_parser_failed")
            raise OverlayRepositoryError("overlay_projection_pending") from None
        try:
            await self.repository.commit_revision(
                reservation=reservation,
                content_hash=stored.content_hash,
                byte_size=stored.byte_size,
                relative_snapshot=relative_snapshot,
                parsed=parsed,
            )
        except OverlayConflictError:
            replay = await self.repository.get_replay(reservation)
            if replay is not None:
                return replay
            await self._record_failure(
                reservation,
                "overlay_projection_pending",
            )
            raise
        except Exception:
            await self._record_failure(
                reservation,
                "overlay_projection_pending",
            )
            raise OverlayRepositoryError("overlay_projection_pending") from None
        return await self.repository.get_page(reservation.overlay_note_id)

    async def _record_failure(
        self,
        reservation: OverlayReservation,
        error_code: str,
    ) -> None:
        try:
            await self.repository.record_failure(
                reservation=reservation,
                error_code=error_code,
            )
        except Exception:
            # The primary error remains the only public error. A later retry
            # re-fingerprints canonical bytes and reconciles from the receipt.
            return


__all__ = ["OverlayService"]
