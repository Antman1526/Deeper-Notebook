import socket
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.contracts import (
    SourceEnvelope,
    validate_snapshot_spans,
)
from deeper_notebook.vault.parsers import VaultParseError, parse_document

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge_engine"
NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def envelope(
    name: str,
    source_kind: str,
    authority: str,
    *,
    raw: bytes | None = None,
) -> SourceEnvelope:
    canonical_bytes = raw if raw is not None else (FIXTURES / name).read_bytes()
    return SourceEnvelope(
        space_id=f"knowledge_engine_space:{source_kind}",
        space_display_name=f"{source_kind.title()} Test Space",
        source_ref=f"fixture:{source_kind}",
        authority_kind=authority,
        source_kind=source_kind,
        format_mode="markdown" if source_kind == "overlay" else source_kind,
        relative_locator=f"Pages/{name}",
        canonical_bytes=canonical_bytes,
        byte_size=len(canonical_bytes),
        declared_encoding=None,
        declared_newline=None,
        observed_content_hash=sha256(canonical_bytes).hexdigest(),
        observed_modified_ns=1,
        observed_at=NOW,
        prior_revision=None,
    )


@pytest.mark.parametrize(
    ("fixture", "source_kind", "authority"),
    [
        ("overlay-daily.md", "overlay", "app_owned"),
        ("obsidian-page.md", "obsidian", "external_read_only"),
        ("logseq-journal.md", "logseq", "external_read_only"),
        ("markdown-page.md", "markdown", "external_read_only"),
    ],
)
def test_adapters_are_deterministic_and_authority_preserving(
    fixture: str,
    source_kind: str,
    authority: str,
):
    source = envelope(fixture, source_kind, authority)

    first = adapter_for(source_kind).project(source)
    second = adapter_for(source_kind).project(source)

    assert first == second
    assert first.document.space_id == source.space_id
    assert first.document.authority_kind == authority
    assert first.revision.content_hash == source.observed_content_hash


def test_external_adapters_never_emit_mutation_capabilities():
    snapshot = adapter_for("obsidian").project(
        envelope("obsidian-page.md", "obsidian", "external_read_only")
    )

    assert "edit_body" not in snapshot.document.capabilities
    assert "toggle_task" not in snapshot.tasks[0].capabilities


def test_obsidian_embed_projects_an_asset_reference():
    snapshot = adapter_for("obsidian").project(
        envelope("obsidian-page.md", "obsidian", "external_read_only")
    )

    assert [asset.relative_locator for asset in snapshot.assets] == ["diagram.png"]
    assert snapshot.assets[0].availability == "referenced"


def test_tag_relations_never_invent_target_documents():
    snapshot = adapter_for("obsidian").project(
        envelope("obsidian-page.md", "obsidian", "external_read_only")
    )
    tag_relations = [
        relation for relation in snapshot.relations if relation.relation_kind == "tag"
    ]

    assert [(relation.target_text, relation.target_document_id, relation.resolved) for relation in tag_relations] == [
        ("research", None, False)
    ]


def test_overlay_adapter_preserves_reserved_identity_and_body():
    snapshot = adapter_for("overlay").project(
        envelope("overlay-daily.md", "overlay", "app_owned")
    )

    assert snapshot.document.source_native_id == "overlay_note:daily-2026-07-30"
    assert snapshot.document.journal_date is not None
    assert snapshot.document.journal_date.isoformat() == "2026-07-30"
    assert snapshot.document.normalized_body.startswith("# 2026-07-30")
    assert "deeper_notebook:" not in snapshot.document.normalized_body


def test_logseq_adapter_normalizes_tasks_without_erasing_raw_state():
    snapshot = adapter_for("logseq").project(
        envelope("logseq-journal.md", "logseq", "external_read_only")
    )

    assert [task.normalized_status for task in snapshot.tasks] == ["open", "done"]
    assert snapshot.tasks[0].raw_status == "TODO"


def test_adapter_preserves_parser_byte_spans():
    source = envelope("obsidian-page.md", "obsidian", "external_read_only")
    parsed = parse_document(
        source.relative_locator, source.canonical_bytes, format_mode="obsidian"
    )
    snapshot = adapter_for("obsidian").project(source)

    assert [
        (block.source_start, block.source_end) for block in snapshot.blocks
    ] == [(block.source_start, block.source_end) for block in parsed.blocks]
    validate_snapshot_spans(snapshot, source_size=source.byte_size)


def test_content_hash_mismatch_rejects_envelope_before_projection():
    source = envelope("markdown-page.md", "markdown", "external_read_only")
    invalid = SourceEnvelope.model_construct(
        **(source.model_dump() | {"observed_content_hash": "0" * 64})
    )

    with pytest.raises(ValueError, match="content hash"):
        adapter_for("markdown").project(invalid)


def test_external_source_declared_app_owned_is_rejected():
    source = envelope("obsidian-page.md", "obsidian", "app_owned")

    with pytest.raises(ValueError, match="authority"):
        adapter_for("obsidian").project(source)


def test_overlay_without_reserved_identity_is_rejected():
    source = envelope(
        "overlay-daily.md",
        "overlay",
        "app_owned",
        raw=b"---\ntitle: Untitled\n---\n# Untitled\n",
    )

    with pytest.raises(ValueError, match="reserved"):
        adapter_for("overlay").project(source)


def test_absolute_targets_remain_unresolved_text():
    source = envelope(
        "markdown-page.md",
        "markdown",
        "external_read_only",
        raw=b"# Portable\n\n[private](/Users/Antman/Private.md)\n",
    )
    snapshot = adapter_for("markdown").project(source)

    assert snapshot.relations[0].target_text == "/Users/Antman/Private.md"
    assert snapshot.relations[0].target_document_id is None
    assert snapshot.relations[0].resolved is False
    assert snapshot.assets == []


def test_malformed_frontmatter_exposes_only_stable_parser_code():
    source = envelope(
        "obsidian-page.md",
        "obsidian",
        "external_read_only",
        raw=b"---\ntitle: [broken\n---\n# Broken\n",
    )

    with pytest.raises(VaultParseError) as raised:
        adapter_for("obsidian").project(source)

    assert raised.value.code == "invalid_frontmatter"


def test_adapters_project_only_supplied_bytes(monkeypatch: pytest.MonkeyPatch):
    source = envelope("markdown-page.md", "markdown", "external_read_only")

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("projection must not access host services")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    snapshot = adapter_for("markdown").project(source)

    assert snapshot.document.title == "Portable Page"


def test_adapter_selector_rejects_unknown_source_kind():
    with pytest.raises(ValueError, match="unsupported knowledge source kind"):
        adapter_for("unsupported")  # type: ignore[arg-type]


def test_source_envelope_rejects_mismatched_hash_at_construction():
    raw = b"# Safe\n"

    with pytest.raises(ValidationError, match="observed_content_hash"):
        SourceEnvelope(
            **(
                envelope("markdown-page.md", "markdown", "external_read_only")
                .model_dump()
                | {
                    "canonical_bytes": raw,
                    "byte_size": len(raw),
                    "observed_content_hash": "0" * 64,
                }
            )
        )
