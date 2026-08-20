"""Best-effort, write-contained engine projections after legacy success."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from typing import Protocol

from loguru import logger

from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import (
    KnowledgeIdentityClaim,
    KnowledgeSnapshot,
    SourceEnvelope,
    SourceKind,
    validate_snapshot_spans,
)
from deeper_notebook.knowledge_engine.identity import engine_record_id
from deeper_notebook.overlay.contracts import OverlayNote
from deeper_notebook.vault.repository import VaultMount
from deeper_notebook.vault.watcher import VaultWorkItem


class _KnowledgeRepository(Protocol):
    async def commit_snapshot(
        self, snapshot: KnowledgeSnapshot, *, operation_id: str
    ) -> object: ...

    async def record_projection_failure(
        self,
        *,
        operation_id: str,
        space_id: str,
        relative_locator: str,
        input_hash: str,
        error_code: str,
    ) -> object: ...


class KnowledgeShadowProjector(Protocol):
    """Legacy-service dependency that can only submit derived engine state."""

    async def project_external(
        self,
        *,
        legacy_operation_id: str,
        mount: VaultMount,
        observation: VaultWorkItem,
        source_kind: SourceKind,
        vault_file_id: str,
        projected_note_id: str,
    ) -> None: ...

    async def project_overlay(
        self,
        *,
        legacy_operation_id: str,
        overlay_note: OverlayNote,
        canonical_markdown: str,
        observed_modified_ns: int,
    ) -> None: ...

    async def record_external_failure(
        self,
        *,
        legacy_operation_id: str,
        mount: VaultMount,
        observation: VaultWorkItem,
        error: Exception,
    ) -> None: ...

    async def record_overlay_failure(
        self,
        *,
        legacy_operation_id: str,
        overlay_note: OverlayNote,
        canonical_markdown: str,
        error: Exception,
    ) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _space_id(source_ref: str) -> str:
    return f"knowledge_engine_space:{sha256(source_ref.encode()).hexdigest()}"


def _operation_id(
    legacy_operation_id: str, relative_locator: str, source_hash: str
) -> str:
    legacy_hash = sha256(legacy_operation_id.encode("utf-8")).hexdigest()
    locator_hash = sha256(relative_locator.encode("utf-8")).hexdigest()
    return f"shadow-v1:{legacy_hash}:{locator_hash}:{source_hash}"


def _failure_code(error: Exception) -> str:
    value = getattr(error, "code", None)
    if isinstance(value, str) and re.fullmatch(
        r"knowledge_engine_[a-z0-9_]{1,103}", value
    ):
        return value
    return "knowledge_engine_projection_failed"


def _claim(
    legacy_kind: str,
    legacy_id: str,
    engine_kind: str,
    engine_id: str,
    revision_id: str,
) -> KnowledgeIdentityClaim:
    payload = "\0".join(
        (legacy_kind, legacy_id, engine_kind, engine_id, revision_id)
    ).encode()
    return KnowledgeIdentityClaim(
        legacy_kind=legacy_kind,
        legacy_id=legacy_id,
        engine_kind=engine_kind,
        engine_id=engine_id,
        source_revision_id=revision_id,
        claim_hash=sha256(payload).hexdigest(),
    )


class KnowledgeShadowCoordinator:
    """Project known canonical bytes without participating in legacy writes."""

    def __init__(
        self,
        *,
        repository: _KnowledgeRepository,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    async def project_external(
        self,
        *,
        legacy_operation_id: str,
        mount: VaultMount,
        observation: VaultWorkItem,
        source_kind: SourceKind,
        vault_file_id: str,
        projected_note_id: str,
    ) -> None:
        if source_kind not in {"obsidian", "logseq", "markdown"}:
            raise ValueError("invalid_knowledge_shadow_external_source_kind")
        space_id = _space_id(mount.id)
        envelope = SourceEnvelope(
            space_id=space_id,
            space_display_name=mount.name,
            source_ref=mount.id,
            authority_kind="external_read_only",
            source_kind=source_kind,
            format_mode=mount.format_mode,
            relative_locator=observation.relative_path,
            canonical_bytes=observation.content,
            byte_size=observation.byte_size,
            declared_encoding=None,
            declared_newline=None,
            observed_content_hash=observation.content_hash,
            observed_modified_ns=observation.modified_ns,
            observed_at=self._clock(),
        )
        document_id = engine_record_id("document", space_id, observation.relative_path)
        revision_id = engine_record_id(
            "revision",
            space_id,
            f"{observation.relative_path}/revisions/{observation.content_hash}",
        )
        await self._submit(
            envelope=envelope,
            operation_id=_operation_id(
                legacy_operation_id,
                observation.relative_path,
                observation.content_hash,
            ),
            claims=(
                _claim("vault_mount", mount.id, "space", space_id, revision_id),
                _claim(
                    "vault_file", vault_file_id, "document", document_id, revision_id
                ),
                _claim("note", projected_note_id, "document", document_id, revision_id),
            ),
        )

    async def project_overlay(
        self,
        *,
        legacy_operation_id: str,
        overlay_note: OverlayNote,
        canonical_markdown: str,
        observed_modified_ns: int,
    ) -> None:
        canonical_bytes = canonical_markdown.encode("utf-8")
        content_hash = sha256(canonical_bytes).hexdigest()
        space_id = _space_id("overlay:default")
        envelope = SourceEnvelope(
            space_id=space_id,
            space_display_name="Deeper Notebook Overlay",
            source_ref="overlay:default",
            authority_kind="app_owned",
            source_kind="overlay",
            format_mode="markdown",
            relative_locator=overlay_note.relative_path,
            canonical_bytes=canonical_bytes,
            byte_size=len(canonical_bytes),
            declared_encoding=overlay_note.encoding,
            declared_newline=overlay_note.newline,
            observed_content_hash=content_hash,
            observed_modified_ns=observed_modified_ns,
            observed_at=self._clock(),
        )
        document_id = engine_record_id("document", space_id, overlay_note.relative_path)
        revision_id = engine_record_id(
            "revision",
            space_id,
            f"{overlay_note.relative_path}/revisions/{content_hash}",
        )
        await self._submit(
            envelope=envelope,
            operation_id=_operation_id(
                legacy_operation_id,
                overlay_note.relative_path,
                content_hash,
            ),
            claims=(
                _claim(
                    "overlay_space",
                    overlay_note.space_id,
                    "space",
                    space_id,
                    revision_id,
                ),
                _claim(
                    "overlay_note",
                    overlay_note.id,
                    "document",
                    document_id,
                    revision_id,
                ),
                _claim(
                    "note",
                    overlay_note.projected_note_id,
                    "document",
                    document_id,
                    revision_id,
                ),
            ),
        )

    async def record_external_failure(
        self,
        *,
        legacy_operation_id: str,
        mount: VaultMount,
        observation: VaultWorkItem,
        error: Exception,
    ) -> None:
        await self._record_failure(
            space_id=_space_id(mount.id),
            relative_locator=observation.relative_path,
            input_hash=observation.content_hash,
            operation_id=_operation_id(
                legacy_operation_id,
                observation.relative_path,
                observation.content_hash,
            ),
            error_code=_failure_code(error),
        )

    async def record_overlay_failure(
        self,
        *,
        legacy_operation_id: str,
        overlay_note: OverlayNote,
        canonical_markdown: str,
        error: Exception,
    ) -> None:
        canonical_bytes = canonical_markdown.encode("utf-8")
        content_hash = sha256(canonical_bytes).hexdigest()
        await self._record_failure(
            space_id=_space_id("overlay:default"),
            relative_locator=overlay_note.relative_path,
            input_hash=content_hash,
            operation_id=_operation_id(
                legacy_operation_id,
                overlay_note.relative_path,
                content_hash,
            ),
            error_code=_failure_code(error),
        )

    async def _submit(
        self,
        *,
        envelope: SourceEnvelope,
        operation_id: str,
        claims: tuple[KnowledgeIdentityClaim, ...],
    ) -> None:
        try:
            snapshot = adapter_for(envelope.source_kind).project(envelope)
            snapshot = snapshot.model_copy(
                update={"identity_claims": [*snapshot.identity_claims, *claims]}
            )
            snapshot = KnowledgeSnapshot.model_validate(
                snapshot.model_dump(mode="python")
            )
            validate_snapshot_spans(snapshot, source_size=envelope.byte_size)
            receipt = await self._repository.commit_snapshot(
                snapshot, operation_id=operation_id
            )
            if getattr(receipt, "status", None) not in {"projected", "unchanged"}:
                raise RuntimeError("knowledge_engine_commit_invalid")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._record_failure(
                space_id=envelope.space_id,
                relative_locator=envelope.relative_locator,
                input_hash=envelope.observed_content_hash,
                operation_id=operation_id,
                error_code=_failure_code(error),
            )

    async def _record_failure(
        self,
        *,
        space_id: str,
        relative_locator: str,
        input_hash: str,
        operation_id: str,
        error_code: str,
    ) -> None:
        try:
            receipt = await self._repository.record_projection_failure(
                operation_id=operation_id,
                space_id=space_id,
                relative_locator=relative_locator,
                input_hash=input_hash,
                error_code=error_code,
            )
            if getattr(receipt, "status", None) != "failed":
                raise RuntimeError("knowledge_engine_failure_receipt_invalid")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Knowledge shadow failure receipt unavailable space_id={} operation_id={} code={}",
                space_id,
                operation_id,
                "knowledge_engine_failure_receipt_unavailable",
            )
            return
        logger.warning(
            "Knowledge shadow projection failed space_id={} operation_id={} code={}",
            space_id,
            operation_id,
            error_code,
        )


__all__ = ["KnowledgeShadowCoordinator", "KnowledgeShadowProjector"]
