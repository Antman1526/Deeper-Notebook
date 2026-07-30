"""Authenticated, bounded API contracts for app-owned overlay Markdown."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayNote,
    OverlayPage,
    UpdateOverlayNote,
)
from deeper_notebook.overlay.repository import (
    OverlayConflictError,
    OverlayRepositoryError,
)
from deeper_notebook.overlay.storage import OverlayStorageError

_JSON_CEILING = 10 * 1024 * 1024 + 64 * 1024
_MAX_OFFSET = 1_000_000
_INVALID_REQUEST = {"detail": {"code": "overlay_request_invalid"}}


def _note(
    note_id: str,
    *,
    kind: str,
    title: str,
    date_key: str | None,
    revision: int = 1,
) -> OverlayNote:
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    return OverlayNote(
        id=note_id,
        space_id="overlay_space:default",
        projected_note_id=f"note:{note_id.removeprefix('overlay_note:')}",
        stable_id=f"01JTESTOVERLAY{note_id[-8:].upper():0>12}",
        kind=kind,
        date_key=date_key,
        relative_path=(
            f"Daily/{date_key}.md"
            if kind == "daily"
            else "Notes/20260729-1200 Research.md"
        ),
        title=title,
        content_hash="a" * 64,
        revision=revision,
        projection_state="current",
        created_at=now,
        updated_at=now,
    )


def _page(note: OverlayNote, markdown: str | None = None) -> OverlayPage:
    return OverlayPage(
        overlay=note,
        note={
            "id": note.projected_note_id,
            "title": note.title,
            "content": markdown or f"# {note.title}\n",
        },
    )


class _OverlayService:
    def __init__(self) -> None:
        self.notes: dict[str, OverlayPage] = {}
        self.unique_keys: dict[str, str] = {}
        self.last_get_id: str | None = None
        self.list_requests: list[tuple[int, int]] = []

    async def create_daily(self, request: CreateDailyNote) -> OverlayPage:
        note_id = f"overlay_note:daily-{request.date_key}"
        if note_id not in self.notes:
            self.notes[note_id] = _page(
                _note(
                    note_id,
                    kind="daily",
                    title=request.date_key,
                    date_key=request.date_key,
                )
            )
        return self.notes[note_id]

    async def create_unique(self, request: CreateUniqueNote) -> OverlayPage:
        note_id = self.unique_keys.get(request.idempotency_key)
        if note_id is None:
            note_id = "overlay_note:unique-one"
            self.unique_keys[request.idempotency_key] = note_id
            self.notes[note_id] = _page(
                _note(
                    note_id,
                    kind="unique",
                    title=request.title,
                    date_key=None,
                )
            )
        return self.notes[note_id]

    async def get_page(self, note_id: str) -> OverlayPage:
        self.last_get_id = note_id
        try:
            return self.notes[note_id]
        except KeyError:
            raise LookupError("overlay_not_found") from None

    async def list_notes(self, limit: int, offset: int) -> list[OverlayNote]:
        self.list_requests.append((limit, offset))
        return [page.overlay for page in self.notes.values()][offset : offset + limit]

    async def update(
        self,
        note_id: str,
        request: UpdateOverlayNote,
    ) -> OverlayPage:
        current = await self.get_page(note_id)
        if request.expected_revision != current.overlay.revision:
            raise OverlayConflictError("overlay_revision_conflict")
        updated = current.overlay.model_copy(
            update={
                "title": request.title,
                "revision": current.overlay.revision + 1,
            }
        )
        page = _page(updated, request.markdown)
        self.notes[note_id] = page
        return page


@pytest.fixture()
def client():
    from api.main import app

    service = _OverlayService()
    app.state.overlay_service = service
    test_client = TestClient(app)
    try:
        yield test_client, service
    finally:
        test_client.close()
        app.state.overlay_service = None


async def _asgi_json_request(
    app: FastAPI,
    *,
    method: str,
    path: str,
    frames: list[bytes],
) -> tuple[int, dict[str, Any]]:
    receive_messages = [
        {
            "type": "http.request",
            "body": frame,
            "more_body": index < len(frames) - 1,
        }
        for index, frame in enumerate(frames)
    ]
    sent_messages: list[dict[str, Any]] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }

    async def receive() -> dict[str, Any]:
        if receive_messages:
            return receive_messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent_messages.append(message)

    await app(scope, receive, send)
    start = next(
        message for message in sent_messages if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in sent_messages
        if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(body)


def _asgi_app() -> tuple[FastAPI, _OverlayService]:
    from api.routers.overlay import router

    app = FastAPI()
    service = _OverlayService()
    app.state.overlay_service = service
    app.include_router(router, prefix="/api/deeper-notebook")
    return app, service


def test_overlay_routes_are_canonical_and_vault_routes_stay_read_only(client):
    test_client, _ = client
    routes = {
        path: {method.upper() for method in operations}
        for path, operations in test_client.app.openapi()["paths"].items()
    }
    assert routes["/api/deeper-notebook/overlay"] == {"GET"}
    assert routes["/api/deeper-notebook/overlay/notes"] == {"GET"}
    assert routes["/api/deeper-notebook/overlay/daily/{date_key}"] == {"PUT"}
    assert routes["/api/deeper-notebook/overlay/notes/unique"] == {"POST"}
    assert routes["/api/deeper-notebook/overlay/notes/{note_id}"] == {
        "GET",
        "PUT",
    }
    assert "/api/onp/overlay" not in routes
    assert not any(path.startswith("/api/onp/overlay") for path in routes)
    assert test_client.get("/api/onp/overlay").status_code == 404
    for path, methods in routes.items():
        if path.startswith("/api/deeper-notebook/vaults"):
            assert not methods & {"PUT", "PATCH", "DELETE"}


def test_overlay_root_list_and_encoded_note_id_use_service_methods(client):
    test_client, service = client
    created = test_client.post(
        "/api/deeper-notebook/overlay/notes/unique",
        json={"title": "Research", "idempotency_key": "create-1"},
    )
    assert created.status_code == 201
    assert test_client.get("/api/deeper-notebook/overlay").json() == {
        "id": "overlay_space:default",
        "source_authority": "overlay",
    }
    listed = test_client.get("/api/deeper-notebook/overlay/notes?limit=1&offset=0")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "overlay_note:unique-one"
    fetched = test_client.get(
        "/api/deeper-notebook/overlay/notes/overlay_note%3Aunique-one"
    )
    assert fetched.status_code == 200
    assert service.last_get_id == "overlay_note:unique-one"


def test_overlay_page_serializes_identity_aliases_and_local_graph(client):
    test_client, service = client
    note = _note(
        "overlay_note:center",
        kind="unique",
        title="Center",
        date_key=None,
    )
    mapped = {
        "id": "note_link:mapped",
        "source_note_id": note.projected_note_id,
        "source_overlay_note_id": note.id,
        "source_relative_path": note.relative_path,
        "target_note_id": "note:target",
        "target_overlay_note_id": "overlay_note:target",
        "target_note_title": "Target",
        "target_relative_path": "Notes/20260729-1201 Target.md",
        "target_text": "Target",
        "link_kind": "wikilink",
        "resolved": True,
        "source_start": 0,
        "source_end": 6,
    }
    external = {
        **mapped,
        "id": "note_link:external",
        "target_note_id": "note:external",
        "target_overlay_note_id": None,
        "target_note_title": "External",
        "target_text": "External",
    }
    service.notes[note.id] = OverlayPage(
        overlay=note,
        note={"id": note.projected_note_id, "title": note.title},
        outgoing_links=[mapped, external],
    )

    response = test_client.get(
        "/api/deeper-notebook/overlay/notes/overlay_note%3Acenter"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outgoing_links"][0]["source_overlay_note_id"] == note.id
    assert body["outgoing_links"][0]["source_relative_path"] == note.relative_path
    assert (
        body["outgoing_links"][0]["target_overlay_note_id"]
        == "overlay_note:target"
    )
    assert body["outgoing_links"][1]["target_overlay_note_id"] is None
    assert {node["id"] for node in body["graph"]["nodes"]} == {
        note.projected_note_id,
        "note:target",
    }
    assert body["graph"]["edges"] == [{
        "id": "note_link:mapped",
        "source": note.projected_note_id,
        "target": "note:target",
        "kind": "wikilink",
        "resolved": True,
    }]


def test_daily_create_is_idempotent_and_contains_no_absolute_path(client):
    test_client, _ = client
    first = test_client.put("/api/deeper-notebook/overlay/daily/2026-07-29")
    second = test_client.put("/api/deeper-notebook/overlay/daily/2026-07-29")
    assert first.status_code == second.status_code == 200
    assert first.json()["overlay"]["id"] == second.json()["overlay"]["id"]
    assert "/Users/" not in first.text


def test_unique_and_update_require_strict_revision_contract(client):
    test_client, _ = client
    created = test_client.post(
        "/api/deeper-notebook/overlay/notes/unique",
        json={"title": "Research", "idempotency_key": "create-1"},
    )
    assert created.status_code == 201
    note_id = created.json()["overlay"]["id"]
    conflict = test_client.put(
        f"/api/deeper-notebook/overlay/notes/{note_id}",
        json={
            "title": "Research",
            "markdown": "# Changed\n",
            "expected_revision": 99,
            "idempotency_key": "save-1",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "overlay_revision_conflict"


def test_overlay_requests_reject_unknown_and_non_strict_fields(client):
    test_client, _ = client
    rejected = test_client.post(
        "/api/deeper-notebook/overlay/notes/unique",
        json={
            "title": "Research",
            "idempotency_key": "create-1",
            "external_vault_id": "vault_mount:forbidden",
        },
    )
    assert rejected.status_code == 422
    assert (
        test_client.post(
            "/api/deeper-notebook/overlay/notes/unique",
            json={"title": "x" * 513, "idempotency_key": "create-1"},
        ).status_code
        == 422
    )
    assert (
        test_client.post(
            "/api/deeper-notebook/overlay/notes/unique",
            json={"title": "Research", "idempotency_key": "x" * 129},
        ).status_code
        == 422
    )
    assert (
        test_client.put(
            "/api/deeper-notebook/overlay/notes/overlay_note:one",
            json={
                "title": "Research",
                "markdown": "# Changed\n",
                "expected_revision": 1.0,
                "idempotency_key": "save-1",
            },
        ).status_code
        == 422
    )
    assert (
        test_client.put("/api/deeper-notebook/overlay/daily/2026-02-30").status_code
        == 422
    )
    assert (
        test_client.get(
            f"/api/deeper-notebook/overlay/notes/overlay_note:{'x' * 129}"
        ).status_code
        == 422
    )
    assert (
        test_client.get("/api/deeper-notebook/overlay/notes?limit=501").status_code
        == 422
    )


def test_invalid_overlay_body_path_and_query_are_typed_and_non_reflective(client):
    test_client, _ = client
    hostile_values = (
        "/Users/owner/private.md",
        "SECRET_BODY_CONTENT",
        "SECRET_PATH_CONTENT!",
        "SECRET_QUERY_CONTENT",
    )
    responses = (
        test_client.post(
            "/api/deeper-notebook/overlay/notes/unique",
            json={
                "title": "Research",
                "idempotency_key": "create-1",
                "external_vault_id": ("/Users/owner/private.md SECRET_BODY_CONTENT"),
            },
        ),
        test_client.get(
            "/api/deeper-notebook/overlay/notes/overlay_note:SECRET_PATH_CONTENT%21"
        ),
        test_client.get(
            "/api/deeper-notebook/overlay/notes?offset=SECRET_QUERY_CONTENT"
        ),
    )
    for response in responses:
        assert response.status_code == 422
        assert response.json() == _INVALID_REQUEST
        for hostile in hostile_values:
            assert hostile not in response.text


def test_overlay_offset_is_bounded_before_service_calls(client):
    test_client, service = client
    boundary = test_client.get(
        f"/api/deeper-notebook/overlay/notes?limit=1&offset={_MAX_OFFSET}"
    )
    assert boundary.status_code == 200
    assert service.list_requests == [(1, _MAX_OFFSET)]

    rejected = test_client.get(
        f"/api/deeper-notebook/overlay/notes?limit=1&offset={_MAX_OFFSET + 1}"
    )
    assert rejected.status_code == 422
    assert rejected.json() == _INVALID_REQUEST
    assert service.list_requests == [(1, _MAX_OFFSET)]


def test_overlay_rejects_body_above_exact_json_ceiling_before_parsing(client):
    test_client, _ = client
    too_large = test_client.put(
        "/api/deeper-notebook/overlay/notes/overlay_note:one",
        content=b"x" * (_JSON_CEILING + 1),
        headers={"content-type": "application/json"},
    )
    assert too_large.status_code == 413
    assert too_large.json() == {"detail": {"code": "overlay_request_too_large"}}
    below_ceiling = test_client.put(
        "/api/deeper-notebook/overlay/notes/overlay_note:one",
        content=b"SECRET_INVALID_JSON",
        headers={"content-type": "application/json"},
    )
    assert below_ceiling.status_code == 422
    assert below_ceiling.json() == _INVALID_REQUEST
    assert "SECRET_INVALID_JSON" not in below_ceiling.text


def test_multiframe_body_without_content_length_rejects_ceiling_plus_one():
    app, _ = _asgi_app()
    status_code, body = asyncio.run(
        _asgi_json_request(
            app,
            method="PUT",
            path="/api/deeper-notebook/overlay/notes/overlay_note:one",
            frames=[b"x" * _JSON_CEILING, b"x"],
        )
    )
    assert status_code == 413
    assert body == {"detail": {"code": "overlay_request_too_large"}}


def test_multiframe_body_without_content_length_is_replayed_for_json_parsing():
    app, service = _asgi_app()
    payload = json.dumps(
        {"title": "Research", "idempotency_key": "multiframe-create"}
    ).encode()
    status_code, body = asyncio.run(
        _asgi_json_request(
            app,
            method="POST",
            path="/api/deeper-notebook/overlay/notes/unique",
            frames=[payload[:7], payload[7:31], payload[31:]],
        )
    )
    assert status_code == 201
    assert body["overlay"]["id"] == "overlay_note:unique-one"
    assert service.unique_keys == {"multiframe-create": "overlay_note:unique-one"}


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (LookupError("overlay_not_found"), 404, "overlay_not_found"),
        (
            OverlayConflictError("overlay_hash_conflict"),
            409,
            "overlay_revision_conflict",
        ),
        (
            OverlayStorageError("overlay_file_too_large"),
            413,
            "overlay_file_too_large",
        ),
        (
            OverlayRepositoryError("overlay_projection_pending"),
            503,
            "overlay_projection_pending",
        ),
        (
            OverlayStorageError("overlay_storage_unavailable"),
            503,
            "overlay_storage_unavailable",
        ),
    ],
)
def test_overlay_errors_use_only_the_stable_error_map(
    client,
    error,
    status_code,
    code,
):
    test_client, service = client

    async def fail(_limit: int, _offset: int):
        raise error

    service.list_notes = fail
    response = test_client.get("/api/deeper-notebook/overlay/notes")
    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code}}


def test_unknown_failures_and_unavailable_service_are_redacted(client):
    test_client, service = client

    async def fail(_limit: int, _offset: int):
        raise RuntimeError(
            "driver failed at /Users/owner/private.md with SECRET_SOURCE_TEXT"
        )

    service.list_notes = fail
    response = test_client.get("/api/deeper-notebook/overlay/notes")
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "overlay_unavailable"}}
    assert "/Users/" not in response.text
    assert "SECRET_SOURCE_TEXT" not in response.text

    test_client.app.state.overlay_service = None
    unavailable = test_client.get("/api/deeper-notebook/overlay/notes")
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": {"code": "overlay_unavailable"}}


def test_service_http_exception_is_fail_closed_and_non_reflective(client):
    test_client, service = client

    async def fail(_limit: int, _offset: int):
        raise HTTPException(
            status_code=418,
            detail={
                "path": "/Users/owner/private.md",
                "secret": "SECRET_SERVICE_CONTENT",
                "content": "# Private source content",
            },
        )

    service.list_notes = fail
    response = test_client.get("/api/deeper-notebook/overlay/notes")
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "overlay_unavailable"}}
    assert "/Users/" not in response.text
    assert "SECRET_SERVICE_CONTENT" not in response.text
    assert "Private source content" not in response.text


def test_overlay_routes_remain_behind_password_auth(monkeypatch):
    from api.auth import PasswordAuthMiddleware
    from api.routers.overlay import router

    monkeypatch.setenv("DEEPER_NOTEBOOK_PASSWORD", "overlay-test-password")
    auth_app = FastAPI()
    auth_app.state.overlay_service = _OverlayService()
    auth_app.include_router(router, prefix="/api/deeper-notebook")
    auth_app.add_middleware(PasswordAuthMiddleware)

    with TestClient(auth_app) as auth_client:
        assert auth_client.get("/api/deeper-notebook/overlay").status_code == 401
        assert (
            auth_client.get(
                "/api/deeper-notebook/overlay",
                headers={"Authorization": "Bearer overlay-test-password"},
            ).status_code
            == 200
        )
