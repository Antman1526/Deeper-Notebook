from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from deeper_notebook.database.repository import db_connection, repo_query
from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedLink,
    ParsedTask,
)
from deeper_notebook.vault.repository import VaultMount, VaultRepository
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


def _work(content_hash: str = "a" * 64) -> VaultWorkItem:
    return VaultWorkItem(
        vault_id="vault_mount:integration",
        relative_path="Pages/Alpha.md",
        file_kind="markdown",
        protected=False,
        content=b"# Alpha\n- [ ] Task [[Beta]]",
        content_hash=content_hash,
        byte_size=28,
        modified_ns=123,
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
