"""Authenticated, bounded API contracts for app-owned overlay Markdown."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
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
        content=b"x" * (_JSON_CEILING - 1),
        headers={"content-type": "application/json"},
    )
    assert below_ceiling.status_code == 422


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
