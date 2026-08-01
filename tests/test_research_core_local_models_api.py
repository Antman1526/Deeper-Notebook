"""Research Core's redacted local-model readiness API."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(local_models_router.router)
    return app


def test_readiness_endpoint_keeps_every_disallowed_state_visible_and_redacted(
    monkeypatch,
    tmp_path: Path,
):
    root = tmp_path / "AI_Models"
    root.mkdir()
    active = root / "active-unverified-7b-q4_k_m.gguf"
    mismatch = root / "runtime-mismatch-7b-q4_k_m.gguf"
    partial = root / "partial-7b-q4_k_m.gguf.part"
    active.write_bytes(b"active weights")
    mismatch.write_bytes(b"mismatched weights")
    partial.write_bytes(b"partial weights")
    transformers = root / "Transformers" / "example__unsupported-4B"
    transformers.mkdir(parents=True)
    (transformers / "config.json").write_text('{"model_type": "example"}')
    (transformers / "model.safetensors").write_bytes(b"transformer weights")
    manifest = root / "manifests" / "model_inventory.md"
    manifest.parent.mkdir()
    manifest.write_text(
        "\n".join([
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            "| Planned | primary | `planned/model` | `MLX/planned__model` | MLX | planned | later |",
            "| Removed | backup | `removed/model` | `GGUF/removed.gguf` | GGUF | removed | retired |",
        ])
    )
    before = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(root))
    monkeypatch.setenv("DEEPER_NOTEBOOK_ACTIVE_GGUF_MODEL", str(active))

    with TestClient(_app()) as client:
        response = client.get("/api/local-models/readiness")

    assert response.status_code == 200
    body = response.json()
    assert "path" not in str(body)
    states = {row["readiness"] for row in body["models"]}
    assert {
        "planned",
        "removed",
        "incomplete",
        "installed_unsupported",
        "ready_unverified",
        "runtime_unavailable",
    } <= states
    for row in body["models"]:
        assert {
            "model_id",
            "format",
            "modality",
            "readiness",
            "readiness_reason",
            "measured_tier",
            "accepted_roles",
            "route_eligible",
        } <= set(row)
        assert row["route_eligible"] is False
        assert "path" not in row
    after = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
