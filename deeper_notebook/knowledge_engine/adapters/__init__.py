"""Deterministic source adapters for canonical knowledge projections."""

from __future__ import annotations

from deeper_notebook.knowledge_engine.adapters.base import KnowledgeAdapter
from deeper_notebook.knowledge_engine.adapters.logseq import LogseqKnowledgeAdapter
from deeper_notebook.knowledge_engine.adapters.markdown import MarkdownKnowledgeAdapter
from deeper_notebook.knowledge_engine.adapters.obsidian import ObsidianKnowledgeAdapter
from deeper_notebook.knowledge_engine.adapters.overlay import OverlayKnowledgeAdapter
from deeper_notebook.knowledge_engine.contracts import SourceKind

_ADAPTERS: dict[SourceKind, KnowledgeAdapter] = {
    "overlay": OverlayKnowledgeAdapter(),
    "obsidian": ObsidianKnowledgeAdapter(),
    "logseq": LogseqKnowledgeAdapter(),
    "markdown": MarkdownKnowledgeAdapter(),
}


def adapter_for(source_kind: SourceKind) -> KnowledgeAdapter:
    try:
        return _ADAPTERS[source_kind]
    except KeyError:
        raise ValueError("unsupported knowledge source kind") from None


__all__ = ["KnowledgeAdapter", "adapter_for"]
