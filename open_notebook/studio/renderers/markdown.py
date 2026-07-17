"""Deterministic Markdown rendering for Studio artifact documents."""

from __future__ import annotations

from functools import singledispatch

from open_notebook.studio.schemas import (
    ArtifactDocumentBase,
    CoursePackDocument,
    DataTableDocument,
    FlashcardsDocument,
    GenericDocument,
    InfographicDocument,
    MindMapDocument,
    MindMapNode,
    PodcastOutlineDocument,
    QuizDocument,
    QuizQuestion,
    ResearchRunDocument,
    SlideDeckDocument,
)


def _finish(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def _citations(markers: list[str]) -> str:
    return " ".join(markers)


def _cited_text(text: str, markers: list[str]) -> str:
    citations = _citations(markers)
    return f"{text} {citations}" if citations else text


def _source(markers: list[str]) -> str:
    citations = _citations(markers)
    return f"Source: {citations}" if citations else ""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _render_quiz_question(question: QuizQuestion, index: int) -> list[str]:
    parts = [f"## Question {index}", question.prompt]
    parts.append(
        "\n".join(f"{option.id}. {option.text}" for option in question.options)
    )
    parts.append(f"Answer: {question.correct_option_id}")
    if question.explanation:
        parts.append(f"Explanation: {question.explanation}")
    source = _source(question.citations)
    if source:
        parts.append(source)
    return parts


@singledispatch
def render_artifact_markdown(document: ArtifactDocumentBase) -> str:
    raise TypeError(f"Unsupported artifact document: {type(document).__name__}")


@render_artifact_markdown.register
def _(document: GenericDocument) -> str:
    parts = [f"# {document.title}"]
    if document.summary:
        parts.append(document.summary)
    for section in document.sections:
        parts.append(f"## {section.heading}")
        if section.body:
            parts.append(section.body)
        if section.bullets:
            parts.append(_bullets(section.bullets))
        source = _source(section.citations)
        if source:
            parts.append(source)
    return _finish(parts)


@render_artifact_markdown.register
def _(document: FlashcardsDocument) -> str:
    parts = [f"# {document.title}"]
    for index, card in enumerate(document.cards, start=1):
        parts.extend(
            [
                f"## Flashcard {index}",
                f"Front: {card.front}",
                f"Back: {card.back}",
            ]
        )
        source = _source(card.citations)
        if source:
            parts.append(source)
    return _finish(parts)


@render_artifact_markdown.register
def _(document: QuizDocument) -> str:
    parts = [f"# {document.title}"]
    for index, question in enumerate(document.questions, start=1):
        parts.extend(_render_quiz_question(question, index))
    return _finish(parts)


def _escape_table_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\r\n", "<br>").replace(
        "\n", "<br>"
    )


def _append_missing_citations(value: str, markers: list[str]) -> str:
    missing = [marker for marker in markers if marker not in value]
    return _cited_text(value, missing)


@render_artifact_markdown.register
def _(document: DataTableDocument) -> str:
    include_citation_column = "Source" not in document.columns
    columns = [
        *document.columns,
        *(["Source"] if include_citation_column else []),
    ]
    parts = [f"# {document.title}"]
    parts.append("| " + " | ".join(_escape_table_cell(c) for c in columns) + " |")
    parts.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in document.rows:
        values = [
            _escape_table_cell(
                _append_missing_citations(row.values[column], row.citations)
                if column == "Source"
                else row.values[column]
            )
            for column in document.columns
        ]
        if include_citation_column:
            values.append(_citations(row.citations))
        parts.append("| " + " | ".join(values) + " |")
    return _finish([parts[0], "\n".join(parts[1:])])


def _render_mind_map_node(node: MindMapNode, depth: int = 0) -> list[str]:
    if depth >= 8:
        raise ValueError("mind map depth must not exceed 8 levels")
    relationship = f" ({node.relationship})" if node.relationship else ""
    label = _cited_text(f"{node.label}{relationship}", node.citations)
    lines = [f"{'  ' * depth}- {label}"]
    for child in node.children:
        lines.extend(_render_mind_map_node(child, depth + 1))
    return lines


@render_artifact_markdown.register
def _(document: MindMapDocument) -> str:
    return _finish(
        [f"# {document.title}", "\n".join(_render_mind_map_node(document.root))]
    )


@render_artifact_markdown.register
def _(document: SlideDeckDocument) -> str:
    parts = [f"# {document.title}"]
    if document.audience:
        parts.append(f"Audience: {document.audience}")
    for index, slide in enumerate(document.slides, start=1):
        parts.append(f"## Slide {index}: {slide.title}")
        if slide.bullets:
            parts.append(_bullets(slide.bullets))
        if slide.speaker_notes:
            parts.append(f"Speaker notes: {slide.speaker_notes}")
        if slide.visual_direction:
            parts.append(f"Visual direction: {slide.visual_direction}")
        source = _source(slide.citations)
        if source:
            parts.append(source)
    return _finish(parts)


@render_artifact_markdown.register
def _(document: InfographicDocument) -> str:
    parts = [f"# {document.title}", f"Orientation: {document.orientation}"]
    for panel in document.panels:
        parts.extend([f"## {panel.heading}", f"Type: {panel.kind}"])
        if panel.value:
            parts.append(f"Value: {panel.value}")
        if panel.body:
            parts.append(panel.body)
        source = _source(panel.citations)
        if source:
            parts.append(source)
    return _finish(parts)


@render_artifact_markdown.register
def _(document: CoursePackDocument) -> str:
    parts = [
        f"# {document.title}",
        f"Audience: {document.audience}",
        "## Learning Outcomes",
        _bullets(document.learning_outcomes),
    ]
    if document.prerequisites:
        parts.extend(["## Prerequisites", _bullets(document.prerequisites)])
    for module_index, module in enumerate(document.modules, start=1):
        parts.append(f"## Module {module_index}: {module.title}")
        if module.summary:
            parts.append(module.summary)
        for lesson_index, lesson in enumerate(module.lessons, start=1):
            parts.append(f"### Lesson {lesson_index}: {lesson.title}")
            if lesson.duration_minutes:
                parts.append(f"Duration: {lesson.duration_minutes} minutes")
            parts.append(lesson.content)
            if lesson.exercise:
                parts.append(f"Exercise: {lesson.exercise}")
            if lesson.facilitator_notes:
                parts.extend(
                    ["#### Facilitator notes", lesson.facilitator_notes]
                )
            source = _source(lesson.citations)
            if source:
                parts.append(source)
    if document.final_assessment:
        parts.append("## Final Assessment")
        for index, question in enumerate(document.final_assessment, start=1):
            question_parts = _render_quiz_question(question, index)
            question_parts[0] = f"### Question {index}"
            parts.extend(question_parts)
    return _finish(parts)


@render_artifact_markdown.register
def _(document: PodcastOutlineDocument) -> str:
    parts = [f"# {document.title}", "## Cold Open", document.cold_open]
    for index, segment in enumerate(document.segments, start=1):
        parts.append(f"## Segment {index}: {segment.title}")
        if segment.beats:
            parts.append(_bullets(segment.beats))
        if segment.transition:
            parts.append(f"Transition: {segment.transition}")
        source = _source(segment.citations)
        if source:
            parts.append(source)
    if document.takeaways:
        parts.extend(
            [
                "## Takeaways",
                _bullets(
                    [
                        _cited_text(takeaway.text, takeaway.citations)
                        for takeaway in document.takeaways
                    ]
                ),
            ]
        )
    return _finish(parts)


@render_artifact_markdown.register
def _(document: ResearchRunDocument) -> str:
    parts = [f"# {document.title}", f"Objective: {document.objective}"]
    if document.hypotheses:
        parts.extend(["## Hypotheses", _bullets(document.hypotheses)])
    for index, stage in enumerate(document.stages, start=1):
        parts.extend([f"## Stage {index}: {stage.title}", f"Status: {stage.status}"])
        if stage.findings:
            parts.append(
                _bullets(
                    [
                        _cited_text(finding.text, finding.citations)
                        for finding in stage.findings
                    ]
                )
            )
    if document.gaps:
        parts.extend(["## Evidence Gaps", _bullets(document.gaps)])
    if document.next_actions:
        parts.extend(["## Next Actions", _bullets(document.next_actions)])
    return _finish(parts)
