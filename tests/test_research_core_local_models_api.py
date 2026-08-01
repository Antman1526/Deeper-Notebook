"""Research Core's redacted local-model readiness API."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models.contracts import LocalModelRouteCandidate


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


def test_settings_api_persists_valid_root_without_returning_config_secrets(
    monkeypatch, tmp_path: Path
):
    from desktop.config import Config

    root = tmp_path / "Model Library With Spaces"
    root.mkdir()
    config_path = tmp_path / "config.toml"
    Config(
        model_dir=root,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="not-for-api",
        encryption_key="not-for-api-either",
    ).save(config_path)
    monkeypatch.setattr("desktop.config.default_config_path", lambda: config_path)

    with TestClient(_app()) as client:
        response = client.put(
            "/api/local-models/settings",
            json={"model_dir": str(root), "compute_profile": "balanced"},
        )
        fetched = client.get("/api/local-models/settings")

    assert response.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["model_dir"] == str(root)
    assert "not-for-api" not in str(fetched.json())
    assert "encryption" not in str(fetched.json()).lower()


def test_settings_api_rejects_an_invalid_model_root(monkeypatch, tmp_path: Path):
    from desktop.config import Config

    config_path = tmp_path / "config.toml"
    root = tmp_path / "valid"
    root.mkdir()
    Config(root, "none", "", "root", "not-for-api").save(config_path)
    monkeypatch.setattr("desktop.config.default_config_path", lambda: config_path)

    with TestClient(_app()) as client:
        response = client.put(
            "/api/local-models/settings", json={"model_dir": str(tmp_path / "missing")}
        )

    assert response.status_code == 422


def test_strict_local_route_plan_does_not_use_injected_non_loopback_transport():
    app = _app()
    calls: list[str] = []
    app.state.local_model_route_candidates = [
        LocalModelRouteCandidate(
            model_id="remote-model",
            provider="remote",
            fingerprint="remote",
            modalities=("text",),
            accepted_roles=("research_chat",),
            context_tokens=4096,
            supports_structured_output=True,
            readiness="ready_verified",
            health_healthy=True,
            accepted_quality=1.0,
            benchmarked_at=1.0,
            peak_memory_bytes=1,
            latency_ms=1,
            is_local=False,
        )
    ]
    app.state.local_model_transport = lambda url: calls.append(url)

    with TestClient(app) as client:
        response = client.post(
            "/api/local-models/route-plan",
            json={
                "role": "research_chat",
                "execution_policy": "strict_local",
                "compute_profile": "balanced",
            },
        )

    assert response.status_code == 200
    assert response.json()["outcome"] == "blocked"
    assert calls == []
