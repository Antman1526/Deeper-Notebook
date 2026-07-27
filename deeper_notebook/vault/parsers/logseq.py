"""Logseq outliner parsing with hierarchy and task semantics."""

from __future__ import annotations

import re
from datetime import date

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
    split_property_value,
)

_BLOCK = re.compile(r"^([ \t]*)[-*+][ \t]+(.*)$")
_PROPERTY = re.compile(r"^([ \t]*)([A-Za-z0-9_.-]{1,128})::[ \t]*(.*)$")
_TASK = re.compile(
    r"^(TODO|DOING|DONE|CANCELED|CANCELLED|NOW|LATER|WAITING)\b[ \t]*(.*)$"
)
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_MARKER = re.compile(
    r"^[ \t]*(SCHEDULED|DEADLINE|COMPLETED|CLOSED):[ \t]*(.*)$",
    re.IGNORECASE,
)
_INLINE_MARKER = re.compile(
    r"\b(SCHEDULED|DEADLINE|COMPLETED|CLOSED):[ \t]*"
    r"(<[^>\r\n]{1,256}>|\[[^\]\r\n]{1,256}\])",
    re.IGNORECASE,
)
_PRIORITY = re.compile(r"\[#([A-Za-z0-9_-]{1,32})\]")
_RECURRENCE = re.compile(r"(?:\.\+|\+\+|\+)\d+[hdwmy]\b", re.IGNORECASE)
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
    task_by_block: dict[str, ParsedTask] = {}
    page_properties_open = True
    fence_marker: tuple[str, int] | None = None
    scan_jobs: list[tuple[SourceLine, str | None]] = []

    for line in source.body_lines():
        if not line.content.strip():
            continue
        fence_match = _FENCE.match(line.content)
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
            accumulator.blocks.append(block)
            if (
                fence_match is not None
                and fence_match.group(1)[0] == fence_marker[0]
                and len(fence_match.group(1)) >= fence_marker[1]
            ):
                fence_marker = None
            continue
        if fence_match is not None:
            parent_id = block_stack[-1][1] if block_stack else None
            block = make_block(
                relative_path=relative_path,
                parent_id=parent_id,
                position=len(accumulator.blocks),
                block_kind="code",
                line=line,
                plain_text=line.content,
            )
            accumulator.blocks.append(block)
            fence_marker = (fence_match.group(1)[0], len(fence_match.group(1)))
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
                task = task_by_block.get(owner_id)
                lowered = key.lower()
                if lowered == "id" and isinstance(value, str):
                    owner.stable_source_id = value
                elif lowered == "priority" and task is not None:
                    task.priority = str(value)
                elif lowered in {"tags", "tag"} and task is not None:
                    task.tags = _property_tags(value)
                scan_jobs.append((line, owner_id))
                continue

        marker_match = _MARKER.match(line.content)
        if marker_match and accumulator.blocks:
            indent = _leading_indent(line.content)
            owner_id = _owner_at_indent(block_stack, indent)
            task = task_by_block.get(owner_id or "")
            if task is not None:
                _apply_task_marker(task, marker_match.group(1), marker_match.group(2))
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
        accumulator.blocks.append(block)
        block_by_id[block.parser_id] = block
        block_stack.append((indent, block.parser_id))

        if status:
            task_text = task_match.group(2)
            priority = _extract_priority(task_text)
            recurrence = _extract_recurrence(task_text)
            task = ParsedTask(
                block_parser_id=block.parser_id,
                status=status,
                priority=priority,
                recurrence=recurrence,
                tags=[],
            )
            for marker in _INLINE_MARKER.finditer(task_text):
                _apply_task_marker(task, marker.group(1), marker.group(2))
            accumulator.tasks.append(task)
            task_by_block[block.parser_id] = task

        scan_jobs.append((line, block.parser_id))

    _scan_queued_regions(accumulator, scan_jobs)
    for task in accumulator.tasks:
        extracted_tags = [
            link.target_text
            for link in accumulator.links
            if link.link_kind == "tag"
            and link.source_block_parser_id == task.block_parser_id
        ]
        task.tags = ordered_unique(task.tags + extracted_tags)
    accumulator.tags = ordered_unique(accumulator.tags)
    return accumulator


def _scan_queued_regions(
    accumulator: ParseAccumulator,
    jobs: list[tuple[SourceLine, str | None]],
) -> None:
    current_lines: list[SourceLine] = []
    current_block_id: str | None = None

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
