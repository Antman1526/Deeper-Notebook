"""Artifact schema resolution and validation."""

from __future__ import annotations

from typing import Any

from open_notebook.exceptions import InvalidInputError

from .documents import (
    ArtifactDocumentBase,
    CoursePackDocument,
    DataTableDocument,
    FlashcardsDocument,
    GenericDocument,
    InfographicDocument,
    MindMapDocument,
    PodcastOutlineDocument,
    QuizDocument,
    ResearchRunDocument,
    SlideDeckDocument,
)

_SCHEMAS: dict[str, type[ArtifactDocumentBase]] = {
    "report": GenericDocument,
    "study_guide": GenericDocument,
    "course_pack": CoursePackDocument,
    "training_guide": CoursePackDocument,
    "briefing": GenericDocument,
    "faq": GenericDocument,
    "flashcards": FlashcardsDocument,
    "quiz": QuizDocument,
    "data_table": DataTableDocument,
    "mind_map": MindMapDocument,
    "timeline": GenericDocument,
    "infographic": InfographicDocument,
    "slide_deck": SlideDeckDocument,
    "podcast_outline": PodcastOutlineDocument,
    "research_run": ResearchRunDocument,
}


def schema_for_artifact_type(artifact_type: str) -> type[ArtifactDocumentBase]:
    try:
        return _SCHEMAS[artifact_type]
    except KeyError as exc:
        raise InvalidInputError(
            f"Artifact type {artifact_type!r} does not support structured generation"
        ) from exc


def parse_artifact_document(
    artifact_type: str,
    payload: dict[str, Any],
) -> ArtifactDocumentBase:
    schema = schema_for_artifact_type(artifact_type)
    return schema.model_validate(payload)
