"""Knowledge-workspace state and persistence."""

from deeper_notebook.workspace.contracts import (
    KnowledgePaneState,
    KnowledgeTabState,
    KnowledgeViewMode,
    KnowledgeWorkspaceDocument,
    KnowledgeWorkspaceDocumentV2,
    PaneLayoutNode,
    SplitDirection,
    SplitLayoutNode,
    default_knowledge_workspace,
    default_knowledge_workspace_v2,
    migrate_workspace_v1,
    parse_workspace_document,
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
    "KnowledgeWorkspaceDocumentV2",
    "MAX_KNOWLEDGE_WORKSPACE_BYTES",
    "PaneLayoutNode",
    "SplitDirection",
    "SplitLayoutNode",
    "WorkspaceStateError",
    "default_knowledge_workspace",
    "default_knowledge_workspace_v2",
    "knowledge_workspace_path",
    "load_knowledge_workspace",
    "migrate_workspace_v1",
    "parse_workspace_document",
    "save_knowledge_workspace",
]
