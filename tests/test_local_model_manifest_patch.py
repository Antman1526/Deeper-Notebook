"""Safe manifest row preview/apply tests for local model curation."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models.manifest import load_model_manifest


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(local_models_router.router)
    return app


def _write_manifest(root: Path) -> Path:
    manifest = root / "manifests" / "model_inventory.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "\n".join(
            [
                "# Local Model Inventory",
                "",
                "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
                "|---|---|---|---|---|---|---|",
                f"| Coding Assistant - GGUF | primary | `local/Qwen3-Coder` | `{root / 'GGUF' / 'qwen-coder.gguf'}` | GGUF | downloaded - verified | ready |",
            ]
        )
        + "\n"
    )
    return manifest


def test_manifest_row_preview_validates_without_writing(monkeypatch, tmp_path):
    manifest = _write_manifest(tmp_path)
    original = manifest.read_text()
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    row = (
        "| Fast study tools - Suggested | candidate - study_fast | "
        "`unsloth/Qwen3-8B-GGUF` | "
        f"`{tmp_path / 'GGUF' / 'Qwen3-8B-Q4_K_M.gguf'}` | "
        "GGUF | suggested - review | suggested backup |"
    )

    with TestClient(_app()) as client:
        resp = client.post(
            "/api/local-models/manifest/rows/preview",
            json={"row": row},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["manifest_path"] == str(manifest)
    assert body["duplicate"] is False
    assert body["entry"]["repo"] == "unsloth/Qwen3-8B-GGUF"
    assert body["row"] == row
    assert manifest.read_text() == original


def test_manifest_row_apply_appends_normalized_row_and_creates_backup(
    monkeypatch, tmp_path
):
    manifest = _write_manifest(tmp_path)
    original = manifest.read_text()
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    row = (
        "| Embedding and retrieval - Suggested | candidate - embedding | "
        "`nomic-ai/nomic-embed-text-v1.5-GGUF` | "
        f"`{tmp_path / 'GGUF' / 'nomic-embed-text-v1.5.f16.gguf'}` | "
        "GGUF | suggested - review | embedding candidate |"
    )

    with TestClient(_app()) as client:
        resp = client.post(
            "/api/local-models/manifest/rows/apply",
            json={"row": row},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["duplicate"] is False
    assert body["backup_path"]
    backup = Path(body["backup_path"])
    assert backup.exists()
    assert backup.read_text() == original
    assert row in manifest.read_text()
    entries = load_model_manifest(tmp_path)
    assert entries[-1].category == "Embedding and retrieval - Suggested"
    assert entries[-1].repo == "nomic-ai/nomic-embed-text-v1.5-GGUF"


def test_manifest_row_apply_rejects_duplicates_without_appending(monkeypatch, tmp_path):
    manifest = _write_manifest(tmp_path)
    original = manifest.read_text()
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    duplicate_row = (
        "| Coding Assistant - GGUF | backup | `local/Qwen3-Coder` | "
        f"`{tmp_path / 'GGUF' / 'qwen-coder.gguf'}` | GGUF | suggested - review | duplicate |"
    )

    with TestClient(_app()) as client:
        preview = client.post(
            "/api/local-models/manifest/rows/preview",
            json={"row": duplicate_row},
        )
        resp = client.post(
            "/api/local-models/manifest/rows/apply",
            json={"row": duplicate_row},
        )

    assert preview.status_code == 200
    assert preview.json()["duplicate"] is True
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]
    assert manifest.read_text() == original
    assert not list(manifest.parent.glob("model_inventory.md.bak-*"))


def test_manifest_row_preview_rejects_bad_rows(monkeypatch, tmp_path):
    _write_manifest(tmp_path)
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(_app()) as client:
        resp = client.post(
            "/api/local-models/manifest/rows/preview",
            json={"row": "| Category | Role | Repo |"},
        )

    assert resp.status_code == 400
    assert "seven cells" in resp.json()["detail"]


def test_manifest_row_preview_requires_configured_model_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path / "missing"))

    with TestClient(_app()) as client:
        resp = client.post(
            "/api/local-models/manifest/rows/preview",
            json={
                "row": "| A | b | `repo/name` | `/tmp/model.gguf` | GGUF | suggested | note |"
            },
        )

    assert resp.status_code == 400
    assert "Model directory not found" in resp.json()["detail"]
