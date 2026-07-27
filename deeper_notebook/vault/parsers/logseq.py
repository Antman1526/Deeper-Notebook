"""Logseq outliner parsing with hierarchy and task semantics."""

from __future__ import annotations

import re

from deeper_notebook.vault.contracts import ParsedTask
from deeper_notebook.vault.parsers.common import (
    DecodedSource,
    SourceLine,
    SourceRegion,
    explicit_block_id,
    make_block,
    ordered_unique,
    plain_text,
)
from deeper_notebook.vault.parsers.markdown import (
    ParseAccumulator,
    parse_iso_date,
    semantic_visible_text,
    split_property_value,
)

_BLOCK = re.compile(r"^([ \t]*)[-*+][ \t]+(.*)$")
_PROPERTY = re.compile(r"^([ \t]*)([A-Za-z0-9_.-]{1,128})::[ \t]*(.*)$")
_TASK = re.compile(
    r"^(TODO|DOING|DONE|CANCELED|CANCELLED|NOW|LATER|WAITING)\b[ \t]*(.*)$"
)
_INLINE_MARKER = re.compile(
    r"\b(SCHEDULED|DEADLINE|COMPLETED|CLOSED):[ \t]*"
    r"(<[^>\r\n]{1,256}>|\[[^\]\r\n]{1,256}\])",
    re.IGNORECASE,
)
_PRIORITY = re.compile(r"\[#([A-Za-z0-9_-]{1,32})\]")
_RECURRENCE = re.compile(r"(?:\.\+|\+\+|\+)\d+[hdwmy]\b", re.IGNORECASE)
_SEMANTIC_PROPERTY = re.compile(
    r"^[ \t]*([A-Za-z0-9_.-]{1,128})::[ \t]*(.*)$",
    re.MULTILINE,
)
_STATUS = {
    "TODO": "todo",
    "DOING": "doing",
    "DONE": "done",
    "CANCELED": "canceled",
    "CANCELLED": "canceled",
    "NOW": "doing",
    "LATER": "todo",
    "WAITING": "todo",
}


def parse_logseq(relative_path: str, source: DecodedSource) -> ParseAccumulator:
    accumulator = ParseAccumulator(relative_path=relative_path, source=source)
    block_stack: list[tuple[int, str]] = []
    block_by_id = {}
    page_properties_open = True
    fence_marker: tuple[str, int] | None = None
    scan_jobs: list[tuple[SourceLine, str | None]] = []

    for line in source.body_lines():
        if fence_marker is not None:
            parent_id = block_stack[-1][1] if block_stack else None
            block = make_block(
                relative_path=relative_path,
                parent_id=parent_id,
                position=len(accumulator.blocks),
                block_kind="code",
                line=line,
                plain_text=line.content,
            )
            accumulator.add_block(block)
            if _is_fence_closer(line.content, fence_marker):
                fence_marker = None
            continue
        fence_opener = _fence_opener(line.content)
        if fence_opener is not None:
            parent_id = block_stack[-1][1] if block_stack else None
            block = make_block(
                relative_path=relative_path,
                parent_id=parent_id,
                position=len(accumulator.blocks),
                block_kind="code",
                line=line,
                plain_text=line.content,
            )
            accumulator.add_block(block)
            fence_marker = fence_opener
            continue
        if not line.content.strip():
            continue
        property_match = _PROPERTY.match(line.content)
        block_match = _BLOCK.match(line.content)

        if property_match and page_properties_open and not accumulator.blocks:
            key = property_match.group(2)
            accumulator.source.properties[key] = split_property_value(
                property_match.group(3)
            )
            scan_jobs.append((line, None))
            continue

        page_properties_open = False
        if property_match and accumulator.blocks:
            indent = _indent_width(property_match.group(1))
            owner_id = _owner_at_indent(block_stack, indent)
            if owner_id is not None:
                owner = block_by_id[owner_id]
                key = property_match.group(2)
                value = split_property_value(property_match.group(3))
                owner.properties[key] = value
                lowered = key.lower()
                if lowered == "id" and isinstance(value, str):
                    owner.stable_source_id = value
                scan_jobs.append((line, owner_id))
                continue

        if not block_match and accumulator.blocks:
            indent = _leading_indent(line.content)
            owner_id = _owner_at_indent(block_stack, indent)
            if owner_id is not None:
                scan_jobs.append((line, owner_id))
                continue

        indent = _indent_width(block_match.group(1)) if block_match else 0
        while block_stack and block_stack[-1][0] >= indent:
            block_stack.pop()
        parent_id = block_stack[-1][1] if block_stack else None
        content = block_match.group(2) if block_match else line.content.strip()
        task_match = _TASK.match(content)
        status = _STATUS[task_match.group(1)] if task_match else None
        stable_source_id = explicit_block_id(line.markdown)
        block = make_block(
            relative_path=relative_path,
            parent_id=parent_id,
            position=len(accumulator.blocks),
            block_kind="task"
            if status
            else ("list-item" if block_match else "paragraph"),
            line=line,
            plain_text=plain_text(line.markdown),
            stable_source_id=stable_source_id,
            task_state=status,
        )
        accumulator.add_block(block)
        block_by_id[block.parser_id] = block
        block_stack.append((indent, block.parser_id))

        if status:
            task = ParsedTask(
                block_parser_id=block.parser_id,
                status=status,
                tags=[],
            )
            accumulator.add_task(task)

        scan_jobs.append((line, block.parser_id))

    semantic_by_block = _scan_queued_regions(accumulator, scan_jobs)
    tags_by_block: dict[str, list[str]] = {}
    for link in accumulator.links:
        if link.link_kind == "tag" and link.source_block_parser_id is not None:
            tags_by_block.setdefault(link.source_block_parser_id, []).append(
                link.target_text
            )
    for task in accumulator.tasks:
        semantic = semantic_by_block.get(task.block_parser_id, "")
        _hydrate_task_metadata(
            task,
            semantic,
            tags_by_block.get(task.block_parser_id, []),
        )
    accumulator.tags = ordered_unique(accumulator.tags)
    return accumulator


def _scan_queued_regions(
    accumulator: ParseAccumulator,
    jobs: list[tuple[SourceLine, str | None]],
) -> dict[str, str]:
    current_lines: list[SourceLine] = []
    current_block_id: str | None = None
    semantic_regions: dict[str, list[str]] = {}

    def flush() -> None:
        if not current_lines:
            return
        markdown = "".join(line.markdown for line in current_lines)
        region = SourceRegion(
            source_start=current_lines[0].source_start,
            source_end=current_lines[-1].source_end,
            markdown=markdown,
            content=markdown.rstrip("\r\n"),
        )
        accumulator.scan_inline(region, current_block_id)
        if current_block_id is not None:
            semantic_regions.setdefault(current_block_id, []).append(
                semantic_visible_text(region.content)
            )

    for line, block_id in jobs:
        if current_lines and (
            block_id != current_block_id
            or current_lines[-1].source_end != line.source_start
        ):
            flush()
            current_lines = []
        if not current_lines:
            current_block_id = block_id
        current_lines.append(line)
    flush()
    return {
        block_id: "\n".join(regions) for block_id, regions in semantic_regions.items()
    }


def _fence_opener(content: str) -> tuple[str, int] | None:
    stripped = content.lstrip(" \t")
    if not stripped or stripped[0] not in {"`", "~"}:
        return None
    marker = stripped[0]
    run_end = 1
    while run_end < len(stripped) and stripped[run_end] == marker:
        run_end += 1
    if run_end < 3:
        return None
    info = stripped[run_end:]
    if marker == "`" and "`" in info:
        return None
    return marker, run_end


def _is_fence_closer(content: str, opener: tuple[str, int]) -> bool:
    stripped = content.lstrip(" \t")
    marker, minimum_length = opener
    if not stripped or stripped[0] != marker:
        return False
    run_end = 1
    while run_end < len(stripped) and stripped[run_end] == marker:
        run_end += 1
    return run_end >= minimum_length and not stripped[run_end:].strip()


def _hydrate_task_metadata(
    task: ParsedTask,
    semantic: str,
    projected_tags: list[str],
) -> None:
    task.priority = _extract_priority(semantic)
    task.recurrence = _extract_recurrence(semantic)
    property_tags: list[str] = []
    for matched in _SEMANTIC_PROPERTY.finditer(semantic):
        key = matched.group(1).lower()
        value = matched.group(2)
        if key == "priority":
            task.priority = value.strip() or task.priority
        elif key in {"tags", "tag"}:
            property_tags.extend(_property_tags(split_property_value(value)))
    for marker in _INLINE_MARKER.finditer(semantic):
        _apply_task_marker(task, marker.group(1), marker.group(2))
    task.tags = ordered_unique(property_tags + projected_tags)


def _owner_at_indent(
    block_stack: list[tuple[int, str]], continuation_indent: int
) -> str | None:
    for indent, parser_id in reversed(block_stack):
        if indent < continuation_indent or continuation_indent == 0:
            return parser_id
    return block_stack[-1][1] if block_stack else None


def _leading_indent(value: str) -> int:
    matched = re.match(r"^[ \t]*", value)
    return _indent_width(matched.group(0) if matched else "")


def _indent_width(indent: str) -> int:
    return sum(4 if character == "\t" else 1 for character in indent)


def _apply_task_marker(task: ParsedTask, marker: str, value: str) -> None:
    marker_name = marker.upper()
    parsed_date = parse_iso_date(value)
    if marker_name == "SCHEDULED":
        task.scheduled = parsed_date
    elif marker_name == "DEADLINE":
        task.due = parsed_date
    else:
        task.completed = parsed_date
    recurrence = _extract_recurrence(value)
    if recurrence is not None:
        task.recurrence = recurrence


def _extract_priority(value: str) -> str | None:
    matched = _PRIORITY.search(value)
    return matched.group(1) if matched else None


def _extract_recurrence(value: str) -> str | None:
    matched = _RECURRENCE.search(value)
    return matched.group(0) if matched else None


def _property_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).lstrip("#") for item in value if str(item)]
    return [item.lstrip("#") for item in str(value).split() if item]


__all__ = ["parse_logseq"]
