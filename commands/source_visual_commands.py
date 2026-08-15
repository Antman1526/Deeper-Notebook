"""Surreal command registration for bounded source visual extraction."""

from __future__ import annotations

from surreal_commands import command

from deeper_notebook.source_visuals.authority import SourceVisualAuthorityError
from deeper_notebook.source_visuals.media import SourceVisualMediaError
from deeper_notebook.source_visuals.service import (
    ExtractSourceVisualInput,
    ExtractSourceVisualOutput,
    SourceVisualService,
)


@command(
    "extract_source_visual",
    # Persisted queue identity: never derive or rename this literal.
    app="open_notebook",
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
    try:
        return await SourceVisualService().execute(input_data)
    except (SourceVisualAuthorityError, SourceVisualMediaError) as exc:
        # These two error classes are terminal under the command retry policy;
        # preserve a bounded public receipt even if an adapter raises directly.
        error_code = str(getattr(exc, "code", "extraction_failed")).lower()
        return ExtractSourceVisualOutput(
            source_id=input_data.source_id,
            content_sha256=input_data.expected_content_sha256,
            duration_ms=0,
            outcome="failed",
            error_code=error_code,
        )


__all__ = [
    "ExtractSourceVisualInput",
    "ExtractSourceVisualOutput",
    "extract_source_visual_command",
]
