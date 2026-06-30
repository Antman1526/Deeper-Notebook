from typing import ClassVar, Optional

from loguru import logger
from pydantic import Field

from open_notebook.database.repository import repo_query
from open_notebook.domain.base import ObjectModel, RecordModel


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


class DefaultPrompts(RecordModel):
    record_id: ClassVar[str] = "open_notebook:default_prompts"
    transformation_instructions: Optional[str] = Field(
        None, description="Instructions for executing a transformation"
    )
