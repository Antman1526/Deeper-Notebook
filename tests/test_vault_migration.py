from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedEmbed,
    ParsedLink,
)

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/32.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/32_down.surrealql"
UPGRADE = ROOT / "deeper_notebook/database/migrations/33.surrealql"
UPGRADE_DOWN = ROOT / "deeper_notebook/database/migrations/33_down.surrealql"
NEWLINE_UP = ROOT / "deeper_notebook/database/migrations/35.surrealql"
NEWLINE_DOWN = ROOT / "deeper_notebook/database/migrations/35_down.surrealql"

VAULT_TABLES = (
    "vault_mount",
    "vault_file",
    "note_block",
    "note_link",
    "knowledge_task",
    "vault_revision",
    "vault_sync_receipt",
    "vault_trust_record",
)

NOTE_FIELDS = (
    "vault_id",
    "vault_file_id",
    "source_format",
    "canonical_external",
    "properties",
    "tags",
    "source_hash",
    "external_state",
)

REQUIRED_INDEXES = (
    "idx_vault_mount_root",
    "idx_vault_file_path",
    "idx_note_vault_file",
    "idx_note_block_parser",
    "idx_note_link_span",
    "idx_task_block",
    "idx_vault_receipt_operation",
    "idx_vault_trust_manifest",
)

TRUST_FIELDS = (
    "vault_id ON TABLE vault_trust_record TYPE option<record<vault_mount>>",
    "canonical_relative_path ON TABLE vault_trust_record TYPE option<string>",
    "manifest_relative_path ON TABLE vault_trust_record TYPE string",
)


def test_vault_migration_is_present_schemafull_and_idempotent():
    sql = UP.read_text(encoding="utf-8")

    for table in VAULT_TABLES:
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    for field in NOTE_FIELDS:
        assert f"DEFINE FIELD IF NOT EXISTS {field} ON TABLE note" in sql
    for index in REQUIRED_INDEXES:
        assert f"DEFINE INDEX IF NOT EXISTS {index}" in sql

    defines = [
        line.strip()
        for line in sql.splitlines()
        if line.strip().upper().startswith("DEFINE ")
    ]
    assert defines
    assert all("IF NOT EXISTS" in line.upper() for line in defines)
    for table in VAULT_TABLES:
        assert f"schema_version ON TABLE {table}" in sql


def test_vault_migration_pins_read_only_state_semantics():
    sql = UP.read_text(encoding="utf-8")

    assert (
        "parent_vault_id ON TABLE vault_mount TYPE option<record<vault_mount>>" in sql
    )
    assert "watch_enabled ON TABLE vault_mount TYPE bool DEFAULT false" in sql
    assert '$this.format_mode != "mixed" OR $value = false' in sql
    assert (
        'deleted_state ON TABLE vault_file TYPE string DEFAULT "present" '
        'ASSERT $value IN ["present", "missing"]'
    ) in sql
    assert (
        'status ON TABLE vault_trust_record TYPE string DEFAULT "approved" '
        'ASSERT $value = "approved"'
    ) in sql
    assert (
        'resolution_state ON TABLE vault_trust_record TYPE string DEFAULT "unresolved" '
        'ASSERT $value IN ["resolved", "unresolved"]'
    ) in sql
    for field in TRUST_FIELDS:
        assert f"DEFINE FIELD IF NOT EXISTS {field};" in sql


def test_vault_down_migration_removes_only_vault_schema():
    sql = DOWN.read_text(encoding="utf-8")

    for table in VAULT_TABLES:
        assert f"REMOVE TABLE IF EXISTS {table};" in sql
    assert "REMOVE TABLE IF EXISTS note;" not in sql
    for field in NOTE_FIELDS:
        assert f"REMOVE FIELD IF EXISTS {field} ON TABLE note;" in sql
    assert "REMOVE TABLE IF EXISTS vault_trust_record;" in sql


def test_migration_33_repairs_already_recorded_v32_schema_idempotently():
    sql = UPGRADE.read_text(encoding="utf-8")

    assert "DEFINE FIELD IF NOT EXISTS title_key ON TABLE note" in sql
    assert "DEFINE FIELD IF NOT EXISTS target_title_key ON TABLE note_link" in sql
    assert "DEFINE INDEX IF NOT EXISTS idx_note_vault_title_key" in sql
    assert "REMOVE INDEX IF EXISTS idx_vault_trust_manifest" in sql
    assert "COLUMNS vault_id, manifest_relative_path, manifest_id UNIQUE" in sql
    preserving_defines = {
        "DEFINE FIELD OVERWRITE updated ON note DEFAULT time::now() "
        "VALUE $before OR time::now();",
        "DEFINE FIELD OVERWRITE updated ON TABLE note_link TYPE datetime "
        "DEFAULT time::now() VALUE $before OR time::now();",
    }
    assert preserving_defines.issubset(set(sql.splitlines()))
    defines = [
        line.strip()
        for line in sql.splitlines()
        if line.strip().upper().startswith("DEFINE ")
        and line.strip() not in preserving_defines
    ]
    assert defines
    assert all("IF NOT EXISTS" in statement.upper() for statement in defines)


def test_migration_33_down_is_discoverable_and_non_destructive():
    sql = UPGRADE_DOWN.read_text(encoding="utf-8")

    assert sql.strip()
    assert "REMOVE FIELD" not in sql
    assert "REMOVE TABLE" not in sql


def test_migration_35_adds_optional_vault_file_newline_metadata():
    sql = NEWLINE_UP.read_text(encoding="utf-8")
    assert (
        "DEFINE FIELD IF NOT EXISTS newline ON TABLE vault_file "
        "TYPE option<string> ASSERT $value = NONE OR $value IN "
        '["lf", "crlf", "mixed", "none"];'
    ) in sql


def test_migration_35_down_removes_only_vault_file_newline_metadata():
    sql = NEWLINE_DOWN.read_text(encoding="utf-8")
    assert sql.strip() == "REMOVE FIELD IF EXISTS newline ON TABLE vault_file;"


def _document(**updates) -> ParsedDocument:
    data = {
        "relative_path": "Pages/Café.md",
        "source_format": "obsidian",
        "title": "Café",
        "markdown": "éx",
        "content_hash": "a" * 64,
        "newline": "none",
    }
    data.update(updates)
    return ParsedDocument(**data)


def test_contracts_forbid_unknown_fields_and_coercion():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _document(unknown=True)

    with pytest.raises(ValidationError):
        ParsedBlock(
            parser_id="block-1",
            position="0",
            block_kind="paragraph",
            markdown="é",
            plain_text="é",
            source_start=0,
            source_end=2,
        )


@pytest.mark.parametrize(
    "span_model, kwargs",
    [
        (
            ParsedBlock,
            {
                "parser_id": "block-1",
                "position": 0,
                "block_kind": "paragraph",
                "markdown": "x",
                "plain_text": "x",
            },
        ),
        (
            ParsedLink,
            {
                "target_text": "Page",
                "link_kind": "wikilink",
            },
        ),
        (
            ParsedEmbed,
            {
                "target_text": "image.png",
            },
        ),
    ],
)
def test_span_contracts_reject_reversed_byte_ranges(span_model, kwargs):
    with pytest.raises(ValidationError, match="source_end"):
        span_model(**kwargs, source_start=3, source_end=2)


def test_document_validates_zero_based_utf8_byte_spans():
    block = ParsedBlock(
        parser_id="block-1",
        position=0,
        block_kind="paragraph",
        markdown="é",
        plain_text="é",
        source_start=0,
        source_end=2,
    )
    link = ParsedLink(
        target_text="x",
        link_kind="wikilink",
        source_start=2,
        source_end=3,
    )

    document = _document(blocks=[block], links=[link])
    assert document.blocks[0].source_end == len("é".encode("utf-8"))

    with pytest.raises(ValidationError, match="outside the original file bytes"):
        _document(
            embeds=[
                ParsedEmbed(
                    target_text="image.png",
                    source_start=2,
                    source_end=4,
                )
            ]
        )
