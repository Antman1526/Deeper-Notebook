import re
from typing import ClassVar, Optional

from loguru import logger
from pydantic import Field

from deeper_notebook.database.repository import repo_query
from deeper_notebook.domain.base import ObjectModel, RecordModel


class Transformation(ObjectModel):
    table_name: ClassVar[str] = "transformation"
    name: str
    title: str
    description: str
    prompt: str
    apply_default: bool


# v0.8.88 — built-in "Summary" transformation for opt-in source auto-summary
# (improvement roadmap, Batch 4). Seeded lazily (idempotent get-or-create) the
# first time auto-summary runs, so it works out of the box and is then editable
# in Settings → Transformations.
SUMMARIZE_TRANSFORMATION_NAME = "summarize"
SUMMARIZE_TRANSFORMATION_TITLE = "Summary"
_SUMMARIZE_PROMPT = (
    "Provide a concise summary of the following content in 2-3 short "
    "paragraphs. Capture the main points, key arguments, and conclusions. "
    "Write in clear, neutral prose and do not add information that isn't in "
    "the source."
)


async def get_or_create_summarize_transformation() -> "Transformation":
    """Return the built-in summarize transformation, creating it if absent.

    Idempotent on the common path (returns the existing record). A first-add
    race could in theory create two; that's a harmless cosmetic dup, not a
    correctness problem.
    """
    rows = await repo_query(
        "SELECT * FROM transformation WHERE name = $name LIMIT 1",
        {"name": SUMMARIZE_TRANSFORMATION_NAME},
    )
    if rows:
        return Transformation(**rows[0])

    logger.info("Seeding built-in 'summarize' transformation (auto-summary).")
    transformation = Transformation(
        name=SUMMARIZE_TRANSFORMATION_NAME,
        title=SUMMARIZE_TRANSFORMATION_TITLE,
        description="Auto-generated concise summary of the source's content.",
        prompt=_SUMMARIZE_PROMPT,
        apply_default=False,
    )
    await transformation.save()
    return transformation


# v0.8.91 — built-in "Key Topics" transformation for opt-in key-topics
# extraction (improvement roadmap, later idea). Same lazy get-or-create pattern
# as the summary one; its output is parsed into the source's `topics` field.
KEY_TOPICS_TRANSFORMATION_NAME = "key_topics"
KEY_TOPICS_TRANSFORMATION_TITLE = "Key Topics"
_KEY_TOPICS_PROMPT = (
    "Identify the 5-8 most important topics, themes, or concepts in the "
    "following content. Respond with ONLY a plain bulleted list — one short "
    "topic per line (2-4 words each), no commentary, no numbering, no "
    "explanations."
)
_MAX_TOPICS = 8
_MAX_TOPIC_LEN = 60


async def get_or_create_key_topics_transformation() -> "Transformation":
    """Return the built-in key-topics transformation, creating it if absent."""
    rows = await repo_query(
        "SELECT * FROM transformation WHERE name = $name LIMIT 1",
        {"name": KEY_TOPICS_TRANSFORMATION_NAME},
    )
    if rows:
        return Transformation(**rows[0])

    logger.info("Seeding built-in 'key_topics' transformation.")
    transformation = Transformation(
        name=KEY_TOPICS_TRANSFORMATION_NAME,
        title=KEY_TOPICS_TRANSFORMATION_TITLE,
        description="Auto-extracted key topics/themes for the source.",
        prompt=_KEY_TOPICS_PROMPT,
        apply_default=False,
    )
    await transformation.save()
    return transformation


def parse_topics(text: Optional[str]) -> list[str]:
    """Parse the key-topics LLM output (a bulleted list) into clean topics.

    Strips bullet/number markers, trims, drops empties + over-long lines (which
    are usually the model ignoring the format), de-dupes case-insensitively, and
    caps the count. Pure + testable.
    """
    if not text:
        return []
    topics: list[str] = []
    seen: set[str] = set()
    for raw in str(text).splitlines():
        line = raw.strip()
        # Strip a leading bullet/number marker: -, *, •, "1.", "1)".
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        # Strip surrounding markdown emphasis/quotes.
        line = line.strip("*_`\"' ").strip()
        if not line or len(line) > _MAX_TOPIC_LEN:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(line)
        if len(topics) >= _MAX_TOPICS:
            break
    return topics


class DefaultPrompts(RecordModel):
    record_id: ClassVar[str] = "open_notebook:default_prompts"
    transformation_instructions: Optional[str] = Field(
        None, description="Instructions for executing a transformation"
    )
