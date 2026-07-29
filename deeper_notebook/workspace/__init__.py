"""Knowledge-workspace state and persistence."""

from deeper_notebook.workspace.contracts import (
    KnowledgePaneState,
    KnowledgeTabState,
    KnowledgeViewMode,
    KnowledgeWorkspaceDocument,
    PaneLayoutNode,
    SplitDirection,
    SplitLayoutNode,
    default_knowledge_workspace,
)
from deeper_notebook.workspace.persistence import (
    MAX_KNOWLEDGE_WORKSPACE_BYTES,
    WorkspaceStateError,
    knowledge_workspace_path,
    load_knowledge_workspace,
    save_knowledge_workspace,
)

__all__ = [
    "KnowledgePaneState",
    "KnowledgeTabState",
    "KnowledgeViewMode",
    "KnowledgeWorkspaceDocument",
    "MAX_KNOWLEDGE_WORKSPACE_BYTES",
    "PaneLayoutNode",
    "SplitDirection",
    "SplitLayoutNode",
    "WorkspaceStateError",
    "default_knowledge_workspace",
    "knowledge_workspace_path",
    "load_knowledge_workspace",
    "save_knowledge_workspace",
]
