from __future__ import annotations

import pytest

from deeper_notebook.database.repository import repo_query

pytestmark = pytest.mark.integration_surreal


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
