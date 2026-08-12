from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import study_anki
from deeper_notebook.study.anki_package import inspect_anki_package
from deeper_notebook.study.anki_repository import AnkiCompatibilityReceipt
from tests.fixtures.anki.build_fixtures import build_apkg
from tests.test_study_anki_export import PLAN_EXPORT


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    study_anki._IMPORT_JOBS.clear()
    study_anki._DOWNLOADS.clear()
    monkeypatch.setattr(study_anki, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_anki, "_export_root", lambda: tmp_path / "exports")
    monkeypatch.setattr(study_anki, "_import_root", lambda: tmp_path / "imports")
    monkeypatch.setattr(study_anki, "_load_export_plan", lambda plan_id: PLAN_EXPORT)
    app = FastAPI()
    app.include_router(study_anki.router, prefix="/api")
    return TestClient(app)


def _receipt(package: Path, request_id: str) -> AnkiCompatibilityReceipt:
    inspection = inspect_anki_package(package)
    return AnkiCompatibilityReceipt(
        receipt_id="study_anki_import:" + "a" * 64,
        plan_id="study_plan:one",
        request_id=request_id,
        payload_sha256="b" * 64,
        package_sha256=inspection.package_sha256,
        collection_sha256=inspection.collection_sha256,
        collection_member=inspection.collection_member,
        card_count=len(inspection.cards),
        transformed_count=inspection.transformed_count,
        skipped_count=inspection.skipped_count,
        card_ids=tuple(card.card_id for card in inspection.cards),
        deck_names=inspection.deck_names,
        tags=inspection.tags,
        media_names=inspection.media_names,
        created_at=datetime.now(UTC),
    )


def test_feature_off_is_uniform_404_before_body_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(study_anki, "study_workbench_enabled", lambda: False)
    app = FastAPI()
    app.include_router(study_anki.router, prefix="/api")
    with TestClient(app) as client:
        responses = [
            client.post("/api/study/plans/not-a-plan/anki/import", data={"options": "{"}),
            client.post("/api/study/plans/not-a-plan/anki/export", json={"unexpected": True}),
            client.get("/api/study/plans/not-a-plan/anki/import/../../etc/passwd"),
        ]
    assert {response.status_code for response in responses} == {404}


def test_upload_preview_does_not_publish_and_returns_bounded_summary(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "deck.apkg"
    package.write_bytes(b"not-a-package")
    publish_called = False

    async def forbidden_publish(*args: object, **kwargs: object) -> object:
        nonlocal publish_called
        publish_called = True
        raise AssertionError("preview must not publish")

    monkeypatch.setattr(study_anki, "_publish_import", forbidden_publish)
    response = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("deck.apkg", io.BytesIO(package.read_bytes()), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert response.status_code == 422
    assert publish_called is False


def test_valid_preview_requires_explicit_publish_and_replay_is_bound(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = build_apkg(tmp_path / "valid.apkg")
    request_id = "anki-request-one"
    receipt = _receipt(package, request_id)
    published: list[str] = []

    async def fake_publish(plan_id: str, job: object, options: object, caller_request_id: str):
        published.append(caller_request_id)
        return receipt

    monkeypatch.setattr(study_anki, "_publish_import", fake_publish)
    preview = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("valid.apkg", package.read_bytes(), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert preview.status_code == 200
    job_id = preview.json()["job_id"]
    assert preview.json()["status"] == "preview_ready"
    assert client.get(f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}").json()["receipt_id"] is None

    missing_confirmation = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert missing_confirmation.status_code == 200
    assert missing_confirmation.json()["status"] == "published"
    assert published == [request_id]
    assert not study_anki._IMPORT_JOBS[job_id].path.exists()

    replay = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert replay.status_code == 200 and replay.json()["status"] == "replayed"
    mismatch = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": "different-request", "options": {"schema_version": 1}},
    )
    assert mismatch.status_code == 409


def test_upload_bound_and_download_symlink_are_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(study_anki, "MAX_UPLOAD_BYTES", 4)
    oversized = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("oversized.apkg", b"12345", "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert oversized.status_code == 413

    root = study_anki._export_root()
    root.mkdir(parents=True)
    outside = tmp_path / "outside.apkg"
    outside.write_bytes(b"private")
    link = root / "link.apkg"
    link.symlink_to(outside)
    download_id = "anki_download:" + "c" * 64
    study_anki._DOWNLOADS[download_id] = link
    assert client.get(f"/api/study/plans/anki/download/{download_id}").status_code == 404


def test_export_returns_opaque_download_id_and_download_has_safe_headers(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/study/plans/study_plan%3Aexport/anki/export",
        json={"schema_version": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["download_id"].startswith("anki_download:")
    assert "/" not in body["download_id"]
    downloaded = client.get(f"/api/study/plans/anki/download/{body['download_id']}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/zip")
    assert "path" not in downloaded.text.lower()
