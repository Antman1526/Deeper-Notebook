from datetime import datetime, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import (
    BackfillCheckpoint,
    KnowledgeAsset,
    KnowledgeBlock,
    KnowledgeDocument,
    KnowledgeSnapshot,
    KnowledgeSpace,
    KnowledgeTask,
    KnowledgeView,
    ProjectionReceipt,
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


def test_external_models_reject_injected_mutation_capabilities():
    injected = ["read", "copy_content", "bookmark", "cite", "edit_body"]
    task_injected = ["read", "copy_content", "bookmark", "cite", "toggle_task"]

    with pytest.raises(ValidationError, match="server-derived capabilities"):
        _external_space(capabilities=injected)
    with pytest.raises(ValidationError, match="server-derived capabilities"):
        _external_document(capabilities=injected)
    with pytest.raises(ValidationError, match="server-derived capabilities"):
        KnowledgeSnapshot(
            space=_external_space(),
            document=_external_document(),
            revision=_external_revision(),
            blocks=[_external_block(capabilities=injected)],
        )
    with pytest.raises(ValidationError, match="server-derived capabilities"):
        KnowledgeSnapshot(
            space=_external_space(),
            document=_external_document(),
            revision=_external_revision(),
            tasks=[_external_task(capabilities=task_injected)],
        )
    with pytest.raises(ValidationError, match="server-derived capabilities"):
        KnowledgeSnapshot(
            space=_external_space(),
            document=_external_document(),
            revision=_external_revision(),
            assets=[_external_asset(capabilities=injected)],
        )
    with pytest.raises(ValidationError, match="server-derived capabilities"):
        KnowledgeView(
            id="knowledge_engine_view:external",
            space_id="knowledge_engine_space:external",
            view_kind="document",
            name="External",
            revision=1,
            target_ids=["knowledge_engine_document:external"],
            definition={},
            view_state={"kind": "document", "mode": "reading"},
            capabilities=injected,
            created_at=NOW,
            updated_at=NOW,
        )


def test_optional_contract_fields_accept_explicit_null():
    asset = KnowledgeAsset(
        id="knowledge_engine_asset:nullable",
        space_id="knowledge_engine_space:external",
        source_document_id="knowledge_engine_document:external",
        relative_locator="diagram.png",
        media_kind="image",
        content_hash=None,
        byte_size=None,
        availability="referenced",
        metadata={},
        provenance="obsidian",
        source_revision_id="knowledge_engine_revision:external",
    )
    receipt = ProjectionReceipt(
        operation_id="project:one",
        space_id="knowledge_engine_space:external",
        document_id="knowledge_engine_document:external",
        source_revision_id="knowledge_engine_revision:external",
        relative_locator="Pages/External.md",
        input_hash="b" * 64,
        output_hash=None,
        adapter_version="knowledge-adapter-v1",
        schema_version=1,
        status="failed",
        error_code="knowledge_adapter_invalid",
        started_at=NOW,
        completed_at=NOW,
    )
    checkpoint = BackfillCheckpoint(
        space_id="knowledge_engine_space:external",
        last_relative_locator=None,
        last_source_hash=None,
        status="pending",
        projected=0,
        unchanged=0,
        failed=0,
        updated_at=NOW,
    )

    assert asset.content_hash is None
    assert receipt.output_hash is None
    assert checkpoint.last_relative_locator is None
    assert checkpoint.last_source_hash is None


def test_projection_digest_normalizes_redacted_membership_order() -> None:
    from deeper_notebook.knowledge_engine.contracts import ProjectionDigest

    digest = ProjectionDigest(
        space_id="knowledge_engine_space:test",
        document_count=0,
        block_count=0,
        relation_count=0,
        task_count=0,
        asset_count=0,
        property_count=0,
        tag_count=0,
        document_hashes={"Pages/B.md": "b" * 64, "Pages/A.md": "a" * 64},
        outgoing_membership={"Pages/B.md": ["Pages/C.md", "Pages/A.md"]},
        backlink_membership={"Pages/B.md": ["Pages/C.md", "Pages/A.md"]},
        overlay_revision_mappings={
            "overlay_note:b": "knowledge_engine_revision:b"
        },
    )

    assert list(digest.document_hashes) == ["Pages/A.md", "Pages/B.md"]
    assert digest.outgoing_membership == {"Pages/B.md": ["Pages/A.md", "Pages/C.md"]}
    assert digest.backlink_membership == {"Pages/B.md": ["Pages/A.md", "Pages/C.md"]}


@pytest.mark.parametrize("field", ["outgoing_membership", "backlink_membership"])
@pytest.mark.parametrize("locator", ["/Users/Antman/private.md", "../private.md", "Pages\\private.md"])
def test_projection_digest_rejects_noncanonical_membership_keys(
    field: str, locator: str
) -> None:
    from deeper_notebook.knowledge_engine.contracts import ProjectionDigest

    with pytest.raises(ValidationError):
        ProjectionDigest(
            space_id="knowledge_engine_space:test",
            document_count=0,
            block_count=0,
            relation_count=0,
            task_count=0,
            asset_count=0,
            **{field: {locator: ["Pages/Member.md"]}},
        )


def test_projection_digest_requires_sha256_exact_search_membership_keys() -> None:
    from deeper_notebook.knowledge_engine.contracts import ProjectionDigest

    with pytest.raises(ValidationError):
        ProjectionDigest(
            space_id="knowledge_engine_space:test",
            document_count=0,
            block_count=0,
            relation_count=0,
            task_count=0,
            asset_count=0,
            exact_search_membership={"research": ["Pages/Member.md"]},
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity_pairs", {"note:/Users/Antman/private": "knowledge_engine_document:one"}),
        ("overlay_revision_mappings", {"overlay_note:one": "C:\\secrets"}),
        ("graph_edges", ["note:one->note:/Users/Antman/private:wikilink"]),
    ],
)
def test_projection_digest_rejects_absolute_or_token_like_redacted_fields(
    field: str, value: object
) -> None:
    from deeper_notebook.knowledge_engine.contracts import ProjectionDigest

    with pytest.raises(ValidationError):
        ProjectionDigest(
            space_id="knowledge_engine_space:test",
            document_count=0,
            block_count=0,
            relation_count=0,
            task_count=0,
            asset_count=0,
            **{field: value},
        )


@pytest.mark.parametrize("value", ["/Users/Antman/secret", "test-only-token"])
def test_equivalence_difference_cannot_retain_paths_or_tokens(value: str) -> None:
    from deeper_notebook.knowledge_engine.contracts import EquivalenceDifference

    with pytest.raises(ValidationError):
        EquivalenceDifference(
            code="document_hash_mismatch",
            legacy_value=value,
            unified_value="a" * 64,
        )


@pytest.mark.parametrize(
    ("view_kind", "target_ids", "view_state"),
    [
        ("document", ["knowledge_engine_document:one"], {"kind": "graph", "depth": 1}),
        ("document", ["knowledge_engine_document:one"], {"kind": "document", "absolute_path": "/Users/Antman/private.md"}),
        ("document", ["knowledge_engine_document:one"], {"kind": "document", "canonical_bytes": b"secret"}),
        ("collection", ["knowledge_engine_document:one"], {"kind": "collection"}),
    ],
)
def test_view_state_is_typed_and_matches_its_view_kind(
    view_kind: str,
    target_ids: list[str],
    view_state: dict[str, object],
):
    with pytest.raises(ValidationError):
        KnowledgeView(
            id="knowledge_engine_view:typed",
            space_id="knowledge_engine_space:external",
            view_kind=view_kind,
            name="Typed",
            revision=1,
            target_ids=target_ids,
            definition={},
            view_state=view_state,
            capabilities=sorted(capabilities_for("external_read_only", "document")),
            created_at=NOW,
            updated_at=NOW,
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
        capabilities=sorted(capabilities_for("app_owned", "space")),
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
        capabilities=sorted(capabilities_for("app_owned", "note")),
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


def _external_space(*, capabilities: list[str] | None = None) -> KnowledgeSpace:
    return KnowledgeSpace(
        id="knowledge_engine_space:external",
        display_name="External",
        authority_kind="external_read_only",
        source_kind="obsidian",
        format_mode="obsidian",
        source_ref="vault_mount:external",
        availability_state="available",
        projection_state="ready",
        adapter_version="knowledge-adapter-v1",
        parser_version="vault-parser-v1",
        policy_version=1,
        capabilities=capabilities
        or sorted(capabilities_for("external_read_only", "space")),
        created_at=NOW,
        updated_at=NOW,
    )


def _external_document(
    *, capabilities: list[str] | None = None
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id="knowledge_engine_document:external",
        space_id="knowledge_engine_space:external",
        source_native_id="vault_file:external",
        authority_kind="external_read_only",
        relative_locator="Pages/External.md",
        document_kind="note",
        title="External",
        normalized_body="# External\n",
        properties={},
        tags=[],
        content_hash="b" * 64,
        source_revision_id="knowledge_engine_revision:external",
        provenance="obsidian",
        availability="available",
        parse_state="ready",
        journal_date=None,
        capabilities=capabilities
        or sorted(capabilities_for("external_read_only", "note")),
        created_at=NOW,
        observed_at=NOW,
        updated_at=NOW,
    )


def _external_revision() -> SourceRevision:
    return SourceRevision(
        id="knowledge_engine_revision:external",
        space_id="knowledge_engine_space:external",
        document_id="knowledge_engine_document:external",
        content_hash="b" * 64,
        byte_size=11,
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


def _external_task(*, capabilities: list[str]) -> KnowledgeTask:
    return KnowledgeTask(
        id="knowledge_engine_task:external",
        space_id="knowledge_engine_space:external",
        document_id="knowledge_engine_document:external",
        block_id=None,
        raw_status="TODO",
        normalized_status="open",
        scheduled=None,
        due=None,
        completed=None,
        priority=None,
        recurrence=None,
        tags=[],
        properties={},
        source_start=0,
        source_end=1,
        source_revision_id="knowledge_engine_revision:external",
        capabilities=capabilities,
    )


def _external_block(*, capabilities: list[str]) -> KnowledgeBlock:
    return KnowledgeBlock(
        id="knowledge_engine_block:external",
        space_id="knowledge_engine_space:external",
        document_id="knowledge_engine_document:external",
        parent_block_id=None,
        position=0,
        source_key="block:external",
        block_kind="paragraph",
        markdown="External",
        plain_text="External",
        properties={},
        raw_task_state=None,
        normalized_task_state=None,
        heading_path=[],
        source_start=0,
        source_end=8,
        source_revision_id="knowledge_engine_revision:external",
        capabilities=capabilities,
    )


def _external_asset(*, capabilities: list[str]) -> KnowledgeAsset:
    return KnowledgeAsset(
        id="knowledge_engine_asset:external",
        space_id="knowledge_engine_space:external",
        source_document_id="knowledge_engine_document:external",
        relative_locator="diagram.png",
        media_kind="image",
        content_hash=None,
        byte_size=None,
        availability="referenced",
        metadata={},
        provenance="obsidian",
        source_revision_id="knowledge_engine_revision:external",
        capabilities=capabilities,
    )
