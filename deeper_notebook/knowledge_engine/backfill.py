"""Read-only canonical catalog and restartable unified-engine backfill."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import (
    BackfillCheckpoint,
    KnowledgeIdentityClaim,
    KnowledgeSnapshot,
    SourceEnvelope,
    SourceKind,
    SourceRevision,
    validate_snapshot_spans,
)
from deeper_notebook.knowledge_engine.identity import engine_record_id
from deeper_notebook.knowledge_engine.repository import KnowledgeRepository
from deeper_notebook.overlay.contracts import OverlayNote
from deeper_notebook.overlay.repository import OverlayRepository
from deeper_notebook.overlay.storage import OverlayStorage, OverlayStorageError
from deeper_notebook.vault.contracts import VaultFormat
from deeper_notebook.vault.repository import VaultFile, VaultMount, VaultRepository
from deeper_notebook.vault.security import (
    VaultSecurityError,
    approve_vault_root,
    secure_read,
)

_PAGE_SIZE = 500
_MAX_EQUIVALENCE_SOURCES = 10_000
_EXTERNAL_FORMATS = frozenset({"obsidian", "logseq", "markdown"})
_BACKFILL_LOCK = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _space_id(source_ref: str) -> str:
    return f"knowledge_engine_space:{sha256(source_ref.encode()).hexdigest()}"


def _revision_id(space_id: str, locator: str, content_hash: str) -> str:
    return engine_record_id("revision", space_id, f"{locator}/revisions/{content_hash}")


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


@dataclass(frozen=True, slots=True)
class CanonicalSource:
    """One revalidated, root-free source ready for pure projection."""

    space_id: str
    space_display_name: str
    source_ref: str
    authority_kind: Literal["app_owned", "external_read_only"]
    source_kind: SourceKind
    format_mode: VaultFormat
    relative_locator: str
    canonical_bytes: bytes
    byte_size: int
    declared_encoding: str | None
    declared_newline: Literal["lf", "crlf", "mixed", "none"] | None
    observed_content_hash: str
    observed_modified_ns: int
    observed_at: datetime
    prior_revision: SourceRevision | None
    legacy_identities: tuple[KnowledgeIdentityClaim, ...]


@dataclass(frozen=True, slots=True)
class CatalogFailure:
    """A scrubbed, checkpointable read failure for one catalog record."""

    space_id: str
    relative_locator: str
    observed_content_hash: str
    error_code: str


@dataclass(frozen=True, slots=True)
class BackfillResult:
    projected: int = 0
    unchanged: int = 0
    failed: int = 0
    skipped: int = 0


class CanonicalSourceCatalog:
    """Read canonical Overlay and vault bytes without retaining source roots."""

    def __init__(
        self,
        *,
        overlay_repository: OverlayRepository,
        overlay_storage: OverlayStorage,
        vault_repository: VaultRepository,
        max_markdown_bytes: int | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._overlay_repository = overlay_repository
        self._overlay_storage = overlay_storage
        self._vault_repository = vault_repository
        self._max_markdown_bytes = max_markdown_bytes
        self._clock = clock
        self.failures: list[CatalogFailure] = []

    async def iter_sources(self) -> AsyncIterator[CanonicalSource]:
        """Yield only bytes which still agree with their durable observations."""
        self.failures = []
        overlay_sources = await self._overlay_sources()
        vault_sources = await self._vault_sources()
        for source in sorted(
            (*overlay_sources, *vault_sources),
            key=lambda value: (value.space_id, value.relative_locator),
        ):
            yield source

    async def iter_sources_for_space(
        self, space_id: str
    ) -> AsyncIterator[CanonicalSource]:
        """Read one selected legacy space with a hard, fail-closed inventory cap."""
        self.failures = []
        overlay_sources: list[CanonicalSource] = []
        if space_id == _space_id("overlay:default"):
            overlay_sources = await self._overlay_sources(
                max_sources=_MAX_EQUIVALENCE_SOURCES
            )
        vault_sources = await self._vault_sources(
            space_id=space_id,
            max_sources=_MAX_EQUIVALENCE_SOURCES - len(overlay_sources),
        )
        sources = [*overlay_sources, *vault_sources]
        if len(sources) > _MAX_EQUIVALENCE_SOURCES:
            raise RuntimeError("knowledge_engine_equivalence_inventory_too_large")
        for source in sorted(sources, key=lambda value: value.relative_locator):
            yield source

    async def _overlay_sources(
        self, *, max_sources: int | None = None
    ) -> list[CanonicalSource]:
        sources: list[CanonicalSource] = []
        offset = 0
        while True:
            notes = await self._overlay_repository.list_notes(_PAGE_SIZE, offset)
            if not notes:
                break
            for note in notes:
                source = self._read_overlay(note)
                if source is not None:
                    if max_sources is not None and len(sources) >= max_sources:
                        raise RuntimeError("knowledge_engine_equivalence_inventory_too_large")
                    sources.append(source)
            offset += len(notes)
            if len(notes) < _PAGE_SIZE:
                break
        return sources

    def _read_overlay(self, note: OverlayNote) -> CanonicalSource | None:
        source_ref = "overlay:default"
        space_id = _space_id(source_ref)
        try:
            stored = self._overlay_storage.read(note.relative_path)
            canonical_bytes = stored.markdown.encode("utf-8")
            observed_hash = sha256(canonical_bytes).hexdigest()
            if (
                observed_hash != note.content_hash
                or observed_hash != stored.content_hash
                or len(canonical_bytes) != stored.byte_size
            ):
                raise OverlayStorageError("overlay_catalog_changed")
        except OverlayStorageError as error:
            self.failures.append(
                CatalogFailure(
                    space_id=space_id,
                    relative_locator=note.relative_path,
                    observed_content_hash=note.content_hash,
                    error_code=error.code,
                )
            )
            return None
        revision_id = _revision_id(space_id, note.relative_path, observed_hash)
        document_id = engine_record_id("document", space_id, note.relative_path)
        claims = tuple(
            sorted(
                (
                    _claim("overlay_space", note.space_id, "space", space_id, revision_id),
                    _claim("overlay_note", note.id, "document", document_id, revision_id),
                    _claim("note", note.projected_note_id, "document", document_id, revision_id),
                ),
                key=lambda claim: (claim.legacy_kind, claim.legacy_id),
            )
        )
        return CanonicalSource(
            space_id=space_id,
            space_display_name="Deeper Notebook Overlay",
            source_ref=source_ref,
            authority_kind="app_owned",
            source_kind="overlay",
            format_mode="markdown",
            relative_locator=note.relative_path,
            canonical_bytes=canonical_bytes,
            byte_size=len(canonical_bytes),
            declared_encoding=note.encoding,
            declared_newline=note.newline,
            observed_content_hash=observed_hash,
            observed_modified_ns=stored.modified_ns,
            observed_at=self._clock(),
            prior_revision=None,
            legacy_identities=claims,
        )

    async def _vault_sources(
        self,
        *,
        space_id: str | None = None,
        max_sources: int | None = None,
    ) -> list[CanonicalSource]:
        sources: list[CanonicalSource] = []
        for mount in await self._vault_repository.list_mounts():
            if space_id is not None and _space_id(mount.id) != space_id:
                continue
            files = await self._vault_files(mount.id)
            relevant = [
                file
                for file in files
                if file.deleted_state == "present"
                and file.parse_status in {"parsed", "invalid"}
            ]
            if not relevant:
                continue
            try:
                with approve_vault_root(mount.root_path) as root:
                    for file in relevant:
                        source = self._read_vault_file(mount, file, root)
                        if source is not None:
                            if max_sources is not None and len(sources) >= max_sources:
                                raise RuntimeError(
                                    "knowledge_engine_equivalence_inventory_too_large"
                                )
                            sources.append(source)
            except VaultSecurityError as error:
                for file in relevant:
                    self._vault_failure(mount, file, error.code)
        return sources

    async def _vault_files(self, vault_id: str) -> list[VaultFile]:
        files: list[VaultFile] = []
        offset = 0
        while True:
            page = await self._vault_repository.list_files(
                vault_id, "", _PAGE_SIZE, offset
            )
            files.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += len(page)
        return sorted(files, key=lambda item: (item.vault_id, item.relative_path))

    def _read_vault_file(self, mount: VaultMount, file: VaultFile, root: object) -> CanonicalSource | None:
        if file.format not in _EXTERNAL_FORMATS or file.content_hash is None:
            self._vault_failure(mount, file, "knowledge_catalog_invalid_format")
            return None
        try:
            result = secure_read(root, file.relative_path, max_bytes=self._max_markdown_bytes)  # type: ignore[arg-type]
            if (
                result.sha256 != file.content_hash
                or result.byte_size != file.size_bytes
                or result.modified_ns != file.modified_ns
            ):
                raise VaultSecurityError("changed_during_read")
        except VaultSecurityError as error:
            self._vault_failure(mount, file, error.code)
            return None
        source_ref = mount.id
        space_id = _space_id(source_ref)
        source_kind = file.format
        revision_id = _revision_id(space_id, file.relative_path, result.sha256)
        document_id = engine_record_id("document", space_id, file.relative_path)
        claims = tuple(
            sorted(
                (
                    _claim("vault_mount", mount.id, "space", space_id, revision_id),
                    _claim("vault_file", file.id, "document", document_id, revision_id),
                    _claim("note", file.note_id, "document", document_id, revision_id),
                ),
                key=lambda claim: (claim.legacy_kind, claim.legacy_id),
            )
        )
        return CanonicalSource(
            space_id=space_id,
            space_display_name=mount.name,
            source_ref=source_ref,
            authority_kind="external_read_only",
            source_kind=source_kind,  # type: ignore[arg-type]
            format_mode=mount.format_mode,
            relative_locator=file.relative_path,
            canonical_bytes=result.content,
            byte_size=result.byte_size,
            declared_encoding=file.encoding,
            declared_newline=file.newline,
            observed_content_hash=result.sha256,
            observed_modified_ns=result.modified_ns,
            observed_at=self._clock(),
            prior_revision=None,
            legacy_identities=claims,
        )

    def _vault_failure(self, mount: VaultMount, file: VaultFile, code: str) -> None:
        self.failures.append(
            CatalogFailure(
                space_id=_space_id(mount.id),
                relative_locator=file.relative_path,
                observed_content_hash=file.content_hash or sha256(
                    f"{mount.id}\0{file.relative_path}".encode()
                ).hexdigest(),
                error_code=code,
            )
        )


class KnowledgeBackfillService:
    """Project catalogued source bytes through deterministic, durable receipts."""

    def __init__(
        self,
        *,
        catalog: CanonicalSourceCatalog,
        repository: KnowledgeRepository,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self._clock = clock

    async def run(self) -> BackfillResult:
        async with _BACKFILL_LOCK:
            sources = [source async for source in self.catalog.iter_sources()]
            entries: dict[str, list[CanonicalSource | CatalogFailure]] = defaultdict(list)
            for source in sources:
                entries[source.space_id].append(source)
            for failure in self.catalog.failures:
                entries[failure.space_id].append(failure)

            result = BackfillResult()
            for space_id in sorted(entries):
                checkpoint = await self.repository.get_checkpoint(space_id)
                resume_after = self._resume_after(checkpoint)
                counts = self._checkpoint_counts(checkpoint)
                for entry in sorted(entries[space_id], key=lambda item: item.relative_locator):
                    if (
                        resume_after is not None
                        and entry.relative_locator < resume_after
                    ):
                        result = self._increment(result, "skipped")
                        continue
                    if (
                        checkpoint is not None
                        and resume_after is not None
                        and entry.relative_locator == resume_after
                        and entry.observed_content_hash == checkpoint.last_source_hash
                    ):
                        result = self._increment(result, "skipped")
                        continue
                    if isinstance(entry, CatalogFailure):
                        await self._record_failure(entry)
                        counts["failed"] += 1
                        result = self._increment(result, "failed")
                        checkpoint = await self._persist_checkpoint(
                            space_id, entry.relative_locator, entry.observed_content_hash, counts
                        )
                        continue
                    try:
                        snapshot = self._project(entry)
                        receipt = await self.repository.commit_snapshot(
                            snapshot,
                            operation_id=self._operation_id(entry),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        await self._record_failure(
                            CatalogFailure(
                                space_id=entry.space_id,
                                relative_locator=entry.relative_locator,
                                observed_content_hash=entry.observed_content_hash,
                                error_code="knowledge_adapter_invalid",
                            )
                        )
                        counts["failed"] += 1
                        result = self._increment(result, "failed")
                        checkpoint = await self._persist_checkpoint(
                            space_id, entry.relative_locator, entry.observed_content_hash, counts
                        )
                        continue
                    status = getattr(receipt, "status", "")
                    if status == "projected":
                        counts["projected"] += 1
                        result = self._increment(result, "projected")
                    elif status == "unchanged":
                        counts["unchanged"] += 1
                        result = self._increment(result, "unchanged")
                    else:
                        await self._record_failure(
                            CatalogFailure(
                                space_id=entry.space_id,
                                relative_locator=entry.relative_locator,
                                observed_content_hash=entry.observed_content_hash,
                                error_code="knowledge_commit_invalid",
                            )
                        )
                        counts["failed"] += 1
                        result = self._increment(result, "failed")
                    checkpoint = await self._persist_checkpoint(
                        space_id, entry.relative_locator, entry.observed_content_hash, counts
                    )
                if checkpoint is not None:
                    await self.repository.save_checkpoint(
                        checkpoint.model_copy(update={"status": "completed", "updated_at": self._clock()})
                    )
            return result

    @staticmethod
    def _resume_after(checkpoint: BackfillCheckpoint | None) -> str | None:
        if checkpoint is None or checkpoint.status == "completed":
            return None
        return checkpoint.last_relative_locator

    @staticmethod
    def _checkpoint_counts(checkpoint: BackfillCheckpoint | None) -> dict[str, int]:
        if checkpoint is None or checkpoint.status == "completed":
            return {"projected": 0, "unchanged": 0, "failed": 0}
        return {
            "projected": checkpoint.projected,
            "unchanged": checkpoint.unchanged,
            "failed": checkpoint.failed,
        }

    def _project(self, source: CanonicalSource) -> KnowledgeSnapshot:
        envelope = SourceEnvelope(
            space_id=source.space_id,
            space_display_name=source.space_display_name,
            source_ref=source.source_ref,
            authority_kind=source.authority_kind,
            source_kind=source.source_kind,
            format_mode=source.format_mode,
            relative_locator=source.relative_locator,
            canonical_bytes=source.canonical_bytes,
            byte_size=source.byte_size,
            declared_encoding=source.declared_encoding,
            declared_newline=source.declared_newline,
            observed_content_hash=source.observed_content_hash,
            observed_modified_ns=source.observed_modified_ns,
            observed_at=source.observed_at,
            prior_revision=source.prior_revision,
        )
        snapshot = adapter_for(source.source_kind).project(envelope)
        if (
            snapshot.revision.content_hash != source.observed_content_hash
            or snapshot.revision.byte_size != source.byte_size
            or (
                source.declared_encoding is not None
                and snapshot.revision.encoding != source.declared_encoding
            )
            or (
                source.declared_newline is not None
                and snapshot.revision.newline != source.declared_newline
            )
        ):
            raise ValueError("knowledge catalog observation mismatch")
        snapshot = snapshot.model_copy(
            update={
                "identity_claims": [
                    *snapshot.identity_claims,
                    *source.legacy_identities,
                ]
            }
        )
        validated = KnowledgeSnapshot.model_validate(snapshot.model_dump(mode="python"))
        validate_snapshot_spans(validated, source_size=source.byte_size)
        return validated

    async def _record_failure(self, failure: CatalogFailure) -> None:
        receipt = await self.repository.record_projection_failure(
            operation_id=self._operation_id(
                failure.space_id,
                failure.relative_locator,
                failure.observed_content_hash,
            ),
            space_id=failure.space_id,
            relative_locator=failure.relative_locator,
            input_hash=failure.observed_content_hash,
            error_code=failure.error_code,
        )
        if getattr(receipt, "status", None) != "failed":
            raise RuntimeError("knowledge_failure_receipt_invalid")

    @staticmethod
    def _operation_id(
        source: CanonicalSource | str,
        relative_locator: str | None = None,
        source_hash: str | None = None,
    ) -> str:
        if isinstance(source, CanonicalSource):
            space_id = source.space_id
            relative_locator = source.relative_locator
            source_hash = source.observed_content_hash
        else:
            space_id = source
        assert relative_locator is not None
        assert source_hash is not None
        locator_hash = sha256(relative_locator.encode("utf-8")).hexdigest()
        return f"backfill-v1:{space_id}:{locator_hash}:{source_hash}"

    @staticmethod
    def _increment(result: BackfillResult, field: str) -> BackfillResult:
        return BackfillResult(
            projected=result.projected + (field == "projected"),
            unchanged=result.unchanged + (field == "unchanged"),
            failed=result.failed + (field == "failed"),
            skipped=result.skipped + (field == "skipped"),
        )

    async def _persist_checkpoint(
        self,
        space_id: str,
        locator: str,
        content_hash: str,
        counts: dict[str, int],
    ) -> BackfillCheckpoint:
        checkpoint = BackfillCheckpoint(
            space_id=space_id,
            last_relative_locator=locator,
            last_source_hash=content_hash,
            status="running",
            projected=counts["projected"],
            unchanged=counts["unchanged"],
            failed=counts["failed"],
            updated_at=self._clock(),
        )
        return await self.repository.save_checkpoint(checkpoint)


__all__ = [
    "BackfillResult",
    "CanonicalSource",
    "CanonicalSourceCatalog",
    "KnowledgeBackfillService",
]
