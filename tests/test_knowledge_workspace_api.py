"""API coverage for the durable Deeper Notebook knowledge workspace."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deeper_notebook.workspace import default_knowledge_workspace


@pytest.fixture()
def api_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    from api.routers import knowledge_workspace

    workspace_path = tmp_path / "knowledge-workspace-v1.json"
    monkeypatch.setattr(
        knowledge_workspace,
        "_workspace_path",
        lambda: workspace_path,
    )

    app = FastAPI()
    app.state.workspace_path = workspace_path
    app.include_router(
        knowledge_workspace.router,
        prefix="/api/deeper-notebook",
    )
    return app


@pytest.mark.asyncio
async def test_legacy_put_defaults_authority_and_serializes_it_explicitly(
    api_app: FastAPI,
) -> None:
    workspace_path = api_app.state.workspace_path
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        initial = await client.get("/api/deeper-notebook/workspace/knowledge")
        assert initial.status_code == 200
        assert str(workspace_path) not in initial.text

        payload = default_knowledge_workspace().model_dump(mode="json")
        payload["panes"]["pane-1"]["tabs"] = [
            {
                "id": "tab:one",
                "vault_id": "vault:one",
                "note_id": "note:one",
                "title": "One",
                "relative_path": "One.md",
                "view_mode": "reading",
            }
        ]
        payload["panes"]["pane-1"]["active_tab_id"] = "tab:one"
        saved = await client.put(
            "/api/deeper-notebook/workspace/knowledge",
            json=payload,
        )
        assert saved.status_code == 200
        from deeper_notebook.workspace.contracts import (
            KnowledgeWorkspaceDocument,
            migrate_workspace_v1,
        )

        expected = migrate_workspace_v1(
            KnowledgeWorkspaceDocument.model_validate(payload)
        ).model_dump(mode="json")
        assert saved.json() == expected
        assert str(workspace_path) not in saved.text

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as restarted_client:
        restored = await restarted_client.get(
            "/api/deeper-notebook/workspace/knowledge"
        )

    assert restored.status_code == 200
    assert restored.json()["panes"]["pane-1"]["active_tab_id"] == "tab:one"
    assert (
        restored.json()["panes"]["pane-1"]["tabs"][0]["target"]["authority"]
        == "external-vault"
    )
    assert str(workspace_path) not in restored.text


@pytest.mark.asyncio
async def test_put_rejects_absolute_relative_path(api_app: FastAPI) -> None:
    payload = default_knowledge_workspace().model_dump(mode="json")
    payload["panes"]["pane-1"]["tabs"] = [
        {
            "id": "tab:bad",
            "vault_id": "v",
            "note_id": "n",
            "title": "Bad",
            "relative_path": "C:\\Users\\me\\secret.md",
            "view_mode": "reading",
        }
    ]
    payload["panes"]["pane-1"]["active_tab_id"] = "tab:bad"

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.put(
            "/api/deeper-notebook/workspace/knowledge",
            json=payload,
        )

    assert response.status_code == 422
    assert str(api_app.state.workspace_path) not in response.text


@pytest.mark.asyncio
async def test_v2_put_persists_canonical_target_ids_and_rejects_path_bearing_ids(
    api_app: FastAPI,
) -> None:
    from deeper_notebook.workspace import default_knowledge_workspace_v2

    payload = default_knowledge_workspace_v2().model_dump(mode="json")
    payload["panes"]["pane-1"]["tabs"] = [
        {
            "id": "tab-graph",
            "mode": "graph",
            "title": "Graph",
            "target": {
                "kind": "graph",
                "root_document_id": "knowledge_engine_document:root",
                "space_ids": ["knowledge_engine_space:primary"],
                "relation_kinds": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
                "origin": None,
            },
        },
        {
            "id": "tab-ask",
            "mode": "ask",
            "title": "Ask",
            "target": {
                "kind": "ask",
                "thread_id": "thread:one",
                "selected_document_ids": ["knowledge_engine_document:one"],
            },
        },
        {
            "id": "tab-podcast",
            "mode": "podcast",
            "title": "Podcast",
            "target": {
                "kind": "podcast",
                "production_id": "production:one",
                "seed_document_ids": ["knowledge_engine_document:two"],
            },
        },
    ]
    payload["panes"]["pane-1"]["active_tab_id"] = "tab-graph"
    payload["navigation"]["selected_space_ids"] = ["knowledge_engine_space:primary"]

    async with AsyncClient(
        transport=ASGITransport(app=api_app), base_url="http://test"
    ) as client:
        saved = await client.put(
            "/api/deeper-notebook/workspace/knowledge", json=payload
        )
        assert saved.status_code == 200
        assert (
            saved.json()["panes"]["pane-1"]["tabs"][0]["target"]["root_document_id"]
            == "knowledge_engine_document:root"
        )

        for tab_index, field, value in (
            (0, "root_document_id", "/private/document"),
            (0, "space_ids", ["../private-space"]),
            (1, "selected_document_ids", ["/private/document"]),
            (2, "seed_document_ids", ["/private/document"]),
        ):
            unsafe = saved.json()
            unsafe["panes"]["pane-1"]["tabs"][tab_index]["target"][field] = value
            rejected = await client.put(
                "/api/deeper-notebook/workspace/knowledge", json=unsafe
            )
            assert rejected.status_code == 422

        unsafe_navigation = saved.json()
        unsafe_navigation["navigation"]["selected_space_ids"] = ["../private-space"]
        rejected_navigation = await client.put(
            "/api/deeper-notebook/workspace/knowledge", json=unsafe_navigation
        )
        assert rejected_navigation.status_code == 422

        restored = await client.get("/api/deeper-notebook/workspace/knowledge")
    assert restored.json() == saved.json()


@pytest.mark.asyncio
async def test_put_rejects_oversized_content_length_before_json_parsing(
    api_app: FastAPI,
) -> None:
    body = b'{"padding":"' + (b"x" * (1024 * 1024)) + b'"}'
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.put(
            "/api/deeper-notebook/workspace/knowledge",
            content=body,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "workspace_request_too_large"}}


@pytest.mark.asyncio
async def test_put_rejects_oversized_chunked_body_while_streaming(
    api_app: FastAPI,
) -> None:
    async def oversized_body():
        yield b'{"padding":"'
        for _ in range(17):
            yield b"x" * (64 * 1024)
        yield b'"}'

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.put(
            "/api/deeper-notebook/workspace/knowledge",
            content=oversized_body(),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "workspace_request_too_large"}}


@pytest.mark.asyncio
async def test_malformed_stored_json_returns_stable_conflict(
    api_app: FastAPI,
) -> None:
    workspace_path = api_app.state.workspace_path
    workspace_path.write_text("{not-json", encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/deeper-notebook/workspace/knowledge")

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "workspace_state_invalid"}}
    assert str(workspace_path) not in response.text


@pytest.mark.asyncio
async def test_read_failure_returns_stable_unavailable(
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import knowledge_workspace

    workspace_path = api_app.state.workspace_path

    def fail_to_load(*, path: Path) -> None:
        assert path == workspace_path
        raise OSError(f"cannot read {path}")

    monkeypatch.setattr(
        knowledge_workspace,
        "load_knowledge_workspace",
        fail_to_load,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/deeper-notebook/workspace/knowledge")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "workspace_state_unavailable"}}
    assert str(workspace_path) not in response.text


@pytest.mark.asyncio
async def test_write_failure_returns_stable_unavailable(
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from api.routers import knowledge_workspace

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    workspace_path = blocker / "knowledge-workspace-v1.json"
    monkeypatch.setattr(
        knowledge_workspace,
        "_workspace_path",
        lambda: workspace_path,
    )

    payload = default_knowledge_workspace().model_dump(mode="json")
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.put(
            "/api/deeper-notebook/workspace/knowledge",
            json=payload,
        )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "workspace_state_unavailable"}}
    assert str(workspace_path) not in response.text


@pytest.mark.asyncio
async def test_encoded_write_over_limit_returns_stable_too_large(
    api_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import knowledge_workspace
    from deeper_notebook.workspace import WorkspaceStateError

    monkeypatch.setattr(
        knowledge_workspace,
        "save_knowledge_workspace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            WorkspaceStateError("encoded state is too large")
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.put(
            "/api/deeper-notebook/workspace/knowledge",
            json=default_knowledge_workspace().model_dump(mode="json"),
        )

    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "workspace_request_too_large"}}


@pytest.mark.asyncio
async def test_router_exposes_only_canonical_get_and_put(api_app: FastAPI) -> None:
    from api.routers.knowledge_workspace import router

    routes: dict[str, set[str]] = {}
    for route in router.routes:
        routes.setdefault(route.path, set()).update(route.methods)
    assert routes == {"/workspace/knowledge": {"GET", "PUT"}}

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        legacy_workspace_path = "/" + "api/" + "onp/workspace/knowledge"
        legacy = await client.put(
            legacy_workspace_path,
            json=default_knowledge_workspace().model_dump(mode="json"),
        )

    assert legacy.status_code == 404


def test_main_app_registers_only_canonical_knowledge_workspace_routes() -> None:
    from api.main import app

    canonical_workspace_path = "/api/deeper-notebook/workspace/knowledge"
    legacy_workspace_path = "/" + "api/" + "onp/workspace/knowledge"
    routes: dict[str, set[str]] = {}
    for route in app.routes:
        candidates = [route]
        effective_routes = getattr(route, "effective_route_contexts", None)
        if effective_routes:
            candidates.extend(effective_routes())
        for candidate in candidates:
            path = getattr(candidate, "path", None)
            if path in {
                canonical_workspace_path,
                legacy_workspace_path,
            }:
                routes.setdefault(path, set()).update(candidate.methods or set())

    assert routes == {
        canonical_workspace_path: {"GET", "PUT"},
    }
