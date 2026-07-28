"""Strict parser contracts for canonical Markdown vault projections."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VaultFormat = Literal["obsidian", "logseq", "mixed", "markdown"]
VaultState = Literal[
    "disconnected",
    "scanning",
    "ready-read-only",
    "ready-write-enabled",
    "stale",
    "conflict",
    "degraded",
    "unavailable",
]
VaultFileState = Literal[
    "pending",
    "parsed",
    "unsupported",
    "invalid",
    "conflict",
    "missing",
]
TaskStatus = Literal["todo", "doing", "done", "canceled", "unknown"]


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _SourceSpan(_StrictContract):
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_source_span(self) -> "_SourceSpan":
        if self.source_end < self.source_start:
            raise ValueError("source_end must be greater than or equal to source_start")
        return self


class ParsedBlock(_SourceSpan):
    parser_id: str
    parent_parser_id: str | None = None
    position: int = Field(ge=0)
    stable_source_id: str | None = None
    block_kind: str
    markdown: str
    plain_text: str
    properties: dict[str, Any] = Field(default_factory=dict)
    task_state: TaskStatus | None = None
    heading_path: list[str] = Field(default_factory=list)


class ParsedLink(_SourceSpan):
    source_block_parser_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    alias: str | None = None
    link_kind: Literal["wikilink", "markdown", "embed", "tag", "block-ref"]


class ParsedTask(_StrictContract):
    block_parser_id: str
    status: TaskStatus
    scheduled: date | None = None
    due: date | None = None
    completed: date | None = None
    priority: str | None = None
    recurrence: str | None = None
    tags: list[str] = Field(default_factory=list)


class ParsedEmbed(_SourceSpan):
    source_block_parser_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None


class ParsedDocument(_StrictContract):
    relative_path: str
    source_format: VaultFormat
    title: str
    markdown: str
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    blocks: list[ParsedBlock] = Field(default_factory=list)
    links: list[ParsedLink] = Field(default_factory=list)
    tasks: list[ParsedTask] = Field(default_factory=list)
    embeds: list[ParsedEmbed] = Field(default_factory=list)
    content_hash: str
    encoding: str = "utf-8"
    newline: Literal["lf", "crlf", "mixed", "none"]

    @model_validator(mode="after")
    def validate_source_spans_are_byte_offsets(self) -> "ParsedDocument":
        try:
            source_size = len(self.markdown.encode(self.encoding))
        except LookupError as exc:
            raise ValueError(f"unknown source encoding: {self.encoding}") from exc

        for collection in (self.blocks, self.links, self.embeds):
            for item in collection:
                if item.source_end > source_size:
                    raise ValueError(
                        "source span is outside the original file bytes: "
                        f"{item.source_start}:{item.source_end} > {source_size}"
                    )
        return self


__all__ = [
    "ParsedBlock",
    "ParsedDocument",
    "ParsedEmbed",
    "ParsedLink",
    "ParsedTask",
    "TaskStatus",
    "VaultFileState",
    "VaultFormat",
    "VaultState",
]
