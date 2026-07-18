"""Versioned, model-independent Evidence Studio document contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CitationMarker = Annotated[str, Field(pattern=r"^\[S[1-9]\d*\]$")]


class ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactDocumentBase(ArtifactModel):
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=240)


class CitedText(ArtifactModel):
    text: str = Field(min_length=1)
    citations: list[CitationMarker] = Field(default_factory=list)


class ArtifactSection(ArtifactModel):
    heading: str = Field(min_length=1)
    body: str = ""
    bullets: list[str] = Field(default_factory=list)
    citations: list[CitationMarker] = Field(default_factory=list)


class GenericDocument(ArtifactDocumentBase):
    artifact_type: Literal[
        "report",
        "study_guide",
        "briefing",
        "faq",
        "timeline",
    ]
    summary: str = ""
    sections: list[ArtifactSection] = Field(min_length=1)


class Flashcard(ArtifactModel):
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    citations: list[CitationMarker] = Field(default_factory=list)


class FlashcardsDocument(ArtifactDocumentBase):
    artifact_type: Literal["flashcards"] = "flashcards"
    cards: list[Flashcard] = Field(min_length=1)


class QuizOption(ArtifactModel):
    id: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1)


class QuizQuestion(ArtifactModel):
    prompt: str = Field(min_length=1)
    options: list[QuizOption] = Field(min_length=2)
    correct_option_id: str = Field(min_length=1)
    explanation: str = ""
    citations: list[CitationMarker] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_correct_option(self) -> "QuizQuestion":
        option_ids = {option.id for option in self.options}
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must match an option id")
        if len(option_ids) != len(self.options):
            raise ValueError("quiz option ids must be unique")
        return self


class QuizDocument(ArtifactDocumentBase):
    artifact_type: Literal["quiz"] = "quiz"
    questions: list[QuizQuestion] = Field(min_length=1)


class DataTableRow(ArtifactModel):
    values: dict[str, str]
    citations: list[CitationMarker] = Field(default_factory=list)


class DataTableDocument(ArtifactDocumentBase):
    artifact_type: Literal["data_table"] = "data_table"
    columns: list[str] = Field(min_length=1)
    rows: list[DataTableRow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_row_columns(self) -> "DataTableDocument":
        columns = set(self.columns)
        if len(columns) != len(self.columns):
            raise ValueError("data table columns must be unique")
        for row in self.rows:
            if set(row.values) != columns:
                raise ValueError("data table row keys must match columns")
        return self


class MindMapNode(ArtifactModel):
    label: str = Field(min_length=1)
    relationship: str = ""
    citations: list[CitationMarker] = Field(default_factory=list)
    children: list["MindMapNode"] = Field(default_factory=list)


class MindMapDocument(ArtifactDocumentBase):
    artifact_type: Literal["mind_map"] = "mind_map"
    root: MindMapNode

    @model_validator(mode="after")
    def validate_depth(self) -> "MindMapDocument":
        def depth(node: MindMapNode) -> int:
            return 1 + max((depth(child) for child in node.children), default=0)

        if depth(self.root) > 8:
            raise ValueError("mind map depth must not exceed 8 levels")
        return self


class Slide(ArtifactModel):
    title: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)
    speaker_notes: str = ""
    visual_direction: str = ""
    citations: list[CitationMarker] = Field(default_factory=list)


class SlideDeckDocument(ArtifactDocumentBase):
    artifact_type: Literal["slide_deck"] = "slide_deck"
    audience: str = ""
    slides: list[Slide] = Field(min_length=1, max_length=40)


class InfographicPanel(ArtifactModel):
    kind: Literal["text", "metric", "timeline", "comparison", "process", "chart"]
    heading: str = Field(min_length=1)
    body: str = ""
    value: str = ""
    citations: list[CitationMarker] = Field(default_factory=list)


class InfographicDocument(ArtifactDocumentBase):
    artifact_type: Literal["infographic"] = "infographic"
    orientation: Literal["portrait", "landscape", "square"] = "portrait"
    panels: list[InfographicPanel] = Field(min_length=1, max_length=20)


class CourseLesson(ArtifactModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    duration_minutes: int | None = Field(default=None, ge=1, le=480)
    exercise: str = ""
    facilitator_notes: str = ""
    citations: list[CitationMarker] = Field(default_factory=list)


class CourseModule(ArtifactModel):
    title: str = Field(min_length=1)
    summary: str = ""
    lessons: list[CourseLesson] = Field(min_length=1)


class CoursePackDocument(ArtifactDocumentBase):
    artifact_type: Literal["course_pack", "training_guide"]
    audience: str = Field(min_length=1)
    learning_outcomes: list[str] = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    modules: list[CourseModule] = Field(min_length=1)
    final_assessment: list[QuizQuestion] = Field(default_factory=list)


class PodcastSegment(ArtifactModel):
    title: str = Field(min_length=1)
    beats: list[str] = Field(default_factory=list)
    transition: str = ""
    citations: list[CitationMarker] = Field(default_factory=list)


class PodcastOutlineDocument(ArtifactDocumentBase):
    artifact_type: Literal["podcast_outline"] = "podcast_outline"
    cold_open: str = Field(min_length=1)
    segments: list[PodcastSegment] = Field(min_length=1)
    takeaways: list[CitedText] = Field(default_factory=list)


class ResearchStage(ArtifactModel):
    title: str = Field(min_length=1)
    findings: list[CitedText] = Field(default_factory=list)
    status: Literal["complete", "incomplete", "blocked"] = "complete"


class ResearchSourcePosition(ArtifactModel):
    """One source's cited position on a normalized research claim."""

    source_id: str = Field(min_length=1)
    claim: str = Field(min_length=1, max_length=2000)
    position: Literal["supports", "contradicts", "unresolved"]
    citations: list[CitationMarker] = Field(min_length=1)


class ResearchAgreement(ArtifactModel):
    """A claim independently supported by at least two cited sources."""

    subject: str = Field(min_length=1, max_length=500)
    predicate: str = Field(min_length=1, max_length=1000)
    positions: list[ResearchSourcePosition] = Field(min_length=2)


class ResearchContradiction(ArtifactModel):
    """Cited source positions whose material values or polarity conflict."""

    subject: str = Field(min_length=1, max_length=500)
    predicate: str = Field(min_length=1, max_length=1000)
    values: list[str] = Field(min_length=2, max_length=20)
    positions: list[ResearchSourcePosition] = Field(min_length=2)


class ResearchRunDocument(ArtifactDocumentBase):
    artifact_type: Literal["research_run"] = "research_run"
    objective: str = Field(min_length=1)
    hypotheses: list[str] = Field(default_factory=list)
    stages: list[ResearchStage] = Field(min_length=1)
    # These additive defaults preserve every schema-v1 Research Run payload
    # created before source-comparison output existed.
    agreements: list[ResearchAgreement] = Field(default_factory=list)
    contradictions: list[ResearchContradiction] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


ArtifactDocument = Annotated[
    GenericDocument
    | FlashcardsDocument
    | QuizDocument
    | DataTableDocument
    | MindMapDocument
    | SlideDeckDocument
    | InfographicDocument
    | CoursePackDocument
    | PodcastOutlineDocument
    | ResearchRunDocument,
    Field(discriminator="artifact_type"),
]
