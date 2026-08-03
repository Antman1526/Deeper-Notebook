"""Adapter for app-owned Deeper Notebook overlay notes."""

from __future__ import annotations

from datetime import date
from typing import Any

from deeper_notebook.knowledge_engine.adapters.base import (
    _MAX_SOURCE_BYTES,
    KnowledgeAdapter,
    snapshot_from_parsed,
    validate_envelope,
)
from deeper_notebook.knowledge_engine.contracts import KnowledgeSnapshot, SourceEnvelope
from deeper_notebook.vault.parsers import parse_document
from deeper_notebook.vault.parsers.common import decode_source


class OverlayKnowledgeAdapter:
    source_kind = "overlay"

    def project(self, envelope: SourceEnvelope) -> KnowledgeSnapshot:
        validate_envelope(envelope)
        if envelope.source_kind != self.source_kind:
            raise ValueError("overlay adapter source kind mismatch")
        if envelope.authority_kind != "app_owned":
            raise ValueError("overlay adapter authority mismatch")
        if envelope.format_mode != "markdown":
            raise ValueError("overlay adapter format mode mismatch")
        decoded = decode_source(
            envelope.canonical_bytes, max_markdown_bytes=_MAX_SOURCE_BYTES
        )
        body_markdown = decoded.body_markdown
        source_native_id, document_kind, journal_date = _reserved_identity(
            decoded.properties
        )
        parsed = parse_document(
            envelope.relative_locator,
            envelope.canonical_bytes,
            format_mode="markdown",
            max_markdown_bytes=_MAX_SOURCE_BYTES,
        )
        return snapshot_from_parsed(
            envelope,
            parsed,
            source_native_id=source_native_id,
            document_kind=document_kind,
            journal_date=journal_date,
            normalized_body=body_markdown,
        )


def _reserved_identity(properties: dict[str, Any]) -> tuple[str, str, date | None]:
    reserved = properties.get("deeper_notebook")
    if not isinstance(reserved, dict):
        raise ValueError("overlay reserved identity is required")
    source_native_id = reserved.get("id")
    document_kind = reserved.get("kind")
    if (
        not isinstance(source_native_id, str)
        or not source_native_id
        or not isinstance(document_kind, str)
        or document_kind not in {"daily", "note", "template", "unique"}
    ):
        raise ValueError("overlay reserved identity is invalid")
    date_key = reserved.get("date_key")
    if document_kind == "daily":
        if not isinstance(date_key, str):
            raise ValueError("overlay reserved identity is invalid")
        try:
            return source_native_id, document_kind, date.fromisoformat(date_key)
        except ValueError as exc:
            raise ValueError("overlay reserved identity is invalid") from exc
    return source_native_id, document_kind, None
