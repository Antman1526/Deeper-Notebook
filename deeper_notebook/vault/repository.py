"""Atomic persistence boundary for read-only external-vault projections."""

from __future__ import annotations

import asyncio
import inspect
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Any, Literal, Protocol

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from surreal_commands import submit_command as _submit_command
from surrealdb import RecordID

from deeper_notebook.database.repository import (
    db_connection,
    ensure_record_id,
    parse_record_ids,
)
from deeper_notebook.identity import LEGACY_COMMAND_APP
from deeper_notebook.vault._projection_context import (
    _PROJECTION_CAPABILITY,
    _activate_projection_refresh,
)
from deeper_notebook.vault.contracts import ParsedDocument, VaultFormat, VaultState
from deeper_notebook.vault.normalization import canonical_title_key
from deeper_notebook.vault.security import (
    ApprovedVaultRoot,
    VaultSecurityError,
    approve_vault_root,
    classify_vault_path,
    secure_read,
)
from deeper_notebook.vault.trust import (
    MAX_MANIFEST_BYTES,
    TrustManifestEntry,
    parse_trust_manifest,
)
from deeper_notebook.vault.watcher import VaultFileObservation, VaultWorkItem

if TYPE_CHECKING:
    from deeper_notebook.overlay.contracts import OverlayPage


@dataclass(frozen=True, slots=True)
class OwnedProjectionUnitOfWork:
    """Authority-scoped graph rows and mutations for one caller transaction."""

    variables: dict[str, Any]
    mutation_statement: str


@contextmanager
def _projection_note_refresh():
    """Grant note-refresh authority only inside the vault repository."""

    with _activate_projection_refresh(_PROJECTION_CAPABILITY):
        yield


class _Connection(Protocol):
    async def query(
        self,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> Any: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[_Connection]]
EmbeddingSubmitter = Callable[
    [str, str, dict[str, str]],
    Awaitable[Any] | Any,
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class VaultProjectionError(RuntimeError):
    """Persisted vault projection data violates a public read contract."""


def _canonical_vault_relative_path(value: str) -> str:
    if (
        not value
        or len(value) > 4096
        or value.strip() != value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value) is not None
        or "\\" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("value must be a canonical vault-relative path")
    return value


class VaultMountCreate(_Model):
    name: str
    root_path: str
    format_mode: VaultFormat
    status: VaultState = "disconnected"
    parent_vault_id: str | None = None
    watch_enabled: bool = False
    write_policy: Literal["read-only", "guarded-write"] = "read-only"
    protected_globs: list[str] = Field(default_factory=list)
    parser_version: str


class VaultMount(VaultMountCreate):
    id: str
    last_scan_started_at: datetime | None = None
    last_scan_completed_at: datetime | None = None


class VaultFile(_Model):
    id: str
    note_id: str
    vault_id: str
    relative_path: str
    file_kind: str
    format: str
    content_hash: str | None = None
    size_bytes: int = 0
    modified_ns: int = 0
    encoding: str | None = None
    newline: Literal["lf", "crlf", "mixed", "none"] | None = None
    parse_status: str
    parse_error_code: str | None = None
    deleted_state: Literal["present", "missing"]

    @field_validator("relative_path")
    @classmethod
    def canonical_relative_path(cls, value: str) -> str:
        return _canonical_vault_relative_path(value)


class VaultLink(_Model):
    id: str
    source_note_id: str
    source_note_title: str | None = None
    source_block_id: str | None = None
    target_note_id: str | None = None
    target_note_title: str | None = None
    target_relative_path: str | None = None
    target_block_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    alias: str | None = None
    link_kind: str
    resolved: bool = False
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)

    @field_validator("target_relative_path")
    @classmethod
    def canonical_target_relative_path(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_vault_relative_path(value)

    @model_validator(mode="after")
    def resolved_target_is_canonical(self) -> "VaultLink":
        if self.resolved and (
            self.target_note_id is None
            or self.target_note_title is None
            or self.target_relative_path is None
        ):
            raise ValueError("resolved link is missing canonical target identity")
        if self.source_end < self.source_start:
            raise ValueError("source_end must not precede source_start")
        return self


class VaultPage(_Model):
    file: VaultFile
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLink] = Field(default_factory=list)
    backlinks: list[VaultLink] = Field(default_factory=list)


class VaultGraph(_Model):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class VaultSyncReceipt(_Model):
    id: str | None = None
    operation_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    vault_id: str
    vault_file_id: str
    operation: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    source: str = Field(
        default="vault-indexer",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    before_hash: str | None = None
    after_hash: str | None = None
    observed_modified_ns: int | None = None
    parser_version: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    policy_decision: Literal["read-only"] = "read-only"
    status: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    error_code: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    rollback_path: Literal[None] = None
    started_at: datetime
    completed_at: datetime | None = None


class ProjectionResult(_Model):
    vault_file_id: str
    note_id: str
    status: Literal["projected", "unchanged", "superseded", "conflict"]
    parse_state: Literal["parsed"]
    embedding_state: Literal["pending", "failed"]
    reconciliation_required: bool = False


class FailureResult(_Model):
    vault_file_id: str
    status: Literal["stale-invalid", "superseded", "conflict", "committed"]
    reconciliation_required: bool = False


class VaultTrustRecord(_Model):
    id: str | None = None
    manifest_id: str
    vault_id: str | None
    vault_file_id: str | None = None
    note_id: str | None = None
    canonical_relative_path: str | None
    status: Literal["approved"]
    resolution_state: Literal["resolved", "unresolved"]
    reviewer: str
    reviewed_at: datetime
    source_type: str
    evidence_class: Literal["source", "synthesis"]
    content_hash: str
    derived_from: list[str]
    manifest_relative_path: str


class TrustImportResult(_Model):
    changed: int = 0
    unchanged: int = 0
    resolved: int = 0
    unresolved: int = 0


class VaultTrustSummary(_Model):
    total: int = 0
    resolved: int = 0
    unresolved: int = 0


_SAFE_CODE = re.compile(r"^[a-zA-Z0-9_.-]+")
_SAFE_RECEIPT_FIELD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SCAN_TERMINAL_STATES: frozenset[VaultState] = frozenset(
    {"ready-read-only", "conflict", "degraded", "unavailable"}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_key(kind: str, *parts: str) -> str:
    joined = "\x1f".join((kind, *parts))
    return uuid.uuid5(uuid.NAMESPACE_URL, joined).hex


def _record_id(table: str, *parts: str) -> str:
    return f"{table}:{_record_key(table, *parts)}"


def _db_id(value: str) -> RecordID:
    return ensure_record_id(value)


def _persisted_vault_file(data: dict[str, Any]) -> VaultFile:
    try:
        return VaultFile.model_validate(data)
    except ValidationError as exc:
        raise VaultProjectionError("vault_file_invalid") from exc


def _persisted_vault_link(
    row: dict[str, Any],
    *,
    vault_id: str,
) -> VaultLink:
    if row.get("resolved"):
        target_note_id = str(row.get("target_note_id") or "")
        target_vault_file_id = str(row.get("target_vault_file_id") or "")
        target_vault_id = str(row.get("target_vault_id") or "")
        if (
            not target_note_id
            or not target_vault_file_id
            or target_vault_id != vault_id
            or _record_id("note", target_vault_file_id) != target_note_id
        ):
            raise VaultProjectionError("vault_link_target_invalid")
    try:
        return VaultLink.model_validate(row)
    except ValidationError as exc:
        raise VaultProjectionError("vault_link_invalid") from exc


def _safe_error_code(value: str) -> str:
    match = _SAFE_CODE.match(value)
    return (match.group(0) if match else "vault_error")[:64]


def _receipt_field(value: str, *, name: str, max_length: int) -> str:
    if (
        not value
        or len(value) > max_length
        or _SAFE_RECEIPT_FIELD.fullmatch(value) is None
    ):
        raise ValueError(f"invalid_receipt_{name}")
    return value


def _task_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _document_graph_records(
    *,
    note_id: str,
    identity_scope: str,
    parsed: ParsedDocument,
    vault_file_id: str | None,
    overlay_note_id: str | None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Build shared block, link, and task rows for one parsed Markdown source."""

    if (vault_file_id is None) == (overlay_note_id is None):
        raise ValueError("projection_authority_mismatch")
    block_ids = {
        block.parser_id: _record_id("note_block", identity_scope, block.parser_id)
        for block in parsed.blocks
    }
    blocks: list[dict[str, Any]] = []
    for block in parsed.blocks:
        block_id = block_ids[block.parser_id]
        block_data = {
            "schema_version": 1,
            "note_id": _db_id(note_id),
            "vault_file_id": _db_id(vault_file_id) if vault_file_id else None,
            "parser_id": block.parser_id,
            "parent_block_id": (
                _db_id(block_ids[block.parent_parser_id])
                if block.parent_parser_id
                else None
            ),
            "position": block.position,
            "stable_source_id": block.stable_source_id,
            "block_kind": block.block_kind,
            "markdown": block.markdown,
            "plain_text": block.plain_text,
            "properties": block.properties,
            "task_state": block.task_state,
            "heading_path": block.heading_path,
            "source_start": block.source_start,
            "source_end": block.source_end,
        }
        if overlay_note_id is not None:
            block_data["overlay_note_id"] = _db_id(overlay_note_id)
        blocks.append({"record_id": _db_id(block_id), "data": block_data})

    links: list[dict[str, Any]] = [link.model_dump() for link in parsed.links]
    link_spans = {
        (int(link["source_start"]), int(link["source_end"])) for link in links
    }
    for embed in parsed.embeds:
        span = (embed.source_start, embed.source_end)
        if span in link_spans:
            continue
        links.append(
            {
                **embed.model_dump(),
                "alias": None,
                "link_kind": "embed",
            }
        )
        link_spans.add(span)

    persisted_links: list[dict[str, Any]] = []
    for link in links:
        link_id = _record_id(
            "note_link",
            note_id,
            str(link["source_start"]),
            str(link["source_end"]),
        )
        source_parser_id = link.pop("source_block_parser_id")
        target_text = link["target_text"]
        link_data = {
            "schema_version": 1,
            "source_note_id": _db_id(note_id),
            "source_block_id": (
                _db_id(block_ids[source_parser_id]) if source_parser_id else None
            ),
            "target_note_id": None,
            "target_block_id": None,
            **link,
            "target_title_key": canonical_title_key(target_text),
            "resolved": False,
        }
        persisted_links.append(
            {
                "record_id": _db_id(link_id),
                "data": link_data,
                "target_title": canonical_title_key(target_text),
            }
        )

    tasks: list[dict[str, Any]] = []
    for task in parsed.tasks:
        block_id = block_ids[task.block_parser_id]
        task_id = _record_id("knowledge_task", block_id)
        task_data = {
            "schema_version": 1,
            "note_id": _db_id(note_id),
            "block_id": _db_id(block_id),
            **task.model_dump(),
        }
        task_data.pop("block_parser_id")
        for field in ("scheduled", "due", "completed"):
            task_data[field] = _task_datetime(task_data[field])
        tasks.append({"record_id": _db_id(task_id), "data": task_data})
    return blocks, persisted_links, tasks


async def _await_task_terminal(task: asyncio.Task[Any]) -> Any:
    """Wait through caller cancellation without cancelling a durable side effect."""

    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


async def _default_embedding_submitter(
    app: str,
    command: str,
    payload: dict[str, str],
) -> Any:
    return await asyncio.to_thread(
        _submit_command,
        LEGACY_COMMAND_APP,
        "embed_note",
        payload,
    )


class VaultRepository:
    """Persist projections without acquiring any filesystem write authority."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory | None = None,
        embedding_submitter: EmbeddingSubmitter | None = None,
        approved_roots: dict[str, ApprovedVaultRoot] | None = None,
        failure_receipt_timeout: float = 2.0,
    ) -> None:
        self._connection_factory = connection_factory or db_connection
        self._embedding_submitter = embedding_submitter or _default_embedding_submitter
        self._approved_roots = approved_roots or {}
        self._failure_receipt_timeout = failure_receipt_timeout

    async def _query(
        self,
        connection: _Connection,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = await connection.query(statement, variables)
        if isinstance(result, str):
            raise RuntimeError("database query failed")
        parsed = parse_record_ids(result)
        return parsed if isinstance(parsed, list) else [parsed]

    async def create_mount(self, request: VaultMountCreate) -> VaultMount:
        mount_id = _record_id("vault_mount", request.root_path)
        data = request.model_dump()
        if data["parent_vault_id"]:
            data["parent_vault_id"] = _db_id(data["parent_vault_id"])
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "CREATE $mount_id CONTENT $mount RETURN AFTER;",
                {"mount_id": _db_id(mount_id), "mount": data},
            )
        if rows:
            return VaultMount.model_validate(rows[0])
        return VaultMount(id=mount_id, **request.model_dump())

    async def mark_scan_started(
        self,
        vault_id: str,
        *,
        started_at: datetime | None = None,
    ) -> None:
        async with self._connection_factory() as connection:
            await self._query(
                connection,
                """
                UPDATE $vault_id SET
                    status = "scanning",
                    last_scan_started_at = $started_at;
                """,
                {
                    "vault_id": _db_id(vault_id),
                    "started_at": started_at or _now(),
                },
            )

    async def mark_scan_completed(
        self,
        vault_id: str,
        *,
        status: VaultState,
        completed_at: datetime | None = None,
    ) -> None:
        if status not in _SCAN_TERMINAL_STATES:
            raise ValueError("vault_scan_state_not_terminal")
        async with self._connection_factory() as connection:
            await self._query(
                connection,
                """
                UPDATE $vault_id SET
                    status = $status,
                    last_scan_completed_at = $completed_at;
                """,
                {
                    "vault_id": _db_id(vault_id),
                    "status": status,
                    "completed_at": completed_at or _now(),
                },
            )

    async def record_observation(
        self, observation: VaultFileObservation
    ) -> None:
        """Persist file provenance only; source bytes never cross this boundary."""

        vault_file_id = _record_id(
            "vault_file", observation.vault_id, observation.relative_path
        )
        parse_status = (
            "invalid" if observation.state == "retry" else observation.parse_state
        )
        variables = {
            "vault_file_id": _db_id(vault_file_id),
            "vault_id": _db_id(observation.vault_id),
            "relative_path": observation.relative_path,
            "file_kind": observation.file_kind,
            "format": "markdown",
            "content_hash": observation.content_hash,
            "size_bytes": observation.byte_size or 0,
            "modified_ns": observation.modified_ns or 0,
            "parse_status": parse_status,
            "parse_error_code": (
                _safe_error_code(observation.error_code)
                if observation.error_code
                else None
            ),
        }
        async with self._connection_factory() as connection:
            await self._query(
                connection,
                """
                LET $existing_file = (
                    SELECT * FROM $vault_file_id LIMIT 1
                )[0];
                LET $same_projection = (
                    $existing_file != NONE
                    AND $existing_file.modified_ns = $modified_ns
                    AND $existing_file.size_bytes = $size_bytes
                    AND $existing_file.parse_status IN ['parsed', 'invalid']
                    AND $existing_file.deleted_state = "present"
                    AND (
                        $content_hash = NONE
                        OR $existing_file.content_hash = $content_hash
                    )
                );
                UPSERT $vault_file_id SET
                    vault_id = $vault_id,
                    relative_path = $relative_path,
                    file_kind = $file_kind,
                    format = $format,
                    content_hash = IF $same_projection {
                        $existing_file.content_hash
                    } ELSE {
                        $content_hash
                    },
                    size_bytes = $size_bytes,
                    modified_ns = $modified_ns,
                    parse_status = IF $same_projection {
                        $existing_file.parse_status
                    } ELSE {
                        $parse_status
                    },
                    parse_error_code = IF $same_projection {
                        $existing_file.parse_error_code
                    } ELSE {
                        $parse_error_code
                    },
                    deleted_state = "present",
                    embedding_state = IF $same_projection {
                        $existing_file.embedding_state
                    } ELSE {
                        "pending"
                    };
                """,
                variables,
            )

    async def list_mounts(self) -> list[VaultMount]:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM vault_mount ORDER BY name;",
            )
        return [VaultMount.model_validate(row) for row in rows]

    async def get_mount(self, vault_id: str) -> VaultMount:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM $vault_id;",
                {"vault_id": _db_id(vault_id)},
            )
        if not rows:
            raise LookupError("vault_mount_not_found")
        return VaultMount.model_validate(rows[0])

    async def project_document(
        self,
        vault: VaultMount,
        observation: VaultWorkItem,
        parsed: ParsedDocument,
        operation_id: str,
    ) -> ProjectionResult:
        operation_id = _receipt_field(
            operation_id,
            name="operation_id",
            max_length=128,
        )
        if (
            observation.vault_id != vault.id
            or observation.relative_path != parsed.relative_path
            or observation.content_hash != parsed.content_hash
        ):
            raise ValueError("projection_input_mismatch")

        vault_file_id = _record_id("vault_file", vault.id, observation.relative_path)
        note_id = _record_id("note", vault_file_id)
        started_at = _now()
        variables = self._projection_variables(
            vault=vault,
            observation=observation,
            parsed=parsed,
            operation_id=operation_id,
            vault_file_id=vault_file_id,
            note_id=note_id,
            started_at=started_at,
        )

        async def execute_projection() -> list[dict[str, Any]]:
            with _projection_note_refresh():
                async with self._connection_factory() as connection:
                    return await self._query(
                        connection,
                        self._projection_transaction(),
                        variables,
                    )

        query_task = asyncio.create_task(execute_projection())
        cancelled = False
        query_error: Exception | None = None
        try:
            rows = await asyncio.shield(query_task)
        except asyncio.CancelledError:
            cancelled = True
            try:
                rows = await _await_task_terminal(query_task)
            except Exception as exc:
                rows = []
                query_error = exc
        except Exception as exc:
            rows = []
            query_error = exc

        if query_error is not None:
            reconciled_status = await self._reconcile_projection_commit(
                operation_id=operation_id,
                observation=observation,
                vault_file_id=vault_file_id,
                note_id=note_id,
            )
            if reconciled_status is None:
                await self._record_projection_failure_bounded(
                    vault=vault,
                    observation=observation,
                    operation_id=operation_id,
                    vault_file_id=vault_file_id,
                    before_hash=None,
                    started_at=started_at,
                )
                if cancelled:
                    raise asyncio.CancelledError from None
                raise query_error
            rows = [{"projection_status": reconciled_status}]

        outcome = next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and row.get("projection_status")
            ),
            {},
        )
        projection_status = outcome.get("projection_status")
        if projection_status not in {
            "projected",
            "unchanged",
            "superseded",
            "conflict",
        }:
            if cancelled:
                raise asyncio.CancelledError from None
            raise RuntimeError("projection_outcome_missing")
        if projection_status == "projected":
            cancelled, embedding_failed = await self._submit_embedding_after_commit(
                note_id,
                vault_file_id,
                cancellation_pending=cancelled,
            )
        else:
            embedding_failed = False
        if cancelled:
            raise asyncio.CancelledError from None

        return ProjectionResult(
            vault_file_id=vault_file_id,
            note_id=note_id,
            status=projection_status,
            parse_state="parsed",
            embedding_state="failed" if embedding_failed else "pending",
            reconciliation_required=projection_status == "conflict",
        )

    async def project_owned_document(
        self,
        *,
        source_authority: Literal["overlay"],
        overlay_space_id: str,
        overlay_note_id: str,
        projected_note_id: str,
        parsed: ParsedDocument,
        revision: int,
    ) -> OverlayPage:
        """Project app-owned Markdown without creating or mutating a vault mount."""

        unit = self.owned_projection_unit_of_work(
            source_authority=source_authority,
            overlay_space_id=overlay_space_id,
            overlay_note_id=overlay_note_id,
            projected_note_id=projected_note_id,
            parsed=parsed,
            revision=revision,
        )
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                self._owned_projection_transaction(unit.mutation_statement),
                unit.variables,
            )
        outcome = next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and row.get("outcome")
            ),
            None,
        )
        if outcome is None or outcome.get("outcome") != "projected":
            raise RuntimeError("overlay_projection_outcome_missing")
        from deeper_notebook.overlay.contracts import OverlayPage

        try:
            return OverlayPage.model_validate(outcome.get("page"))
        except ValidationError:
            raise RuntimeError("overlay_projection_invalid") from None

    def owned_projection_unit_of_work(
        self,
        *,
        source_authority: Literal["overlay"],
        overlay_space_id: str,
        overlay_note_id: str,
        projected_note_id: str,
        parsed: ParsedDocument,
        revision: int,
    ) -> OwnedProjectionUnitOfWork:
        """Build the sole overlay graph unit for a caller-owned transaction."""
        if source_authority != "overlay":
            raise ValueError("invalid_source_authority")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("invalid_overlay_revision")
        self._owned_record_id(
            overlay_space_id,
            prefix="overlay_space:",
            error_code="invalid_overlay_space_id",
        )
        self._owned_record_id(
            overlay_note_id,
            prefix="overlay_note:",
            error_code="invalid_overlay_note_id",
        )
        self._owned_record_id(
            projected_note_id,
            prefix="note:",
            error_code="invalid_projected_note_id",
        )
        return OwnedProjectionUnitOfWork(
            variables=self._owned_projection_variables(
                overlay_space_id=overlay_space_id,
                overlay_note_id=overlay_note_id,
                projected_note_id=projected_note_id,
                parsed=parsed,
                revision=revision,
            ),
            mutation_statement=self._owned_projection_mutations(),
        )

    @staticmethod
    def _owned_record_id(value: str, *, prefix: str, error_code: str):
        if (
            not isinstance(value, str)
            or not value.startswith(prefix)
            or len(value) == len(prefix)
        ):
            raise ValueError(error_code)
        try:
            return _db_id(value)
        except Exception:
            raise ValueError(error_code) from None

    def _owned_projection_variables(
        self,
        *,
        overlay_space_id: str,
        overlay_note_id: str,
        projected_note_id: str,
        parsed: ParsedDocument,
        revision: int,
    ) -> dict[str, Any]:
        blocks, links, tasks = _document_graph_records(
            note_id=projected_note_id,
            identity_scope=overlay_note_id,
            parsed=parsed,
            vault_file_id=None,
            overlay_note_id=overlay_note_id,
        )
        return {
            "overlay_space_id": _db_id(overlay_space_id),
            "overlay_note_id": _db_id(overlay_note_id),
            "projected_note_id": _db_id(projected_note_id),
            "revision": revision,
            "projected_note": {
                "title": parsed.title,
                "title_key": canonical_title_key(parsed.title),
                "note_type": "human",
                "content": parsed.markdown,
                "source_format": parsed.source_format,
                "canonical_external": False,
                "source_authority": "overlay",
                "overlay_space_id": _db_id(overlay_space_id),
                "overlay_note_id": _db_id(overlay_note_id),
                "properties": parsed.properties,
                "tags": parsed.tags,
                "source_hash": parsed.content_hash,
                "external_state": None,
            },
            "blocks": blocks,
            "links": links,
            "tasks": tasks,
        }

    @staticmethod
    def _owned_projection_mutations() -> str:
        return """
        UPSERT $projected_note_id MERGE $projected_note;
        DELETE note_block WHERE note_id = $projected_note_id;
        DELETE note_link WHERE source_note_id = $projected_note_id;
        DELETE knowledge_task WHERE note_id = $projected_note_id;
        FOR $block IN $blocks {
            UPSERT $block.record_id CONTENT $block.data;
        };
        FOR $link IN $links {
            UPSERT $link.record_id CONTENT $link.data;
        };
        FOR $task IN $tasks {
            UPSERT $task.record_id CONTENT $task.data;
        };
        FOR $affected_link IN (
            SELECT * FROM note_link
            WHERE source_note_id IN (
                SELECT VALUE id FROM note
                WHERE source_authority = 'overlay'
                AND overlay_space_id = $overlay_space_id
            )
            AND (
                source_note_id = $projected_note_id
                OR target_title_key = $prior_projected_note.title_key
                OR target_title_key = $projected_note.title_key
            )
        ) {
            LET $targets = (
                SELECT VALUE id FROM note
                WHERE source_authority = 'overlay'
                AND overlay_space_id = $overlay_space_id
                AND title_key = $affected_link.target_title_key
            );
            UPDATE $affected_link.id SET
                target_note_id = IF array::len($targets) = 1 {
                    $targets[0]
                } ELSE {
                    NONE
                },
                resolved = array::len($targets) = 1;
        };
        """

    @staticmethod
    def _owned_projection_transaction(
        mutation_statement: str,
    ) -> str:
        return (
            """
            BEGIN TRANSACTION;
            LET $overlay = (SELECT * FROM $overlay_note_id LIMIT 1)[0];
            LET $prior_projected_note = (
                SELECT * FROM $projected_note_id LIMIT 1
            )[0];
            LET $valid_overlay = (
                $overlay != NONE
                AND $overlay.space_id = $overlay_space_id
                AND $overlay.projected_note_id = $projected_note_id
                AND $overlay.revision = $revision
                AND $overlay.content_hash = $projected_note.source_hash
                AND (
                    $prior_projected_note = NONE
                    OR (
                        $prior_projected_note.source_authority = 'overlay'
                        AND $prior_projected_note.overlay_space_id
                            = $overlay_space_id
                        AND $prior_projected_note.overlay_note_id
                            = $overlay_note_id
                    )
                )
            );
            IF $valid_overlay {
            """
            + mutation_statement
            + """
            };
            LET $page = {
                overlay: (SELECT * FROM $overlay_note_id LIMIT 1)[0],
                note: (SELECT * FROM $projected_note_id LIMIT 1)[0],
                blocks: (
                    SELECT * FROM note_block
                    WHERE note_id = $projected_note_id
                    ORDER BY position
                ),
                tasks: (
                    SELECT * FROM knowledge_task
                    WHERE note_id = $projected_note_id
                ),
                outgoing_links: (
                    SELECT *,
                        source_note_id.title AS source_note_title,
                        source_note_id.overlay_note_id
                            AS source_overlay_note_id,
                        target_note_id.title AS target_note_title,
                        target_note_id.overlay_note_id
                            AS target_overlay_note_id,
                        target_note_id.overlay_note_id.relative_path
                            AS target_relative_path
                    FROM note_link
                    WHERE source_note_id = $projected_note_id
                ),
                backlinks: (
                    SELECT *,
                        source_note_id.title AS source_note_title,
                        source_note_id.overlay_note_id
                            AS source_overlay_note_id,
                        target_note_id.title AS target_note_title,
                        target_note_id.overlay_note_id
                            AS target_overlay_note_id,
                        target_note_id.overlay_note_id.relative_path
                            AS target_relative_path
                    FROM note_link
                    WHERE target_note_id = $projected_note_id
                )
            };
            RETURN {
                outcome: IF $valid_overlay {
                    'projected'
                } ELSE {
                    'conflict'
                },
                page: $page
            };
            COMMIT TRANSACTION;
            """
        )

    async def _submit_embedding_after_commit(
        self,
        note_id: str,
        vault_file_id: str,
        *,
        cancellation_pending: bool,
    ) -> tuple[bool, bool]:
        async def submit() -> None:
            submitted = self._embedding_submitter(
                LEGACY_COMMAND_APP,
                "embed_note",
                {"note_id": note_id},
            )
            if inspect.isawaitable(submitted):
                await submitted

        task = asyncio.create_task(submit())
        if cancellation_pending:
            try:
                await _await_task_terminal(task)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Vault embedding submission failed for note {} ({})",
                    note_id,
                    type(exc).__name__,
                )
            return True, False
        try:
            await asyncio.shield(task)
            return False, False
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if (
                task.done()
                and task.cancelled()
                and not (current and current.cancelling())
            ):
                raise
            try:
                await _await_task_terminal(task)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Vault embedding submission failed for note {} ({})",
                    note_id,
                    type(exc).__name__,
                )
            return True, False
        except Exception as exc:
            logger.warning(
                "Vault embedding submission failed for note {} ({})",
                note_id,
                type(exc).__name__,
            )
            marked_failed = await self._mark_embedding_failed(vault_file_id)
            return False, marked_failed

    async def _mark_embedding_failed(self, vault_file_id: str) -> bool:
        """Persist only local projection lifecycle state after submission failure."""
        try:
            async with self._connection_factory() as connection:
                await self._query(
                    connection,
                    "UPDATE $vault_file_id SET embedding_state = 'failed';",
                    {"vault_file_id": _db_id(vault_file_id)},
                )
            return True
        except Exception as exc:
            logger.warning(
                "Vault embedding failure state update failed ({})", type(exc).__name__
            )
            return False

    async def _reconcile_projection_commit(
        self,
        *,
        operation_id: str,
        observation: VaultWorkItem,
        vault_file_id: str,
        note_id: str,
    ) -> Literal["projected", "unchanged", "superseded", "conflict"] | None:
        receipt_id = _record_id("vault_sync_receipt", operation_id, vault_file_id)

        async def reconcile() -> (
            Literal["projected", "unchanged", "superseded", "conflict"] | None
        ):
            async with self._connection_factory() as connection:
                rows = await self._query(
                    connection,
                    """
                    RETURN {
                        receipt: (SELECT * FROM $receipt_id LIMIT 1)[0],
                        file: (SELECT * FROM $vault_file_id LIMIT 1)[0],
                        note: (SELECT * FROM $note_id LIMIT 1)[0]
                    };
                    """,
                    {
                        "receipt_id": _db_id(receipt_id),
                        "vault_file_id": _db_id(vault_file_id),
                        "note_id": _db_id(note_id),
                    },
                )
            proof = rows[-1] if rows else {}
            receipt = proof.get("receipt") or {}
            file_row = proof.get("file") or {}
            note_row = proof.get("note") or {}
            status = receipt.get("status")
            if status == "conflict":
                if (
                    receipt.get("after_hash") == observation.content_hash
                    and receipt.get("observed_modified_ns") == observation.modified_ns
                    and receipt.get("error_code") == "reconciliation_required"
                    and file_row.get("modified_ns") == observation.modified_ns
                    and file_row.get("content_hash") != observation.content_hash
                    and file_row.get("parse_status") == "parsed"
                    and file_row.get("deleted_state") == "present"
                    and note_row.get("source_hash") == file_row.get("content_hash")
                    and note_row.get("external_state") == "current"
                ):
                    return "conflict"
                return None
            if status == "superseded":
                if (
                    receipt.get("after_hash") == observation.content_hash
                    and file_row.get("parse_status") == "parsed"
                    and file_row.get("deleted_state") == "present"
                    and note_row.get("external_state") == "current"
                    and file_row.get("content_hash") == note_row.get("source_hash")
                ):
                    return "superseded"
                return None
            if (
                status not in {"success", "unchanged"}
                or receipt.get("after_hash") != observation.content_hash
                or file_row.get("content_hash") != observation.content_hash
                or file_row.get("parse_status") != "parsed"
                or file_row.get("deleted_state") != "present"
                or note_row.get("source_hash") != observation.content_hash
                or note_row.get("external_state") != "current"
            ):
                return None
            return "unchanged" if status == "unchanged" else "projected"

        try:
            return await asyncio.wait_for(
                reconcile(),
                timeout=self._failure_receipt_timeout,
            )
        except Exception as exc:
            logger.warning(
                "Vault commit reconciliation failed ({})",
                type(exc).__name__,
            )
            return None

    def _projection_variables(
        self,
        *,
        vault: VaultMount,
        observation: VaultWorkItem,
        parsed: ParsedDocument,
        operation_id: str,
        vault_file_id: str,
        note_id: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        file_data = {
            "schema_version": 1,
            "vault_id": _db_id(vault.id),
            "relative_path": observation.relative_path,
            "file_kind": observation.file_kind,
            "format": parsed.source_format,
            "content_hash": observation.content_hash,
            "size_bytes": observation.byte_size,
            "modified_ns": observation.modified_ns,
            "encoding": parsed.encoding,
            "newline": parsed.newline,
            "parse_status": "pending",
            "parse_error_code": None,
            "embedding_state": "pending",
            "deleted_state": "present",
        }
        note_data = {
            "title": parsed.title,
            "title_key": canonical_title_key(parsed.title),
            "note_type": "human",
            "content": parsed.markdown,
            "vault_id": _db_id(vault.id),
            "vault_file_id": _db_id(vault_file_id),
            "source_format": parsed.source_format,
            "canonical_external": True,
            "properties": parsed.properties,
            "tags": parsed.tags,
            "source_hash": parsed.content_hash,
            "external_state": "current",
        }
        blocks, persisted_links, tasks = _document_graph_records(
            note_id=note_id,
            identity_scope=vault_file_id,
            parsed=parsed,
            vault_file_id=vault_file_id,
            overlay_note_id=None,
        )

        success_receipt = self._receipt_data(
            operation_id=operation_id,
            vault=vault,
            vault_file_id=vault_file_id,
            operation="project",
            status="success",
            before_hash=None,
            after_hash=observation.content_hash,
            observed_modified_ns=observation.modified_ns,
            started_at=started_at,
        )
        unchanged_receipt = {
            **success_receipt,
            "status": "unchanged",
        }
        superseded_receipt = {
            **success_receipt,
            "status": "superseded",
        }
        conflict_receipt = {
            **success_receipt,
            "status": "conflict",
            "error_code": "reconciliation_required",
        }
        receipt_id = _record_id("vault_sync_receipt", operation_id, vault_file_id)
        return {
            "vault_id": _db_id(vault.id),
            "vault_file_id": _db_id(vault_file_id),
            "note_id": _db_id(note_id),
            "relative_path": observation.relative_path,
            "content_hash": observation.content_hash,
            "observed_modified_ns": observation.modified_ns,
            "started_at": started_at,
            "vault_file": file_data,
            "note": note_data,
            "blocks": blocks,
            "links": persisted_links,
            "tasks": tasks,
            "receipt_id": _db_id(receipt_id),
            "success_receipt": success_receipt,
            "unchanged_receipt": unchanged_receipt,
            "superseded_receipt": superseded_receipt,
            "conflict_receipt": conflict_receipt,
        }

    @staticmethod
    def _projection_transaction() -> str:
        return """
        BEGIN TRANSACTION;
        LET $existing_file = (
            SELECT * FROM vault_file
            WHERE vault_id = $vault_id
            AND relative_path = $relative_path
            LIMIT 1
        )[0];
        LET $existing_note = (SELECT * FROM $note_id LIMIT 1)[0];
        LET $superseded = IF $existing_file = NONE {
            false
        } ELSE {
            $existing_file.modified_ns > $observed_modified_ns
        };
        LET $conflict = IF $existing_file = NONE {
            false
        } ELSE {
            $existing_file.modified_ns = $observed_modified_ns
            AND $existing_file.content_hash != $content_hash
        };
        LET $unchanged = IF $existing_file = NONE {
            false
        } ELSE {
            !$superseded
            AND !$conflict
            AND $existing_file.modified_ns = $observed_modified_ns
            AND $existing_file.content_hash = $content_hash
            AND $existing_file.parse_status = 'parsed'
            AND $existing_file.deleted_state = 'present'
        };
        IF !$unchanged AND !$superseded AND !$conflict {
            UPSERT $vault_file_id MERGE $vault_file;
            UPSERT $note_id MERGE $note;
            DELETE note_block WHERE vault_file_id = $vault_file_id;
            DELETE note_link WHERE source_note_id = $note_id;
            DELETE knowledge_task WHERE note_id = $note_id;
            FOR $block IN $blocks {
                UPSERT $block.record_id CONTENT $block.data;
            };
            FOR $link IN $links {
                UPSERT $link.record_id CONTENT $link.data;
            };
            FOR $task IN $tasks {
                UPSERT $task.record_id CONTENT $task.data;
            };
            FOR $affected_link IN (
                SELECT * FROM note_link
                WHERE source_note_id IN (
                    SELECT VALUE id FROM note WHERE vault_id = $vault_id
                )
                AND (
                    source_note_id = $note_id
                    OR target_title_key = $existing_note.title_key
                    OR target_title_key = $note.title_key
                )
            ) {
                LET $targets = (
                    SELECT VALUE id FROM note
                    WHERE vault_id = $vault_id
                    AND title_key = $affected_link.target_title_key
                );
                UPDATE $affected_link.id SET
                    target_note_id = IF array::len($targets) = 1 {
                        $targets[0]
                    } ELSE {
                        NONE
                    },
                    resolved = array::len($targets) = 1;
            };
            UPDATE $vault_file_id SET
                parse_status = 'parsed',
                parse_error_code = NONE,
                indexed_at = time::now(),
                deleted_state = 'present';
            UPDATE $note_id SET external_state = 'current';
        };
        IF $conflict {
            CREATE $receipt_id CONTENT $conflict_receipt; -- vault_sync_receipt
        } ELSE {
            IF $superseded {
                CREATE $receipt_id CONTENT $superseded_receipt;
            } ELSE {
                IF $unchanged {
                    CREATE $receipt_id CONTENT $unchanged_receipt;
                } ELSE {
                    CREATE $receipt_id CONTENT $success_receipt;
                };
            };
        };
        UPDATE $receipt_id SET before_hash = $existing_file.content_hash;
        LET $changed_status = IF $superseded {
            'superseded'
        } ELSE {
            'projected'
        };
        LET $ordered_status = IF $conflict {
            'conflict'
        } ELSE {
            $changed_status
        };
        LET $projection_status = IF $unchanged {
            'unchanged'
        } ELSE {
            $ordered_status
        };
        RETURN { projection_status: $projection_status };
        COMMIT TRANSACTION;
        """

    def _receipt_data(
        self,
        *,
        operation_id: str,
        vault: VaultMount,
        vault_file_id: str,
        operation: str,
        status: str,
        before_hash: str | None,
        after_hash: str | None,
        observed_modified_ns: int | None,
        started_at: datetime,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        safe_operation_id = _receipt_field(
            operation_id,
            name="operation_id",
            max_length=128,
        )
        safe_operation = _receipt_field(
            operation,
            name="operation",
            max_length=32,
        )
        safe_status = _receipt_field(
            status,
            name="status",
            max_length=32,
        )
        safe_error = _safe_error_code(error_code) if error_code is not None else None
        safe_parser_version = _receipt_field(
            vault.parser_version,
            name="parser_version",
            max_length=128,
        )
        return {
            "schema_version": 1,
            "operation_id": safe_operation_id,
            "vault_id": _db_id(vault.id),
            "vault_file_id": _db_id(vault_file_id),
            "operation": safe_operation,
            "source": "vault-indexer",
            "before_hash": before_hash,
            "after_hash": after_hash,
            "observed_modified_ns": observed_modified_ns,
            "parser_version": safe_parser_version,
            "policy_decision": "read-only",
            "status": safe_status,
            "error_code": safe_error,
            "rollback_path": None,
            "started_at": started_at,
            "completed_at": _now(),
        }

    async def _create_receipt(
        self, connection: _Connection, receipt: dict[str, Any]
    ) -> None:
        receipt_id = _record_id(
            "vault_sync_receipt",
            str(receipt["operation_id"]),
            str(receipt["vault_file_id"]),
        )
        await self._query(
            connection,
            "CREATE $receipt_id CONTENT $receipt RETURN AFTER; -- vault_sync_receipt",
            {
                "receipt_id": _db_id(receipt_id),
                "receipt": receipt,
            },
        )

    @staticmethod
    def _failure_transaction() -> str:
        return """
        BEGIN TRANSACTION;
        LET $operation_receipt = (SELECT * FROM $receipt_id LIMIT 1)[0];
        LET $existing_file = (SELECT * FROM $vault_file_id LIMIT 1)[0];
        LET $newer = IF $existing_file = NONE {
            true
        } ELSE {
            $modified_ns > $existing_file.modified_ns
            OR (
                $modified_ns = $existing_file.modified_ns
                AND $content_hash = $existing_file.content_hash
                AND $existing_file.parse_status != 'parsed'
            )
        };
        LET $conflict = IF $existing_file = NONE {
            false
        } ELSE {
            $modified_ns = $existing_file.modified_ns
            AND $content_hash != $existing_file.content_hash
        };
        LET $superseded = IF $existing_file = NONE {
            false
        } ELSE {
            $modified_ns < $existing_file.modified_ns
            OR (
                $modified_ns = $existing_file.modified_ns
                AND $content_hash = $existing_file.content_hash
                AND $existing_file.parse_status = 'parsed'
            )
        };
        IF $operation_receipt = NONE {
            IF $newer {
                UPSERT $vault_file_id MERGE {
                    schema_version: 1,
                    vault_id: $vault_id,
                    relative_path: $relative_path,
                    file_kind: $file_kind,
                    format: $format,
                    content_hash: $content_hash,
                    size_bytes: $size_bytes,
                    modified_ns: $modified_ns,
                    parse_status: 'invalid',
                    parse_error_code: $error_code,
                    deleted_state: 'present'
                };
                UPDATE note SET external_state = 'stale'
                    WHERE vault_file_id = $vault_file_id;
            };
            LET $ordered_receipt = IF $superseded {
                $superseded_receipt
            } ELSE {
                $stale_invalid_receipt
            };
            LET $receipt = IF $conflict {
                $conflict_receipt
            } ELSE {
                $ordered_receipt
            };
            CREATE $receipt_id CONTENT $receipt; -- vault_sync_receipt
            UPDATE $receipt_id SET before_hash = $existing_file.content_hash;
        };
        LET $operation_committed = IF $operation_receipt = NONE {
            false
        } ELSE {
            $operation_receipt.status IN ['success', 'unchanged']
        };
        LET $operation_status = IF $operation_committed {
            'committed'
        } ELSE {
            $operation_receipt.status
        };
        LET $observed_status = IF $conflict {
            'conflict'
        } ELSE {
            'stale-invalid'
        };
        LET $ordered_status = IF $superseded {
            'superseded'
        } ELSE {
            $observed_status
        };
        LET $failure_status = IF $operation_receipt != NONE {
            $operation_status
        } ELSE {
            $ordered_status
        };
        RETURN { failure_status: $failure_status };
        COMMIT TRANSACTION;
        """

    async def _record_projection_failure_bounded(
        self,
        *,
        vault: VaultMount,
        observation: VaultWorkItem,
        operation_id: str,
        vault_file_id: str,
        before_hash: str | None,
        started_at: datetime,
    ) -> None:
        async def record() -> None:
            failed_receipt = self._receipt_data(
                operation_id=operation_id,
                vault=vault,
                vault_file_id=vault_file_id,
                operation="project",
                status="failed",
                before_hash=before_hash,
                after_hash=observation.content_hash,
                observed_modified_ns=observation.modified_ns,
                started_at=started_at,
                error_code="projection_failed",
            )
            superseded_receipt = {
                **failed_receipt,
                "status": "superseded",
            }
            stale_invalid_receipt = {
                **failed_receipt,
                "status": "stale-invalid",
            }
            conflict_receipt = {
                **failed_receipt,
                "status": "conflict",
                "error_code": "reconciliation_required",
            }
            receipt_id = _record_id("vault_sync_receipt", operation_id, vault_file_id)
            variables = {
                "vault_file_id": _db_id(vault_file_id),
                "vault_id": _db_id(vault.id),
                "relative_path": observation.relative_path,
                "file_kind": observation.file_kind,
                "format": "markdown",
                "content_hash": observation.content_hash,
                "size_bytes": observation.byte_size or 0,
                "modified_ns": observation.modified_ns or 0,
                "error_code": "projection_failed",
                "receipt_id": _db_id(receipt_id),
                "failed_receipt": failed_receipt,
                "superseded_receipt": superseded_receipt,
                "stale_invalid_receipt": stale_invalid_receipt,
                "conflict_receipt": conflict_receipt,
            }
            async with self._connection_factory() as connection:
                await self._query(
                    connection,
                    self._failure_transaction(),
                    variables,
                )

        try:
            await asyncio.wait_for(
                record(),
                timeout=self._failure_receipt_timeout,
            )
        except Exception as exc:
            logger.warning(
                "Vault failure receipt was not persisted ({})",
                type(exc).__name__,
            )

    async def record_failure(
        self,
        vault_id: str,
        observation: VaultWorkItem | VaultFileObservation,
        operation_id: str,
        error_code: str,
    ) -> FailureResult:
        operation_id = _receipt_field(
            operation_id,
            name="operation_id",
            max_length=128,
        )
        vault_file_id = _record_id("vault_file", vault_id, observation.relative_path)
        safe_code = _safe_error_code(error_code)
        vault = VaultMount(
            id=vault_id,
            name="vault",
            root_path="/redacted",
            format_mode="markdown",
            status="degraded",
            parser_version="unknown",
        )
        failed_receipt = self._receipt_data(
            operation_id=operation_id,
            vault=vault,
            vault_file_id=vault_file_id,
            operation="parse",
            status="failed",
            before_hash=None,
            after_hash=observation.content_hash,
            observed_modified_ns=observation.modified_ns,
            started_at=_now(),
            error_code=safe_code,
        )
        superseded_receipt = {
            **failed_receipt,
            "status": "superseded",
        }
        stale_invalid_receipt = {
            **failed_receipt,
            "status": "stale-invalid",
        }
        conflict_receipt = {
            **failed_receipt,
            "status": "conflict",
            "error_code": "reconciliation_required",
        }
        variables = {
            "vault_id": _db_id(vault_id),
            "vault_file_id": _db_id(vault_file_id),
            "relative_path": observation.relative_path,
            "file_kind": observation.file_kind,
            "format": "markdown",
            "content_hash": observation.content_hash,
            "size_bytes": observation.byte_size or 0,
            "modified_ns": observation.modified_ns or 0,
            "error_code": safe_code,
            "receipt_id": _db_id(
                _record_id(
                    "vault_sync_receipt",
                    operation_id,
                    vault_file_id,
                )
            ),
            "failed_receipt": failed_receipt,
            "superseded_receipt": superseded_receipt,
            "stale_invalid_receipt": stale_invalid_receipt,
            "conflict_receipt": conflict_receipt,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                self._failure_transaction(),
                variables,
            )
        outcome = next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and row.get("failure_status")
            ),
            {},
        )
        failure_status = outcome.get("failure_status")
        if failure_status not in {
            "stale-invalid",
            "superseded",
            "conflict",
            "committed",
        }:
            raise RuntimeError("failure_outcome_missing")
        return FailureResult(
            vault_file_id=vault_file_id,
            status=failure_status,
            reconciliation_required=failure_status == "conflict",
        )

    async def mark_missing(
        self,
        vault_id: str,
        relative_path: str,
        operation_id: str,
    ) -> None:
        operation_id = _receipt_field(
            operation_id,
            name="operation_id",
            max_length=128,
        )
        vault_file_id = _record_id("vault_file", vault_id, relative_path)
        vault = VaultMount(
            id=vault_id,
            name="vault",
            root_path="/redacted",
            format_mode="markdown",
            status="stale",
            parser_version="unknown",
        )
        receipt = self._receipt_data(
            operation_id=operation_id,
            vault=vault,
            vault_file_id=vault_file_id,
            operation="missing",
            status="success",
            before_hash=None,
            after_hash=None,
            observed_modified_ns=None,
            started_at=_now(),
        )
        variables = {
            "vault_id": _db_id(vault_id),
            "vault_file_id": _db_id(vault_file_id),
            "relative_path": relative_path,
            "receipt_id": _db_id(
                _record_id("vault_sync_receipt", operation_id, vault_file_id)
            ),
            "receipt": receipt,
        }
        async with self._connection_factory() as connection:
            await self._query(
                connection,
                """
                BEGIN TRANSACTION;
                LET $existing_file = (
                    SELECT * FROM vault_file
                    WHERE vault_id = $vault_id
                    AND relative_path = $relative_path
                    LIMIT 1
                )[0];
                LET $transitioned = $existing_file = NONE
                    OR $existing_file.deleted_state != 'missing';
                IF $transitioned {
                    IF $existing_file = NONE {
                        UPSERT $vault_file_id CONTENT {
                            schema_version: 1,
                            vault_id: $vault_id,
                            relative_path: $relative_path,
                            file_kind: 'markdown',
                            format: 'markdown',
                            content_hash: NONE,
                            size_bytes: 0,
                            modified_ns: 0,
                            encoding: NONE,
                            parse_status: 'missing',
                            parse_error_code: NONE,
                            deleted_state: 'missing'
                        };
                    } ELSE {
                        UPDATE $vault_file_id SET
                            parse_status = 'missing',
                            deleted_state = 'missing';
                    };
                    UPDATE note SET external_state = 'stale'
                    WHERE vault_id = $vault_id
                    AND vault_file_id = $vault_file_id;
                    CREATE $receipt_id CONTENT $receipt; -- vault_sync_receipt
                };
                RETURN { transitioned: $transitioned };
                COMMIT TRANSACTION;
                """,
                variables,
            )

    async def list_files(
        self,
        vault_id: str,
        prefix: str,
        limit: int,
        offset: int,
    ) -> list[VaultFile]:
        self._validate_page(limit, offset)
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM vault_file
                WHERE vault_id = $vault_id
                AND string::starts_with(relative_path, $prefix)
                ORDER BY relative_path LIMIT $limit START $offset;
                """,
                {
                    "vault_id": _db_id(vault_id),
                    "prefix": prefix,
                    "limit": limit,
                    "offset": offset,
                },
            )
        # Task 6 makes the projection note identity deterministic from the
        # durable vault-file record. Return that identity explicitly rather
        # than asking API clients to reconstruct an implementation detail.
        return [
            _persisted_vault_file(
                {**row, "note_id": _record_id("note", str(row["id"]))}
            )
            for row in rows
        ]

    async def get_page(self, vault_id: str, note_id: str) -> VaultPage:
        async with self._connection_factory() as connection:
            notes = await self._query(
                connection,
                "SELECT * FROM $note_id WHERE vault_id = $vault_id;",
                {"note_id": _db_id(note_id), "vault_id": _db_id(vault_id)},
            )
            if not notes:
                raise LookupError("vault_note_not_found")
            note = notes[0]
            vault_file_id = str(note.get("vault_file_id") or "")
            if not vault_file_id:
                raise LookupError("vault_note_file_not_found")
            files = await self._query(
                connection,
                "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id;",
                {
                    "vault_file_id": _db_id(vault_file_id),
                    "vault_id": _db_id(vault_id),
                },
            )
            if not files:
                raise LookupError("vault_note_file_not_found")
            file_row = files[0]
            file_record_id = str(file_row.get("id") or "")
            stored_note_id = str(note.get("id") or "")
            canonical_note_id = (
                _record_id("note", file_record_id) if file_record_id else ""
            )
            if (
                not canonical_note_id
                or file_record_id != vault_file_id
                or canonical_note_id != stored_note_id
                or canonical_note_id != note_id
            ):
                raise VaultProjectionError("vault_page_identity_invalid")
            file = _persisted_vault_file(
                {
                    **file_row,
                    "note_id": canonical_note_id,
                }
            )
            blocks = await self._query(
                connection,
                "SELECT * FROM note_block WHERE note_id = $note_id ORDER BY position;",
                {"note_id": _db_id(note_id)},
            )
            tasks = await self._query(
                connection,
                "SELECT * FROM knowledge_task WHERE note_id = $note_id;",
                {"note_id": _db_id(note_id)},
            )
            outgoing = await self._link_rows(
                connection,
                vault_id,
                note_id,
                outgoing=True,
                validate_note=False,
            )
            incoming = await self._link_rows(
                connection,
                vault_id,
                note_id,
                outgoing=False,
                validate_note=False,
            )
        return VaultPage(
            file=file,
            note=note,
            blocks=blocks,
            tasks=tasks,
            outgoing_links=outgoing,
            backlinks=incoming,
        )

    async def _link_rows(
        self,
        connection: _Connection,
        vault_id: str,
        note_id: str,
        *,
        outgoing: bool,
        validate_note: bool = True,
    ) -> list[VaultLink]:
        if validate_note:
            await self._require_note_in_vault(connection, vault_id, note_id)
        field = "source_note_id" if outgoing else "target_note_id"
        rows = await self._query(
            connection,
            f"""
            SELECT *,
                source_note_id.title AS source_note_title,
                target_note_id.title AS target_note_title,
                target_note_id.vault_file_id AS target_vault_file_id,
                target_note_id.vault_file_id.vault_id AS target_vault_id,
                target_note_id.vault_file_id.relative_path AS target_relative_path
            FROM note_link
            WHERE {field} = $note_id
            AND source_note_id IN (
                SELECT VALUE id FROM note WHERE vault_id = $vault_id
            )
            AND (
                target_note_id = NONE
                OR target_note_id IN (
                    SELECT VALUE id FROM note WHERE vault_id = $vault_id
                )
            );
            """,
            {"note_id": _db_id(note_id), "vault_id": _db_id(vault_id)},
        )
        return [
            _persisted_vault_link(row, vault_id=vault_id)
            for row in rows
        ]

    async def _require_note_in_vault(
        self,
        connection: _Connection,
        vault_id: str,
        note_id: str,
    ) -> None:
        rows = await self._query(
            connection,
            "SELECT VALUE id FROM $note_id WHERE vault_id = $vault_id;",
            {"note_id": _db_id(note_id), "vault_id": _db_id(vault_id)},
        )
        if not rows:
            raise LookupError("vault_note_not_found")

    async def backlinks(self, vault_id: str, note_id: str) -> list[VaultLink]:
        async with self._connection_factory() as connection:
            rows = await self._link_rows(connection, vault_id, note_id, outgoing=False)
        return rows

    async def outgoing_links(self, vault_id: str, note_id: str) -> list[VaultLink]:
        async with self._connection_factory() as connection:
            rows = await self._link_rows(connection, vault_id, note_id, outgoing=True)
        return rows

    async def graph(
        self,
        vault_id: str,
        center_note_id: str,
        depth: int,
        limit: int,
    ) -> VaultGraph:
        if depth < 0 or limit <= 0:
            raise ValueError("invalid_graph_bounds")
        seen = {center_note_id}
        frontier = {center_note_id}
        edge_rows: dict[str, dict[str, Any]] = {}
        async with self._connection_factory() as connection:
            await self._require_note_in_vault(connection, vault_id, center_note_id)
            for _ in range(depth):
                if not frontier or len(seen) >= limit:
                    break
                rows = await self._query(
                    connection,
                    """
                    SELECT * FROM note_link
                    WHERE (
                        source_note_id IN $frontier
                        OR target_note_id IN $frontier
                    )
                    AND source_note_id IN (
                        SELECT VALUE id FROM note WHERE vault_id = $vault_id
                    )
                    AND target_note_id IN (
                        SELECT VALUE id FROM note WHERE vault_id = $vault_id
                    )
                    AND resolved = true
                    LIMIT $limit;
                    """,
                    {
                        "vault_id": _db_id(vault_id),
                        "frontier": [_db_id(note) for note in frontier],
                        "limit": limit,
                    },
                )
                next_frontier: set[str] = set()
                for row in rows:
                    source = str(row["source_note_id"])
                    target_value = row.get("target_note_id")
                    if not target_value:
                        continue
                    target = str(target_value)
                    edge_rows[str(row["id"])] = row
                    for candidate in (source, target):
                        if candidate not in seen and len(seen) < limit:
                            seen.add(candidate)
                            next_frontier.add(candidate)
                frontier = next_frontier
            note_rows = await self._query(
                connection,
                """
                SELECT id, title, source_format, external_state
                FROM note WHERE vault_id = $vault_id AND id IN $note_ids;
                """,
                {
                    "vault_id": _db_id(vault_id),
                    "note_ids": [_db_id(note) for note in seen],
                },
            )
        nodes = [
            {
                "id": str(row["id"]),
                "title": row.get("title"),
                "source_format": row.get("source_format"),
                "external_state": row.get("external_state"),
            }
            for row in note_rows
        ]
        edges = [
            {
                "id": str(row["id"]),
                "source": str(row["source_note_id"]),
                "target": str(row["target_note_id"]),
                "kind": row["link_kind"],
            }
            for row in edge_rows.values()
        ]
        return VaultGraph(nodes=nodes, edges=edges)

    async def append_receipt(self, receipt: VaultSyncReceipt) -> VaultSyncReceipt:
        validated = VaultSyncReceipt.model_validate(receipt.model_dump())
        data = validated.model_dump(exclude={"id"})
        data["rollback_path"] = None
        data["vault_id"] = _db_id(validated.vault_id)
        data["vault_file_id"] = _db_id(validated.vault_file_id)
        receipt_id = _record_id(
            "vault_sync_receipt",
            validated.operation_id,
            validated.vault_file_id,
        )
        async with self._connection_factory() as connection:
            await self._query(
                connection,
                """
                BEGIN TRANSACTION;
                CREATE $receipt_id CONTENT $receipt; -- vault_sync_receipt
                COMMIT TRANSACTION;
                """,
                {
                    "receipt_id": _db_id(receipt_id),
                    "receipt": data,
                },
            )
        return validated

    async def list_receipts(
        self,
        vault_id: str,
        limit: int,
        offset: int,
    ) -> list[VaultSyncReceipt]:
        self._validate_page(limit, offset)
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM vault_sync_receipt
                WHERE vault_id = $vault_id
                ORDER BY started_at DESC LIMIT $limit START $offset;
                """,
                {
                    "vault_id": _db_id(vault_id),
                    "limit": limit,
                    "offset": offset,
                },
            )
        return [VaultSyncReceipt.model_validate(row) for row in rows]

    async def import_trust_manifest(
        self,
        vault_id: str,
        manifest_relative_path: str,
    ) -> TrustImportResult:
        supplied_root = self._approved_roots.get(vault_id)
        if supplied_root is not None:
            return await self._import_trust_from_root(
                vault_id, manifest_relative_path, supplied_root
            )
        vault = await self.get_mount(vault_id)
        with approve_vault_root(vault.root_path) as approved:
            return await self._import_trust_from_root(
                vault_id, manifest_relative_path, approved
            )

    async def _import_trust_from_root(
        self,
        vault_id: str,
        manifest_relative_path: str,
        root: ApprovedVaultRoot,
    ) -> TrustImportResult:
        classification = classify_vault_path(manifest_relative_path)
        if (
            classification.kind != "connector"
            or not manifest_relative_path.casefold().endswith(".json")
        ):
            raise ValueError("invalid_trust_manifest_path")
        manifest_read = secure_read(
            root,
            manifest_relative_path,
            max_bytes=MAX_MANIFEST_BYTES,
        )
        manifest = parse_trust_manifest(manifest_read.content)
        resolutions: list[
            tuple[TrustManifestEntry, Literal["resolved", "unresolved"], Any | None]
        ] = []
        for entry in manifest.entries:
            canonical_read = None
            try:
                candidate = secure_read(root, entry.canonical_relative_path)
                if candidate.sha256 == entry.content_hash:
                    canonical_read = candidate
                    resolution: Literal["resolved", "unresolved"] = "resolved"
                else:
                    resolution = "unresolved"
            except VaultSecurityError:
                resolution = "unresolved"
            resolutions.append((entry, resolution, canonical_read))

        manifest_file_id = _record_id("vault_file", vault_id, manifest_relative_path)
        resolved = sum(state == "resolved" for _, state, _ in resolutions)
        unresolved = len(resolutions) - resolved
        variables: dict[str, Any] = {
            "vault_id": _db_id(vault_id),
            "manifest_relative_path": manifest_relative_path,
            "manifest_file_id": _db_id(manifest_file_id),
            "manifest_file": {
                "schema_version": 1,
                "vault_id": _db_id(vault_id),
                "relative_path": manifest_relative_path,
                "file_kind": "connector",
                "format": "json",
                "content_hash": manifest_read.sha256,
                "size_bytes": manifest_read.byte_size,
                "modified_ns": manifest_read.modified_ns,
                "encoding": "utf-8",
                "parse_status": "unsupported",
                "parse_error_code": None,
                "deleted_state": "present",
            },
        }
        statements = [
            "BEGIN TRANSACTION;",
            (
                "LET $existing_manifest = (SELECT * FROM vault_file "
                "WHERE id = $manifest_file_id LIMIT 1)[0];"
            ),
            "UPSERT $manifest_file_id MERGE $manifest_file;",
        ]
        changed_expressions: list[str] = []
        for index, (entry, resolution, canonical_read) in enumerate(resolutions):
            suffix = str(index)
            trust_name = f"trust_{suffix}"
            prior_name = f"prior_{suffix}"
            changed_name = f"changed_{suffix}"
            canonical_file_id: str | None = None
            trust_id = _record_id(
                "vault_trust_record",
                vault_id,
                manifest_relative_path,
                entry.manifest_id,
            )
            if canonical_read is not None:
                canonical_file_id = _record_id(
                    "vault_file", vault_id, entry.canonical_relative_path
                )
            trust_record = {
                "schema_version": 1,
                "manifest_id": entry.manifest_id,
                "vault_id": _db_id(vault_id),
                "vault_file_id": (
                    _db_id(canonical_file_id) if canonical_file_id else None
                ),
                "note_id": None,
                "canonical_relative_path": entry.canonical_relative_path,
                "status": "approved",
                "resolution_state": resolution,
                "reviewer": entry.reviewer,
                "reviewed_at": entry.reviewed_at,
                "source_type": entry.source_type,
                "evidence_class": entry.evidence_class,
                "content_hash": entry.content_hash,
                "derived_from": list(entry.derived_from),
                "manifest_relative_path": manifest_relative_path,
            }
            variables.update(
                {
                    f"manifest_id_{suffix}": entry.manifest_id,
                    f"trust_id_{suffix}": _db_id(trust_id),
                    trust_name: trust_record,
                }
            )
            statements.extend(
                [
                    (
                        f"LET ${prior_name} = (SELECT * FROM vault_trust_record "
                        f"WHERE vault_id = $vault_id "
                        f"AND manifest_relative_path = $manifest_relative_path "
                        f"AND manifest_id = $manifest_id_{suffix} LIMIT 1)[0];"
                    ),
                    (
                        f"LET ${changed_name} = ${prior_name} = NONE "
                        f"OR ${prior_name}.content_hash != ${trust_name}.content_hash "
                        f"OR ${prior_name}.resolution_state != "
                        f"${trust_name}.resolution_state "
                        f"OR ${prior_name}.vault_id != ${trust_name}.vault_id "
                        f"OR ${prior_name}.canonical_relative_path != "
                        f"${trust_name}.canonical_relative_path "
                        f"OR ${prior_name}.manifest_relative_path != "
                        f"${trust_name}.manifest_relative_path "
                        f"OR ${prior_name}.derived_from != ${trust_name}.derived_from "
                        f"OR ${prior_name}.reviewer != ${trust_name}.reviewer "
                        f"OR ${prior_name}.reviewed_at != ${trust_name}.reviewed_at "
                        f"OR ${prior_name}.source_type != ${trust_name}.source_type "
                        f"OR ${prior_name}.evidence_class != "
                        f"${trust_name}.evidence_class;"
                    ),
                    f"IF ${changed_name} {{",
                ]
            )
            if canonical_read is not None and canonical_file_id is not None:
                variables.update(
                    {
                        f"canonical_file_id_{suffix}": _db_id(canonical_file_id),
                        f"canonical_file_{suffix}": {
                            "schema_version": 1,
                            "vault_id": _db_id(vault_id),
                            "relative_path": entry.canonical_relative_path,
                            "file_kind": "trusted-source",
                            "format": entry.source_type,
                            "content_hash": canonical_read.sha256,
                            "size_bytes": canonical_read.byte_size,
                            "modified_ns": canonical_read.modified_ns,
                            "encoding": None,
                            "parse_status": "unsupported",
                            "parse_error_code": None,
                            "deleted_state": "present",
                        },
                    }
                )
                statements.append(
                    f"UPSERT $canonical_file_id_{suffix} "
                    f"MERGE $canonical_file_{suffix};"
                )
            statements.extend(
                [
                    f"UPSERT $trust_id_{suffix} MERGE ${trust_name};",
                    "};",
                ]
            )
            changed_expressions.append(f"IF ${changed_name} {{ 1 }} ELSE {{ 0 }}")
        changed_expression = " + ".join(changed_expressions) or "0"
        statements.extend(
            [
                f"LET $changed_count = {changed_expression};",
                f"LET $unchanged_count = {len(resolutions)} - $changed_count;",
            ]
        )
        vault = VaultMount(
            id=vault_id,
            name="vault",
            root_path="/redacted",
            format_mode="markdown",
            status="ready-read-only",
            parser_version="trust-importer",
        )
        operation_id = f"trust-{uuid.uuid4().hex}"
        receipt = self._receipt_data(
            operation_id=operation_id,
            vault=vault,
            vault_file_id=manifest_file_id,
            operation="import_trust",
            status="unresolved" if unresolved else "success",
            before_hash=None,
            after_hash=manifest_read.sha256,
            observed_modified_ns=manifest_read.modified_ns,
            started_at=_now(),
        )
        variables.update(
            {
                "receipt_id": _db_id(
                    _record_id("vault_sync_receipt", operation_id, manifest_file_id)
                ),
                "receipt": receipt,
                "resolved_count": resolved,
                "unresolved_count": unresolved,
            }
        )
        statements.extend(
            [
                "IF $changed_count > 0 {",
                ("CREATE $receipt_id CONTENT $receipt; -- vault_sync_receipt"),
                (
                    "UPDATE $receipt_id SET before_hash = "
                    "$existing_manifest.content_hash;"
                ),
                "};",
                (
                    "RETURN { changed: $changed_count, "
                    "unchanged: $unchanged_count, resolved: $resolved_count, "
                    "unresolved: $unresolved_count };"
                ),
                "COMMIT TRANSACTION;",
            ]
        )
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "\n".join(statements),
                variables,
            )
        outcome = next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and "changed" in row
            ),
            None,
        )
        if outcome is None:
            raise RuntimeError("trust_import_outcome_missing")
        return TrustImportResult.model_validate(outcome)

    async def list_trust_records(
        self,
        vault_id: str,
        limit: int,
        offset: int,
    ) -> list[VaultTrustRecord]:
        self._validate_page(limit, offset)
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM vault_trust_record
                WHERE vault_id = $vault_id
                ORDER BY manifest_id LIMIT $limit START $offset;
                """,
                {
                    "vault_id": _db_id(vault_id),
                    "limit": limit,
                    "offset": offset,
                },
            )
        return [VaultTrustRecord.model_validate(row) for row in rows]

    async def trust_summary(self, vault_id: str) -> VaultTrustSummary:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT
                    count() AS total,
                    math::sum(if resolution_state = 'resolved' then 1 else 0 end)
                        AS resolved,
                    math::sum(if resolution_state = 'unresolved' then 1 else 0 end)
                        AS unresolved
                FROM vault_trust_record
                WHERE vault_id = $vault_id GROUP ALL;
                """,
                {"vault_id": _db_id(vault_id)},
            )
        return VaultTrustSummary.model_validate(rows[0] if rows else {})

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
        ):
            raise ValueError("invalid_pagination")


__all__ = [
    "FailureResult",
    "OwnedProjectionUnitOfWork",
    "ProjectionResult",
    "TrustImportResult",
    "VaultFile",
    "VaultGraph",
    "VaultLink",
    "VaultMount",
    "VaultMountCreate",
    "VaultPage",
    "VaultProjectionError",
    "VaultRepository",
    "VaultSyncReceipt",
    "VaultTrustRecord",
    "VaultTrustSummary",
]
