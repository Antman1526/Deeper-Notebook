"""Bounded, byte-aware helpers shared by Markdown vault parsers."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, NoReturn

import yaml
from yaml.events import AliasEvent

from deeper_notebook.vault.contracts import ParsedBlock

DEFAULT_MAX_MARKDOWN_BYTES = 10 * 1024 * 1024
MAX_CONFIGURED_MARKDOWN_BYTES = 100 * 1024 * 1024
MAX_FRONTMATTER_BYTES = 256 * 1024
MAX_FRONTMATTER_DEPTH = 20
MAX_FRONTMATTER_NODES = 10_000
MAX_SOURCE_LINES = 100_000
MAX_STRUCTURAL_LINES = 50_000
UTF8_BOM = b"\xef\xbb\xbf"

_SAFE_MESSAGES = {
    "file_too_large": "Markdown file exceeds the configured parser limit.",
    "unsupported_encoding": "Markdown must use UTF-8 encoding.",
    "invalid_frontmatter": "YAML frontmatter is invalid.",
    "frontmatter_not_mapping": "YAML frontmatter must be a mapping.",
    "frontmatter_too_large": "YAML frontmatter exceeds the parser limit.",
    "frontmatter_too_deep": "YAML frontmatter nesting exceeds the parser limit.",
    "frontmatter_alias": "YAML aliases are not accepted.",
    "frontmatter_not_json_safe": "YAML frontmatter contains an unsupported value.",
    "invalid_format_mode": "Vault format mode is invalid.",
    "invalid_document": "Markdown structure could not be projected safely.",
    "projection_too_large": "Markdown projection exceeds the parser limit.",
}


class VaultParseError(ValueError):
    """Typed parser error whose rendering never includes source data or paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_SAFE_MESSAGES.get(code, "Markdown parsing failed."))


@dataclass(frozen=True, slots=True)
class SourceLine:
    """One decoded line plus its exact offsets in the original byte stream."""

    number: int
    source_start: int
    source_end: int
    markdown: str
    content: str

    def span_for_chars(self, start: int, end: int) -> tuple[int, int]:
        prefix = self.markdown[:start].encode("utf-8")
        matched = self.markdown[start:end].encode("utf-8")
        source_start = self.source_start + len(prefix)
        return source_start, source_start + len(matched)


@dataclass(frozen=True, slots=True)
class SourceRegion:
    """A possibly multiline source slice with original byte coordinates."""

    source_start: int
    source_end: int
    markdown: str
    content: str

    def span_for_chars(self, start: int, end: int) -> tuple[int, int]:
        prefix = self.markdown[:start].encode("utf-8")
        matched = self.markdown[start:end].encode("utf-8")
        source_start = self.source_start + len(prefix)
        return source_start, source_start + len(matched)


@dataclass(frozen=True, slots=True)
class DecodedSource:
    raw: bytes
    markdown: str
    encoding: str
    newline: str
    bom_size: int
    body_start: int
    properties: dict[str, Any]

    @property
    def body_markdown(self) -> str:
        return self.raw[self.body_start :].decode("utf-8")

    def body_lines(self) -> list[SourceLine]:
        lines: list[SourceLine] = []
        cursor = self.body_start
        for number, raw_line in enumerate(
            self.raw[self.body_start :].splitlines(keepends=True)
        ):
            source_end = cursor + len(raw_line)
            markdown = raw_line.decode("utf-8")
            content = markdown.rstrip("\r\n")
            lines.append(
                SourceLine(
                    number=number,
                    source_start=cursor,
                    source_end=source_end,
                    markdown=markdown,
                    content=content,
                )
            )
            cursor = source_end
        if cursor < len(self.raw):
            raw_line = self.raw[cursor:]
            markdown = raw_line.decode("utf-8")
            lines.append(
                SourceLine(
                    number=len(lines),
                    source_start=cursor,
                    source_end=len(self.raw),
                    markdown=markdown,
                    content=markdown.rstrip("\r\n"),
                )
            )
        return lines


def fail(code: str) -> NoReturn:
    raise VaultParseError(code)


def configured_max_markdown_bytes(explicit: int | None) -> int:
    if explicit is not None:
        if isinstance(explicit, bool) or explicit <= 0:
            return DEFAULT_MAX_MARKDOWN_BYTES
        return min(explicit, MAX_CONFIGURED_MARKDOWN_BYTES)

    raw = os.getenv("DN_VAULT_MAX_MARKDOWN_BYTES")
    if raw is None:
        return DEFAULT_MAX_MARKDOWN_BYTES
    try:
        value = int(raw, 10)
    except (TypeError, ValueError):
        return DEFAULT_MAX_MARKDOWN_BYTES
    if value <= 0:
        return DEFAULT_MAX_MARKDOWN_BYTES
    return min(value, MAX_CONFIGURED_MARKDOWN_BYTES)


def decode_source(
    raw: bytes, *, max_markdown_bytes: int | None = None
) -> DecodedSource:
    limit = configured_max_markdown_bytes(max_markdown_bytes)
    if len(raw) > limit:
        fail("file_too_large")

    bom_size = len(UTF8_BOM) if raw.startswith(UTF8_BOM) else 0
    encoded_markdown = raw[bom_size:]
    _preflight_source_structure(encoded_markdown)
    try:
        markdown = encoded_markdown.decode("utf-8")
    except UnicodeDecodeError:
        fail("unsupported_encoding")

    properties, body_start = _parse_frontmatter(raw, bom_size)
    return DecodedSource(
        raw=raw,
        markdown=markdown,
        encoding="utf-8-sig" if bom_size else "utf-8",
        newline=detect_newline(encoded_markdown),
        bom_size=bom_size,
        body_start=body_start,
        properties=properties,
    )


def detect_newline(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    without_crlf = raw.replace(b"\r\n", b"")
    lf = without_crlf.count(b"\n")
    cr = without_crlf.count(b"\r")
    if not crlf and not lf and not cr:
        return "none"
    if crlf and not lf and not cr:
        return "crlf"
    if lf and not crlf and not cr:
        return "lf"
    return "mixed"


def _preflight_source_structure(raw: bytes) -> None:
    if not raw:
        return
    line_count = 0
    nonblank_count = 0
    line_has_content = False
    cursor = 0
    while cursor < len(raw):
        byte = raw[cursor]
        if byte in {10, 13}:
            line_count += 1
            if line_has_content:
                nonblank_count += 1
            if byte == 13 and cursor + 1 < len(raw) and raw[cursor + 1] == 10:
                cursor += 1
            line_has_content = False
            if line_count > MAX_SOURCE_LINES or nonblank_count > MAX_STRUCTURAL_LINES:
                fail("projection_too_large")
        elif byte not in {9, 32}:
            line_has_content = True
        cursor += 1
    if raw[-1] not in {10, 13}:
        line_count += 1
        if line_has_content:
            nonblank_count += 1
    if line_count > MAX_SOURCE_LINES or nonblank_count > MAX_STRUCTURAL_LINES:
        fail("projection_too_large")


def _parse_frontmatter(raw: bytes, bom_size: int) -> tuple[dict[str, Any], int]:
    lines = raw[bom_size:].splitlines(keepends=True)
    if not lines or lines[0].rstrip(b"\r\n") != b"---":
        return {}, bom_size

    cursor = bom_size + len(lines[0])
    frontmatter_start = cursor
    closing_end: int | None = None
    closing_start: int | None = None
    for raw_line in lines[1:]:
        next_cursor = cursor + len(raw_line)
        if raw_line.rstrip(b"\r\n") == b"---":
            closing_start = cursor
            closing_end = next_cursor
            break
        cursor = next_cursor
    if closing_start is None or closing_end is None:
        fail("invalid_frontmatter")

    frontmatter_bytes = raw[frontmatter_start:closing_start]
    if len(frontmatter_bytes) > MAX_FRONTMATTER_BYTES:
        fail("frontmatter_too_large")
    try:
        frontmatter_text = frontmatter_bytes.decode("utf-8")
        if any(
            isinstance(event, AliasEvent)
            for event in yaml.parse(frontmatter_text, Loader=yaml.SafeLoader)
        ):
            fail("frontmatter_alias")
        loaded = yaml.safe_load(frontmatter_text)
    except VaultParseError:
        raise
    except RecursionError:
        fail("frontmatter_too_deep")
    except (UnicodeDecodeError, yaml.YAMLError, TypeError, ValueError):
        fail("invalid_frontmatter")

    if not isinstance(loaded, Mapping):
        fail("frontmatter_not_mapping")
    normalized = _normalize_yaml(
        loaded,
        depth=0,
        active_ids=set(),
        seen_container_ids=set(),
        node_count=[0],
    )
    if not isinstance(normalized, dict):
        fail("frontmatter_not_mapping")
    return normalized, closing_end


def _normalize_yaml(
    value: Any,
    *,
    depth: int,
    active_ids: set[int],
    seen_container_ids: set[int],
    node_count: list[int],
) -> Any:
    node_count[0] += 1
    if node_count[0] > MAX_FRONTMATTER_NODES:
        fail("frontmatter_not_json_safe")
    if depth > MAX_FRONTMATTER_DEPTH:
        fail("frontmatter_too_deep")

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            fail("frontmatter_not_json_safe")
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, (Mapping, list)):
        identity = id(value)
        if identity in active_ids or identity in seen_container_ids:
            fail("frontmatter_alias")
        active_ids.add(identity)
        seen_container_ids.add(identity)
        try:
            if isinstance(value, Mapping):
                normalized_mapping: dict[str, Any] = {}
                for key, child in value.items():
                    if not isinstance(key, str):
                        fail("frontmatter_not_json_safe")
                    normalized_mapping[key] = _normalize_yaml(
                        child,
                        depth=depth + 1,
                        active_ids=active_ids,
                        seen_container_ids=seen_container_ids,
                        node_count=node_count,
                    )
                return normalized_mapping
            return [
                _normalize_yaml(
                    child,
                    depth=depth + 1,
                    active_ids=active_ids,
                    seen_container_ids=seen_container_ids,
                    node_count=node_count,
                )
                for child in value
            ]
        finally:
            active_ids.remove(identity)

    fail("frontmatter_not_json_safe")


def make_parser_id(
    relative_path: str,
    parent_id: str | None,
    position: int,
    block_kind: str,
    markdown: str,
) -> str:
    payload = (
        f"{relative_path}\0{parent_id or ''}\0{position}\0{block_kind}\0{markdown}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def make_block(
    *,
    relative_path: str,
    parent_id: str | None,
    position: int,
    block_kind: str,
    line: SourceLine | SourceRegion,
    plain_text: str,
    properties: dict[str, Any] | None = None,
    stable_source_id: str | None = None,
    task_state: str | None = None,
    heading_path: list[str] | None = None,
) -> ParsedBlock:
    parser_id = make_parser_id(
        relative_path,
        parent_id,
        position,
        block_kind,
        line.markdown,
    )
    return ParsedBlock(
        parser_id=parser_id,
        parent_parser_id=parent_id,
        position=position,
        stable_source_id=stable_source_id,
        block_kind=block_kind,
        markdown=line.markdown,
        plain_text=plain_text,
        properties=properties or {},
        task_state=task_state,
        heading_path=heading_path or [],
        source_start=line.source_start,
        source_end=line.source_end,
    )


_PLAIN_PREFIX = re.compile(
    r"^\s*(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX-]\]\s+)?|>\s*|\d+[.)]\s+)"
)
_EXPLICIT_BLOCK_ID = re.compile(r"\s+\^([A-Za-z0-9][\w-]*)\s*$")


def plain_text(markdown: str) -> str:
    text = markdown.rstrip("\r\n")
    text = _PLAIN_PREFIX.sub("", text)
    text = _EXPLICIT_BLOCK_ID.sub("", text)
    return text.strip()


def explicit_block_id(markdown: str) -> str | None:
    matched = _EXPLICIT_BLOCK_ID.search(markdown.rstrip("\r\n"))
    return matched.group(1) if matched else None


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


__all__ = [
    "DecodedSource",
    "SourceLine",
    "SourceRegion",
    "VaultParseError",
    "decode_source",
    "explicit_block_id",
    "fail",
    "make_block",
    "make_parser_id",
    "ordered_unique",
    "plain_text",
]
