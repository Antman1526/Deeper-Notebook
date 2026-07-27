"""Safe, deterministic parsers for canonical Markdown vault sources."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Literal, cast

from deeper_notebook.vault.contracts import ParsedDocument, VaultFormat
from deeper_notebook.vault.parsers.common import VaultParseError, decode_source
from deeper_notebook.vault.parsers.logseq import parse_logseq
from deeper_notebook.vault.parsers.markdown import parse_markdown_blocks
from deeper_notebook.vault.parsers.obsidian import parse_obsidian

ResolvedFormat = Literal["obsidian", "logseq", "markdown"]


def detect_format(relative_path: str, format_mode: str) -> ResolvedFormat:
    if format_mode in {"obsidian", "logseq", "markdown"}:
        return cast(ResolvedFormat, format_mode)
    if format_mode != "mixed":
        raise VaultParseError("invalid_format_mode")

    normalized = relative_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    path = PurePosixPath(normalized)
    parts = path.parts
    if len(parts) >= 2 and parts[0] == "Obsidian Brain":
        return "obsidian"
    if (
        len(parts) >= 3
        and parts[0] == "Logseq Brain"
        and parts[1] in {"pages", "journals"}
    ):
        return "logseq"
    return "markdown"


def parse_document(
    relative_path: str,
    raw: bytes,
    *,
    format_mode: VaultFormat = "mixed",
    max_markdown_bytes: int | None = None,
) -> ParsedDocument:
    """Parse bytes without filesystem access, rendering, or source mutation."""

    source = decode_source(raw, max_markdown_bytes=max_markdown_bytes)
    source_format = detect_format(relative_path, format_mode)
    if source_format == "obsidian":
        parsed = parse_obsidian(relative_path, source)
    elif source_format == "logseq":
        parsed = parse_logseq(relative_path, source)
    else:
        parsed = parse_markdown_blocks(relative_path, source)

    properties = dict(source.properties)
    title_property = properties.get("title")
    if isinstance(title_property, str) and title_property.strip():
        title = title_property.strip()
    elif parsed.title:
        title = parsed.title
    else:
        title = PurePosixPath(relative_path.replace("\\", "/")).stem

    return ParsedDocument(
        relative_path=relative_path,
        source_format=source_format,
        title=title,
        markdown=source.markdown,
        properties=properties,
        tags=parsed.tags,
        blocks=parsed.blocks,
        links=parsed.links,
        tasks=parsed.tasks,
        embeds=parsed.embeds,
        content_hash=hashlib.sha256(raw).hexdigest(),
        encoding=source.encoding,
        newline=source.newline,
    )


__all__ = ["VaultParseError", "detect_format", "parse_document"]
