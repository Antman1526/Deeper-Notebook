"""Pure normalization from safe vault parser output to knowledge snapshots."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Protocol

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import (
    KnowledgeAsset,
    KnowledgeBlock,
    KnowledgeDocument,
    KnowledgeIdentityClaim,
    KnowledgeRelation,
    KnowledgeSnapshot,
    KnowledgeSpace,
    KnowledgeTask,
    SourceEnvelope,
    SourceKind,
    SourceRevision,
    TaskState,
    validate_snapshot_spans,
)
from deeper_notebook.knowledge_engine.identity import (
    canonical_locator,
    engine_record_id,
)
from deeper_notebook.vault.contracts import ParsedDocument, ParsedEmbed, ParsedLink

ADAPTER_VERSION = "knowledge-adapter-v1"
PARSER_VERSION = "vault-parser-v1"
_MAX_SOURCE_BYTES = 100 * 1024 * 1024
_LOGSEQ_RAW_STATUS = re.compile(
    r"^[ \t]*[-*+][ \t]+(TODO|DOING|DONE|CANCELED|CANCELLED|NOW|LATER|WAITING)\b"
)
_ATTACHMENT_KINDS = {
    ".aac": "audio",
    ".avi": "video",
    ".bmp": "image",
    ".csv": "document",
    ".doc": "document",
    ".docx": "document",
    ".epub": "document",
    ".gif": "image",
    ".jpeg": "image",
    ".jpg": "image",
    ".m4a": "audio",
    ".mkv": "video",
    ".mov": "video",
    ".mp3": "audio",
    ".mp4": "video",
    ".ogg": "audio",
    ".pdf": "document",
    ".png": "image",
    ".ppt": "document",
    ".pptx": "document",
    ".svg": "image",
    ".tiff": "image",
    ".wav": "audio",
    ".webm": "video",
    ".webp": "image",
    ".xls": "document",
    ".xlsx": "document",
}


class KnowledgeAdapter(Protocol):
    source_kind: SourceKind

    def project(self, envelope: SourceEnvelope) -> KnowledgeSnapshot:
        raise NotImplementedError


def validate_envelope(envelope: SourceEnvelope) -> None:
    """Recheck canonical input before any parser is invoked."""
    if not isinstance(envelope.canonical_bytes, bytes):
        raise ValueError("source envelope canonical bytes are invalid")
    if envelope.byte_size != len(envelope.canonical_bytes):
        raise ValueError("source envelope byte size mismatch")
    if sha256(envelope.canonical_bytes).hexdigest() != envelope.observed_content_hash:
        raise ValueError("source envelope content hash mismatch")


def snapshot_from_parsed(
    envelope: SourceEnvelope,
    parsed: ParsedDocument,
    *,
    source_native_id: str,
    document_kind: str,
    journal_date: date | None,
    normalized_body: str | None = None,
) -> KnowledgeSnapshot:
    """Build a validated snapshot without resolving, loading, or mutating sources."""
    validate_envelope(envelope)
    if parsed.content_hash != envelope.observed_content_hash:
        raise ValueError("parser content hash does not match source envelope")

    space_id = envelope.space_id
    document_id = engine_record_id("document", space_id, envelope.relative_locator)
    revision_id = engine_record_id(
        "revision",
        space_id,
        f"{envelope.relative_locator}/revisions/{envelope.observed_content_hash}",
    )
    capabilities = sorted(capabilities_for(envelope.authority_kind, document_kind))
    block_ids = {
        block.parser_id: engine_record_id(
            "block",
            space_id,
            _block_source_key(envelope.relative_locator, block.stable_source_id, block.parser_id),
        )
        for block in parsed.blocks
    }
    if normalized_body is None:
        normalized_body = parsed.markdown

    revision = SourceRevision(
        id=revision_id,
        space_id=space_id,
        document_id=document_id,
        content_hash=envelope.observed_content_hash,
        byte_size=envelope.byte_size,
        encoding=parsed.encoding,
        newline=parsed.newline,
        observed_modified_ns=envelope.observed_modified_ns,
        adapter_version=ADAPTER_VERSION,
        parser_version=PARSER_VERSION,
        parse_status="ready",
        diagnostics=[],
        observed_at=envelope.observed_at,
        created_at=envelope.observed_at,
    )
    space = KnowledgeSpace(
        id=space_id,
        display_name=envelope.space_display_name,
        authority_kind=envelope.authority_kind,
        source_kind=envelope.source_kind,
        format_mode=envelope.format_mode,
        source_ref=envelope.source_ref,
        availability_state="available",
        projection_state="ready",
        adapter_version=ADAPTER_VERSION,
        parser_version=PARSER_VERSION,
        policy_version=1,
        capabilities=sorted(capabilities_for(envelope.authority_kind, "space")),
        created_at=envelope.observed_at,
        updated_at=envelope.observed_at,
    )
    document = KnowledgeDocument(
        id=document_id,
        space_id=space_id,
        source_native_id=source_native_id,
        authority_kind=envelope.authority_kind,
        relative_locator=envelope.relative_locator,
        document_kind=document_kind,
        title=parsed.title,
        normalized_body=normalized_body,
        properties=dict(parsed.properties),
        tags=_document_tags(parsed),
        content_hash=envelope.observed_content_hash,
        source_revision_id=revision_id,
        provenance=envelope.source_kind,
        availability="available",
        parse_state="ready",
        journal_date=journal_date,
        capabilities=capabilities,
        created_at=envelope.observed_at,
        observed_at=envelope.observed_at,
        updated_at=envelope.observed_at,
    )
    blocks = [
        KnowledgeBlock(
            id=block_ids[block.parser_id],
            space_id=space_id,
            document_id=document_id,
            parent_block_id=block_ids.get(block.parent_parser_id),
            position=block.position,
            source_key=_block_source_key(
                envelope.relative_locator, block.stable_source_id, block.parser_id
            ),
            block_kind=block.block_kind,
            markdown=block.markdown,
            plain_text=block.plain_text,
            properties=dict(block.properties),
            raw_task_state=_raw_block_task_state(envelope.source_kind, block.markdown, block.task_state),
            normalized_task_state=(
                _normalize_task_state(block.task_state)
                if block.task_state is not None
                else None
            ),
            heading_path=list(block.heading_path),
            source_start=block.source_start,
            source_end=block.source_end,
            source_revision_id=revision_id,
            capabilities=capabilities,
        )
        for block in parsed.blocks
    ]
    relations = _relations_from_parsed(
        envelope,
        parsed.links,
        parsed.embeds,
        tags=_document_tags(parsed),
        document_id=document_id,
        revision_id=revision_id,
        block_ids=block_ids,
    )
    tasks = _tasks_from_parsed(
        envelope,
        parsed,
        document_id=document_id,
        revision_id=revision_id,
        block_ids=block_ids,
        capabilities=capabilities,
    )
    assets = _assets_from_embeds(
        envelope,
        parsed.embeds,
        document_id=document_id,
        revision_id=revision_id,
        capabilities=capabilities,
    )
    identity_claims = _identity_claims(
        parsed,
        document_id=document_id,
        source_native_id=source_native_id,
        revision_id=revision_id,
        block_ids=block_ids,
    )
    snapshot = KnowledgeSnapshot(
        space=space,
        document=document,
        blocks=blocks,
        relations=relations,
        tasks=tasks,
        assets=assets,
        identity_claims=identity_claims,
        diagnostics=[],
        revision=revision,
    )
    validate_snapshot_spans(snapshot, source_size=envelope.byte_size)
    return snapshot


def _block_source_key(
    locator: str, stable_source_id: str | None, parser_id: str
) -> str:
    return f"{locator}/blocks/{stable_source_id or parser_id}"


def _normalize_task_state(value: str | None) -> TaskState:
    return {
        "todo": "open",
        "doing": "in_progress",
        "done": "done",
        "canceled": "cancelled",
    }.get(value or "", "unknown")


def _raw_block_task_state(
    source_kind: SourceKind, markdown: str, parsed_state: str | None
) -> str | None:
    if parsed_state is None:
        return None
    if source_kind == "logseq":
        matched = _LOGSEQ_RAW_STATUS.match(markdown)
        if matched is not None:
            return matched.group(1)
    return parsed_state


def _document_tags(parsed: ParsedDocument) -> list[str]:
    property_tags = parsed.properties.get("tags")
    if isinstance(property_tags, list):
        values: Iterable[object] = [*property_tags, *parsed.tags]
    elif isinstance(property_tags, str):
        values = [property_tags, *parsed.tags]
    else:
        values = parsed.tags
    return list(dict.fromkeys(str(value).lstrip("#") for value in values if str(value)))


def _relations_from_parsed(
    envelope: SourceEnvelope,
    links: list[ParsedLink],
    embeds: list[ParsedEmbed],
    *,
    tags: list[str],
    document_id: str,
    revision_id: str,
    block_ids: dict[str, str],
) -> list[KnowledgeRelation]:
    relation_inputs: list[tuple[str, ParsedLink | ParsedEmbed]] = [
        (link.link_kind, link) for link in links
    ]
    seen_embed_keys = {
        _embed_key(link.source_block_parser_id, link.target_text, link.source_start, link.source_end)
        for link in links
        if link.link_kind == "embed"
    }
    relation_inputs.extend(
        ("embed", embed)
        for embed in embeds
        if _embed_key(
            embed.source_block_parser_id,
            embed.target_text,
            embed.source_start,
            embed.source_end,
        )
        not in seen_embed_keys
    )
    relations: list[KnowledgeRelation] = []
    for position, (relation_kind, link) in enumerate(relation_inputs):
        source_key = (
            f"{envelope.relative_locator}/relations/"
            f"{link.source_start}-{link.source_end}-{position}"
        )
        relations.append(
            KnowledgeRelation(
                id=engine_record_id("relation", envelope.space_id, source_key),
                space_id=envelope.space_id,
                source_document_id=document_id,
                source_block_id=block_ids.get(link.source_block_parser_id),
                target_document_id=None,
                target_block_id=None,
                target_text=link.target_text,
                target_heading=link.target_heading,
                target_block=link.target_block,
                alias=getattr(link, "alias", None),
                relation_kind=relation_kind,
                resolved=False,
                source_start=link.source_start,
                source_end=link.source_end,
                source_revision_id=revision_id,
            )
        )
    emitted_tags = {
        relation.target_text
        for relation in relations
        if relation.relation_kind == "tag"
    }
    for tag in tags:
        if tag in emitted_tags:
            continue
        position = len(relations)
        source_key = f"{envelope.relative_locator}/relations/tag-{position}"
        relations.append(
            KnowledgeRelation(
                id=engine_record_id("relation", envelope.space_id, source_key),
                space_id=envelope.space_id,
                source_document_id=document_id,
                source_block_id=None,
                target_document_id=None,
                target_block_id=None,
                target_text=tag,
                target_heading=None,
                target_block=None,
                alias=None,
                relation_kind="tag",
                resolved=False,
                source_start=0,
                source_end=0,
                source_revision_id=revision_id,
            )
        )
    return relations


def _embed_key(
    block_id: str | None, target: str, source_start: int, source_end: int
) -> tuple[str | None, str, int, int]:
    return (block_id, target, source_start, source_end)


def _tasks_from_parsed(
    envelope: SourceEnvelope,
    parsed: ParsedDocument,
    *,
    document_id: str,
    revision_id: str,
    block_ids: dict[str, str],
    capabilities: list[str],
) -> list[KnowledgeTask]:
    blocks = {block.parser_id: block for block in parsed.blocks}
    tasks: list[KnowledgeTask] = []
    for task in parsed.tasks:
        block = blocks[task.block_parser_id]
        source_key = f"{envelope.relative_locator}/tasks/{task.block_parser_id}"
        tasks.append(
            KnowledgeTask(
                id=engine_record_id("task", envelope.space_id, source_key),
                space_id=envelope.space_id,
                document_id=document_id,
                block_id=block_ids.get(task.block_parser_id),
                raw_status=_raw_block_task_state(
                    envelope.source_kind, block.markdown, task.status
                )
                or task.status,
                normalized_status=_normalize_task_state(task.status),
                scheduled=task.scheduled,
                due=task.due,
                completed=task.completed,
                priority=task.priority,
                recurrence=task.recurrence,
                tags=list(task.tags),
                properties=dict(block.properties),
                source_start=block.source_start,
                source_end=block.source_end,
                source_revision_id=revision_id,
                capabilities=capabilities,
            )
        )
    return tasks


def _assets_from_embeds(
    envelope: SourceEnvelope,
    embeds: list[ParsedEmbed],
    *,
    document_id: str,
    revision_id: str,
    capabilities: list[str],
) -> list[KnowledgeAsset]:
    assets: list[KnowledgeAsset] = []
    seen: set[str] = set()
    for embed in embeds:
        locator = _attachment_locator(embed.target_text)
        if locator is None or locator in seen:
            continue
        seen.add(locator)
        media_kind = _ATTACHMENT_KINDS[PurePosixPath(locator).suffix.lower()]
        source_key = f"{envelope.relative_locator}/assets/{locator}"
        assets.append(
            KnowledgeAsset(
                id=engine_record_id("asset", envelope.space_id, source_key),
                space_id=envelope.space_id,
                source_document_id=document_id,
                relative_locator=locator,
                media_kind=media_kind,
                content_hash=None,
                byte_size=None,
                availability="referenced",
                metadata={},
                provenance=envelope.source_kind,
                source_revision_id=revision_id,
                capabilities=capabilities,
            )
        )
    return assets


def _attachment_locator(target: str) -> str | None:
    try:
        locator = canonical_locator(target)
    except ValueError:
        return None
    if PurePosixPath(locator).suffix.lower() not in _ATTACHMENT_KINDS:
        return None
    return locator


def _identity_claims(
    parsed: ParsedDocument,
    *,
    document_id: str,
    source_native_id: str,
    revision_id: str,
    block_ids: dict[str, str],
) -> list[KnowledgeIdentityClaim]:
    claims = [
        _identity_claim(
            "source_native_document",
            source_native_id,
            "document",
            document_id,
            revision_id,
        )
    ]
    claims.extend(
        _identity_claim(
            "source_native_block",
            block.stable_source_id or block.parser_id,
            "block",
            block_ids[block.parser_id],
            revision_id,
        )
        for block in parsed.blocks
    )
    return claims


def _identity_claim(
    legacy_kind: str,
    legacy_id: str,
    engine_kind: str,
    engine_id: str,
    revision_id: str,
) -> KnowledgeIdentityClaim:
    payload = "\0".join(
        (legacy_kind, legacy_id, engine_kind, engine_id, revision_id)
    ).encode()
    return KnowledgeIdentityClaim(
        legacy_kind=legacy_kind,
        legacy_id=legacy_id,
        engine_kind=engine_kind,
        engine_id=engine_id,
        source_revision_id=revision_id,
        claim_hash=sha256(payload).hexdigest(),
    )
