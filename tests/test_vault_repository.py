from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from surrealdb import RecordID

from deeper_notebook.identity import LEGACY_COMMAND_APP
from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedLink,
    ParsedTask,
)
from deeper_notebook.vault.repository import (
    ProjectionResult,
    VaultFile,
    VaultLink,
    VaultMount,
    VaultProjectionError,
    VaultRepository,
    VaultSyncReceipt,
    _record_id,
)
from deeper_notebook.vault.security import approve_vault_root
from deeper_notebook.vault.trust import TrustManifestError, parse_trust_manifest
from deeper_notebook.vault.watcher import VaultFileObservation, VaultWorkItem


class QueryRecorder:
    def __init__(
        self,
        *,
        existing_file: dict[str, Any] | None = None,
        notes: list[dict[str, Any]] | None = None,
        fail_on: str | None = None,
        trust_records: dict[str, dict[str, Any]] | None = None,
        lost_response_after_commit: bool = False,
        reconciliation_proof: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.existing_file = existing_file
        self.notes = notes or []
        self.fail_on = fail_on
        self.trust_records = trust_records if trust_records is not None else {}
        self.lost_response_after_commit = lost_response_after_commit
        self.reconciliation_proof = reconciliation_proof
        self.receipts_created = 0

    async def query(
        self, statement: str, variables: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        variables = variables or {}
        compact = " ".join(statement.split())
        self.calls.append((compact, variables))
        if "RETURN { receipt:" in compact:
            return [self.reconciliation_proof] if self.reconciliation_proof else []
        if "SELECT VALUE id FROM $note_id" in compact:
            return [str(variables["note_id"])]
        if self.fail_on and self.fail_on in compact:
            raise RuntimeError("synthetic database failure")
        if "LET $unchanged =" in compact:
            existing_modified_ns = (
                self.existing_file.get("modified_ns", variables["observed_modified_ns"])
                if self.existing_file
                else None
            )
            observed_modified_ns = variables["observed_modified_ns"]
            conflict = bool(
                self.existing_file
                and existing_modified_ns == observed_modified_ns
                and self.existing_file.get("content_hash") != variables["content_hash"]
            )
            superseded = bool(
                self.existing_file and existing_modified_ns > observed_modified_ns
            )
            unchanged = bool(
                self.existing_file
                and existing_modified_ns == observed_modified_ns
                and self.existing_file.get("content_hash") == variables["content_hash"]
                and self.existing_file.get("parse_status") == "parsed"
                and self.existing_file.get("deleted_state") == "present"
            )
            self.receipts_created += 1
            if self.lost_response_after_commit:
                raise ConnectionError("synthetic lost response")
            status = (
                "conflict"
                if conflict
                else "superseded"
                if superseded
                else "unchanged"
                if unchanged
                else "projected"
            )
            return [{"projection_status": status}]
        if "LET $failure_status =" in compact:
            existing_modified_ns = (
                self.existing_file.get("modified_ns", 0) if self.existing_file else None
            )
            observed_modified_ns = variables["modified_ns"]
            conflict = bool(
                self.existing_file
                and existing_modified_ns == observed_modified_ns
                and self.existing_file.get("content_hash") != variables["content_hash"]
            )
            superseded = bool(
                self.existing_file
                and (
                    existing_modified_ns > observed_modified_ns
                    or (
                        existing_modified_ns == observed_modified_ns
                        and self.existing_file.get("content_hash")
                        == variables["content_hash"]
                        and self.existing_file.get("parse_status") == "parsed"
                    )
                )
            )
            self.receipts_created += 1
            return [
                {
                    "failure_status": (
                        "conflict"
                        if conflict
                        else "superseded"
                        if superseded
                        else "stale-invalid"
                    )
                }
            ]
        if "LET $transitioned =" in compact:
            transitioned = not (
                self.existing_file
                and self.existing_file.get("deleted_state") == "missing"
            )
            self.receipts_created += int(transitioned)
            return [{"transitioned": transitioned}]
        if "LET $changed_count =" in compact:
            trust = variables["trust_0"]
            prior = self.trust_records.get(trust["manifest_id"])
            semantic_fields = (
                "content_hash",
                "resolution_state",
                "canonical_relative_path",
                "manifest_relative_path",
                "derived_from",
            )
            unchanged = bool(
                prior
                and str(prior.get("vault_id")) == str(trust["vault_id"])
                and all(
                    prior.get(field) == trust.get(field) for field in semantic_fields
                )
            )
            if not unchanged:
                self.trust_records[trust["manifest_id"]] = {
                    "id": variables["trust_id_0"],
                    **trust,
                }
                self.receipts_created += 1
            return [
                {
                    "changed": 0 if unchanged else 1,
                    "unchanged": 1 if unchanged else 0,
                    "resolved": variables["resolved_count"],
                    "unresolved": variables["unresolved_count"],
                }
            ]
        if "SELECT * FROM vault_file" in compact:
            return [self.existing_file] if self.existing_file else []
        if "SELECT id, title FROM note" in compact:
            return self.notes
        if "RETURN AFTER" in compact and "vault_sync_receipt" in compact:
            return [{"id": variables.get("receipt_id"), **variables.get("receipt", {})}]
        return []


@pytest.mark.asyncio
async def test_record_observation_persists_pending_file_without_source_content():
    connection = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
    )
    observation = VaultFileObservation(
        vault_id="vault_mount:test",
        relative_path="pages/alpha.md",
        state="pending",
        file_kind="markdown",
        protected=False,
        content_hash=None,
        byte_size=42,
        modified_ns=123,
        parse_state="pending",
        embedding_state="not_submitted",
        observed_at=1.0,
    )

    await repository.record_observation(observation)

    statement, variables = connection.calls[0]
    assert "UPSERT $vault_file_id" in statement
    assert "LET $existing_file" in statement
    assert "LET $same_projection" in statement
    assert "$existing_file.parse_status IN ['parsed', 'invalid']" in statement
    assert "$content_hash = NONE" in statement
    assert "content_hash = IF $same_projection" in statement
    assert "parse_status = IF $same_projection" in statement
    assert "embedding_state = IF $same_projection" in statement
    assert variables["relative_path"] == "pages/alpha.md"
    assert variables["parse_status"] == "pending"
    assert "content" not in variables


class ConnectionSequence:
    def __init__(self, *connections: QueryRecorder) -> None:
        self.connections = list(connections)
        self.opened: list[QueryRecorder] = []

    @asynccontextmanager
    async def __call__(self):
        connection = self.connections.pop(0)
        self.opened.append(connection)
        yield connection


def _mount(root_path: str = "/synthetic/approved-vault") -> VaultMount:
    return VaultMount(
        id="vault_mount:test",
        name="Synthetic",
        root_path=root_path,
        format_mode="obsidian",
        status="ready-read-only",
        watch_enabled=True,
        write_policy="read-only",
        protected_globs=[],
        parser_version="test-parser",
    )


@pytest.mark.asyncio
async def test_scan_lifecycle_is_persisted_with_utc_timestamps():
    started_at = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 7, 28, 12, 1, tzinfo=timezone.utc)
    connection = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection, connection)
    )

    await repository.mark_scan_started("vault_mount:test", started_at=started_at)
    await repository.mark_scan_completed(
        "vault_mount:test",
        status="ready-read-only",
        completed_at=completed_at,
    )

    started_statement, started_variables = connection.calls[0]
    completed_statement, completed_variables = connection.calls[1]
    assert "UPDATE $vault_id SET" in started_statement
    assert 'status = "scanning"' in started_statement
    assert "last_scan_started_at = $started_at" in started_statement
    assert started_variables == {
        "vault_id": RecordID("vault_mount", "test"),
        "started_at": started_at,
    }
    assert "UPDATE $vault_id SET" in completed_statement
    assert "status = $status" in completed_statement
    assert "last_scan_completed_at = $completed_at" in completed_statement
    assert completed_variables == {
        "vault_id": RecordID("vault_mount", "test"),
        "status": "ready-read-only",
        "completed_at": completed_at,
    }


@pytest.mark.asyncio
async def test_scan_completion_rejects_non_terminal_state():
    repository = VaultRepository(
        connection_factory=ConnectionSequence(QueryRecorder()),
    )

    with pytest.raises(ValueError, match="vault_scan_state_not_terminal"):
        await repository.mark_scan_completed(
            "vault_mount:test",
            status="scanning",
        )


def _work(
    *,
    relative_path: str = "Pages/Alpha.md",
    content_hash: str = "a" * 64,
    modified_ns: int = 123,
) -> VaultWorkItem:
    return VaultWorkItem(
        vault_id="vault_mount:test",
        relative_path=relative_path,
        file_kind="markdown",
        protected=False,
        content=b"# Alpha\n- [ ] Task [[Beta]]",
        content_hash=content_hash,
        byte_size=28,
        modified_ns=modified_ns,
    )


def _document(
    *,
    relative_path: str = "Pages/Alpha.md",
    content_hash: str = "a" * 64,
) -> ParsedDocument:
    markdown = "# Alpha\n- [ ] Task [[Beta]]"
    return ParsedDocument(
        relative_path=relative_path,
        source_format="obsidian",
        title="Alpha",
        markdown=markdown,
        content_hash=content_hash,
        newline="lf",
        blocks=[
            ParsedBlock(
                parser_id="heading",
                position=0,
                block_kind="heading",
                markdown="# Alpha",
                plain_text="Alpha",
                source_start=0,
                source_end=7,
            ),
            ParsedBlock(
                parser_id="task",
                position=1,
                block_kind="task",
                markdown="- [ ] Task [[Beta]]",
                plain_text="Task Beta",
                task_state="todo",
                source_start=8,
                source_end=len(markdown.encode()),
            ),
        ],
        links=[
            ParsedLink(
                source_block_parser_id="task",
                target_text="Beta",
                link_kind="wikilink",
                source_start=19,
                source_end=27,
            )
        ],
        tasks=[ParsedTask(block_parser_id="task", status="todo")],
    )


@pytest.mark.asyncio
async def test_projection_is_one_ordered_transaction_and_embeds_after_commit():
    connection = QueryRecorder(notes=[{"id": "note:beta", "title": "Beta"}])
    connections = ConnectionSequence(connection)
    embedding_calls: list[tuple[str, str, dict[str, str]]] = []

    async def embed(app: str, command: str, payload: dict[str, str]) -> None:
        assert "COMMIT TRANSACTION;" in connection.calls[-1][0]
        embedding_calls.append((app, command, payload))

    repository = VaultRepository(
        connection_factory=connections,
        embedding_submitter=embed,
    )
    result = await repository.project_document(
        _mount(), _work(), _document(), "operation-1"
    )

    assert result == ProjectionResult(
        vault_file_id=result.vault_file_id,
        note_id=result.note_id,
        status="projected",
        parse_state="parsed",
        embedding_state="pending",
    )
    assert len(connection.calls) == 1
    transaction = connection.calls[0][0]
    assert transaction.startswith("BEGIN TRANSACTION;")
    assert "COMMIT TRANSACTION;" in transaction
    ordered_fragments = [
        "UPSERT $vault_file_id MERGE $vault_file",
        "UPSERT $note_id MERGE $note",
        "DELETE note_block",
        "DELETE note_link",
        "DELETE knowledge_task",
        "UPSERT $block.record_id CONTENT $block.data",
        "UPSERT $link.record_id CONTENT $link.data",
        "UPSERT $task.record_id CONTENT $task.data",
        "UPDATE $affected_link.id SET",
        "UPDATE $vault_file_id SET parse_status",
        "UPDATE $note_id SET external_state",
        "CREATE $receipt_id CONTENT",
    ]
    positions = [transaction.index(fragment) for fragment in ordered_fragments]
    assert positions == sorted(positions)
    assert "artifact" not in transaction.casefold()
    assert "before_hash = $existing_file.content_hash" in transaction
    assert embedding_calls == [
        (LEGACY_COMMAND_APP, "embed_note", {"note_id": result.note_id})
    ]


@pytest.mark.asyncio
async def test_unchanged_hash_only_appends_one_unchanged_receipt():
    existing = {
        "id": "vault_file:existing",
        "content_hash": "a" * 64,
        "modified_ns": 123,
        "parse_status": "parsed",
        "deleted_state": "present",
    }
    connection = QueryRecorder(existing_file=existing)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )

    result = await repository.project_document(
        _mount(), _work(), _document(), "operation-unchanged"
    )

    assert result.status == "unchanged"
    assert len(connection.calls) == 1
    assert connection.receipts_created == 1
    assert connection.calls[0][1]["unchanged_receipt"]["status"] == "unchanged"
    assert connection.calls[0][1]["unchanged_receipt"]["after_hash"] == "a" * 64
    assert "before_hash = $existing_file.content_hash" in connection.calls[0][0]


@pytest.mark.asyncio
async def test_changed_projection_receipt_binds_prior_and_current_hashes_atomically():
    existing = {
        "id": "vault_file:existing",
        "content_hash": "a" * 64,
        "modified_ns": 100,
        "parse_status": "parsed",
        "deleted_state": "present",
    }
    connection = QueryRecorder(existing_file=existing)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )
    await repository.project_document(
        _mount(),
        _work(content_hash="b" * 64),
        _document(content_hash="b" * 64),
        "operation-changed",
    )

    transaction, variables = connection.calls[0]
    assert variables["success_receipt"]["after_hash"] == "b" * 64
    assert "before_hash = $existing_file.content_hash" in transaction


@pytest.mark.asyncio
async def test_task_dates_are_converted_to_timezone_aware_utc_before_query():
    connection = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )
    parsed = _document().model_copy(
        update={
            "tasks": [
                ParsedTask(
                    block_parser_id="task",
                    status="done",
                    scheduled=date(2026, 7, 28),
                    due=date(2026, 7, 29),
                    completed=date(2026, 7, 30),
                )
            ]
        }
    )

    await repository.project_document(_mount(), _work(), parsed, "operation-task-dates")

    task = connection.calls[0][1]["tasks"][0]["data"]
    for field in ("scheduled", "due", "completed"):
        assert isinstance(task[field], datetime)
        assert task[field].tzinfo is timezone.utc
        assert task[field].hour == 0
        assert task[field].minute == 0


@pytest.mark.asyncio
async def test_projection_transaction_has_atomic_stale_writer_supersession():
    connection = QueryRecorder(
        existing_file={
            "id": "vault_file:existing",
            "content_hash": "b" * 64,
            "modified_ns": 200,
            "parse_status": "parsed",
            "deleted_state": "present",
        }
    )
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )

    await repository.project_document(
        _mount(),
        _work(content_hash="a" * 64),
        _document(content_hash="a" * 64),
        "operation-stale-projection",
    )

    transaction = connection.calls[0][0]
    assert "LET $superseded" in transaction
    assert "LET $conflict" in transaction
    assert "observed_modified_ns" in transaction
    assert "$superseded_receipt" in transaction
    assert "$conflict_receipt" in transaction
    assert "$current_success.started_at" not in transaction
    assert transaction.index("LET $superseded") < transaction.index(
        "UPSERT $vault_file_id"
    )


@pytest.mark.asyncio
async def test_equal_timestamp_different_hash_projection_requires_reconciliation():
    connection = QueryRecorder(
        existing_file={
            "id": "vault_file:existing",
            "content_hash": "b" * 64,
            "modified_ns": 200,
            "parse_status": "parsed",
            "deleted_state": "present",
        }
    )
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )

    result = await repository.project_document(
        _mount(),
        _work(content_hash="a" * 64, modified_ns=200),
        _document(content_hash="a" * 64),
        "operation-equal-conflict",
    )

    assert result.status == "conflict"
    assert result.reconciliation_required is True
    assert connection.calls[0][1]["conflict_receipt"]["status"] == "conflict"
    assert (
        connection.calls[0][1]["conflict_receipt"]["error_code"]
        == "reconciliation_required"
    )


@pytest.mark.asyncio
async def test_newer_failure_invalidates_file_but_preserves_projection_graph():
    connection = QueryRecorder(
        existing_file={
            "id": "vault_file:existing",
            "content_hash": "b" * 64,
            "modified_ns": 200,
            "parse_status": "parsed",
            "deleted_state": "present",
        }
    )
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    result = await repository.record_failure(
        "vault_mount:test",
        _work(content_hash="c" * 64, modified_ns=300),
        "operation-newer-failure",
        "frontmatter_invalid",
    )

    transaction = connection.calls[0][0]
    assert "LET $superseded" in transaction
    assert "LET $conflict" in transaction
    assert "$superseded_receipt" in transaction
    assert "$conflict_receipt" in transaction
    assert "$stale_invalid_receipt" in transaction
    assert "UPDATE note SET external_state = 'stale'" in transaction
    assert "DELETE note" not in transaction
    assert "DELETE note_block" not in transaction
    assert "DELETE note_link" not in transaction
    assert "DELETE knowledge_task" not in transaction
    assert transaction.index("LET $superseded") < transaction.index(
        "UPSERT $vault_file_id"
    )
    assert result.status == "stale-invalid"
    assert result.reconciliation_required is False


@pytest.mark.asyncio
async def test_equal_timestamp_different_hash_failure_requires_reconciliation():
    connection = QueryRecorder(
        existing_file={
            "id": "vault_file:existing",
            "content_hash": "b" * 64,
            "modified_ns": 200,
            "parse_status": "parsed",
            "deleted_state": "present",
        }
    )
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    result = await repository.record_failure(
        "vault_mount:test",
        _work(content_hash="a" * 64, modified_ns=200),
        "operation-conflicting-failure",
        "parse_failed",
    )

    assert result.status == "conflict"
    assert result.reconciliation_required is True
    variables = connection.calls[0][1]
    assert variables["conflict_receipt"]["status"] == "conflict"
    assert variables["conflict_receipt"]["error_code"] == "reconciliation_required"


@pytest.mark.asyncio
async def test_equal_timestamp_same_hash_failure_does_not_invalidate_success():
    connection = QueryRecorder(
        existing_file={
            "id": "vault_file:existing",
            "content_hash": "b" * 64,
            "modified_ns": 200,
            "parse_status": "parsed",
            "deleted_state": "present",
        }
    )
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    result = await repository.record_failure(
        "vault_mount:test",
        _work(content_hash="b" * 64, modified_ns=200),
        "operation-idempotent-failure",
        "parse_failed",
    )

    assert result.status == "superseded"
    assert result.reconciliation_required is False
    assert "$existing_file.parse_status = 'parsed'" in connection.calls[0][0]


@pytest.mark.asyncio
async def test_equal_timestamp_same_hash_failure_invalidates_pending_observation():
    connection = QueryRecorder(
        existing_file={
            "id": "vault_file:existing",
            "content_hash": "b" * 64,
            "modified_ns": 200,
            "parse_status": "pending",
            "deleted_state": "present",
        }
    )
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    result = await repository.record_failure(
        "vault_mount:test",
        _work(content_hash="b" * 64, modified_ns=200),
        "operation-pending-failure",
        "invalid_frontmatter",
    )

    assert result.status == "stale-invalid"
    assert result.reconciliation_required is False


@pytest.mark.asyncio
async def test_projection_persists_python_canonical_title_keys_and_reconciles_inbound():
    connection = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )
    parsed = _document().model_copy(
        update={
            "title": "  Ｂｅｔａ  ",
            "links": [
                ParsedLink(
                    source_block_parser_id="task",
                    target_text="  Ｂｅｔａ  ",
                    link_kind="wikilink",
                    source_start=19,
                    source_end=27,
                )
            ],
        }
    )

    await repository.project_document(_mount(), _work(), parsed, "operation-title-key")

    transaction, variables = connection.calls[0]
    assert variables["note"]["title_key"] == "beta"
    assert variables["links"][0]["data"]["target_title_key"] == "beta"
    assert "target_title_key" in transaction
    assert "array::len($targets) = 1" in transaction
    assert "source_note_id IN" in transaction
    assert "WHERE vault_id = $vault_id" in transaction
    assert "string::lowercase(title)" not in transaction


def test_atomic_repository_paths_never_split_begin_and_commit_rpcs():
    source = Path(VaultRepository.project_document.__code__.co_filename).read_text(
        encoding="utf-8"
    )
    assert 'self._query(connection, "BEGIN TRANSACTION;")' not in source
    assert 'self._query(connection, "COMMIT TRANSACTION;")' not in source


@pytest.mark.asyncio
async def test_projection_failure_cancels_and_records_bounded_receipt_separately():
    failed = QueryRecorder(fail_on="FOR $link IN $links")
    reconciliation = QueryRecorder()
    failure_receipt = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(failed, reconciliation, failure_receipt),
        embedding_submitter=lambda *_args: None,
        failure_receipt_timeout=0.5,
    )

    with pytest.raises(RuntimeError, match="synthetic database failure"):
        await repository.project_document(
            _mount(), _work(), _document(), "operation-failed"
        )

    assert len(failed.calls) == 1
    assert len(reconciliation.calls) == 1
    assert len(failure_receipt.calls) == 1
    assert failure_receipt.calls[0][0].startswith("BEGIN TRANSACTION;")
    assert "COMMIT TRANSACTION;" in failure_receipt.calls[0][0]
    variables = failure_receipt.calls[0][1]
    serialized = json.dumps(variables, default=str)
    assert "# Alpha" not in serialized
    assert "/Users/" not in serialized
    assert variables["failed_receipt"]["error_code"] == "projection_failed"


@pytest.mark.asyncio
async def test_lost_response_after_commit_reconciles_without_failure_overwrite():
    primary = QueryRecorder(lost_response_after_commit=True)
    reconciliation = QueryRecorder(
        reconciliation_proof={
            "receipt": {
                "status": "success",
                "after_hash": "a" * 64,
            },
            "file": {
                "content_hash": "a" * 64,
                "parse_status": "parsed",
                "deleted_state": "present",
            },
            "note": {
                "source_hash": "a" * 64,
                "external_state": "current",
            },
        }
    )
    repository = VaultRepository(
        connection_factory=ConnectionSequence(primary, reconciliation),
        embedding_submitter=lambda *_args: None,
    )

    result = await repository.project_document(
        _mount(), _work(), _document(), "operation-lost-response"
    )

    assert result.status == "projected"
    assert len(primary.calls) == 1
    assert len(reconciliation.calls) == 1


@pytest.mark.asyncio
async def test_cancellation_issues_cancel_and_never_embeds():
    class CancellingRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "FOR $link IN $links" in compact:
                self.calls.append((compact, variables or {}))
                raise asyncio.CancelledError
            return await super().query(statement, variables)

    connection = CancellingRecorder()
    embedded = False

    async def embed(*_args):
        nonlocal embedded
        embedded = True

    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=embed,
    )
    with pytest.raises(asyncio.CancelledError):
        await repository.project_document(
            _mount(), _work(), _document(), "operation-cancelled"
        )

    assert len(connection.calls) == 1
    assert embedded is False


@pytest.mark.asyncio
async def test_cancellation_waits_for_query_terminal_state_and_arranges_embedding_once():
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    embedding_calls: list[str] = []

    class DelayedConnection(QueryRecorder):
        async def query(self, statement, variables=None):
            self.calls.append((" ".join(statement.split()), variables or {}))
            started.set()
            try:
                await release.wait()
                return [{"projection_status": "projected"}]
            finally:
                completed.set()

    connection = DelayedConnection()

    async def embed(_app, _command, payload):
        embedding_calls.append(payload["note_id"])

    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=embed,
    )
    projection = asyncio.create_task(
        repository.project_document(
            _mount(), _work(), _document(), "operation-cancel-terminal"
        )
    )
    await started.wait()
    projection.cancel()
    await asyncio.sleep(0)
    assert not completed.is_set()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await projection

    assert completed.is_set()
    assert len(embedding_calls) == 1


@pytest.mark.asyncio
async def test_failed_parse_receipt_preserves_projection_and_redacts_source():
    existing = {
        "id": "vault_file:existing",
        "content_hash": "a" * 64,
        "parse_status": "parsed",
        "deleted_state": "present",
    }
    connection = QueryRecorder(existing_file=existing)
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    await repository.record_failure(
        "vault_mount:test",
        _work(),
        "operation-parse-failed",
        "frontmatter-invalid:/Users/private:# Secret",
    )

    statements = [statement for statement, _ in connection.calls]
    assert all("DELETE note" not in statement for statement in statements)
    assert all("DELETE note_block" not in statement for statement in statements)
    serialized = json.dumps(connection.calls, default=str)
    assert "# Secret" not in serialized
    assert "/Users/private" not in serialized
    assert "frontmatter-invalid" in serialized


@pytest.mark.asyncio
async def test_missing_is_atomic_transition_idempotent_and_supports_late_resurrection():
    current = {
        "id": "vault_file:existing",
        "content_hash": "a" * 64,
        "parse_status": "parsed",
        "deleted_state": "present",
    }
    first = QueryRecorder(existing_file=current)
    already_missing = QueryRecorder(
        existing_file={**current, "parse_status": "missing", "deleted_state": "missing"}
    )
    resurrected = QueryRecorder(existing_file=current)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(first, already_missing, resurrected)
    )

    await repository.mark_missing("vault_mount:test", "Pages/Alpha.md", "missing-1")
    await repository.mark_missing(
        "vault_mount:test", "Pages/Alpha.md", "missing-repeat"
    )
    await repository.mark_missing(
        "vault_mount:test", "Pages/Alpha.md", "missing-corrective"
    )

    assert first.receipts_created == 1
    assert already_missing.receipts_created == 0
    assert resurrected.receipts_created == 1
    for recorder in (first, resurrected):
        assert len(recorder.calls) == 1
        transaction = recorder.calls[0][0]
        assert transaction.startswith("BEGIN TRANSACTION;")
        assert "COMMIT TRANSACTION;" in transaction
        assert "external_state = 'stale'" in transaction
        assert "DELETE" not in transaction


@pytest.mark.asyncio
async def test_link_resolution_is_scoped_to_same_mount_and_never_artifact():
    connection = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        embedding_submitter=lambda *_args: None,
    )
    await repository.project_document(_mount(), _work(), _document(), "operation-links")

    resolution = connection.calls[0]
    assert "WHERE vault_id = $vault_id" in resolution[0]
    assert str(resolution[1]["vault_id"]) == "vault_mount:test"
    assert all(
        "artifact" not in statement.casefold() for statement, _ in connection.calls
    )


@pytest.mark.asyncio
async def test_embedding_submission_failure_marks_only_local_file_state_after_commit():
    projection = QueryRecorder()
    failure_state = QueryRecorder()

    async def broken_embed(*_args):
        raise ValueError("sensitive submission detail")

    repository = VaultRepository(
        connection_factory=ConnectionSequence(projection, failure_state),
        embedding_submitter=broken_embed,
    )
    result = await repository.project_document(
        _mount(), _work(), _document(), "operation-embed-failure"
    )

    assert "COMMIT TRANSACTION;" in projection.calls[-1][0]
    assert result.parse_state == "parsed"
    assert result.embedding_state == "failed"
    assert len(projection.calls) == 1
    assert projection.calls[0][1]["vault_file"]["embedding_state"] == "pending"
    assert len(failure_state.calls) == 1
    statement, variables = failure_state.calls[0]
    assert statement == "UPDATE $vault_file_id SET embedding_state = 'failed';"
    assert isinstance(variables["vault_file_id"], RecordID)
    assert str(variables["vault_file_id"]) == result.vault_file_id
    assert all(
        "CANCEL TRANSACTION" not in statement for statement, _ in projection.calls
    )


@pytest.mark.asyncio
async def test_embedding_failure_remains_pending_when_local_failure_state_update_fails(
    monkeypatch,
):
    projection = QueryRecorder()
    failure_state = QueryRecorder(
        fail_on="UPDATE $vault_file_id SET embedding_state = 'failed';"
    )
    warnings: list[tuple[object, ...]] = []

    class WarningRecorder:
        def warning(self, *args: object) -> None:
            warnings.append(args)

    async def broken_embed(*_args):
        raise ValueError("sensitive submission detail")

    monkeypatch.setattr("deeper_notebook.vault.repository.logger", WarningRecorder())
    repository = VaultRepository(
        connection_factory=ConnectionSequence(projection, failure_state),
        embedding_submitter=broken_embed,
    )

    result = await repository.project_document(
        _mount(), _work(), _document(), "operation-embed-update-failure"
    )

    assert result.embedding_state == "pending"
    assert len(failure_state.calls) == 1
    assert warnings == [
        (
            "Vault embedding submission failed for note {} ({})",
            result.note_id,
            "ValueError",
        ),
        ("Vault embedding failure state update failed ({})", "RuntimeError"),
    ]
    assert all(
        "CANCEL TRANSACTION" not in statement for statement, _ in projection.calls
    )


@pytest.mark.asyncio
async def test_successful_embedding_submission_leaves_local_state_pending():
    projection = QueryRecorder()
    failure_state = QueryRecorder()

    repository = VaultRepository(
        connection_factory=ConnectionSequence(projection, failure_state),
        embedding_submitter=lambda *_args: None,
    )

    result = await repository.project_document(
        _mount(), _work(), _document(), "operation-embed-success"
    )

    assert result.embedding_state == "pending"
    assert failure_state.calls == []


@pytest.mark.asyncio
async def test_post_commit_embedding_cancellation_propagates_after_durable_commit():
    projection = QueryRecorder()
    failure_state = QueryRecorder()

    async def cancelled_embed(*_args):
        raise asyncio.CancelledError

    repository = VaultRepository(
        connection_factory=ConnectionSequence(projection, failure_state),
        embedding_submitter=cancelled_embed,
    )
    with pytest.raises(asyncio.CancelledError):
        await repository.project_document(
            _mount(), _work(), _document(), "operation-embed-cancelled"
        )

    assert "COMMIT TRANSACTION;" in projection.calls[-1][0]
    assert failure_state.calls == []
    assert all(
        "CANCEL TRANSACTION" not in statement for statement, _ in projection.calls
    )


def test_receipts_are_append_and_list_only():
    public = {name for name in dir(VaultRepository) if not name.startswith("_")}
    assert {"append_receipt", "list_receipts"} <= public
    assert (
        not {
            "update_receipt",
            "delete_receipt",
            "update_external_file",
            "delete_external_file",
        }
        & public
    )


@pytest.mark.parametrize(
    "override",
    [
        {"operation_id": "operation\nsecret"},
        {"operation": "project\nsecret"},
        {"source": "vault-indexer\nsecret"},
        {"parser_version": "/Users/private/parser"},
        {"parser_version": "parser\\private"},
        {"parser_version": "parser\nsecret"},
        {"parser_version": "x" * 129},
        {"policy_decision": "guarded-write"},
        {"policy_decision": "read-only\n/Users/private"},
        {"policy_decision": "x" * 100_000},
        {"error_code": "x" * 65},
        {"rollback_path": "/tmp/phase-1-must-not-write"},
    ],
    ids=[
        "operation-newline",
        "operation-kind-newline",
        "source-newline",
        "parser-path",
        "parser-backslash",
        "parser-newline",
        "parser-too-long",
        "write-policy",
        "policy-newline",
        "policy-too-long",
        "error-too-long",
        "rollback-path",
    ],
)
def test_receipt_contract_rejects_unbounded_or_phase_1_unsafe_fields(override):
    values = {
        "operation_id": "operation-safe",
        "vault_id": "vault_mount:test",
        "vault_file_id": "vault_file:test",
        "operation": "project",
        "source": "vault-indexer",
        "parser_version": "test",
        "status": "success",
        "started_at": datetime.now(timezone.utc),
        **override,
    }

    with pytest.raises(ValidationError):
        VaultSyncReceipt.model_validate(values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("parser_version", "/Users/private/parser"),
        ("parser_version", "parser\nsecret"),
        ("policy_decision", "x" * 100_000),
    ],
    ids=["parser-path", "parser-newline", "policy-too-long"],
)
async def test_append_receipt_revalidates_adversarial_constructed_models(field, value):
    values = {
        "operation_id": "operation-safe",
        "vault_id": "vault_mount:test",
        "vault_file_id": "vault_file:test",
        "operation": "project",
        "source": "vault-indexer",
        "parser_version": "test",
        "policy_decision": "read-only",
        "status": "success",
        "started_at": datetime.now(timezone.utc),
    }
    values[field] = value
    unsafe = VaultSyncReceipt.model_construct(**values)
    repository = VaultRepository(connection_factory=ConnectionSequence())

    with pytest.raises(ValidationError):
        await repository.append_receipt(unsafe)


@pytest.mark.asyncio
async def test_graph_uses_only_vault_links_and_same_mount_notes():
    class GraphRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            variables = variables or {}
            self.calls.append((compact, variables))
            if "SELECT VALUE id FROM $note_id" in compact:
                return [str(variables["note_id"])]
            if "FROM note_link" in compact:
                return [
                    {
                        "id": "note_link:alpha-beta",
                        "source_note_id": "note:alpha",
                        "target_note_id": "note:beta",
                        "target_text": "Beta",
                        "link_kind": "wikilink",
                        "resolved": True,
                    }
                ]
            if "FROM note WHERE" in compact:
                return [
                    {"id": "note:alpha", "title": "Alpha"},
                    {"id": "note:beta", "title": "Beta"},
                ]
            return []

    connection = GraphRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection, connection)
    )
    graph = await repository.graph("vault_mount:test", "note:alpha", depth=1, limit=10)

    assert {node["id"] for node in graph.nodes} == {"note:alpha", "note:beta"}
    assert graph.edges == [
        {
            "id": "note_link:alpha-beta",
            "source": "note:alpha",
            "target": "note:beta",
            "kind": "wikilink",
        }
    ]
    assert all(
        "artifact" not in statement.casefold() for statement, _ in connection.calls
    )
    assert all("vault_id = $vault_id" in statement for statement, _ in connection.calls)


@pytest.mark.asyncio
async def test_link_reads_validate_center_and_filter_both_resolved_endpoints():
    connection = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection, connection)
    )

    await repository.outgoing_links("vault_mount:test", "note:alpha")

    statements = [statement for statement, _ in connection.calls]
    assert any("SELECT VALUE id FROM $note_id" in statement for statement in statements)
    link_query = next(
        statement for statement in statements if "FROM note_link" in statement
    )
    assert "source_note_id IN" in link_query
    assert "target_note_id = NONE OR target_note_id IN" in link_query


@pytest.mark.asyncio
async def test_get_page_returns_its_canonical_file_record():
    file_id = "vault_file:alpha"
    canonical_note_id = _record_id("note", file_id)

    class PageRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            self.calls.append((compact, variables or {}))
            if "SELECT * FROM $note_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": canonical_note_id,
                        "vault_id": "vault_mount:test",
                        "vault_file_id": file_id,
                        "title": "Alpha",
                        "content": "# Alpha\n",
                    }
                ]
            if "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": file_id,
                        "vault_id": "vault_mount:test",
                        "relative_path": "pages/alpha.md",
                        "file_kind": "markdown",
                        "format": "obsidian",
                        "content_hash": "a" * 64,
                        "encoding": "utf-8",
                        "newline": "lf",
                        "parse_status": "parsed",
                        "deleted_state": "present",
                    }
                ]
            return []

    recorder = PageRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(recorder),
    )

    page = await repository.get_page("vault_mount:test", canonical_note_id)

    assert page.file.note_id == canonical_note_id
    assert page.file.relative_path == "pages/alpha.md"
    assert page.file.content_hash == "a" * 64
    assert page.file.newline == "lf"
    file_call = next(
        variables
        for statement, variables in recorder.calls
        if "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id" in statement
    )
    assert str(file_call["vault_file_id"]) == "vault_file:alpha"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_note_id", "requested_note_id"),
    [
        ("note:stored-mismatch", None),
        (None, "note:requested-mismatch"),
    ],
)
async def test_get_page_rejects_noncanonical_note_file_pair(
    stored_note_id,
    requested_note_id,
):
    file_id = "vault_file:alpha"
    canonical_note_id = _record_id("note", file_id)
    stored_note_id = stored_note_id or canonical_note_id
    requested_note_id = requested_note_id or canonical_note_id

    class MismatchRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "SELECT * FROM $note_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": stored_note_id,
                        "vault_id": "vault_mount:test",
                        "vault_file_id": file_id,
                        "title": "Alpha",
                    }
                ]
            if "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": file_id,
                        "vault_id": "vault_mount:test",
                        "relative_path": "pages/alpha.md",
                        "file_kind": "markdown",
                        "format": "obsidian",
                        "content_hash": "a" * 64,
                        "parse_status": "parsed",
                        "deleted_state": "present",
                    }
                ]
            return []

    repository = VaultRepository(
        connection_factory=ConnectionSequence(MismatchRecorder()),
    )

    with pytest.raises(VaultProjectionError, match="vault_page_identity_invalid"):
        await repository.get_page("vault_mount:test", requested_note_id)


@pytest.mark.asyncio
async def test_get_page_wraps_invalid_persisted_file_path():
    file_id = "vault_file:alpha"
    canonical_note_id = _record_id("note", file_id)

    class InvalidFileRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "SELECT * FROM $note_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": canonical_note_id,
                        "vault_id": "vault_mount:test",
                        "vault_file_id": file_id,
                        "title": "Alpha",
                    }
                ]
            if "SELECT * FROM $vault_file_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": file_id,
                        "vault_id": "vault_mount:test",
                        "relative_path": "/Users/private/alpha.md",
                        "file_kind": "markdown",
                        "format": "obsidian",
                        "content_hash": "a" * 64,
                        "parse_status": "parsed",
                        "deleted_state": "present",
                    }
                ]
            return []

    repository = VaultRepository(
        connection_factory=ConnectionSequence(InvalidFileRecorder()),
    )

    with pytest.raises(VaultProjectionError, match="vault_file_invalid"):
        await repository.get_page("vault_mount:test", canonical_note_id)


@pytest.mark.asyncio
async def test_get_page_rejects_note_without_canonical_file():
    class OrphanRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "SELECT * FROM $note_id WHERE vault_id = $vault_id" in compact:
                return [
                    {
                        "id": "note:alpha",
                        "vault_id": "vault_mount:test",
                        "vault_file_id": "vault_file:missing",
                        "title": "Alpha",
                    }
                ]
            return []

    repository = VaultRepository(
        connection_factory=ConnectionSequence(OrphanRecorder()),
    )

    with pytest.raises(LookupError, match="vault_note_file_not_found"):
        await repository.get_page("vault_mount:test", "note:alpha")


@pytest.mark.asyncio
async def test_backlinks_project_source_note_title_for_display_identity():
    target_file_id = "vault_file:target"
    target_note_id = _record_id("note", target_file_id)

    class BacklinkRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            self.calls.append((compact, variables or {}))
            if "SELECT VALUE id FROM $note_id" in compact:
                return [target_note_id]
            if "FROM note_link" in compact:
                return [
                    {
                        "id": "note_link:source-target",
                        "source_note_id": "note:source",
                        "target_note_id": target_note_id,
                        "target_vault_file_id": target_file_id,
                        "target_vault_id": "vault_mount:test",
                        "target_text": "Target",
                        "source_note_title": "Source title",
                        "target_note_title": "Target title",
                        "target_relative_path": "pages/target.md",
                        "source_start": 12,
                        "source_end": 22,
                        "link_kind": "wikilink",
                        "resolved": True,
                    }
                ]
            return []

    connection = BacklinkRecorder()
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    backlinks = await repository.backlinks("vault_mount:test", target_note_id)

    assert backlinks[0].source_note_title == "Source title"
    assert backlinks[0].target_note_title == "Target title"
    assert backlinks[0].target_relative_path == "pages/target.md"
    assert backlinks[0].source_start == 12
    assert backlinks[0].source_end == 22
    link_query = next(
        statement for statement, _ in connection.calls if "FROM note_link" in statement
    )
    assert "source_note_id.title AS source_note_title" in link_query
    assert "target_note_id.title AS target_note_title" in link_query
    assert "target_note_id.vault_file_id AS target_vault_file_id" in link_query
    assert (
        "target_note_id.vault_file_id.vault_id AS target_vault_id" in link_query
    )
    assert (
        "target_note_id.vault_file_id.relative_path AS target_relative_path"
        in link_query
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_updates",
    [
        {"target_vault_file_id": None},
        {"target_vault_id": "vault_mount:other"},
        {"target_vault_file_id": "vault_file:inconsistent"},
    ],
)
async def test_resolved_link_rejects_invalid_target_file_scope(target_updates):
    target_file_id = "vault_file:target"
    target_note_id = _record_id("note", target_file_id)

    class InvalidTargetFileRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "SELECT VALUE id FROM $note_id" in compact:
                return ["note:source"]
            if "FROM note_link" in compact:
                return [
                    {
                        "id": "note_link:invalid-target-file",
                        "source_note_id": "note:source",
                        "target_note_id": target_note_id,
                        "target_vault_file_id": target_file_id,
                        "target_vault_id": "vault_mount:test",
                        "target_note_title": "Target",
                        "target_relative_path": "pages/target.md",
                        "target_text": "Target",
                        "source_start": 4,
                        "source_end": 14,
                        "link_kind": "wikilink",
                        "resolved": True,
                        **target_updates,
                    }
                ]
            return []

    repository = VaultRepository(
        connection_factory=ConnectionSequence(InvalidTargetFileRecorder()),
    )

    with pytest.raises(VaultProjectionError, match="vault_link_target_invalid"):
        await repository.outgoing_links("vault_mount:test", "note:source")


@pytest.mark.asyncio
async def test_resolved_link_wraps_invalid_persisted_metadata():
    target_file_id = "vault_file:target"
    target_note_id = _record_id("note", target_file_id)

    class InvalidResolvedLinkRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            if "SELECT VALUE id FROM $note_id" in compact:
                return ["note:source"]
            if "FROM note_link" in compact:
                return [
                    {
                        "id": "note_link:invalid-metadata",
                        "source_note_id": "note:source",
                        "target_note_id": target_note_id,
                        "target_vault_file_id": target_file_id,
                        "target_vault_id": "vault_mount:test",
                        "target_note_title": None,
                        "target_relative_path": "pages/target.md",
                        "target_text": "Target",
                        "source_start": 4,
                        "source_end": 14,
                        "link_kind": "wikilink",
                        "resolved": True,
                    }
                ]
            return []

    repository = VaultRepository(
        connection_factory=ConnectionSequence(InvalidResolvedLinkRecorder()),
    )

    with pytest.raises(VaultProjectionError, match="vault_link_invalid"):
        await repository.outgoing_links("vault_mount:test", "note:source")


@pytest.mark.asyncio
async def test_unresolved_link_keeps_null_target_identity_and_explicit_spans():
    class UnresolvedLinkRecorder(QueryRecorder):
        async def query(self, statement, variables=None):
            compact = " ".join(statement.split())
            self.calls.append((compact, variables or {}))
            if "SELECT VALUE id FROM $note_id" in compact:
                return ["note:source"]
            if "FROM note_link" in compact:
                return [
                    {
                        "id": "note_link:unresolved",
                        "source_note_id": "note:source",
                        "target_note_id": None,
                        "target_note_title": None,
                        "target_relative_path": None,
                        "target_text": "Missing",
                        "source_start": 4,
                        "source_end": 15,
                        "link_kind": "wikilink",
                        "resolved": False,
                    }
                ]
            return []

    connection = UnresolvedLinkRecorder()
    repository = VaultRepository(connection_factory=ConnectionSequence(connection))

    links = await repository.outgoing_links("vault_mount:test", "note:source")

    assert links[0].target_note_title is None
    assert links[0].target_relative_path is None
    assert links[0].source_start == 4
    assert links[0].source_end == 15


def test_resolved_link_requires_canonical_target_identity():
    with pytest.raises(ValidationError):
        VaultLink(
            id="note_link:broken",
            source_note_id="note:source",
            target_note_id="note:target",
            target_text="Target",
            source_start=0,
            source_end=8,
            link_kind="wikilink",
            resolved=True,
        )


def test_resolved_link_allows_present_empty_canonical_title():
    link = VaultLink(
        id="note_link:empty-title",
        source_note_id="note:source",
        target_note_id="note:target",
        target_note_title="",
        target_relative_path="pages/target.md",
        target_text="Target",
        source_start=0,
        source_end=8,
        link_kind="wikilink",
        resolved=True,
    )
    assert link.target_note_title == ""


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        "/absolute.md",
        "../outside.md",
        "pages\\outside.md",
        "a//b.md",
        "pages/\x00outside.md",
        "C:/outside.md",
        " pages/outside.md",
        "pages/outside.md ",
        "p" * 4097,
    ],
)
def test_vault_models_reject_noncanonical_relative_paths(relative_path):
    with pytest.raises(ValidationError, match="canonical vault-relative path"):
        VaultFile(
            id="vault_file:broken",
            note_id="note:broken",
            vault_id="vault_mount:test",
            relative_path=relative_path,
            file_kind="markdown",
            format="markdown",
            parse_status="parsed",
            deleted_state="present",
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)
async def test_trust_manifest_is_contained_hashed_and_idempotent():
    vault_root = Path(__file__).parent / "fixtures" / "vault" / "trust" / "resolved"
    root = approve_vault_root(vault_root)
    records: dict[str, dict[str, Any]] = {}

    first = QueryRecorder(trust_records=records)
    second = QueryRecorder(trust_records=records)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(first, second),
        approved_roots={"vault_mount:test": root},
    )
    try:
        imported = await repository.import_trust_manifest(
            "vault_mount:test", "brain-engine/trust.json"
        )
        unchanged = await repository.import_trust_manifest(
            "vault_mount:test", "brain-engine/trust.json"
        )
    finally:
        root.close()

    assert imported.resolved == 1
    assert imported.unresolved == 0
    assert imported.changed == 1
    assert unchanged.unchanged == 1
    assert unchanged.changed == 0
    trust = records["manifest-alpha"]
    assert str(trust["vault_id"]) == "vault_mount:test"
    assert trust["canonical_relative_path"] == "sources/alpha.md"
    assert trust["resolution_state"] == "resolved"
    assert trust["manifest_relative_path"] == "brain-engine/trust.json"
    assert trust["status"] == "approved"
    assert trust["derived_from"] == []
    all_calls = [*first.calls, *second.calls]
    assert all(
        not (
            "UPSERT $note_id" in statement
            and variables.get("note", {}).get("vault_file_id")
        )
        for statement, variables in all_calls
    )
    assert first.receipts_created == 1
    assert second.receipts_created == 0


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)
async def test_changed_trust_hash_updates_record_and_stays_unresolved():
    vault_root = Path(__file__).parent / "fixtures" / "vault" / "trust" / "unresolved"
    root = approve_vault_root(vault_root)
    old_record = {
        "id": "vault_trust_record:existing",
        "manifest_id": "manifest-alpha",
        "content_hash": "7b47b84df5787c002d234d9c5a4bb80c90ca40f44efbb8034a5349c084ebf29c",
    }

    records = {"manifest-alpha": old_record}
    connection = QueryRecorder(trust_records=records)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        approved_roots={"vault_mount:test": root},
    )
    try:
        result = await repository.import_trust_manifest(
            "vault_mount:test", "brain-engine/trust.json"
        )
    finally:
        root.close()

    assert result.changed == 1
    assert result.unresolved == 1
    trust_record = connection.calls[0][1]["trust_0"]
    assert trust_record["resolution_state"] == "unresolved"
    assert trust_record["derived_from"] == ["source-1"]
    assert connection.receipts_created == 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)
async def test_same_trust_hash_transitions_unresolved_to_resolved_with_receipt():
    vault_root = Path(__file__).parent / "fixtures" / "vault" / "trust" / "resolved"
    root = approve_vault_root(vault_root)
    prior = {
        "id": "vault_trust_record:existing",
        "manifest_id": "manifest-alpha",
        "vault_id": "vault_mount:test",
        "canonical_relative_path": "sources/alpha.md",
        "content_hash": (
            "332b38d0775248ac056ecf1bd3c708d96be35d5b1cbc5ed81bb4ab7b7d80d914"
        ),
        "resolution_state": "unresolved",
    }

    records = {"manifest-alpha": prior}
    connection = QueryRecorder(trust_records=records)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(connection),
        approved_roots={"vault_mount:test": root},
    )
    try:
        result = await repository.import_trust_manifest(
            "vault_mount:test", "brain-engine/trust.json"
        )
    finally:
        root.close()

    assert result.changed == 1
    assert result.unchanged == 0
    trust = connection.calls[0][1]["trust_0"]
    assert trust["resolution_state"] == "resolved"
    assert connection.receipts_created == 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)
async def test_trust_record_identity_is_scoped_by_vault_and_manifest_path():
    vault_root = Path(__file__).parent / "fixtures" / "vault" / "trust" / "resolved"
    root = approve_vault_root(vault_root)
    first = QueryRecorder()
    second = QueryRecorder()
    repository = VaultRepository(
        connection_factory=ConnectionSequence(first, second),
        approved_roots={
            "vault_mount:first": root,
            "vault_mount:second": root,
        },
    )
    try:
        await repository.import_trust_manifest(
            "vault_mount:first", "brain-engine/trust.json"
        )
        await repository.import_trust_manifest(
            "vault_mount:second", "brain-engine/trust.json"
        )
    finally:
        root.close()

    first_variables = first.calls[0][1]
    second_variables = second.calls[0][1]
    assert first_variables["trust_id_0"] != second_variables["trust_id_0"]
    assert "vault_id = $vault_id" in first.calls[0][0]
    assert "manifest_relative_path = $manifest_relative_path" in first.calls[0][0]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX descriptor-relative vault access required",
)
async def test_trust_import_rejects_non_connector_json_before_database_access():
    vault_root = Path(__file__).parent / "fixtures" / "vault" / "trust" / "resolved"
    root = approve_vault_root(vault_root)
    repository = VaultRepository(
        connection_factory=ConnectionSequence(),
        approved_roots={"vault_mount:test": root},
    )
    try:
        with pytest.raises(ValueError, match="invalid_trust_manifest_path"):
            await repository.import_trust_manifest(
                "vault_mount:test", "sources/trust.json"
            )
    finally:
        root.close()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"{" + b" " * (1024 * 1024) + b"}", "manifest_too_large"),
        (
            json.dumps(
                {
                    "vaultRoot": "/old/root",
                    "records": [{}] * 1001,
                }
            ).encode(),
            "too_many_records",
        ),
        (
            json.dumps(
                {
                    "vaultRoot": "/old/root",
                    "records": [
                        {
                            "manifestId": "x" * 513,
                            "sourcePath": "/old/root/source.md",
                            "status": "approved",
                            "reviewer": "owner",
                            "reviewedAt": "2026-07-27T00:00:00+00:00",
                            "sourceType": "markdown",
                            "evidenceClass": "source",
                            "contentHash": "a" * 64,
                            "derivedFrom": [],
                        }
                    ],
                }
            ).encode(),
            "manifest_id_too_long",
        ),
        (
            json.dumps(
                {
                    "vaultRoot": "/old/root",
                    "records": [
                        {
                            "manifestId": "alpha",
                            "sourcePath": "/old/root/source.md",
                            "status": "approved",
                            "reviewer": "owner",
                            "reviewedAt": "2026-07-27T00:00:00+00:00",
                            "sourceType": "markdown",
                            "evidenceClass": "source",
                            "contentHash": "a" * 64,
                            "derivedFrom": ["source"] * 257,
                        }
                    ],
                }
            ).encode(),
            "too_many_derived_from",
        ),
    ],
    ids=[
        "manifest-too-large",
        "too-many-records",
        "manifest-id-too-long",
        "too-many-derived-from",
    ],
)
def test_trust_manifest_parser_enforces_explicit_budgets(payload: bytes, code: str):
    with pytest.raises(TrustManifestError) as caught:
        parse_trust_manifest(payload)
    assert caught.value.code == code


def test_trust_manifest_parser_accepts_canonical_connector_documents():
    payload = json.dumps(
        {
            "vaultRoot": "/approved/vault",
            "documents": [
                {
                    "id": "source-alpha",
                    "sourcePath": "/approved/vault/Obsidian Brain/source.md",
                    "approval": {
                        "status": "approved",
                        "reviewer": "owner",
                        "reviewedAt": "2026-07-27T00:00:00+00:00",
                    },
                    "sourceType": "markdown",
                    "evidenceClass": "source",
                    "contentHash": "sha256:" + "a" * 64,
                    "derivedFrom": [],
                }
            ],
        }
    ).encode()

    manifest = parse_trust_manifest(payload)

    assert len(manifest.entries) == 1
    assert manifest.entries[0].manifest_id == "source-alpha"
    assert (
        manifest.entries[0].canonical_relative_path
        == "Obsidian Brain/source.md"
    )
    assert manifest.entries[0].reviewer == "owner"
    assert manifest.entries[0].content_hash == "a" * 64


def test_mark_missing_returns_outcome_before_transaction_commit():
    transaction = VaultRepository.mark_missing.__code__.co_consts
    statement = next(
        value
        for value in transaction
        if isinstance(value, str) and "LET $transitioned" in value
    )
    assert statement.index("RETURN { transitioned: $transitioned };") < statement.index(
        "COMMIT TRANSACTION;"
    )
