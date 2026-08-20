"""Pure prompt and model-role helpers for Evidence Studio artifacts."""

from __future__ import annotations

_ARTIFACT_TYPE_INSTRUCTIONS: dict[str, str] = {
    "report": "Create a concise executive report with a title, summary, key findings, risks, recommendations, and open questions.",
    "study_guide": "Create a practical study guide with an overview, key concepts, glossary, review questions, and source-grounded examples.",
    "course_pack": "Create an instructor-ready Course Pack in markdown from the provided linked and uploaded source content. Include audience, learning outcomes, prerequisite knowledge, source readiness notes, a module roadmap, timed lesson blocks, hands-on exercises, facilitator notes, learner handouts, knowledge checks, a final assessment, source citations, and follow-up resources. Treat video and audio sources as lesson segments, PDFs and documents as readings or reference modules, and links as external resources or source-backed exercises. Warn when transcript/source text appears thin. Ground every substantive lesson point in citation markers.",
    "training_guide": "Create an instructor-ready Course Pack in markdown from the provided linked and uploaded source content. Include audience, learning outcomes, prerequisite knowledge, source readiness notes, a module roadmap, timed lesson blocks, hands-on exercises, facilitator notes, learner handouts, knowledge checks, a final assessment, source citations, and follow-up resources. Treat video and audio sources as lesson segments, PDFs and documents as readings or reference modules, and links as external resources or source-backed exercises. Warn when transcript/source text appears thin. Ground every substantive lesson point in citation markers. This artifact type is a legacy alias for Course Pack.",
    "briefing": "Create a short briefing with the essential facts, implications, and recommended next actions.",
    "faq": "Create a source-grounded FAQ with direct, useful answers.",
    "timeline": "Create a chronological timeline of source-backed events and milestones.",
    "flashcards": "Create source-grounded flashcards in markdown. Each card must include a front prompt, a back answer, and the source title that supports it.",
    "quiz": "Create a source-grounded quiz in markdown with multiple-choice questions, an answer key, and short explanations tied to the cited sources.",
    "data_table": "Create a source-grounded Data Table in markdown. Return one concise markdown table with columns for Topic, Evidence, Source, Confidence, and Notes. Every evidence cell must include a source marker such as [S1]. Prefer comparable facts, dates, claims, numbers, entities, or decisions that help a reader scan the sources like a spreadsheet.",
    "mind_map": "Create a source-grounded mind map as a nested markdown outline. Start with a central concept, group related branches beneath it, name the relationships between branches, and cite source markers on each major node.",
    "slide_deck": "Create a source-grounded slide deck outline in markdown. Include a title slide, 5-8 numbered slides, concise slide bullets, speaker notes for each slide, and citation markers for source-backed claims.",
    "infographic": "Create a source-grounded infographic brief in markdown. Organize it into clear visual sections, include hierarchy, labels, data callouts, caption text, and citation markers for each major claim.",
    "podcast_outline": "Create a source-grounded podcast outline for an audio overview in markdown. Include a cold open, host segments, key beats, transitions, listener takeaways, questions for discussion, and citation markers for source-backed claims.",
    "research_run": "Create a source-grounded Research Run in markdown. Treat it as a multi-step investigation: state the research objective, list working hypotheses, extract evidence-backed findings, identify contradictions or gaps, propose follow-up questions, and end with recommended next actions. Use citation markers on every evidence-backed claim.",
}

_ARTIFACT_TYPE_MODEL_ROLE: dict[str, str] = {
    "report": "source_synthesis",
    "study_guide": "source_synthesis",
    "course_pack": "source_synthesis",
    "training_guide": "source_synthesis",
    "briefing": "source_synthesis",
    "faq": "source_synthesis",
    "timeline": "source_synthesis",
    "data_table": "source_synthesis",
    "mind_map": "source_synthesis",
    "infographic": "source_synthesis",
    "slide_deck": "source_synthesis",
    "podcast_outline": "source_synthesis",
    "research_run": "source_synthesis",
    "flashcards": "study_fast",
    "quiz": "study_fast",
}


def study_unit_prompt(
    artifact_type: str,
    *,
    plan_goal: str,
    unit_title: str,
    objectives: tuple[str, ...] | list[str],
    prerequisite_unit_ids: tuple[str, ...] | list[str] = (),
    source_ids: tuple[str, ...] | list[str] = (),
    context: str | None = None,
) -> str:
    """Build the bounded steering prompt for one approved study unit.

    The source body remains the responsibility of Evidence Studio's context
    adapter.  This helper contributes only the typed syllabus metadata and a
    caller-bounded steering note, keeping unit generation from becoming a
    second prompt/generation pipeline.
    """
    objective_lines = "\n".join(f"- {item}" for item in objectives)
    prerequisites = ", ".join(prerequisite_unit_ids) or "none"
    linked_sources = ", ".join(source_ids)
    steering = (
        context.strip() if isinstance(context, str) and context.strip() else "none"
    )
    return (
        f"Create a {artifact_type.replace('_', ' ')} for the approved study unit.\n"
        f"Plan goal: {plan_goal}\n"
        f"Unit: {unit_title}\n"
        f"Objectives:\n{objective_lines}\n"
        f"Prerequisite units: {prerequisites}\n"
        f"Linked source IDs: {linked_sources}\n"
        f"Additional learner context (bounded): {steering}\n"
        "Use only the linked source evidence and preserve uncertainty or gaps."
    )


def artifact_instruction(artifact: object) -> str:
    artifact_type = str(getattr(artifact, "artifact_type", ""))
    base = _ARTIFACT_TYPE_INSTRUCTIONS.get(
        artifact_type, "Create a useful source-grounded markdown artifact."
    )
    prompt = getattr(artifact, "prompt", None)
    return f"{base}\n\nUser steering prompt:\n{prompt}" if prompt else base


def artifact_model_role(artifact_type: str) -> str:
    return _ARTIFACT_TYPE_MODEL_ROLE.get(artifact_type, "chat")
