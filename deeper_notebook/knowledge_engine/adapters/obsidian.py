"""Adapter for read-only Obsidian Markdown sources."""

from __future__ import annotations

from deeper_notebook.knowledge_engine.adapters.base import (
    _MAX_SOURCE_BYTES,
    KnowledgeAdapter,
    snapshot_from_parsed,
    validate_envelope,
)
from deeper_notebook.knowledge_engine.contracts import KnowledgeSnapshot, SourceEnvelope
from deeper_notebook.vault.parsers import parse_document


class ObsidianKnowledgeAdapter:
    source_kind = "obsidian"

    def project(self, envelope: SourceEnvelope) -> KnowledgeSnapshot:
        validate_envelope(envelope)
        if envelope.source_kind != self.source_kind:
            raise ValueError("obsidian adapter source kind mismatch")
        if envelope.authority_kind != "external_read_only":
            raise ValueError("obsidian adapter authority mismatch")
        if envelope.format_mode not in {self.source_kind, "mixed"}:
            raise ValueError("obsidian adapter format mode mismatch")
        parsed = parse_document(
            envelope.relative_locator,
            envelope.canonical_bytes,
            format_mode="obsidian",
            max_markdown_bytes=_MAX_SOURCE_BYTES,
        )
        return snapshot_from_parsed(
            envelope,
            parsed,
            source_native_id=f"obsidian:{envelope.relative_locator}",
            document_kind="note",
            journal_date=None,
        )
