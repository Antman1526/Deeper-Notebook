"""Durable API for the local Deeper Notebook knowledge workspace."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.routing import APIRoute

from deeper_notebook.workspace import (
    MAX_KNOWLEDGE_WORKSPACE_BYTES,
    KnowledgeWorkspaceDocument,
    KnowledgeWorkspaceDocumentV2,
    WorkspaceStateError,
    knowledge_workspace_path,
    load_knowledge_workspace,
    save_knowledge_workspace,
)


class _BoundedWorkspaceRequest(Request):
    async def body(self) -> bytes:
        if hasattr(self, "_body"):
            return self._body

        content_length = self.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_KNOWLEDGE_WORKSPACE_BYTES:
                    raise _error(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        "workspace_request_too_large",
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        received = 0
        async for chunk in self.stream():
            received += len(chunk)
            if received > MAX_KNOWLEDGE_WORKSPACE_BYTES:
                raise _error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "workspace_request_too_large",
                )
            chunks.append(chunk)
        self._body = b"".join(chunks)
        return self._body


class _BoundedWorkspaceRoute(APIRoute):
    def get_route_handler(
        self,
    ) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def bounded_route_handler(request: Request) -> Response:
            bounded_request = _BoundedWorkspaceRequest(
                request.scope,
                request.receive,
            )
            return await original_route_handler(bounded_request)

        return bounded_route_handler


router = APIRouter(route_class=_BoundedWorkspaceRoute)


def _workspace_path() -> Path:
    return knowledge_workspace_path()


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


@router.get("/workspace/knowledge", response_model=KnowledgeWorkspaceDocumentV2)
def get_knowledge_workspace() -> KnowledgeWorkspaceDocumentV2:
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


@router.put("/workspace/knowledge", response_model=KnowledgeWorkspaceDocumentV2)
def put_knowledge_workspace(
    document: KnowledgeWorkspaceDocument | KnowledgeWorkspaceDocumentV2,
) -> KnowledgeWorkspaceDocumentV2:
    try:
        return save_knowledge_workspace(document, path=_workspace_path())
    except WorkspaceStateError:
        raise _error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "workspace_request_too_large",
        ) from None
    except OSError:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "workspace_state_unavailable",
        ) from None
