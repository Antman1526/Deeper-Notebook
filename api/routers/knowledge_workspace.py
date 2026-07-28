"""Durable API for the local Deeper Notebook knowledge workspace."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from deeper_notebook.workspace import (
    KnowledgeWorkspaceDocument,
    WorkspaceStateError,
    knowledge_workspace_path,
    load_knowledge_workspace,
    save_knowledge_workspace,
)

router = APIRouter()


def _workspace_path() -> Path:
    return knowledge_workspace_path()


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


@router.get("/workspace/knowledge", response_model=KnowledgeWorkspaceDocument)
def get_knowledge_workspace() -> KnowledgeWorkspaceDocument:
    try:
        return load_knowledge_workspace(path=_workspace_path())
    except WorkspaceStateError:
        raise _error(
            status.HTTP_409_CONFLICT,
            "workspace_state_invalid",
        ) from None
    except OSError:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "workspace_state_unavailable",
        ) from None


@router.put("/workspace/knowledge", response_model=KnowledgeWorkspaceDocument)
def put_knowledge_workspace(
    document: KnowledgeWorkspaceDocument,
) -> KnowledgeWorkspaceDocument:
    try:
        save_knowledge_workspace(document, path=_workspace_path())
    except OSError:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "workspace_state_unavailable",
        ) from None
    return document
