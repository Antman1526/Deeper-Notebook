"""Neutral Markdown parsing with semantic and byte-accurate source locations."""

from __future__ import annotations

import re
from bisect import bisect_right
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
    SourceRegion,
    explicit_block_id,
    fail,
    make_block,
    ordered_unique,
    plain_text,
)

_HEADING = re.compile(r"^(?:[ \t]*>[ \t]*)*(#{1,6})[ \t]+(.+?)[ \t]*$")
_CALLOUT = re.compile(r"^[ \t]*>[ \t]*\[![^\]\r\n]{1,80}\]")
_FOOTNOTE = re.compile(r"^[ \t]*\[\^[^\]\r\n]{1,200}\]:")
_CHECKBOX_TASK = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\[([ xX-])\][ \t]+")
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
_HTML_TAG = re.compile(
    r"</?([A-Za-z][A-Za-z0-9-]{0,63})(?:[ \t]+[^>\r\n]{0,4096})?[ \t]*/?>"
)
_RAW_HTML_CONTENT_TAGS = frozenset({"code", "pre", "script", "style"})
_MAX_WIKILINK_TARGET_CHARS = 4096
_MAX_MARKDOWN_LABEL_CHARS = 1024
_MAX_MARKDOWN_TARGET_CHARS = 4096

_MD = MarkdownIt("commonmark", options_update={"html": True})

SourceText = SourceLine | SourceRegion


@dataclass(frozen=True, slots=True)
class ProtectedRanges:
    """Merged half-open character ranges with logarithmic intersection checks."""

    ranges: tuple[tuple[int, int], ...]
    starts: tuple[int, ...]

    @classmethod
    def from_ranges(cls, ranges: list[tuple[int, int]]) -> "ProtectedRanges":
        merged: list[tuple[int, int]] = []
        for start, end in sorted(ranges):
            if end <= start:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return cls(
            ranges=tuple(merged),
            starts=tuple(start for start, _end in merged),
        )

    def overlaps(self, start: int, end: int) -> bool:
        if not self.ranges or end <= start:
            return False
        index = bisect_right(self.starts, start) - 1
        if index >= 0 and self.ranges[index][1] > start:
            return True
        next_index = index + 1
        return next_index < len(self.ranges) and self.ranges[next_index][0] < end

    def containing(self, position: int) -> tuple[int, int] | None:
        if not self.ranges:
            return None
        index = bisect_right(self.starts, position) - 1
        if index >= 0:
            start, end = self.ranges[index]
            if start <= position < end:
                return start, end
        return None


@dataclass(frozen=True, slots=True)
class ByteOffsetMapper:
    source_start: int
    offsets: tuple[int, ...] | None

    @classmethod
    def from_source(cls, source_text: SourceText) -> "ByteOffsetMapper":
        if source_text.content.isascii():
            return cls(source_start=source_text.source_start, offsets=None)
        offsets = [0]
        for character in source_text.content:
            offsets.append(offsets[-1] + len(character.encode("utf-8")))
        return cls(
            source_start=source_text.source_start,
            offsets=tuple(offsets),
        )

    def span(self, start: int, end: int) -> tuple[int, int]:
        if self.offsets is None:
            return self.source_start + start, self.source_start + end
        return (
            self.source_start + self.offsets[start],
            self.source_start + self.offsets[end],
        )


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

    def scan_inline(self, source_text: SourceText, block_id: str | None) -> None:
        text = source_text.content
        byte_offsets = ByteOffsetMapper.from_source(source_text)
        occupied = list(_literal_spans(text))
        literals = ProtectedRanges.from_ranges(occupied)

        for start, end, embedded, label, raw_target in _iter_markdown_links(
            text, literals
        ):
            target = _markdown_target(raw_target)
            if not target:
                continue
            occupied.append((start, end))
            span_start, span_end = byte_offsets.span(start, end)
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    alias=label or None,
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

        for matched in _LOGSEQ_EMBED.finditer(text):
            if _is_escaped(text, matched.start()) or literals.overlaps(*matched.span()):
                continue
            occupied.append(matched.span())
            span_start, span_end = byte_offsets.span(*matched.span())
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

        for matched in _LOGSEQ_BLOCK_EMBED.finditer(text):
            if _is_escaped(text, matched.start()) or literals.overlaps(*matched.span()):
                continue
            occupied.append(matched.span())
            span_start, span_end = byte_offsets.span(*matched.span())
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

        protected = ProtectedRanges.from_ranges(occupied)
        for start, end, embedded, value in _iter_wikilinks(text, protected):
            occupied.append((start, end))
            target, heading, target_block, alias = _split_wikilink(value)
            span_start, span_end = byte_offsets.span(start, end)
            self.links.append(
                ParsedLink(
                    source_block_parser_id=block_id,
                    target_text=target,
                    target_heading=heading,
                    target_block=target_block,
                    alias=alias,
                    link_kind="embed" if embedded else "wikilink",
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

        protected = ProtectedRanges.from_ranges(occupied)
        for matched in _LOGSEQ_BLOCK_REF.finditer(text):
            if _is_escaped(text, matched.start()) or protected.overlaps(
                *matched.span()
            ):
                continue
            occupied.append(matched.span())
            span_start, span_end = byte_offsets.span(*matched.span())
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

        protected = ProtectedRanges.from_ranges(occupied)
        for matched in _TAG.finditer(text):
            if (
                _is_escaped(text, matched.start())
                or protected.overlaps(*matched.span())
                or _is_priority_marker(text, matched.start(), matched.end())
            ):
                continue
            span_start, span_end = byte_offsets.span(*matched.span())
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


@dataclass(slots=True)
class ContainerContext:
    kind: str
    parser_id: str | None = None


@dataclass(frozen=True, slots=True)
class MappedSource:
    source: DecodedSource
    relative_line_offsets: tuple[int, ...]

    @classmethod
    def from_source(cls, source: DecodedSource) -> "MappedSource":
        offsets = [0]
        for raw_line in source.raw[source.body_start :].splitlines(keepends=True):
            offsets.append(offsets[-1] + len(raw_line))
        return cls(source=source, relative_line_offsets=tuple(offsets))

    def region_for_lines(self, start: int, end: int) -> SourceRegion:
        if start < 0 or end <= start or end >= len(self.relative_line_offsets):
            fail("invalid_document")
        source_start = self.source.body_start + self.relative_line_offsets[start]
        source_end = self.source.body_start + self.relative_line_offsets[end]
        markdown = self.source.raw[source_start:source_end].decode("utf-8")
        return SourceRegion(
            source_start=source_start,
            source_end=source_end,
            markdown=markdown,
            content=markdown.rstrip("\r\n"),
        )


def parse_markdown_blocks(
    relative_path: str,
    source: DecodedSource,
    *,
    obsidian: bool = False,
) -> ParseAccumulator:
    """Project Markdown-It semantic block maps, never rendered output."""

    accumulator = ParseAccumulator(relative_path=relative_path, source=source)
    tokens: list[Any] = []
    normalized_markdown = source.body_markdown.replace("\r\n", "\n").replace("\r", "\n")
    _MD.block.parse(normalized_markdown, _MD, {}, tokens)
    mapped_source = MappedSource.from_source(source)
    container_stack: list[ContainerContext] = []
    heading_stack: list[tuple[int, str, str]] = []

    for index, token in enumerate(tokens):
        if token.type == "blockquote_open":
            container_stack.append(ContainerContext(kind="blockquote"))
            continue

        if token.type == "blockquote_close":
            _close_container(container_stack, "blockquote")
            continue

        if token.type == "list_item_open":
            container_stack.append(ContainerContext(kind="list-item"))
            continue

        if token.type == "list_item_close":
            _close_container(container_stack, "list-item")
            continue

        if token.type == "heading_open":
            region = _region_for_token(mapped_source, token.map)
            level = int(token.tag[1:])
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            title = _inline_content(tokens, index) or plain_text(region.markdown)
            parent_id = (
                _container_parent(container_stack)
                if _container_parent(container_stack) is not None
                else (heading_stack[-1][2] if heading_stack else None)
            )
            heading_path = _current_heading_path(heading_stack) + [title]
            block = _append_block(
                accumulator,
                region,
                parent_id=parent_id,
                block_kind="heading",
                heading_path=heading_path,
            )
            accumulator.scan_inline(region, block.parser_id)
            _bind_unbound_containers(container_stack, block.parser_id)
            heading_stack.append((level, title, block.parser_id))
            if accumulator.title is None and level == 1:
                accumulator.title = title
            continue

        if token.type == "paragraph_open":
            region = _region_for_token(mapped_source, token.map)
            task_match = _CHECKBOX_TASK.match(region.content)
            task_state = _checkbox_status(task_match.group(1)) if task_match else None
            if task_state:
                kind = "task"
            elif _FOOTNOTE.match(region.content):
                kind = "footnote"
            elif _unbound_container_kind(container_stack) == "list-item":
                kind = "list-item"
            elif _unbound_container_kind(container_stack) == "blockquote":
                kind = "callout" if _CALLOUT.match(region.content) else "blockquote"
            else:
                kind = "paragraph"
            block = _append_block(
                accumulator,
                region,
                parent_id=_current_parent(container_stack, heading_stack),
                block_kind=kind,
                stable_source_id=(
                    explicit_block_id(region.markdown) if obsidian else None
                ),
                task_state=task_state,
                heading_path=_current_heading_path(heading_stack),
            )
            if task_state:
                accumulator.tasks.append(
                    ParsedTask(
                        block_parser_id=block.parser_id,
                        status=task_state,
                    )
                )
            accumulator.scan_inline(region, block.parser_id)
            _bind_unbound_containers(container_stack, block.parser_id)
            continue

        if token.type in {"fence", "code_block", "html_block", "hr"}:
            region = _region_for_token(mapped_source, token.map)
            kind = {
                "fence": "code",
                "code_block": "code",
                "html_block": "html",
                "hr": "thematic-break",
            }[token.type]
            block = _append_block(
                accumulator,
                region,
                parent_id=_current_parent(container_stack, heading_stack),
                block_kind=kind,
                heading_path=_current_heading_path(heading_stack),
            )
            _bind_unbound_containers(container_stack, block.parser_id)

    accumulator.tags = ordered_unique(accumulator.tags)
    return accumulator


def _append_block(
    accumulator: ParseAccumulator,
    region: SourceRegion,
    *,
    parent_id: str | None,
    block_kind: str,
    stable_source_id: str | None = None,
    task_state: str | None = None,
    heading_path: list[str],
) -> ParsedBlock:
    block = make_block(
        relative_path=accumulator.relative_path,
        parent_id=parent_id,
        position=len(accumulator.blocks),
        block_kind=block_kind,
        line=region,
        plain_text=plain_text(region.markdown),
        stable_source_id=stable_source_id,
        task_state=task_state,
        heading_path=heading_path,
    )
    accumulator.blocks.append(block)
    return block


def _region_for_token(source: MappedSource, line_map: list[int] | None) -> SourceRegion:
    if line_map is None or len(line_map) != 2:
        raise ValueError("semantic token has no source map")
    return source.region_for_lines(line_map[0], line_map[1])


def _inline_content(tokens: list[Any], index: int) -> str | None:
    next_index = index + 1
    if next_index < len(tokens) and tokens[next_index].type == "inline":
        return tokens[next_index].content.strip()
    return None


def _current_parent(
    containers: list[ContainerContext],
    headings: list[tuple[int, str, str]],
) -> str | None:
    container_parent = _container_parent(containers)
    if container_parent is not None:
        return container_parent
    return headings[-1][2] if headings else None


def _container_parent(
    containers: list[ContainerContext],
) -> str | None:
    for context in reversed(containers):
        if context.parser_id is not None:
            return context.parser_id
    return None


def _unbound_container_kind(
    containers: list[ContainerContext],
) -> str | None:
    for context in reversed(containers):
        if context.parser_id is None:
            return context.kind
    return None


def _bind_unbound_containers(
    containers: list[ContainerContext], parser_id: str
) -> None:
    for context in containers:
        if context.parser_id is None:
            context.parser_id = parser_id


def _current_heading_path(
    headings: list[tuple[int, str, str]],
) -> list[str]:
    return [title for _level, title, _parser_id in headings]


def _close_container(containers: list[ContainerContext], expected_kind: str) -> None:
    for index in range(len(containers) - 1, -1, -1):
        if containers[index].kind == expected_kind:
            del containers[index:]
            return


def _literal_spans(text: str) -> list[tuple[int, int]]:
    spans = _code_spans(text)
    spans.extend(_html_spans(text))
    return spans


def _code_spans(text: str) -> list[tuple[int, int]]:
    pending: dict[int, tuple[int, int]] = {}
    spans: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] != "`" or _is_escaped(text, cursor):
            cursor += 1
            continue
        end = cursor + 1
        while end < len(text) and text[end] == "`":
            end += 1
        run_length = end - cursor
        opening = pending.pop(run_length, None)
        if opening is None:
            pending[run_length] = (cursor, end)
        else:
            spans.append((opening[0], end))
        cursor = end
    return spans


def _html_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    lowered = text.lower()
    cursor = 0
    while cursor < len(text):
        opening = text.find("<", cursor)
        if opening < 0:
            break
        if _is_escaped(text, opening):
            cursor = opening + 1
            continue
        if text.startswith("<!--", opening):
            closing = text.find("-->", opening + 4)
            end = len(text) if closing < 0 else closing + 3
            spans.append((opening, end))
            cursor = end
            continue
        matched = _HTML_TAG.match(text, opening)
        if matched is None:
            cursor = opening + 1
            continue
        tag = matched.group(1).lower()
        end = matched.end()
        is_closing = text.startswith("</", opening)
        is_self_closing = text[opening:end].rstrip().endswith("/>")
        if tag in _RAW_HTML_CONTENT_TAGS and not is_closing and not is_self_closing:
            closing_start = lowered.find(f"</{tag}", end)
            if closing_start >= 0:
                closing_end = text.find(">", closing_start + len(tag) + 2)
                if closing_end >= 0:
                    end = closing_end + 1
        spans.append((opening, end))
        cursor = end
    return spans


def _iter_wikilinks(text: str, protected: ProtectedRanges):
    """Yield wiki links in one forward-only pass over the source."""

    cursor = 0
    length = len(text)
    while cursor + 1 < length:
        containing = protected.containing(cursor)
        if containing is not None:
            cursor = containing[1]
            continue
        if text[cursor] != "[" or text[cursor + 1] != "[":
            cursor += 1
            continue
        if _is_escaped(text, cursor):
            cursor += 2
            continue

        embedded = cursor > 0 and text[cursor - 1] == "!"
        escaped_bang = embedded and _is_escaped(text, cursor - 1)
        if escaped_bang:
            cursor += 2
            continue
        start = cursor - 1 if embedded else cursor
        target_start = cursor + 2
        scan = target_start
        limit = min(length, target_start + _MAX_WIKILINK_TARGET_CHARS + 2)
        while scan + 1 < limit:
            protected_region = protected.containing(scan)
            if protected_region is not None:
                scan = protected_region[1]
                break
            if text[scan] in "\r\n":
                break
            if (
                text[scan] == "]"
                and text[scan + 1] == "]"
                and not _is_escaped(text, scan)
            ):
                end = scan + 2
                yield start, end, embedded, text[target_start:scan]
                cursor = end
                break
            scan += 1
        else:
            scan = limit

        if cursor < target_start:
            cursor = max(scan, target_start)


def _iter_markdown_links(text: str, protected: ProtectedRanges):
    """Yield links and images with bounded, forward-only label/target scans."""

    cursor = 0
    length = len(text)
    while cursor < length:
        containing = protected.containing(cursor)
        if containing is not None:
            cursor = containing[1]
            continue
        embedded = text[cursor] == "!" and cursor + 1 < length
        opening = cursor + 1 if embedded else cursor
        if text[opening] != "[" or _is_escaped(text, cursor):
            cursor += 1
            continue
        if opening + 1 < length and text[opening + 1] == "[":
            cursor = opening + 2
            continue

        label_start = opening + 1
        scan = label_start
        label_limit = min(length, label_start + _MAX_MARKDOWN_LABEL_CHARS + 1)
        closing_label: int | None = None
        label_depth = 0
        while scan < label_limit:
            if text[scan] in "\r\n":
                break
            if not _is_escaped(text, scan):
                if text[scan] == "[":
                    label_depth += 1
                    if label_depth > 32:
                        break
                elif text[scan] == "]":
                    if label_depth:
                        label_depth -= 1
                    else:
                        closing_label = scan
                        break
            scan += 1
        if (
            closing_label is None
            or closing_label + 1 >= length
            or text[closing_label + 1] != "("
        ):
            cursor = max(scan, label_start)
            continue

        target_start = closing_label + 2
        scan = target_start
        target_limit = min(length, target_start + _MAX_MARKDOWN_TARGET_CHARS + 1)
        closing_target: int | None = None
        target_depth = 0
        quote: str | None = None
        while scan < target_limit:
            if text[scan] in "\r\n":
                break
            if _is_escaped(text, scan):
                scan += 1
            elif quote is not None:
                if text[scan] == quote:
                    quote = None
            elif text[scan] in {'"', "'"}:
                quote = text[scan]
            elif text[scan] == "(":
                target_depth += 1
                if target_depth > 32:
                    break
            elif text[scan] == ")":
                if target_depth:
                    target_depth -= 1
                else:
                    closing_target = scan
                    break
            scan += 1
        if closing_target is None:
            cursor = max(scan, target_start)
            continue

        end = closing_target + 1
        if protected.overlaps(cursor, end):
            cursor = end
            continue
        yield (
            cursor,
            end,
            embedded,
            text[label_start:closing_label],
            text[target_start:closing_target],
        )
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
    depth = 0
    cursor = 0
    while cursor < len(stripped):
        character = stripped[cursor]
        if character == "\\" and cursor + 1 < len(stripped):
            cursor += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character.isspace() and depth == 0:
            return stripped[:cursor]
        cursor += 1
    return stripped


def _is_escaped(text: str, position: int) -> bool:
    slashes = 0
    cursor = position - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1


def _is_priority_marker(text: str, start: int, end: int) -> bool:
    return start > 0 and text[start - 1] == "[" and end < len(text) and text[end] == "]"


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
