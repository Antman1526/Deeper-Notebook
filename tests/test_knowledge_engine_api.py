"""Read-only, redacted API contracts for the unified knowledge engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deeper_notebook.knowledge_engine.capabilities import capabilities_for
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument
from deeper_notebook.knowledge_engine.repository import (
    EngineProjectionStatus,
    KnowledgeRepositoryError,
)


def _document(*, document_id: str = "knowledge_engine_document:one") -> KnowledgeDocument:
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    return KnowledgeDocument(
        id=document_id,
        space_id="knowledge_engine_space:primary",
        source_native_id="vault_file:one",
        authority_kind="external_read_only",
        relative_locator="Projects/Plan.md",
        document_kind="note",
        title="Plan",
        normalized_body="# Plan\nPrivate local page\n",
        properties={"private_root": "/Users/Antman/hidden"},
        tags=["plan"],
        content_hash="a" * 64,
        source_revision_id="knowledge_engine_revision:one",
        provenance="obsidian",
        availability="available",
        parse_state="ready",
        capabilities=sorted(capabilities_for("external_read_only", "note")),
        created_at=now,
        observed_at=now,
        updated_at=now,
    )


class _EngineService:
    def __init__(self) -> None:
        self.document = _document()
        self.status_result: EngineProjectionStatus | Exception = EngineProjectionStatus(
            projected=3,
            unchanged=2,
            failed=1,
        )
        self.document_result: KnowledgeDocument | Exception = self.document
        self.list_result: list[KnowledgeDocument] | Exception = [self.document]
        self.list_requests: list[tuple[str | None, int, int]] = []

    async def status(self) -> EngineProjectionStatus:
        if isinstance(self.status_result, Exception):
            raise self.status_result
        return self.status_result

    async def get_document(self, document_id: str) -> KnowledgeDocument:
        if isinstance(self.document_result, Exception):
            raise self.document_result
        if document_id != self.document.id:
            raise LookupError("private document lookup detail")
        return self.document_result

    async def list_documents(
        self, *, space_id: str | None, limit: int, offset: int
    ) -> list[KnowledgeDocument]:
        self.list_requests.append((space_id, limit, offset))
        if isinstance(self.list_result, Exception):
            raise self.list_result
        return self.list_result[offset : offset + limit]


@pytest.fixture()
def app_with_engine() -> FastAPI:
    from api.routers.knowledge_engine import router

    app = FastAPI()
    app.state.knowledge_engine_service = _EngineService()
    app.include_router(router, prefix="/api/deeper-notebook")
    return app


@pytest.fixture()
def valid_document_response():
    from api.schemas.knowledge_engine import KnowledgeDocumentDetailResponse

    document = _document()
    return KnowledgeDocumentDetailResponse(
        id=document.id,
        space_id=document.space_id,
        relative_locator=document.relative_locator,
        title=document.title,
        kind=document.document_kind,
        source_hash=document.content_hash,
        source_revision_id=document.source_revision_id,
        provenance=document.provenance,
        authority_kind=document.authority_kind,
        availability=document.availability,
        state=document.parse_state,
        capabilities=document.capabilities,
        normalized_body=document.normalized_body,
    )


@pytest.mark.asyncio
async def test_diagnostic_routes_are_read_only(app_with_engine: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        status = await client.get("/api/deeper-notebook/knowledge-engine/status")
        documents = await client.get(
            "/api/deeper-notebook/knowledge-engine/documents"
        )
    assert status.status_code == 200
    assert documents.status_code == 200
    paths = app_with_engine.openapi()["paths"]
    engine_paths = {
        path: set(methods)
        for path, methods in paths.items()
        if "/knowledge-engine/" in path
    }
    assert engine_paths
    assert all(methods <= {"get", "parameters"} for methods in engine_paths.values())


def test_wire_contract_never_contains_absolute_root(valid_document_response) -> None:
    serialized = valid_document_response.model_dump_json()
    assert "/Users/" not in serialized
    assert "root_path" not in serialized
    assert "canonical_bytes" not in serialized


@pytest.mark.asyncio
async def test_list_and_detail_are_redacted_and_preserve_safe_fields(
    app_with_engine: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        listed = await client.get(
            "/api/deeper-notebook/knowledge-engine/documents?"
            "space_id=knowledge_engine_space%3Aprimary&limit=1&offset=0"
        )
        detailed = await client.get(
            "/api/deeper-notebook/knowledge-engine/documents/"
            "knowledge_engine_document%3Aone"
        )

    assert listed.status_code == detailed.status_code == 200
    list_document = listed.json()[0]
    detail_document = detailed.json()
    assert list_document == {
        "id": "knowledge_engine_document:one",
        "space_id": "knowledge_engine_space:primary",
        "relative_locator": "Projects/Plan.md",
        "title": "Plan",
        "kind": "note",
        "source_hash": "a" * 64,
        "source_revision_id": "knowledge_engine_revision:one",
        "provenance": "obsidian",
        "authority_kind": "external_read_only",
        "availability": "available",
        "state": "ready",
        "capabilities": ["bookmark", "cite", "copy_content", "read"],
    }
    assert detail_document["normalized_body"] == "# Plan\nPrivate local page\n"
    for payload in (list_document, detail_document):
        assert "properties" not in payload
        assert "source_native_id" not in payload
        assert "canonical_bytes" not in payload
        assert "root_path" not in payload
        assert "/Users/" not in str(payload)
    service = app_with_engine.state.knowledge_engine_service
    assert service.list_requests == [("knowledge_engine_space:primary", 1, 0)]


@pytest.mark.asyncio
async def test_status_exposes_stable_counts_only(app_with_engine: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/deeper-notebook/knowledge-engine/status")

    assert response.status_code == 200
    assert response.json() == {"projected": 3, "unchanged": 2, "failed": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "path", "status_code", "code"),
    [
        (
            "missing_service",
            "/api/deeper-notebook/knowledge-engine/status",
            404,
            "knowledge_engine_disabled",
        ),
        (
            "unavailable_repository",
            "/api/deeper-notebook/knowledge-engine/status",
            503,
            "knowledge_engine_unavailable",
        ),
        (
            "missing_document",
            "/api/deeper-notebook/knowledge-engine/documents/"
            "knowledge_engine_document%3Amissing",
            404,
            "knowledge_document_not_found",
        ),
    ],
)
async def test_stable_errors_are_redacted(
    app_with_engine: FastAPI,
    state: str,
    path: str,
    status_code: int,
    code: str,
) -> None:
    if state == "missing_service":
        delattr(app_with_engine.state, "knowledge_engine_service")
    elif state == "unavailable_repository":
        app_with_engine.state.knowledge_engine_service.status_result = (
            KnowledgeRepositoryError("knowledge_engine_repository_unavailable")
        )
    else:
        app_with_engine.state.knowledge_engine_service.document_result = LookupError(
            "/Users/Antman/private document"
        )

    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code}}
    assert "/Users/" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/deeper-notebook/knowledge-engine/documents?limit=0",
        "/api/deeper-notebook/knowledge-engine/documents?offset=-1",
        "/api/deeper-notebook/knowledge-engine/documents?"
        "space_id=knowledge_engine_space%3Ainvalid/path",
        "/api/deeper-notebook/knowledge-engine/documents/not-an-engine-id",
    ],
)
async def test_invalid_request_uses_stable_error_envelope(
    app_with_engine: FastAPI, path: str
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "knowledge_engine_request_invalid"}
    }


@pytest.mark.asyncio
async def test_existing_password_authentication_protects_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.auth import PasswordAuthMiddleware
    from api.routers.knowledge_engine import router

    monkeypatch.setattr("api.auth.resolve_env", lambda *_args, **_kwargs: "locked")
    app = FastAPI()
    app.state.knowledge_engine_service = _EngineService()
    app.add_middleware(PasswordAuthMiddleware)
    app.include_router(router, prefix="/api/deeper-notebook")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/api/deeper-notebook/knowledge-engine/status")
        allowed = await client.get(
            "/api/deeper-notebook/knowledge-engine/status",
            headers={"Authorization": "Bearer locked"},
        )

    assert denied.status_code == 401
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_main_registers_only_the_canonical_diagnostic_routes() -> None:
    from api.main import app

    canonical = "/api/deeper-notebook/knowledge-engine/status"
    legacy = "/api/onp/knowledge-engine/status"
    paths = app.openapi()["paths"]
    assert set(paths[canonical]) == {"get"}
    assert legacy not in paths

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(legacy)
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result_attribute", "path"),
    [
        ("status_result", "/api/deeper-notebook/knowledge-engine/status"),
        ("list_result", "/api/deeper-notebook/knowledge-engine/documents"),
        (
            "document_result",
            "/api/deeper-notebook/knowledge-engine/documents/"
            "knowledge_engine_document%3Aone",
        ),
    ],
)
async def test_internal_service_value_error_is_unavailable_not_request_invalid(
    app_with_engine: FastAPI,
    result_attribute: str,
    path: str,
) -> None:
    service = app_with_engine.state.knowledge_engine_service
    setattr(service, result_attribute, ValueError("private service detail"))

    async with AsyncClient(
        transport=ASGITransport(app=app_with_engine),
        base_url="http://test",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "knowledge_engine_unavailable"}
    }
    assert "private service detail" not in response.text


def test_engine_openapi_uses_only_the_stable_error_response_schema(
    app_with_engine: FastAPI,
) -> None:
    schema = app_with_engine.openapi()
    paths = schema["paths"]
    error_schema = {"$ref": "#/components/schemas/KnowledgeEngineErrorResponse"}
    expected_errors = {
        "/api/deeper-notebook/knowledge-engine/status": {"404", "422", "503"},
        "/api/deeper-notebook/knowledge-engine/documents": {"404", "422", "503"},
        "/api/deeper-notebook/knowledge-engine/documents/{document_id}": {
            "404",
            "422",
            "503",
        },
    }

    for path, error_codes in expected_errors.items():
        responses = paths[path]["get"]["responses"]
        assert error_codes <= set(responses)
        for code in error_codes:
            assert responses[code]["content"]["application/json"]["schema"] == (
                error_schema
            )
        assert "HTTPValidationError" not in str(responses)
        assert "ValidationError" not in str(responses)

    stable_error = schema["components"]["schemas"]["KnowledgeEngineErrorResponse"]
    assert stable_error["additionalProperties"] is False
    assert stable_error["properties"] == {
        "detail": {"$ref": "#/components/schemas/KnowledgeEngineErrorDetail"}
    }
    assert stable_error["required"] == ["detail"]
