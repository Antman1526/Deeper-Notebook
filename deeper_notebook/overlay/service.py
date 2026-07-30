"""Orchestration boundary for canonical app-owned Markdown."""

from __future__ import annotations

import hashlib
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
from deeper_notebook.vault.parsers.common import decode_source


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _encoded_markdown(markdown: str, maximum: int) -> bytes:
    try:
        payload = markdown.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    except UnicodeEncodeError:
        raise OverlayStorageError("overlay_invalid_markdown") from None
    if len(payload) > maximum:
        raise OverlayStorageError("overlay_file_too_large")
    return payload


def _reject_reserved_body_frontmatter(markdown: str, maximum: int) -> None:
    try:
        decoded = decode_source(
            markdown.encode("utf-8"),
            max_markdown_bytes=maximum,
        )
    except Exception:
        return
    if "deeper_notebook" in decoded.properties:
        raise OverlayStorageError("overlay_request_invalid")


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
        reservation: OverlayReservation | None = None
        while True:
            if reservation is None:
                relative_path = self._next_available_unique_path(
                    local_time,
                    request.title,
                    blocked_paths,
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
                except OverlayConflictError as error:
                    if str(error) != "overlay_path_conflict":
                        raise
                    blocked_paths.add(relative_path)
                    continue
            try:
                return await self._create(
                    reservation,
                    body=f"# {request.title}\n",
                )
            except OverlayConflictError as error:
                if str(error) != "overlay_disk_path_conflict":
                    raise
                blocked_paths.add(reservation.relative_path)
                while True:
                    next_path = self._next_available_unique_path(
                        local_time,
                        request.title,
                        blocked_paths,
                    )
                    try:
                        reservation = await self.repository.reassign_unique_path(
                            reservation=reservation,
                            relative_path=next_path,
                        )
                        break
                    except OverlayConflictError as reassign_error:
                        if str(reassign_error) != "overlay_path_conflict":
                            raise
                        blocked_paths.add(next_path)

    def _next_available_unique_path(
        self,
        local_time: datetime,
        title: str,
        blocked_paths: set[str],
    ) -> str:
        while True:
            relative_path = unique_relative_path(
                local_time,
                title,
                exists=blocked_paths.__contains__,
            )
            try:
                self.storage.read(relative_path)
            except OverlayStorageError as error:
                if error.code == "overlay_not_found":
                    return relative_path
                raise
            blocked_paths.add(relative_path)

    async def _create(
        self,
        reservation: OverlayReservation,
        *,
        body: str,
    ) -> OverlayPage:
        replay = await self.repository.get_replay(reservation)
        if replay is not None:
            return await self.get_page(reservation.overlay_note_id)
        note = await self.repository.get_note(reservation.overlay_note_id)
        markdown = overlay_frontmatter(note, body)
        payload = _encoded_markdown(markdown, self.storage.max_markdown_bytes)
        intended_hash = hashlib.sha256(payload).hexdigest()
        await self.repository.prepare_revision(
            reservation=reservation,
            content_hash=intended_hash,
        )
        try:
            stored = self.storage.create(
                reservation.relative_path,
                markdown,
                operation_id=reservation.operation_id,
            )
        except OverlayStorageConflictError:
            replay = await self.repository.get_replay(reservation)
            if replay is not None:
                return await self.get_page(reservation.overlay_note_id)
            try:
                stored = self.storage.read(reservation.relative_path)
            except OverlayStorageError as error:
                await self._record_failure(reservation, error.code)
                raise
            try:
                self._validate_reserved_bytes(
                    reservation,
                    stored,
                    expected_hash=intended_hash,
                )
            except OverlayConflictError as error:
                await self._record_failure(reservation, str(error))
                if reservation.kind == "unique":
                    raise OverlayConflictError("overlay_disk_path_conflict") from None
                raise
        except OverlayStorageError as error:
            await self._record_failure(reservation, error.code)
            raise
        self._validate_reserved_bytes(
            reservation,
            stored,
            expected_hash=intended_hash,
        )
        return await self._parse_commit_or_mark_pending(
            reservation,
            stored,
        )

    async def get_page(self, note_id: str) -> OverlayPage:
        page = await self.repository.get_page(note_id)
        try:
            stored = self.storage.read(page.overlay.relative_path)
        except OverlayStorageError as error:
            raise OverlayRepositoryError(error.code) from None
        if stored.content_hash != page.overlay.content_hash:
            raise OverlayRepositoryError("overlay_projection_pending")
        try:
            decoded = decode_source(
                stored.markdown.encode("utf-8"),
                max_markdown_bytes=self.storage.max_markdown_bytes,
            )
        except Exception:
            raise OverlayRepositoryError("overlay_projection_pending") from None
        return page.model_copy(update={"editable_markdown": decoded.body_markdown})

    async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]:
        return await self.repository.list_notes(limit, offset)

    async def update(
        self,
        note_id: str,
        request: UpdateOverlayNote,
    ) -> OverlayPage:
        _reject_reserved_body_frontmatter(
            request.markdown,
            self.storage.max_markdown_bytes,
        )
        reservation = await self.repository.reserve_update(
            note_id=note_id,
            expected_revision=request.expected_revision,
            idempotency_key=request.idempotency_key,
        )
        replay = await self.repository.get_replay(reservation)
        if replay is not None:
            return await self.get_page(note_id)

        current = await self.repository.get_note(note_id)
        try:
            stored = self.storage.read(current.relative_path)
        except OverlayStorageError as error:
            await self._record_failure(reservation, error.code)
            raise
        receipt = await self.repository.get_receipt(reservation)
        if receipt is None:
            raise OverlayRepositoryError("overlay_receipt_unavailable")
        candidate = current.model_copy(
            update={
                "title": request.title,
                "updated_at": _aware(receipt.started_at),
            }
        )
        markdown = overlay_frontmatter(candidate, request.markdown)
        payload = _encoded_markdown(markdown, self.storage.max_markdown_bytes)
        intended_hash = hashlib.sha256(payload).hexdigest()
        reconciling = bool(
            receipt.status in {"started", "failed"}
            and receipt.after_hash is not None
            and receipt.after_hash == stored.content_hash
            and receipt.after_hash == intended_hash
            and stored.content_hash != current.content_hash
        )
        published_receipt_mismatch = bool(
            receipt.status in {"started", "failed"}
            and receipt.after_hash is not None
            and receipt.after_hash == stored.content_hash
            and receipt.after_hash != intended_hash
        )
        if published_receipt_mismatch:
            await self._record_failure(reservation, "overlay_hash_conflict")
            raise OverlayConflictError("overlay_hash_conflict")
        if stored.content_hash != current.content_hash and not reconciling:
            await self._record_failure(
                reservation,
                "overlay_revision_conflict",
            )
            raise OverlayConflictError("overlay_revision_conflict")

        updated_reservation = replace(reservation, title=request.title)
        if reconciling:
            self._validate_reserved_bytes(
                updated_reservation,
                stored,
                expected_hash=receipt.after_hash,
            )
            published = stored
        else:
            await self.repository.prepare_revision(
                reservation=reservation,
                content_hash=intended_hash,
            )
            try:
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

        return await self._parse_commit_or_mark_pending(
            updated_reservation,
            published,
        )

    async def _parse_commit_or_mark_pending(
        self,
        reservation: OverlayReservation,
        stored: StoredOverlayBytes,
    ) -> OverlayPage:
        target_revision = (
            1
            if reservation.expected_revision is None
            else reservation.expected_revision + 1
        )
        try:
            snapshot = self.storage.snapshot(
                reservation.overlay_note_id,
                target_revision,
                stored,
            )
        except OverlayStorageError as error:
            await self._record_failure(reservation, error.code)
            raise
        if (
            snapshot.content_hash != stored.content_hash
            or snapshot.byte_size != stored.byte_size
        ):
            await self._record_failure(reservation, "invalid_snapshot_content")
            raise OverlayStorageError("invalid_snapshot_content")
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
                content_hash=snapshot.content_hash,
                byte_size=snapshot.byte_size,
                relative_snapshot=snapshot.relative_snapshot,
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
        return await self.get_page(reservation.overlay_note_id)

    def _validate_reserved_bytes(
        self,
        reservation: OverlayReservation,
        stored: StoredOverlayBytes,
        *,
        expected_hash: str,
    ) -> None:
        if stored.relative_path != reservation.relative_path:
            raise OverlayConflictError("overlay_identity_conflict")
        try:
            parsed = parse_document(
                stored.relative_path,
                stored.markdown.encode("utf-8"),
                format_mode="markdown",
                max_markdown_bytes=self.storage.max_markdown_bytes,
            )
        except Exception:
            raise OverlayConflictError("overlay_identity_conflict") from None
        identity = parsed.properties.get("deeper_notebook")
        expected_date = reservation.date_key if reservation.kind == "daily" else None
        if (
            not isinstance(identity, dict)
            or identity.get("id") != reservation.overlay_note_id
            or identity.get("kind") != reservation.kind
            or identity.get("date_key") != expected_date
        ):
            raise OverlayConflictError("overlay_identity_conflict")
        if stored.content_hash != expected_hash:
            raise OverlayConflictError("overlay_hash_conflict")

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
