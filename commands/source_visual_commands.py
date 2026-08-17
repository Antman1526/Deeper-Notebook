"""Surreal command registration for bounded source visual extraction."""

# v0.8.99 — deliberately NO `from __future__ import annotations` here.
#
# surreal_commands' @command decorator builds a Pydantic input model from this
# function's signature. Under PEP 563 the annotation is the STRING
# "ExtractSourceVisualInput", and the generated model
# (`extract_source_visual_command_input`) could not resolve it, so
# `.model_json_schema()` raised PydanticUserError "is not fully defined".
#
# The failure was invisible in most runs: any test batch that had already
# imported the type elsewhere populated the namespace and the schema resolved,
# so it only surfaced when this module was imported in isolation. Registration
# itself still succeeded, which is why the queue kept working — but anything
# introspecting command schemas (the registry audit test, and any future
# schema-driven UI or validation) hit an unusable model.
#
# Keeping real class objects in the signature is the smallest fix. If this
# import is ever re-added, call `model_rebuild()` on the generated model with
# this module's namespace instead. See tests/test_v0_8_99_command_schemas.py.

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
