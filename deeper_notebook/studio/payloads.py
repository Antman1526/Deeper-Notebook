"""Backward-compatible persistence helpers for Studio artifact output."""

from __future__ import annotations

from typing import Any

from deeper_notebook.exceptions import InvalidInputError
from deeper_notebook.studio.schemas import (
    ArtifactDocumentBase,
    parse_artifact_document,
)

CURRENT_SCHEMA_VERSION = 1


def artifact_markdown(payload: dict[str, Any] | None) -> str:
    """Return canonical markdown while preserving legacy content-only payloads."""
    if not payload:
        return ""

    markdown = payload.get("markdown")
    if isinstance(markdown, str) and markdown:
        return markdown

    content = payload.get("content")
    return content if isinstance(content, str) else ""


def build_structured_payload(
    document: ArtifactDocumentBase,
    markdown: str,
    *,
    validation: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the v1 envelope without discarding artifact-specific metadata."""
    payload = dict(extras or {})
    payload.update(
        {
            "schema_version": document.schema_version,
            "document": document.model_dump(mode="json"),
            "markdown": markdown,
            # Older clients and exports read this key directly.
            "content": markdown,
            "validation": validation
            or {
                "status": "valid",
                "errors": [],
            },
        }
    )
    return payload


def parse_payload_document(
    artifact_type: str,
    payload: dict[str, Any] | None,
) -> ArtifactDocumentBase | None:
    """Parse v1 output or return None when the artifact predates schemas."""
    if not payload or "schema_version" not in payload:
        return None

    schema_version = payload.get("schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise InvalidInputError(
            f"Unsupported artifact schema version: {schema_version!r}"
        )

    document = payload.get("document")
    if not isinstance(document, dict):
        raise InvalidInputError("Structured artifact payload is missing document")

    return parse_artifact_document(artifact_type, document)
