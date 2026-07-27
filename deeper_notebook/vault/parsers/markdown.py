"""Neutral Markdown parsing with byte-accurate source locations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from markdown_it import MarkdownIt

from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedEmbed,
    ParsedLink,
    ParsedTask,
)
from deeper_notebook.vault.parsers.common import (
    DecodedSource,
    SourceLine,
    explicit_block_id,
    make_block,
    ordered_unique,
    plain_text,
)

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_LIST = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])[ \t]+(.*)$")
_CALLOUT = re.compile(r"^[ \t]*>[ \t]*\[![^\]\r\n]{1,80}\]")
_FOOTNOTE = re.compile(r"^[ \t]*\[\^[^\]\r\n]{1,200}\]:")
_CHECKBOX_TASK = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\[([ xX-])\][ \t]+(.*)$")
_MARKDOWN_LINK = re.compile(r"(!?)\[([^\]\r\n]{0,1024})\]\(([^)\r\n]{1,4096})\)")
_TAG = re.compile(r"(?<![\w/#])#([A-Za-z0-9][\w/-]{0,255})")
_LOGSEQ_BLOCK_REF = re.compile(r"\(\(([A-Za-z0-9][\w-]{0,255})\)\)")
_LOGSEQ_EMBED = re.compile(
    r"\{\{embed[ \t]+\[\[([^\]\r\n]{1,4096})\]\]\}\}",
    re.IGNORECASE,
)
_LOGSEQ_BLOCK_EMBED = re.compile(
    r"\{\{embed[ \t]+\(\(([A-Za-z0-9][\w-]{0,255})\)\)\}\}",
    re.IGNORECASE,
)

_MD = MarkdownIt("commonmark", options_update={"html": False})
_TOKEN_KIND = {
    "heading_open": "heading",
    "fence": "code",
    "code_block": "code",
    "blockquote_open": "quote",
    "bullet_list_open": "list-item",
    "ordered_list_open": "list-item",
    "hr": "thematic-break",
    "paragraph_open": "paragraph",
}


@dataclass(slots=True)
class ParseAccumulator:
    relative_path: str
    source: DecodedSource
    blocks: list[ParsedBlock] = field(default_factory=list)
    links: list[ParsedLink] = field(default_factory=list)
    tasks: list[ParsedTask] = field(default_factory=list)
    embeds: list[ParsedEmbed] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    title: str | None = None

    def scan_inline(self, line: SourceLine, block_id: str | None) -> None:
        occupied: list[tuple[int, int]] = []

        for matched in _LOGSEQ_EMBED.finditer(line.content):
            occupied.append(matched.span())
            span_start, span_end = line.span_for_chars(*matched.span())
            target, heading, target_block, _alias = _split_wikilink(matched.group(1))
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_heading=heading,
                    target_block=target_block,
                    link_kind="embed",
                    source_start=span_start,
                    source_end=span_end,
                )
            )
            self.embeds.append(
                ParsedEmbed(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_heading=heading,
                    target_block=target_block,
                    source_start=span_start,
                    source_end=span_end,
                )
            )

        for matched in _LOGSEQ_BLOCK_EMBED.finditer(line.content):
            occupied.append(matched.span())
            span_start, span_end = line.span_for_chars(*matched.span())
            target = matched.group(1)
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_block=target,
                    link_kind="embed",
                    source_start=span_start,
                    source_end=span_end,
                )
            )
            self.embeds.append(
                ParsedEmbed(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_block=target,
                    source_start=span_start,
                    source_end=span_end,
                )
            )

        for start, end, embedded, value in _iter_wikilinks(line.content):
            if _span_is_inside(start, end, occupied):
                continue
            occupied.append((start, end))
            target, heading, target_block, alias = _split_wikilink(value)
            span_start, span_end = line.span_for_chars(start, end)
            kind = "embed" if embedded else "wikilink"
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_heading=heading,
                    target_block=target_block,
                    alias=alias,
                    link_kind=kind,
                    source_start=span_start,
                    source_end=span_end,
                )
            )
            if embedded:
                self.embeds.append(
                    ParsedEmbed(
                        source_block_parser_id=block_id,
                        target_text=target,
                        target_heading=heading,
                        target_block=target_block,
                        source_start=span_start,
                        source_end=span_end,
                    )
                )

        for matched in _MARKDOWN_LINK.finditer(line.content):
            target = _markdown_target(matched.group(3))
            if not target:
                continue
            occupied.append(matched.span())
            span_start, span_end = line.span_for_chars(*matched.span())
            embedded = bool(matched.group(1))
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    alias=matched.group(2) or None,
                    link_kind="embed" if embedded else "markdown",
                    source_start=span_start,
                    source_end=span_end,
                )
            )
            if embedded:
                self.embeds.append(
                    ParsedEmbed(
                        source_block_parser_id=block_id,
                        target_text=target,
                        source_start=span_start,
                        source_end=span_end,
                    )
                )

        for matched in _LOGSEQ_BLOCK_REF.finditer(line.content):
            if _span_is_inside(*matched.span(), occupied):
                continue
            occupied.append(matched.span())
            span_start, span_end = line.span_for_chars(*matched.span())
            target = matched.group(1)
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_block=target,
                    link_kind="block-ref",
                    source_start=span_start,
                    source_end=span_end,
                )
            )

        for matched in _TAG.finditer(line.content):
            if _span_is_inside(*matched.span(), occupied):
                continue
            if (
                matched.start() > 0
                and line.content[matched.start() - 1] == "["
                and matched.end() < len(line.content)
                and line.content[matched.end()] == "]"
            ):
                continue
            span_start, span_end = line.span_for_chars(*matched.span())
            tag = matched.group(1)
            self.tags.append(tag)
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=tag,
                    link_kind="tag",
                    source_start=span_start,
                    source_end=span_end,
                )
            )


def parse_markdown_blocks(
    relative_path: str,
    source: DecodedSource,
    *,
    obsidian: bool = False,
) -> ParseAccumulator:
    accumulator = ParseAccumulator(relative_path=relative_path, source=source)
    token_kinds = _markdown_token_kinds(source.body_markdown)
    heading_stack: list[tuple[int, str, str]] = []
    list_stack: list[tuple[int, str]] = []

    for line in source.body_lines():
        if not line.content.strip():
            continue

        heading = _HEADING.match(line.content)
        listed = _LIST.match(line.content)
        kind = token_kinds.get(line.number, "paragraph")
        parent_id: str | None = None
        heading_path = [item[1] for item in heading_stack]

        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent_id = heading_stack[-1][2] if heading_stack else None
            heading_path = [item[1] for item in heading_stack] + [title]
            kind = "heading"
        elif listed:
            indent = _indent_width(listed.group(1))
            while list_stack and list_stack[-1][0] >= indent:
                list_stack.pop()
            parent_id = list_stack[-1][1] if list_stack else None
            kind = "list-item"

        if _CALLOUT.match(line.content):
            kind = "callout"
        elif _FOOTNOTE.match(line.content):
            kind = "footnote"

        task_match = _CHECKBOX_TASK.match(line.content)
        task_state = _checkbox_status(task_match.group(1)) if task_match else None
        block = make_block(
            relative_path=relative_path,
            parent_id=parent_id,
            position=len(accumulator.blocks),
            block_kind="task" if task_state else kind,
            line=line,
            plain_text=plain_text(line.markdown),
            stable_source_id=explicit_block_id(line.markdown) if obsidian else None,
            task_state=task_state,
            heading_path=heading_path,
        )
        accumulator.blocks.append(block)

        if heading:
            heading_stack.append(
                (len(heading.group(1)), heading.group(2).strip(), block.parser_id)
            )
            list_stack.clear()
            if accumulator.title is None and len(heading.group(1)) == 1:
                accumulator.title = heading.group(2).strip()
        elif listed:
            list_stack.append((_indent_width(listed.group(1)), block.parser_id))

        if task_state:
            accumulator.tasks.append(
                ParsedTask(block_parser_id=block.parser_id, status=task_state)
            )
        accumulator.scan_inline(line, block.parser_id)

    accumulator.tags = ordered_unique(accumulator.tags)
    return accumulator


def _markdown_token_kinds(markdown: str) -> dict[int, str]:
    """Use Markdown-It source maps to classify neutral Markdown boundaries."""

    kinds: dict[int, str] = {}
    try:
        tokens = _MD.parse(markdown)
    except (MemoryError, RecursionError, RuntimeError):
        return kinds
    for token in tokens:
        if token.map is None or token.type not in _TOKEN_KIND:
            continue
        start, end = token.map
        for line_number in range(start, end):
            kinds.setdefault(line_number, _TOKEN_KIND[token.type])
    return kinds


def _iter_wikilinks(line: str):
    cursor = 0
    length = len(line)
    while cursor < length:
        opening = line.find("[[", cursor)
        if opening < 0:
            break
        embedded = opening > 0 and line[opening - 1] == "!"
        start = opening - 1 if embedded else opening
        closing = line.find("]]", opening + 2, min(length, opening + 4098))
        if closing < 0:
            cursor = opening + 2
            continue
        end = closing + 2
        yield start, end, embedded, line[opening + 2 : closing]
        cursor = end


def _split_wikilink(
    value: str,
) -> tuple[str, str | None, str | None, str | None]:
    target_part, separator, alias = value.partition("|")
    alias_value = alias.strip() if separator and alias.strip() else None
    target_part = target_part.strip()
    heading: str | None = None
    target_block: str | None = None

    if "^" in target_part:
        target_part, target_block = target_part.split("^", 1)
        target_block = target_block.strip() or None
    if "#" in target_part:
        target_part, heading = target_part.split("#", 1)
        heading = heading.strip() or None
    return target_part.strip(), heading, target_block, alias_value


def _markdown_target(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("<") and ">" in stripped:
        return stripped[1 : stripped.find(">")]
    return stripped.split(maxsplit=1)[0] if stripped else ""


def _span_is_inside(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(
        start >= outer_start and end <= outer_end for outer_start, outer_end in occupied
    )


def _indent_width(indent: str) -> int:
    return sum(4 if character == "\t" else 1 for character in indent)


def _checkbox_status(marker: str) -> str:
    if marker in {"x", "X"}:
        return "done"
    if marker == "-":
        return "canceled"
    return "todo"


def parse_iso_date(value: str) -> date | None:
    matched = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", value)
    if not matched:
        return None
    try:
        return date.fromisoformat(matched.group(1))
    except ValueError:
        return None


def split_property_value(value: str) -> Any:
    stripped = value.strip()
    if "," in stripped:
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return stripped


__all__ = [
    "ParseAccumulator",
    "parse_iso_date",
    "parse_markdown_blocks",
    "split_property_value",
]
