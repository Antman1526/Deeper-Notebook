from datetime import datetime, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import (
    KnowledgeDocument,
    KnowledgeSnapshot,
    KnowledgeSpace,
    SourceEnvelope,
    SourceRevision,
)
from deeper_notebook.knowledge_engine.identity import engine_record_id

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def test_external_space_never_derives_mutation_capabilities():
    capabilities = capabilities_for("external_read_only", "note")

    assert capabilities == frozenset({"read", "copy_content", "bookmark", "cite"})
    assert "edit_body" not in capabilities
    assert "toggle_task" not in capabilities


def test_overlay_note_derives_app_owned_capabilities():
    capabilities = capabilities_for("app_owned", "note")

    assert {"read", "edit_body", "merge", "archive", "cite"} <= capabilities


def test_source_envelope_rejects_absolute_or_escaping_locator():
    for locator in ("/Users/Antman/private.md", "../private.md", "C:/private.md"):
        with pytest.raises(ValidationError):
            SourceEnvelope(
                space_id="knowledge_engine_space:external",
                space_display_name="External",
                source_ref="vault_mount:external",
                authority_kind="external_read_only",
                source_kind="obsidian",
                format_mode="obsidian",
                relative_locator=locator,
                canonical_bytes=b"# Safe\n",
                byte_size=7,
                declared_encoding="utf-8",
                declared_newline="lf",
                observed_content_hash="ae0158884831f39dc9f97511377720ffd4923e8551919e54e5f943ad79b2ce4f",
                observed_modified_ns=1,
                observed_at=NOW,
                prior_revision=None,
            )


def test_engine_ids_are_deterministic_and_authority_scoped():
    first = engine_record_id("document", "knowledge_space:a", "Pages/Test.md")
    second = engine_record_id("document", "knowledge_space:a", "Pages/Test.md")
    other = engine_record_id("document", "knowledge_space:b", "Pages/Test.md")

    assert first == second
    assert first != other
    assert first.startswith("knowledge_engine_document:")


def test_domain_models_forbid_unknown_fields():
    with pytest.raises(ValidationError, match="Extra inputs"):
        KnowledgeSpace(
            id="knowledge_engine_space:test",
            display_name="Test",
            authority_kind="app_owned",
            source_kind="overlay",
            format_mode="markdown",
            source_ref="overlay_space:default",
            availability_state="available",
            projection_state="ready",
            adapter_version="knowledge-adapter-v1",
            parser_version="vault-parser-v1",
            policy_version=1,
            capabilities=["read"],
            created_at=NOW,
            updated_at=NOW,
            secret="must fail",
        )


def test_source_envelope_requires_exact_bytes_and_hash():
    raw = b"# Safe\n"
    fields = _source_envelope_fields(raw)

    with pytest.raises(ValidationError, match="byte_size"):
        SourceEnvelope(**(fields | {"byte_size": len(raw) - 1}))
    with pytest.raises(ValidationError, match="observed_content_hash"):
        SourceEnvelope(**(fields | {"observed_content_hash": "a" * 64}))


def test_snapshot_rejects_child_from_another_revision():
    revision = _revision()

    with pytest.raises(ValidationError, match="source_revision_id"):
        KnowledgeSnapshot(
            space=_space(),
            document=_document(),
            revision=revision,
            identity_claims=[
                {
                    "legacy_kind": "note",
                    "legacy_id": "note:one",
                    "engine_kind": "document",
                    "engine_id": "knowledge_engine_document:one",
                    "source_revision_id": "knowledge_engine_revision:other",
                    "claim_hash": "a" * 64,
                }
            ],
        )


def _source_envelope_fields(raw: bytes) -> dict[str, object]:
    return {
        "space_id": "knowledge_engine_space:external",
        "space_display_name": "External",
        "source_ref": "vault_mount:external",
        "authority_kind": "external_read_only",
        "source_kind": "obsidian",
        "format_mode": "obsidian",
        "relative_locator": "Pages/Safe.md",
        "canonical_bytes": raw,
        "byte_size": len(raw),
        "declared_encoding": "utf-8",
        "declared_newline": "lf",
        "observed_content_hash": sha256(raw).hexdigest(),
        "observed_modified_ns": 1,
        "observed_at": NOW,
        "prior_revision": None,
    }


def _space() -> KnowledgeSpace:
    return KnowledgeSpace(
        id="knowledge_engine_space:test",
        display_name="Test",
        authority_kind="app_owned",
        source_kind="overlay",
        format_mode="markdown",
        source_ref="overlay_space:default",
        availability_state="available",
        projection_state="ready",
        adapter_version="knowledge-adapter-v1",
        parser_version="vault-parser-v1",
        policy_version=1,
        capabilities=["read"],
        created_at=NOW,
        updated_at=NOW,
    )


def _document() -> KnowledgeDocument:
    return KnowledgeDocument(
        id="knowledge_engine_document:test",
        space_id="knowledge_engine_space:test",
        source_native_id="overlay_note:test",
        authority_kind="app_owned",
        relative_locator="Pages/Test.md",
        document_kind="note",
        title="Test",
        normalized_body="# Test\n",
        properties={},
        tags=[],
        content_hash="a" * 64,
        source_revision_id="knowledge_engine_revision:test",
        provenance="overlay",
        availability="available",
        parse_state="ready",
        journal_date=None,
        capabilities=["read"],
        created_at=NOW,
        observed_at=NOW,
        updated_at=NOW,
    )


def _revision() -> SourceRevision:
    return SourceRevision(
        id="knowledge_engine_revision:test",
        space_id="knowledge_engine_space:test",
        document_id="knowledge_engine_document:test",
        content_hash="a" * 64,
        byte_size=7,
        encoding="utf-8",
        newline="lf",
        observed_modified_ns=1,
        adapter_version="knowledge-adapter-v1",
        parser_version="vault-parser-v1",
        parse_status="ready",
        diagnostics=[],
        observed_at=NOW,
        created_at=NOW,
    )
