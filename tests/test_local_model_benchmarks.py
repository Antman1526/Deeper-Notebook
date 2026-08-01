"""Local model benchmark job foundation tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models import benchmarks as benchmarks_mod
from deeper_notebook.local_models.benchmarks import (
    BenchmarkMeasurement,
    BenchmarkResult,
    QualityMeasurement,
    benchmark_is_accepted,
    clear_benchmark_jobs,
    get_benchmark_job,
    list_benchmark_jobs,
    load_benchmark_history,
    resolve_measured_model_id,
    save_benchmark_history,
    score_benchmark_measurement,
    start_benchmark,
)
from deeper_notebook.local_models.gguf_metadata import GGUFMetadata
from deeper_notebook.local_models.inventory import LocalModelInfo
from deeper_notebook.local_models.role_routing import recommend_model_roles


def _make_gguf(path: Path, name: str) -> Path:
    model = path / "GGUF" / name
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x" * 4096)
    return model


def _local_model(name: str, *, params: float, context: int) -> LocalModelInfo:
    return LocalModelInfo(
        name=name,
        path=f"/models/{name}.gguf",
        runtime="gguf",
        metadata=GGUFMetadata(
            architecture=None,
            context_length=context,
            quant="Q4_K_M",
            parameter_count_b=params,
            file_size_bytes=1024,
        ),
    )


@pytest.mark.asyncio
async def test_benchmark_job_measures_registered_role_models(tmp_path):
    _make_gguf(tmp_path, "Qwen3-Coder-30B-A3B-Q4_K_M.gguf")
    _make_gguf(tmp_path, "gemma-3-4b-it-Q4_K_M.gguf")

    async def _registered_models():
        return [
            SimpleNamespace(
                id="model:qwen-coder",
                name="Qwen3-Coder-30B-A3B-Q4_K_M",
                provider="openai_compatible",
            ),
            SimpleNamespace(
                id="model:gemma",
                name="gemma-3-4b-it-Q4_K_M",
                provider="openai_compatible",
            ),
        ]

    async def _runner(role, registered_model, _local_model):
        if role == "source_synthesis":
            return BenchmarkMeasurement(latency_ms=800, tokens_per_second=42)
        return BenchmarkMeasurement(latency_ms=350, tokens_per_second=68)

    clear_benchmark_jobs()
    job = await start_benchmark(
        tmp_path,
        roles=["source_synthesis", "study_fast"],
        registered_models_loader=_registered_models,
        benchmark_runner=_runner,
        run_inline=True,
    )

    assert job.status == "completed"
    assert [result.role for result in job.results] == ["source_synthesis", "study_fast"]
    by_role = {result.role: result for result in job.results}
    assert by_role["source_synthesis"].status == "completed"
    assert by_role["source_synthesis"].model_id == "model:qwen-coder"
    assert by_role["source_synthesis"].latency_ms == 800
    assert by_role["source_synthesis"].tokens_per_second == 42
    assert by_role["source_synthesis"].benchmark_fingerprint
    assert by_role["study_fast"].model_id == "model:gemma"
    assert by_role["study_fast"].score > by_role["source_synthesis"].score
    history = load_benchmark_history(tmp_path)
    assert [item.role for item in history] == ["source_synthesis", "study_fast"]
    assert history[0].model_id == "model:qwen-coder"


def test_quality_score_uses_role_weights_and_persists_raw_and_normalized_metrics(
    tmp_path,
):
    measurement = BenchmarkMeasurement(
        latency_ms=200,
        tokens_per_second=50,
        quality=QualityMeasurement(
            schema_valid=True,
            citation_fidelity=True,
            instruction_following=True,
            tool_calling=True,
            context_recall=True,
            answer_correctness=True,
            refusal_when_evidence_absent=True,
        ),
    )

    assert score_benchmark_measurement("source_synthesis", measurement) == 100.0

    result = BenchmarkResult(
        role="source_synthesis",
        label="Source synthesis",
        status="completed",
        latency_ms=measurement.latency_ms,
        tokens_per_second=measurement.tokens_per_second,
        quality=measurement.quality,
        normalized_metrics=measurement.normalized_metrics(),
        score=score_benchmark_measurement("source_synthesis", measurement),
    )
    save_benchmark_history(tmp_path, [result])

    restored = load_benchmark_history(tmp_path)[0]
    assert restored.quality == measurement.quality
    assert restored.normalized_metrics == {
        "latency": 100.0,
        "throughput": 100.0,
        "schema": 100.0,
        "citation": 100.0,
        "instruction": 100.0,
        "tool": 100.0,
        "context": 100.0,
        "correctness": 100.0,
        "refusal": 100.0,
    }


def test_legacy_speed_only_history_rows_remain_readable_as_performance_only(tmp_path):
    history_path = benchmarks_mod.benchmark_history_path(tmp_path)
    history_path.parent.mkdir(parents=True)
    history_path.write_text(
        """{"results": [{"role": "chat", "label": "Chat", "status": "completed", "latency_ms": 500, "tokens_per_second": 25, "score": 24.5}]}""",
        encoding="utf-8",
    )

    restored = load_benchmark_history(tmp_path)

    assert len(restored) == 1
    assert restored[0].quality is None
    assert restored[0].normalized_metrics == {"latency": 100.0, "throughput": 50.0}
    assert restored[0].score == 24.5
    assert benchmark_is_accepted(restored[0], now=1_000.0) is False


def test_benchmark_persists_peak_memory_fingerprint_and_fresh_accepted_quality(
    tmp_path,
):
    result = BenchmarkResult(
        role="research_chat",
        label="Research chat",
        status="completed",
        latency_ms=250,
        tokens_per_second=40,
        peak_memory_bytes=4 * 1024**3,
        benchmark_fingerprint="model-fingerprint-1",
        completed_at=900.0,
        quality=QualityMeasurement(answer_correctness=True),
        score=82.0,
    )
    save_benchmark_history(tmp_path, [result])

    restored = load_benchmark_history(tmp_path)[0]

    assert restored.peak_memory_bytes == 4 * 1024**3
    assert restored.benchmark_fingerprint == "model-fingerprint-1"
    assert benchmark_is_accepted(restored, now=1_000.0) is True
    assert benchmark_is_accepted(restored, now=31 * 24 * 60 * 60) is False


def test_legacy_benchmark_filename_is_read_but_new_writes_are_canonical(tmp_path):
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    legacy = manifests / "open-notebook-plus-benchmarks.json"
    legacy.write_text(
        '{"results": [{"role": "chat", "label": "Legacy", '
        '"status": "completed", "score": 1.0}]}',
        encoding="utf-8",
    )

    restored = load_benchmark_history(tmp_path)
    canonical = benchmarks_mod.benchmark_history_path(tmp_path)
    save_benchmark_history(tmp_path, restored)

    assert canonical.name == "deeper-notebook-benchmarks.json"
    assert canonical.is_file()
    assert legacy.read_text(encoding="utf-8").startswith('{"results"')


@pytest.mark.asyncio
async def test_benchmark_skips_role_when_context_or_structured_output_gate_fails(
    tmp_path,
):
    _make_gguf(tmp_path, "Qwen3-Coder-30B-A3B-Q4_K_M.gguf")

    async def _registered_models():
        return [
            SimpleNamespace(
                id="model:qwen-coder",
                name="Qwen3-Coder-30B-A3B-Q4_K_M",
                provider="openai_compatible",
                supports_structured_output=False,
            )
        ]

    async def _runner(_role, _registered_model, _local_model):
        raise AssertionError("runner should not run when a task gate fails")

    clear_benchmark_jobs()
    job = await start_benchmark(
        tmp_path,
        roles=["source_synthesis"],
        registered_models_loader=_registered_models,
        benchmark_runner=_runner,
        run_inline=True,
    )

    result = job.results[0]
    assert result.status == "skipped"
    assert "structured output" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_benchmark_job_marks_unregistered_recommendations_skipped(tmp_path):
    _make_gguf(tmp_path, "Qwen3-Coder-30B-A3B-Q4_K_M.gguf")

    async def _registered_models():
        return []

    async def _runner(_role, _registered_model, _local_model):
        raise AssertionError("runner should not run without registered model")

    clear_benchmark_jobs()
    job = await start_benchmark(
        tmp_path,
        roles=["source_synthesis"],
        registered_models_loader=_registered_models,
        benchmark_runner=_runner,
        run_inline=True,
    )

    assert job.status == "completed"
    assert len(job.results) == 1
    result = job.results[0]
    assert result.status == "skipped"
    assert result.model_id is None
    assert "registered" in (result.error or "").lower()


def test_benchmark_endpoint_starts_and_lists_jobs(app, tmp_path, monkeypatch):
    _make_gguf(tmp_path, "gemma-3-4b-it-Q4_K_M.gguf")
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    async def _registered_models():
        return []

    monkeypatch.setattr(
        benchmarks_mod,
        "_load_registered_language_models",
        _registered_models,
    )
    clear_benchmark_jobs()

    with TestClient(app) as client:
        start_resp = client.post(
            "/api/local-models/benchmarks",
            json={"roles": ["study_fast"], "run_inline": True},
        )
        list_resp = client.get("/api/local-models/benchmarks")

    assert start_resp.status_code == 200
    start_body = start_resp.json()
    assert start_body["status"] == "completed"
    assert start_body["roles"] == ["study_fast"]
    assert list_resp.status_code == 200
    assert [job["job_id"] for job in list_resp.json()["benchmarks"]] == [
        start_body["job_id"]
    ]
    assert get_benchmark_job(start_body["job_id"]) is not None
    assert len(list_benchmark_jobs()) == 1


def test_benchmark_endpoint_rejects_missing_model_dir(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path / "missing"))

    with TestClient(app) as client:
        response = client.post("/api/local-models/benchmarks", json={})

    assert response.status_code == 400
    assert "model directory" in response.json()["detail"].lower()


def test_role_routing_prefers_persisted_benchmark_winner_over_heuristic():
    qwen = _local_model("Qwen3-Coder-30B-A3B-Q4_K_M", params=30, context=262144)
    gemma = _local_model("gemma-3-4b-it-Q4_K_M", params=4, context=32768)

    routes = recommend_model_roles(
        [qwen, gemma],
        benchmark_results=[
            SimpleNamespace(
                role="source_synthesis",
                status="completed",
                model_name="gemma-3-4b-it-Q4_K_M",
                model_path=gemma.path,
                score=95,
            )
        ],
    )

    by_role = {route.role: route for route in routes}
    assert by_role["source_synthesis"].model is not None
    assert by_role["source_synthesis"].model.name == "gemma-3-4b-it-Q4_K_M"
    assert "measured" in by_role["source_synthesis"].reason.lower()


def test_role_routing_endpoint_uses_persisted_benchmark_history(
    app, monkeypatch, tmp_path
):
    _make_gguf(tmp_path, "Qwen3-Coder-30B-A3B-Q4_K_M.gguf")
    gemma_path = _make_gguf(tmp_path, "gemma-3-4b-it-Q4_K_M.gguf")
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    save_benchmark_history(
        tmp_path,
        [
            BenchmarkResult(
                role="source_synthesis",
                label="Source synthesis",
                status="completed",
                model_name="gemma-3-4b-it-Q4_K_M",
                model_path=str(gemma_path),
                model_runtime="gguf",
                model_id="model:gemma",
                provider="openai_compatible",
                latency_ms=200,
                tokens_per_second=96,
                score=95.8,
            )
        ],
    )
    assert load_benchmark_history(tmp_path)[0].model_path == str(gemma_path)

    with TestClient(app) as client:
        response = client.get("/api/local-models/role-routing")

    assert response.status_code == 200
    roles = {route["role"]: route for route in response.json()["routes"]}
    assert roles["source_synthesis"]["model"]["name"] == "gemma-3-4b-it-Q4_K_M"
    assert "Measured" in roles["source_synthesis"]["reason"]


@pytest.mark.asyncio
async def test_resolve_measured_model_id_uses_best_registered_benchmark_match(tmp_path):
    save_benchmark_history(
        tmp_path,
        [
            BenchmarkResult(
                role="chat",
                label="Chat",
                status="completed",
                model_name="Qwen3-Coder-30B-A3B-Q4_K_M",
                model_path="/models/qwen.gguf",
                model_id="model:qwen",
                provider="openai_compatible",
                score=42.0,
            ),
            BenchmarkResult(
                role="chat",
                label="Chat",
                status="completed",
                model_name="gemma-3-4b-it-Q4_K_M",
                model_path="/models/gemma.gguf",
                model_id="model:stale-gemma-id",
                provider="openai_compatible",
                score=95.0,
            ),
        ],
    )

    async def _registered_models():
        return [
            SimpleNamespace(
                id="model:qwen",
                name="Qwen3-Coder-30B-A3B-Q4_K_M",
                provider="openai_compatible",
            ),
            SimpleNamespace(
                id="model:gemma",
                name="gemma-3-4b-it-Q4_K_M",
                provider="openai_compatible",
            ),
        ]

    assert (
        await resolve_measured_model_id(
            tmp_path,
            "chat",
            registered_models_loader=_registered_models,
        )
        == "model:gemma"
    )


@pytest.mark.asyncio
async def test_resolve_measured_model_id_returns_none_without_completed_history(
    tmp_path,
):
    save_benchmark_history(
        tmp_path,
        [
            BenchmarkResult(
                role="chat",
                label="Chat",
                status="failed",
                model_name="gemma-3-4b-it-Q4_K_M",
                model_id="model:gemma",
                score=99.0,
            )
        ],
    )

    async def _registered_models():
        return [
            SimpleNamespace(
                id="model:gemma",
                name="gemma-3-4b-it-Q4_K_M",
                provider="openai_compatible",
            )
        ]

    assert (
        await resolve_measured_model_id(
            tmp_path,
            "chat",
            registered_models_loader=_registered_models,
        )
        is None
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a
