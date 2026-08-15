"""Surreal command registration for bounded source visual extraction."""

from __future__ import annotations

from surreal_commands import command

from deeper_notebook.identity import LEGACY_COMMAND_APP
from deeper_notebook.source_visuals.authority import SourceVisualAuthorityError
from deeper_notebook.source_visuals.media import SourceVisualMediaError
from deeper_notebook.source_visuals.service import (
    ExtractSourceVisualInput,
    ExtractSourceVisualOutput,
    SourceVisualService,
)


@command(
    "extract_source_visual",
    app=LEGACY_COMMAND_APP,
    retry={
        "max_attempts": 3,
        "wait_strategy": "exponential_jitter",
        "wait_min": 1,
        "wait_max": 10,
        "stop_on": [SourceVisualAuthorityError, SourceVisualMediaError],
    },
)
async def extract_source_visual_command(
    input_data: ExtractSourceVisualInput,
) -> ExtractSourceVisualOutput:
    return await SourceVisualService().execute(input_data)


__all__ = [
    "ExtractSourceVisualInput",
    "ExtractSourceVisualOutput",
    "extract_source_visual_command",
]
