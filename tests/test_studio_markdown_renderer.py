from deeper_notebook.studio.renderers import render_artifact_markdown
from deeper_notebook.studio.schemas import parse_artifact_document


def _render(artifact_type: str, document: dict) -> str:
    return render_artifact_markdown(parse_artifact_document(artifact_type, document))


def test_generic_renderer_keeps_sections_bullets_and_citations():
    markdown = _render(
        "report",
        {
            "artifact_type": "report",
            "title": "RAG report",
            "summary": "A grounded overview.",
            "sections": [
                {
                    "heading": "Evidence",
                    "body": "Retrieval reduces unsupported claims.",
                    "bullets": ["Use primary sources"],
                    "citations": ["[S1]"],
                }
            ],
        },
    )

    assert markdown == (
        "# RAG report\n\nA grounded overview.\n\n"
        "## Evidence\n\nRetrieval reduces unsupported claims.\n\n"
        "- Use primary sources\n\nSource: [S1]\n"
    )


def test_flashcard_renderer_matches_existing_viewer_labels():
    markdown = _render(
        "flashcards",
        {
            "artifact_type": "flashcards",
            "title": "Review",
            "cards": [
                {
                    "front": "What is retrieval?",
                    "back": "Finding relevant passages.",
                    "citations": ["[S1]"],
                }
            ],
        },
    )

    assert "## Flashcard 1" in markdown
    assert "Front: What is retrieval?" in markdown
    assert "Back: Finding relevant passages." in markdown
    assert "Source: [S1]" in markdown


def test_quiz_renderer_matches_existing_viewer_labels():
    markdown = _render(
        "quiz",
        {
            "artifact_type": "quiz",
            "title": "Checkpoint",
            "questions": [
                {
                    "prompt": "What happens first?",
                    "options": [
                        {"id": "A", "text": "Retrieve relevant passages"},
                        {"id": "B", "text": "Ignore the sources"},
                    ],
                    "correct_option_id": "A",
                    "explanation": "Grounding starts with retrieval.",
                    "citations": ["[S2]"],
                }
            ],
        },
    )

    assert "## Question 1" in markdown
    assert "A. Retrieve relevant passages" in markdown
    assert "Answer: A" in markdown
    assert "Explanation: Grounding starts with retrieval." in markdown


def test_data_table_renderer_escapes_pipes_and_line_breaks():
    markdown = _render(
        "data_table",
        {
            "artifact_type": "data_table",
            "title": "Comparison",
            "columns": ["Model", "Notes"],
            "rows": [
                {
                    "values": {
                        "Model": "Local | private",
                        "Notes": "Fast\nenough",
                    },
                    "citations": ["[S1]"],
                }
            ],
        },
    )

    assert "| Model | Notes | Source |" in markdown
    assert "| Local \\| private | Fast<br>enough | [S1] |" in markdown


def test_data_table_renderer_appends_citations_to_existing_source_column():
    markdown = _render(
        "data_table",
        {
            "artifact_type": "data_table",
            "title": "Comparison",
            "columns": ["Topic", "Source"],
            "rows": [
                {
                    "values": {
                        "Topic": "Local models",
                        "Source": "Source One",
                    },
                    "citations": ["[S1]"],
                }
            ],
        },
    )

    assert markdown.count("| Topic | Source |") == 1
    assert "| Local models | Source One [S1] |" in markdown


def test_mind_map_renderer_uses_two_space_tree_indentation():
    markdown = _render(
        "mind_map",
        {
            "artifact_type": "mind_map",
            "title": "Knowledge",
            "root": {
                "label": "Root",
                "citations": ["[S1]"],
                "children": [
                    {
                        "label": "Child",
                        "relationship": "supports",
                        "children": [],
                    }
                ],
            },
        },
    )

    assert "- Root [S1]" in markdown
    assert "  - Child (supports)" in markdown


def test_slide_deck_renderer_keeps_notes_and_citations():
    markdown = _render(
        "slide_deck",
        {
            "artifact_type": "slide_deck",
            "title": "RAG briefing",
            "audience": "Engineering leaders",
            "slides": [
                {
                    "title": "Retrieval-Augmented Generation",
                    "bullets": ["Ground answers in evidence"],
                    "speaker_notes": "Explain the retrieval loop.",
                    "visual_direction": "Show source-to-answer flow.",
                    "citations": ["[S1]"],
                }
            ],
        },
    )

    assert "## Slide 1: Retrieval-Augmented Generation" in markdown
    assert "Speaker notes: Explain the retrieval loop." in markdown
    assert "Visual direction: Show source-to-answer flow." in markdown
    assert "Source: [S1]" in markdown


def test_infographic_renderer_keeps_panel_kind_and_metric():
    markdown = _render(
        "infographic",
        {
            "artifact_type": "infographic",
            "title": "Evidence health",
            "orientation": "portrait",
            "panels": [
                {
                    "kind": "metric",
                    "heading": "Grounded claims",
                    "body": "Validated against the source pack.",
                    "value": "92%",
                    "citations": ["[S3]"],
                }
            ],
        },
    )

    assert "Orientation: portrait" in markdown
    assert "## Grounded claims" in markdown
    assert "Type: metric" in markdown
    assert "Value: 92%" in markdown


def test_course_pack_renderer_exposes_modules_lessons_and_assessment():
    markdown = _render(
        "course_pack",
        {
            "artifact_type": "course_pack",
            "title": "RAG onboarding",
            "audience": "New analysts",
            "learning_outcomes": ["Cite every material claim"],
            "modules": [
                {
                    "title": "Grounding",
                    "summary": "Build evidence-first habits.",
                    "lessons": [
                        {
                            "title": "Source selection",
                            "content": "Prefer primary evidence.",
                            "duration_minutes": 20,
                            "exercise": "Rank three candidate sources.",
                            "facilitator_notes": "Discuss trade-offs.",
                            "citations": ["[S1]"],
                        }
                    ],
                }
            ],
            "final_assessment": [
                {
                    "prompt": "Which source is strongest?",
                    "options": [
                        {"id": "A", "text": "Primary documentation"},
                        {"id": "B", "text": "Unsourced summary"},
                    ],
                    "correct_option_id": "A",
                }
            ],
        },
    )

    assert "## Module 1: Grounding" in markdown
    assert "### Lesson 1: Source selection" in markdown
    assert "Duration: 20 minutes" in markdown
    assert "#### Facilitator notes" in markdown
    assert "Discuss trade-offs." in markdown
    assert "## Final Assessment" in markdown


def test_podcast_outline_renderer_keeps_segments_and_takeaways():
    markdown = _render(
        "podcast_outline",
        {
            "artifact_type": "podcast_outline",
            "title": "Evidence hour",
            "cold_open": "Why should an answer earn your trust?",
            "segments": [
                {
                    "title": "The retrieval loop",
                    "beats": ["Find", "Rank", "Answer"],
                    "transition": "Now test the claim.",
                    "citations": ["[S1]"],
                }
            ],
            "takeaways": [
                {"text": "Evidence should stay inspectable.", "citations": ["[S2]"]}
            ],
        },
    )

    assert "## Cold Open" in markdown
    assert "## Segment 1: The retrieval loop" in markdown
    assert "Transition: Now test the claim." in markdown
    assert "- Evidence should stay inspectable. [S2]" in markdown


def test_research_run_renderer_keeps_status_findings_and_gaps():
    markdown = _render(
        "research_run",
        {
            "artifact_type": "research_run",
            "title": "Market scan",
            "objective": "Compare source-grounded notebook tools.",
            "hypotheses": ["Local inference improves privacy"],
            "stages": [
                {
                    "title": "Feature evidence",
                    "status": "incomplete",
                    "findings": [
                        {"text": "Citation UX varies.", "citations": ["[S4]"]}
                    ],
                }
            ],
            "gaps": ["No long-term accuracy benchmark"],
            "next_actions": ["Run a fixed evaluation set"],
        },
    )

    assert "Objective: Compare source-grounded notebook tools." in markdown
    assert "## Stage 1: Feature evidence" in markdown
    assert "Status: incomplete" in markdown
    assert "- Citation UX varies. [S4]" in markdown
    assert "## Evidence Gaps" in markdown
    assert "## Next Actions" in markdown


def test_renderer_output_is_deterministic_and_has_one_trailing_newline():
    document = parse_artifact_document(
        "flashcards",
        {
            "artifact_type": "flashcards",
            "title": "Stable",
            "cards": [{"front": "Q", "back": "A"}],
        },
    )

    first = render_artifact_markdown(document)
    second = render_artifact_markdown(document)

    assert first == second
    assert first.endswith("\n")
    assert not first.endswith("\n\n")
