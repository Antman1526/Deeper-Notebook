from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(local_models_router.router)
    return TestClient(app)


def test_reveal_local_model_path_opens_existing_path_inside_model_dir(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "GGUF" / "repo" / "model.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"gguf")

    calls: list[list[str]] = []

    def fake_popen(command: list[str], *args, **kwargs):  # noqa: ANN001
        calls.append(command)
        return object()

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    response = client.post(
        "/api/local-models/reveal",
        json={"path": str(model_path)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert response.json()["path"] == str(model_path.resolve())
    assert calls == [["open", "-R", str(model_path.resolve())]]


def test_reveal_local_model_path_rejects_missing_path(
    client: TestClient,
    tmp_path: Path,
) -> None:
    response = client.post(
        "/api/local-models/reveal",
        json={"path": str(tmp_path / "missing.gguf")},
    )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_reveal_local_model_path_rejects_paths_outside_model_dir(
    client: TestClient,
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.gguf"
    outside.write_bytes(b"gguf")

    response = client.post(
        "/api/local-models/reveal",
        json={"path": str(outside)},
    )

    assert response.status_code == 400
    assert "configured model directory" in response.json()["detail"]
