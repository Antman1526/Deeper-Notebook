"""Model-role routing foundation for local model fleets."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models.benchmarks import (
    BenchmarkResult,
    save_benchmark_history,
)
from deeper_notebook.local_models.gguf_metadata import GGUFMetadata
from deeper_notebook.local_models.inventory import LocalModelInfo
from deeper_notebook.local_models.manifest import ManifestModelEntry
from deeper_notebook.local_models.role_routing import recommend_model_roles


def _model(
    name: str,
    *,
    runtime: str = "gguf",
    params: float | None = None,
    context: int | None = None,
    arch: str | None = None,
) -> LocalModelInfo:
    return LocalModelInfo(
        name=name,
        path=f"/models/{name}",
        runtime=runtime,
        metadata=GGUFMetadata(
            architecture=arch,
            context_length=context,
            quant=None,
            parameter_count_b=params,
            file_size_bytes=1024,
        ),
    )


def test_role_routing_prefers_specialized_models_without_using_embeddings():
    routes = recommend_model_roles(
        [
            _model("nomic-embed-text-v1.5", params=0.1),
            _model(
                "mlx-community/North-Mini-Code-1.0-6bit",
                runtime="mlx",
                params=7,
                context=32768,
            ),
            _model("Qwen3-Coder-30B-A3B-Q4_K_M", params=30, context=262144),
            _model("gemma-3-4b-it-Q4_K_M", params=4, context=32768),
        ]
    )

    by_role = {route.role: route for route in routes}

    assert by_role["coding_research"].model is not None
    assert by_role["coding_research"].model.name == "Qwen3-Coder-30B-A3B-Q4_K_M"
    assert by_role["source_synthesis"].model is not None
    assert by_role["source_synthesis"].model.name == "Qwen3-Coder-30B-A3B-Q4_K_M"
    assert by_role["study_fast"].model is not None
    assert by_role["study_fast"].model.name == "gemma-3-4b-it-Q4_K_M"
    assert by_role["embedding"].model is not None
    assert by_role["embedding"].model.name == "nomic-embed-text-v1.5"
    assert by_role["chat"].model is not None
    assert "embed" not in by_role["chat"].model.name.lower()


def test_role_routing_returns_empty_recommendations_when_no_model_fits():
    routes = recommend_model_roles(
        [
            _model("nomic-embed-text-v1.5", params=0.1),
        ]
    )

    by_role = {route.role: route for route in routes}

    assert by_role["chat"].model is None
    assert by_role["source_synthesis"].model is None
    assert by_role["coding_research"].model is None
    assert by_role["study_fast"].model is None
    assert by_role["embedding"].model is not None


def test_role_routing_exposes_the_pure_local_planner_adapter():
    from deeper_notebook.local_models.contracts import (
        LocalModelRouteCandidate,
        RouteRequest,
    )
    from deeper_notebook.local_models.role_routing import plan_local_model_route

    candidate = LocalModelRouteCandidate(
        model_id="local:chat",
        provider="loopback",
        fingerprint="fp-chat",
        modalities=("text",),
        accepted_roles=("research_chat",),
        context_tokens=8192,
        supports_structured_output=False,
        readiness="ready_verified",
        health_healthy=True,
        accepted_quality=88.0,
        benchmarked_at=1_000.0,
        peak_memory_bytes=4 * 1024**3,
        latency_ms=100,
    )

    plan = plan_local_model_route(
        [candidate], RouteRequest(role="research_chat"), now=1_001.0
    )

    assert plan.selected_model_id == "local:chat"


def test_role_routing_does_not_recommend_transformers_repos_without_runtime_provider():
    routes = recommend_model_roles(
        [
            _model(
                "microsoft/FastContext-1.0-4B-SFT",
                runtime="transformers",
                params=4,
                context=65536,
            ),
        ]
    )

    by_role = {route.role: route for route in routes}

    assert by_role["chat"].model is None
    assert by_role["source_synthesis"].model is None
    assert by_role["coding_research"].model is None
    assert by_role["study_fast"].model is None


def test_role_routing_prefers_curated_primary_mlx_before_generic_scoring():
    curated = _model(
        "mlx-community/North-Mini-Code-1.0-6bit",
        runtime="mlx",
        params=7,
        context=32768,
    )
    generic = _model("Qwen3-Coder-30B-A3B-Q4_K_M", params=30, context=262144)

    routes = recommend_model_roles(
        [generic, curated],
        manifest_entries=[
            ManifestModelEntry(
                manifest_path="/models/manifests/model_inventory.md",
                category="Coding Assistant - Mac MLX",
                role="primary",
                repo="mlx-community/North-Mini-Code-1.0-6bit",
                local_path=curated.path,
                runtime_type="MLX",
                estimated_status="downloaded - verified",
                notes="coding and agent workflows",
            )
        ],
    )

    by_role = {route.role: route for route in routes}

    assert by_role["coding_research"].model is not None
    assert (
        by_role["coding_research"].model.name
        == "mlx-community/North-Mini-Code-1.0-6bit"
    )
    assert "Curated primary manifest row" in by_role["coding_research"].reason


def test_role_routing_endpoint_uses_inventory(app, monkeypatch, tmp_path):
    repo = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    repo.mkdir(parents=True)
    (repo / "config.json").write_text(
        '{"model_type": "qwen2", "max_position_embeddings": 32768}'
    )
    (repo / "model.safetensors").write_bytes(b"x" * 2048)
    gguf = tmp_path / "GGUF" / "Qwen3-Coder-30B-A3B-Q4_K_M.gguf"
    gguf.parent.mkdir()
    gguf.write_bytes(b"y" * 4096)
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/role-routing")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["model_dir"] == str(tmp_path)
    roles = {route["role"]: route for route in body["routes"]}
    assert roles["chat"]["model"]["runtime"] in {"gguf", "mlx"}
    assert roles["coding_research"]["model"]["name"] == "Qwen3-Coder-30B-A3B-Q4_K_M"


def test_role_routing_endpoint_attaches_manifest_matches(app, monkeypatch, tmp_path):
    repo = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    repo.mkdir(parents=True)
    (repo / "config.json").write_text(
        '{"model_type": "qwen2", "max_position_embeddings": 32768}'
    )
    (repo / "model.safetensors").write_bytes(b"x" * 2048)
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir()
    manifest.write_text(
        "\n".join(
            [
                "# Local Model Inventory",
                "",
                "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
                "|---|---|---|---|---|---|---|",
                "| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `"
                + str(repo)
                + "` | MLX | downloaded - verified | coding and agent workflows |",
            ]
        )
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/role-routing")

    assert resp.status_code == 200
    body = resp.json()
    assert body["manifest"]["available"] is True
    assert body["manifest"]["entry_count"] == 1
    assert body["manifest"]["unmatched_entry_count"] == 0
    assert body["manifest"]["unmatched_entries"] == []
    roles = {route["role"]: route for route in body["routes"]}
    assert (
        roles["chat"]["manifest_matches"][0]["category"] == "Coding Assistant - Mac MLX"
    )
    assert roles["chat"]["manifest_alignment"]["status"] == "primary"
    assert roles["chat"]["manifest_alignment"]["matched_count"] == 1


def test_role_routing_endpoint_reports_unmatched_manifest_entries(
    app, monkeypatch, tmp_path
):
    scanned_repo = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    scanned_repo.mkdir(parents=True)
    (scanned_repo / "config.json").write_text(
        '{"model_type": "qwen2", "max_position_embeddings": 32768}'
    )
    (scanned_repo / "model.safetensors").write_bytes(b"x" * 2048)
    missing_repo = tmp_path / "MLX" / "missing__Curated-Model-4bit"
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir()
    manifest.write_text(
        "\n".join(
            [
                "# Local Model Inventory",
                "",
                "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
                "|---|---|---|---|---|---|---|",
                "| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `"
                + str(scanned_repo)
                + "` | MLX | downloaded - verified | coding and agent workflows |",
                "| Reasoning - Mac MLX | backup | `missing/Curated-Model-4bit` | `"
                + str(missing_repo)
                + "` | MLX | missing from scan | should be checked |",
            ]
        )
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/role-routing")

    assert resp.status_code == 200
    manifest_summary = resp.json()["manifest"]
    assert manifest_summary["entry_count"] == 2
    assert manifest_summary["unmatched_entry_count"] == 1
    assert (
        manifest_summary["unmatched_entries"][0]["repo"] == "missing/Curated-Model-4bit"
    )


def test_role_routing_endpoint_returns_manifest_reconciliation(
    app, monkeypatch, tmp_path
):
    mlx_repo = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    mlx_repo.mkdir(parents=True)
    (mlx_repo / "config.json").write_text(
        '{"model_type": "qwen2", "max_position_embeddings": 32768}'
    )
    (mlx_repo / "model.safetensors").write_bytes(b"x" * 2048)
    transformers_repo = tmp_path / "Transformers" / "microsoft__FastContext-1.0-4B-SFT"
    transformers_repo.mkdir(parents=True)
    (transformers_repo / "config.json").write_text(
        '{"model_type": "llama", "max_position_embeddings": 65536}'
    )
    (transformers_repo / "model.safetensors").write_bytes(b"y" * 2048)
    missing_repo = tmp_path / "MLX" / "missing__Curated-Model-4bit"
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir()
    manifest.write_text(
        "\n".join(
            [
                "# Local Model Inventory",
                "",
                "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
                "|---|---|---|---|---|---|---|",
                f"| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `{mlx_repo}` | MLX | downloaded - verified | ready |",
                f"| Agentic Workflows - Transformers | backup | `microsoft/FastContext-1.0-4B-SFT` | `{transformers_repo}` | Transformers | skipped - existing verified | needs runtime |",
                f"| Reasoning - Mac MLX | backup | `missing/Curated-Model-4bit` | `{missing_repo}` | MLX | missing from scan | should be checked |",
            ]
        )
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/role-routing")

    assert resp.status_code == 200
    manifest_summary = resp.json()["manifest"]
    assert manifest_summary["reconciliation_counts"] == {
        "matched": 1,
        "missing": 1,
        "unsupported_runtime": 1,
    }
    by_repo = {row["repo"]: row for row in manifest_summary["reconciliation_entries"]}
    assert by_repo["mlx-community/North-Mini-Code-1.0-6bit"]["status"] == "matched"
    assert (
        by_repo["microsoft/FastContext-1.0-4B-SFT"]["status"] == "unsupported_runtime"
    )
    assert (
        by_repo["microsoft/FastContext-1.0-4B-SFT"]["setup_task"]["action_type"]
        == "configure_runtime"
    )
    assert by_repo["missing/Curated-Model-4bit"]["status"] == "missing"
    assert (
        by_repo["missing/Curated-Model-4bit"]["setup_task"]["action_type"]
        == "download_snapshot"
    )
    assert by_repo["missing/Curated-Model-4bit"]["setup_task"]["command"] == (
        f"huggingface-cli download missing/Curated-Model-4bit --local-dir {missing_repo}"
    )


def test_role_routing_endpoint_reports_manifest_alignment_counts(
    app, monkeypatch, tmp_path
):
    curated_primary = tmp_path / "GGUF" / "Qwen3-Coder-30B-A3B-Q4_K_M.gguf"
    curated_primary.parent.mkdir(parents=True)
    curated_primary.write_bytes(b"y" * 4096)
    untracked = tmp_path / "GGUF" / "gemma-3-4b-it-Q4_K_M.gguf"
    untracked.write_bytes(b"z" * 4096)
    manifest_fast = tmp_path / "GGUF" / "Qwen3-8B-Q4_K_M.gguf"
    manifest_fast.write_bytes(b"q" * 4096)
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir()
    manifest.write_text(
        "\n".join(
            [
                "# Local Model Inventory",
                "",
                "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
                "|---|---|---|---|---|---|---|",
                f"| Coding Assistant - GGUF | primary | `local/Qwen3-Coder-30B-A3B-Q4_K_M` | `{curated_primary}` | GGUF | downloaded - verified | ready |",
                f"| General Chat / Research - GGUF | backup | `unsloth/Qwen3-8B-GGUF` | `{manifest_fast}` | GGUF | downloaded - verified | fast general fallback |",
            ]
        )
    )
    save_benchmark_history(
        tmp_path,
        [
            BenchmarkResult(
                role="study_fast",
                label="Fast study tools",
                status="completed",
                model_name="gemma-3-4b-it-Q4_K_M",
                model_path=str(untracked),
                model_runtime="gguf",
                model_id="model:gemma",
                provider="openai_compatible",
                score=99.0,
            )
        ],
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/role-routing")

    assert resp.status_code == 200
    body = resp.json()
    assert body["manifest"]["alignment_counts"]["primary"] >= 1
    assert body["manifest"]["alignment_counts"]["untracked"] >= 1
    roles = {route["role"]: route for route in body["routes"]}
    assert roles["coding_research"]["manifest_alignment"]["status"] == "primary"
    assert roles["study_fast"]["manifest_alignment"]["status"] == "untracked"
    assert (
        "not in the curated AI_Models manifest"
        in (roles["study_fast"]["manifest_alignment"]["reason"])
    )
    assert (
        roles["study_fast"]["manifest_alternatives"][0]["repo"]
        == "unsloth/Qwen3-8B-GGUF"
    )
    assert (
        roles["study_fast"]["manifest_alternatives"][0]["matched_model_name"]
        == "Qwen3-8B-Q4_K_M"
    )
    assert "study" in roles["study_fast"]["manifest_alternatives"][0]["reason"].lower()
    assert roles["embedding"]["manifest_alternatives"] == []
    assert "No curated embedding" in roles["embedding"]["manifest_alternative_note"]


def test_role_routing_endpoint_missing_dir(app, monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(missing))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/role-routing")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["routes"] == []


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a
