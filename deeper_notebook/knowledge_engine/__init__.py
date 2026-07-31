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
from deeper_notebook.knowledge_engine.repository import KnowledgePageIdentity

__all__ = [
    "AuthorityKind",
    "KnowledgeCapability",
    "KnowledgePageIdentity",
    "canonical_locator",
    "capabilities_for",
    "engine_record_id",
]
