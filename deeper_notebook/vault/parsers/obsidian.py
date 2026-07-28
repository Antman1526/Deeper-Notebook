"""Obsidian Markdown projection parser."""

from __future__ import annotations

from deeper_notebook.vault.parsers.common import DecodedSource
from deeper_notebook.vault.parsers.markdown import (
    ParseAccumulator,
    parse_markdown_blocks,
)


def parse_obsidian(relative_path: str, source: DecodedSource) -> ParseAccumulator:
    return parse_markdown_blocks(relative_path, source, obsidian=True)


__all__ = ["parse_obsidian"]
