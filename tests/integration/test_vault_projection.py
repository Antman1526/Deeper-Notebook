from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from deeper_notebook.database.repository import (
    db_connection,
    ensure_record_id,
    repo_query,
)
from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedLink,
    ParsedTask,
)
from deeper_notebook.vault.repository import VaultMount, VaultRepository
from deeper_notebook.vault.security import approve_vault_root
from deeper_notebook.vault.watcher import VaultWorkItem

pytestmark = pytest.mark.integration_surreal

ROOT = Path(__file__).resolve().parents[2]
UP = ROOT / "deeper_notebook/database/migrations/32.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/32_down.surrealql"


async def test_migration_creates_vault_projection_tables(clean_namespace):
    rows = await repo_query("INFO FOR DB;")
    head = rows[0] if isinstance(rows, list) else rows
    tables = head.get("tables") or head.get("tb") or {}

    assert {
        "vault_mount",
        "vault_file",
        "note_block",
        "note_link",
        "knowledge_task",
        "vault_revision",
        "vault_sync_receipt",
        "vault_trust_record",
    }.issubset(tables)


async def test_migration_rejects_watching_on_mixed_parent(clean_namespace):
    with pytest.raises(Exception, match=r"(?i)(assert|watch|mixed)"):
        await repo_query(
            "CREATE vault_mount CONTENT $mount;",
            {
                "mount": {
                    "name": "2nd Brains",
                    "root_path": "/approved/2nd Brains",
                    "format_mode": "mixed",
                    "status": "ready-read-only",
                    "watch_enabled": True,
                    "write_policy": "read-only",
                    "protected_globs": [],
                    "parser_version": "test",
                }
            },
        )


async def test_migration_32_up_down_up_and_reapply_are_safe(clean_namespace):
    await repo_query(DOWN.read_text(encoding="utf-8"))
    info_after_down = await repo_query("INFO FOR DB;")
    down_head = (
        info_after_down[0] if isinstance(info_after_down, list) else info_after_down
    )
    tables_after_down = down_head.get("tables") or {}
    assert "vault_mount" not in tables_after_down
    assert "note" in tables_after_down

    up = UP.read_text(encoding="utf-8")
    await repo_query(up)
    await repo_query(up)
    info_after_up = await repo_query("INFO FOR DB;")
    up_head = info_after_up[0] if isinstance(info_after_up, list) else info_after_up
    tables_after_up = up_head.get("tables") or {}
    assert "vault_mount" in tables_after_up
    assert "note" in tables_after_up


def _mount() -> VaultMount:
    return VaultMount(
        id="vault_mount:integration",
        name="Synthetic integration vault",
        root_path="/synthetic/integration-vault",
        format_mode="obsidian",
        status="ready-read-only",
        watch_enabled=True,
        write_policy="read-only",
        protected_globs=[],
        parser_version="integration",
    )


def _work(
    content_hash: str = "a" * 64,
    *,
    modified_ns: int = 123,
) -> VaultWorkItem:
    return VaultWorkItem(
        vault_id="vault_mount:integration",
        relative_path="Pages/Alpha.md",
        file_kind="markdown",
        protected=False,
        content=b"# Alpha\n- [ ] Task [[Beta]]",
        content_hash=content_hash,
        byte_size=28,
        modified_ns=modified_ns,
    )


def _document(content_hash: str = "a" * 64) -> ParsedDocument:
    markdown = "# Alpha\n- [ ] Task [[Beta]]"
    return ParsedDocument(
        relative_path="Pages/Alpha.md",
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


async def _create_mount() -> None:
    await repo_query(
        "CREATE vault_mount:integration CONTENT $mount;",
        {
            "mount": {
                "schema_version": 1,
                "name": "Synthetic integration vault",
                "root_path": "/synthetic/integration-vault",
                "format_mode": "obsidian",
                "status": "ready-read-only",
                "watch_enabled": True,
                "write_policy": "read-only",
                "protected_globs": [],
                "parser_version": "integration",
            }
        },
    )


async def test_complete_projection_is_atomic_and_record_typed(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    result = await repository.project_document(
        _mount(), _work(), _document(), "integration-project"
    )

    assert result.status == "projected"
    assert len(await repo_query("SELECT * FROM vault_file;")) == 1
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM note_block;")) == 2
    assert len(await repo_query("SELECT * FROM note_link;")) == 1
    assert len(await repo_query("SELECT * FROM knowledge_task;")) == 1
    receipts = await repo_query("SELECT * FROM vault_sync_receipt;")
    assert len(receipts) == 1
    assert receipts[0]["status"] == "success"
    assert receipts[0].get("before_hash") is None
    assert receipts[0]["after_hash"] == "a" * 64


class _InjectFailureConnection:
    def __init__(self, connection) -> None:
        self._connection = connection

    async def query(self, statement, variables=None):
        if "FOR $link IN $links" in statement:
            statement = statement.replace(
                "FOR $link IN $links {",
                "THROW 'integration-injected-failure'; FOR $link IN $links {",
                1,
            )
        return await self._connection.query(statement, variables)


@asynccontextmanager
async def _failure_connection():
    async with db_connection() as connection:
        yield _InjectFailureConnection(connection)


async def test_injected_mid_projection_failure_rolls_back_rows(clean_namespace):
    await _create_mount()
    repository = VaultRepository(
        connection_factory=_failure_connection,
        embedding_submitter=lambda *_args: None,
    )
    with pytest.raises(Exception, match="database query failed"):
        await repository.project_document(
            _mount(), _work(), _document(), "integration-failed"
        )

    assert await repo_query("SELECT * FROM note;") == []
    assert await repo_query("SELECT * FROM note_block;") == []
    assert await repo_query("SELECT * FROM note_link;") == []
    assert await repo_query("SELECT * FROM knowledge_task;") == []
    receipts = await repo_query("SELECT * FROM vault_sync_receipt;")
    assert len(receipts) == 1
    assert receipts[0]["status"] == "failed"


async def test_same_hash_is_idempotent_and_missing_preserves_projection(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    first = await repository.project_document(
        _mount(), _work(), _document(), "integration-first"
    )
    second = await repository.project_document(
        _mount(), _work(), _document(), "integration-unchanged"
    )
    assert first.status == "projected"
    assert second.status == "unchanged"
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM note_block;")) == 2
    receipts = await repo_query("SELECT * FROM vault_sync_receipt;")
    assert len(receipts) == 2
    by_operation = {row["operation_id"]: row for row in receipts}
    unchanged = by_operation["integration-unchanged"]
    assert unchanged["status"] == "unchanged"
    assert unchanged["before_hash"] == "a" * 64
    assert unchanged["after_hash"] == "a" * 64

    await repository.mark_missing(
        "vault_mount:integration",
        "Pages/Alpha.md",
        "integration-missing",
    )
    await repository.mark_missing(
        "vault_mount:integration",
        "Pages/Alpha.md",
        "integration-missing-repeat",
    )
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM note_block;")) == 2
    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    assert file_row["deleted_state"] == "missing"
    assert note_row["external_state"] == "stale"
    assert len(await repo_query("SELECT * FROM vault_sync_receipt;")) == 3


def _single_note_work(
    *,
    vault_id: str,
    relative_path: str,
    title: str,
    content_hash: str,
    modified_ns: int,
) -> VaultWorkItem:
    content = f"# {title}".encode()
    return VaultWorkItem(
        vault_id=vault_id,
        relative_path=relative_path,
        file_kind="markdown",
        protected=False,
        content=content,
        content_hash=content_hash,
        byte_size=len(content),
        modified_ns=modified_ns,
    )


def _single_note_document(
    *,
    relative_path: str,
    title: str,
    content_hash: str,
) -> ParsedDocument:
    markdown = f"# {title}"
    return ParsedDocument(
        relative_path=relative_path,
        source_format="obsidian",
        title=title,
        markdown=markdown,
        content_hash=content_hash,
        newline="none",
        blocks=[
            ParsedBlock(
                parser_id="heading",
                position=0,
                block_kind="heading",
                markdown=markdown,
                plain_text=title,
                source_start=0,
                source_end=len(markdown.encode()),
            )
        ],
    )


async def _create_named_mount(
    *,
    vault_id: str,
    name: str,
    root_path: str,
) -> VaultMount:
    mount = VaultMount(
        id=vault_id,
        name=name,
        root_path=root_path,
        format_mode="obsidian",
        status="ready-read-only",
        watch_enabled=True,
        write_policy="read-only",
        protected_globs=[],
        parser_version="integration",
    )
    data = mount.model_dump(exclude={"id", "parent_vault_id"})
    await repo_query(
        "CREATE $mount_id CONTENT $mount;",
        {"mount_id": ensure_record_id(vault_id), "mount": data},
    )
    return mount


async def test_task_dates_round_trip_as_utc_datetimes(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
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

    await repository.project_document(
        _mount(), _work(), parsed, "integration-task-dates"
    )

    task = (await repo_query("SELECT * FROM knowledge_task;"))[0]
    assert task["scheduled"] == datetime(2026, 7, 28, tzinfo=timezone.utc)
    assert task["due"] == datetime(2026, 7, 29, tzinfo=timezone.utc)
    assert task["completed"] == datetime(2026, 7, 30, tzinfo=timezone.utc)
    for field in ("scheduled", "due", "completed"):
        assert task[field].tzinfo is not None
        assert task[field].utcoffset() == timezone.utc.utcoffset(task[field])


async def test_changed_projection_failure_preserves_prior_projection(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.project_document(
        _mount(), _work("a" * 64, modified_ns=100), _document(), "prior-success"
    )

    failing_repository = VaultRepository(
        connection_factory=_failure_connection,
        embedding_submitter=lambda *_args: None,
    )
    with pytest.raises(Exception, match="database query failed"):
        await failing_repository.project_document(
            _mount(),
            _work("b" * 64, modified_ns=200),
            _document("b" * 64),
            "changed-failure",
        )

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    blocks = await repo_query("SELECT * FROM note_block ORDER BY position;")
    assert file_row["content_hash"] == "a" * 64
    assert file_row["parse_status"] == "parsed"
    assert note_row["source_hash"] == "a" * 64
    assert note_row["content"] == _document().markdown
    assert [row["parser_id"] for row in blocks] == ["heading", "task"]


async def test_late_target_duplicate_ambiguity_and_rename_reconcile_links(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    source = await repository.project_document(
        _mount(),
        _work("a" * 64, modified_ns=100),
        _document(),
        "link-source",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is False
    assert link.get("target_note_id") is None

    beta = await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Beta.md",
            title="  Beta  ",
            content_hash="b" * 64,
            modified_ns=200,
        ),
        _single_note_document(
            relative_path="Pages/Beta.md",
            title="  Beta  ",
            content_hash="b" * 64,
        ),
        "late-beta",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is True
    assert str(link["target_note_id"]) == beta.note_id

    duplicate = await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Fullwidth-Beta.md",
            title="ＢＥＴＡ",
            content_hash="c" * 64,
            modified_ns=300,
        ),
        _single_note_document(
            relative_path="Pages/Fullwidth-Beta.md",
            title="ＢＥＴＡ",
            content_hash="c" * 64,
        ),
        "duplicate-beta",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is False
    assert link.get("target_note_id") is None

    await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Fullwidth-Beta.md",
            title="Gamma",
            content_hash="d" * 64,
            modified_ns=400,
        ),
        _single_note_document(
            relative_path="Pages/Fullwidth-Beta.md",
            title="Gamma",
            content_hash="d" * 64,
        ),
        "rename-duplicate",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is True
    assert str(link["target_note_id"]) == beta.note_id

    await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Beta.md",
            title="Delta",
            content_hash="e" * 64,
            modified_ns=500,
        ),
        _single_note_document(
            relative_path="Pages/Beta.md",
            title="Delta",
            content_hash="e" * 64,
        ),
        "rename-beta",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is False
    assert link.get("target_note_id") is None
    assert source.note_id != duplicate.note_id


async def test_link_reads_and_graph_reject_corrupt_cross_mount_target(clean_namespace):
    first = await _create_named_mount(
        vault_id="vault_mount:integration",
        name="First",
        root_path="/synthetic/first",
    )
    second = await _create_named_mount(
        vault_id="vault_mount:second",
        name="Second",
        root_path="/synthetic/second",
    )
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    source = await repository.project_document(
        first, _work(), _document(), "cross-source"
    )
    target = await repository.project_document(
        second,
        _single_note_work(
            vault_id=second.id,
            relative_path="Beta.md",
            title="Beta",
            content_hash="b" * 64,
            modified_ns=200,
        ),
        _single_note_document(
            relative_path="Beta.md",
            title="Beta",
            content_hash="b" * 64,
        ),
        "cross-target",
    )
    await repo_query(
        "UPDATE note_link SET target_note_id = $target, resolved = true;",
        {"target": ensure_record_id(target.note_id)},
    )

    assert await repository.outgoing_links(first.id, source.note_id) == []
    with pytest.raises(LookupError, match="vault_note_not_found"):
        await repository.backlinks(first.id, target.note_id)
    graph = await repository.graph(first.id, source.note_id, depth=2, limit=10)
    assert [node["id"] for node in graph.nodes] == [source.note_id]
    assert graph.edges == []


class _DelayedOrLostResponseConnection:
    def __init__(
        self,
        connection,
        *,
        delay_modified_ns: int | None = None,
        lose_operation_id: str | None = None,
        query_started: asyncio.Event | None = None,
        query_terminal: asyncio.Event | None = None,
    ) -> None:
        self._connection = connection
        self._delay_modified_ns = delay_modified_ns
        self._lose_operation_id = lose_operation_id
        self._query_started = query_started
        self._query_terminal = query_terminal

    async def query(self, statement, variables=None):
        variables = variables or {}
        if self._query_started is not None and "LET $existing_file" in statement:
            self._query_started.set()
        if (
            self._delay_modified_ns is not None
            and variables.get("observed_modified_ns") == self._delay_modified_ns
        ):
            await asyncio.sleep(0.05)
        try:
            result = await self._connection.query(statement, variables)
            receipt = variables.get("success_receipt") or {}
            if receipt.get("operation_id") == self._lose_operation_id:
                raise ConnectionError("synthetic response lost after commit")
            return result
        finally:
            if self._query_terminal is not None and "LET $existing_file" in statement:
                self._query_terminal.set()


def _ordered_connection_factory(
    *,
    delay_modified_ns: int | None = None,
    lose_operation_id: str | None = None,
    query_started: asyncio.Event | None = None,
    query_terminal: asyncio.Event | None = None,
):
    @asynccontextmanager
    async def factory():
        async with db_connection() as connection:
            yield _DelayedOrLostResponseConnection(
                connection,
                delay_modified_ns=delay_modified_ns,
                lose_operation_id=lose_operation_id,
                query_started=query_started,
                query_terminal=query_terminal,
            )

    return factory


async def test_concurrent_stale_projection_and_lost_response_keep_newest(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(
        connection_factory=_ordered_connection_factory(
            delay_modified_ns=100,
            lose_operation_id="older-lost-response",
        ),
        embedding_submitter=lambda *_args: None,
    )

    older = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("a" * 64, modified_ns=100),
            _document("a" * 64),
            "older-lost-response",
        )
    )
    newer = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("b" * 64, modified_ns=200),
            _document("b" * 64),
            "newer-success",
        )
    )
    older_result, newer_result = await asyncio.gather(older, newer)

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    receipts = await repo_query(
        "SELECT operation_id, status, after_hash FROM vault_sync_receipt;"
    )
    assert file_row["content_hash"] == "b" * 64
    assert file_row["modified_ns"] == 200
    assert note_row["source_hash"] == "b" * 64
    assert newer_result.status == "projected"
    assert older_result.status == "superseded"
    assert {row["status"] for row in receipts} == {"success", "superseded"}


async def test_equal_timestamp_stale_failure_cannot_invalidate_other_hash(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.project_document(
        _mount(),
        _work("b" * 64, modified_ns=200),
        _document("b" * 64),
        "current-success",
    )

    await repository.record_failure(
        _mount().id,
        _work("a" * 64, modified_ns=200),
        "stale-equal-timestamp-failure",
        "parse_failed",
    )

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    receipts = await repo_query(
        "SELECT operation_id, status, error_code FROM vault_sync_receipt;"
    )
    by_operation = {row["operation_id"]: row for row in receipts}
    assert file_row["content_hash"] == "b" * 64
    assert file_row["parse_status"] == "parsed"
    assert file_row["deleted_state"] == "present"
    assert by_operation["stale-equal-timestamp-failure"]["status"] == "superseded"
    assert by_operation["stale-equal-timestamp-failure"]["error_code"] == "parse_failed"


async def test_cancellation_waits_for_native_projection_and_embeds_once(
    clean_namespace,
):
    await _create_mount()
    started = asyncio.Event()
    terminal = asyncio.Event()
    embedding_calls: list[str] = []

    async def embed(_app, _command, payload):
        embedding_calls.append(payload["note_id"])

    repository = VaultRepository(
        connection_factory=_ordered_connection_factory(
            delay_modified_ns=100,
            query_started=started,
            query_terminal=terminal,
        ),
        embedding_submitter=embed,
    )
    projection = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("a" * 64, modified_ns=100),
            _document(),
            "cancel-native",
        )
    )
    await started.wait()
    projection.cancel()
    with pytest.raises(asyncio.CancelledError):
        await projection

    assert terminal.is_set()
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM vault_sync_receipt;")) == 1
    assert len(embedding_calls) == 1


async def test_missing_projection_corrective_missing_round_trip(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.mark_missing(
        _mount().id, "Pages/Alpha.md", "missing-before-projection"
    )
    await repository.project_document(
        _mount(),
        _work("a" * 64, modified_ns=100),
        _document(),
        "projection-after-missing",
    )
    await repository.mark_missing(_mount().id, "Pages/Alpha.md", "corrective-missing")

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    assert file_row["parse_status"] == "missing"
    assert file_row["deleted_state"] == "missing"
    assert note_row["external_state"] == "stale"
    assert len(await repo_query("SELECT * FROM vault_sync_receipt;")) == 3


async def test_multi_record_trust_is_vault_scoped_and_idempotent(
    clean_namespace,
):
    root_path = ROOT / "tests/fixtures/vault/trust/multi-a"
    second_root_path = ROOT / "tests/fixtures/vault/trust/multi-b"
    first = await _create_named_mount(
        vault_id="vault_mount:trust_first",
        name="Trust first",
        root_path=str(root_path),
    )
    second = await _create_named_mount(
        vault_id="vault_mount:trust_second",
        name="Trust second",
        root_path=str(second_root_path),
    )
    approved = approve_vault_root(root_path)
    second_approved = approve_vault_root(second_root_path)
    repository = VaultRepository(
        approved_roots={first.id: approved, second.id: second_approved}
    )
    try:
        first_import = await repository.import_trust_manifest(
            first.id, "brain-engine/trust.json"
        )
        unchanged = await repository.import_trust_manifest(
            first.id, "brain-engine/trust.json"
        )
        second_import = await repository.import_trust_manifest(
            second.id, "brain-engine/trust.json"
        )
    finally:
        approved.close()
        second_approved.close()

    rows = await repo_query(
        "SELECT vault_id, manifest_relative_path, manifest_id, content_hash "
        "FROM vault_trust_record;"
    )
    assert first_import.changed == 2
    assert unchanged.unchanged == 2
    assert second_import.changed == 2
    assert len(rows) == 4
    assert {str(row["vault_id"]) for row in rows} == {first.id, second.id}
