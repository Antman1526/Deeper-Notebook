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
async def test_get_returns_default_and_put_survives_new_client(
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

        payload = initial.json()
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
        assert saved.json() == payload
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
        legacy = await client.put(
            "/api/onp/workspace/knowledge",
            json=default_knowledge_workspace().model_dump(mode="json"),
        )

    assert legacy.status_code == 404


def test_main_app_registers_only_canonical_knowledge_workspace_routes() -> None:
    from api.main import app

    routes: dict[str, set[str]] = {}
    for route in app.routes:
        candidates = [route]
        effective_routes = getattr(route, "effective_route_contexts", None)
        if effective_routes:
            candidates.extend(effective_routes())
        for candidate in candidates:
            path = getattr(candidate, "path", None)
            if path in {
                "/api/deeper-notebook/workspace/knowledge",
                "/api/onp/workspace/knowledge",
            }:
                routes.setdefault(path, set()).update(candidate.methods or set())

    assert routes == {
        "/api/deeper-notebook/workspace/knowledge": {"GET", "PUT"},
    }
