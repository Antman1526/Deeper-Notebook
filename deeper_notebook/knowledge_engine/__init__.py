"""Pure contracts for Deeper Notebook's shadow knowledge engine."""

from deeper_notebook.knowledge_engine.capabilities import (
    AuthorityKind,
    KnowledgeCapability,
    capabilities_for,
)
from deeper_notebook.knowledge_engine.identity import (
    canonical_locator,
    engine_record_id,
)

__all__ = [
    "AuthorityKind",
    "KnowledgeCapability",
    "canonical_locator",
    "capabilities_for",
    "engine_record_id",
]
