"""Phase 3 Task 3.2 contracts for measured local-model routing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from open_notebook.ai import models, offline_gate
from open_notebook.health.network import NetworkState
from open_notebook.local_models.gguf_metadata import GGUFMetadata
from open_notebook.local_models.inventory import LocalModelInfo
from open_notebook.local_models.role_routing import (
    BENCHMARK_MAX_AGE_SECONDS,
    MeasuredModelRoute,
    retry_measured_model_route_once,
    select_measured_model_route,
)

NOW = 1_750_000_000.0


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _local_model(tmp_path: Path, name: str, *, context: int = 32_768):
    path = tmp_path / f"{name}.gguf"
    path.write_bytes(b"model")
    return LocalModelInfo(
        name=name,
        path=str(path),
        runtime="gguf",
        metadata=GGUFMetadata(
            architecture="llama",
            context_length=context,
            quant="Q4_K_M",
            parameter_count_b=7.0,
            file_size_bytes=path.stat().st_size,
        ),
    )


def _registered(model_id: str, name: str, **extra):
    return SimpleNamespace(
        id=model_id,
        name=name,
        provider=extra.pop("provider", "openai_compatible"),
        type="language",
        supports_structured_output=extra.pop("supports_structured_output", True),
        **extra,
    )


def _result(model_id: str, model: LocalModelInfo, **extra):
    return SimpleNamespace(
        role=extra.pop("role", "source_synthesis"),
        status="completed",
        model_id=model_id,
        model_name=model.name,
        model_path=model.path,
        score=extra.pop("score", 90.0),
        latency_ms=extra.pop("latency_ms", 300),
        quality=extra.pop("quality", {"answer_correctness": True}),
        benchmarked_at=extra.pop("benchmarked_at", NOW - 60),
        **extra,
    )


def test_measured_route_orders_quality_then_latency_then_model_id(tmp_path):
    alpha = _local_model(tmp_path, "alpha")
    beta = _local_model(tmp_path, "beta")
    gamma = _local_model(tmp_path, "gamma")
    route = select_measured_model_route(
        "source_synthesis",
        benchmark_results=[
            _result("model:gamma", gamma, score=94, latency_ms=10),
            _result("model:beta", beta, score=95, latency_ms=600),
            _result("model:alpha", alpha, score=95, latency_ms=120),
        ],
        registered_models=[
            _registered("model:gamma", gamma.name),
            _registered("model:beta", beta.name),
            _registered("model:alpha", alpha.name),
        ],
        local_models=[alpha, beta, gamma],
        required_context_tokens=8192,
        now=NOW,
    )

    assert route is not None
    assert route.selected_model_id == "model:alpha"
    assert route.fallback_model_id == "model:beta"
    assert route.benchmark_age_seconds == 60


def test_measured_route_requires_fresh_healthy_on_disk_compatible_quality(tmp_path):
    good = _local_model(tmp_path, "good", context=32_768)
    old = _local_model(tmp_path, "old", context=32_768)
    unhealthy = _local_model(tmp_path, "unhealthy", context=32_768)
    small = _local_model(tmp_path, "small", context=4096)
    missing = LocalModelInfo(
        name="missing",
        path=str(tmp_path / "missing.gguf"),
        runtime="gguf",
        metadata=good.metadata,
    )
    route = select_measured_model_route(
        "source_synthesis",
        benchmark_results=[
            _result(
                "model:old",
                old,
                score=100,
                benchmarked_at=NOW - BENCHMARK_MAX_AGE_SECONDS - 1,
            ),
            _result("model:unhealthy", unhealthy, score=99),
            _result("model:small", small, score=98),
            _result("model:missing", missing, score=97),
            _result(
                "model:legacy",
                good,
                score=96,
                quality=None,
                normalized_metrics={"latency": 100},
            ),
            _result("model:good", good, score=80),
        ],
        registered_models=[
            _registered("model:old", old.name),
            _registered("model:unhealthy", unhealthy.name),
            _registered("model:small", small.name),
            _registered("model:missing", missing.name),
            _registered("model:legacy", good.name),
            _registered("model:good", good.name),
        ],
        local_models=[good, old, unhealthy, small, missing],
        health_by_model_id={"model:unhealthy": False},
        required_context_tokens=8192,
        requires_structured_output=True,
        now=NOW,
    )

    assert route is not None
    assert route.selected_model_id == "model:good"
    assert route.fallback_model_id is None


def test_explicit_choice_wins_only_while_eligible_and_forced_offline_rejects_cloud(
    tmp_path,
):
    local = _local_model(tmp_path, "local")
    alternate = _local_model(tmp_path, "alternate")
    route = select_measured_model_route(
        "chat",
        benchmark_results=[
            _result("model:local", local, role="chat", score=70),
            _result("model:alternate", alternate, role="chat", score=95),
            _result("model:cloud", alternate, role="chat", score=100),
        ],
        registered_models=[
            _registered("model:local", local.name),
            _registered("model:alternate", alternate.name),
            _registered("model:cloud", alternate.name, provider="openai"),
        ],
        local_models=[local, alternate],
        explicit_model_id="model:local",
        forced_offline=True,
        now=NOW,
    )

    assert route is not None
    assert route.selected_model_id == "model:local"
    assert route.fallback_model_id == "model:alternate"
    assert "forced-offline" in route.reason
    assert "explicit" in route.reason

    unhealthy_explicit = select_measured_model_route(
        "chat",
        benchmark_results=[
            _result("model:local", local, role="chat", score=70),
            _result("model:alternate", alternate, role="chat", score=95),
        ],
        registered_models=[
            _registered("model:local", local.name),
            _registered("model:alternate", alternate.name),
        ],
        local_models=[local, alternate],
        health_by_model_id={"model:local": False},
        explicit_model_id="model:local",
        now=NOW,
    )
    assert unhealthy_explicit is not None
    assert unhealthy_explicit.selected_model_id == "model:alternate"


def test_route_allows_exactly_one_recoverable_fallback_and_safe_receipt():
    route = MeasuredModelRoute(
        selected_model_id="model:primary",
        fallback_model_id="model:fallback",
        role="source_synthesis",
        reason="quality winner",
        benchmark_age_seconds=42,
    )

    retry = retry_measured_model_route_once(route, "provider_error")

    assert retry is not None
    assert retry.selected_model_id == "model:fallback"
    assert retry.fallback_model_id is None
    assert retry.outcome == "provider_error"
    assert retry_measured_model_route_once(retry, "provider_error") is None
    assert retry_measured_model_route_once(route, "unknown") is None
    assert set(route.receipt()) == {
        "selected_model_id",
        "fallback_model_id",
        "role",
        "reason",
        "benchmark_age_seconds",
        "outcome",
    }


def test_forced_offline_uses_measured_local_route_and_persists_metadata_only(
    monkeypatch,
):
    cloud = _registered("model:cloud", "cloud", provider="openai")
    local = _registered("model:local", "local")
    route = MeasuredModelRoute(
        selected_model_id="model:local",
        fallback_model_id=None,
        role="chat",
        reason="fresh measured quality winner",
        benchmark_age_seconds=15,
    )

    async def _state():
        return NetworkState("offline", True, 0.0, "override")

    async def _records(_model_type):
        return [local]

    recorded: list[dict[str, object]] = []

    async def _persist(receipt):
        recorded.append(receipt)

    monkeypatch.setattr(offline_gate, "get_network_state_with_settings", _state)
    monkeypatch.setattr(offline_gate, "_get_model_record", lambda _id: _async(cloud))
    monkeypatch.setattr(offline_gate, "_get_language_models", _records)
    monkeypatch.setattr(
        offline_gate,
        "find_measured_local_language_route",
        lambda **_kwargs: _async((route, [local])),
    )
    monkeypatch.setattr(offline_gate, "_persist_route_receipt", _persist)

    fallback_out: dict[str, object] = {}
    assert (
        _run(
            offline_gate.gate_language_model_id(
                "model:cloud", fallback_out=fallback_out
            )
        )
        == "model:local"
    )
    assert fallback_out["reason"] == "forced-offline"
    assert recorded == [
        {
            "selected_model_id": "model:local",
            "fallback_model_id": None,
            "role": "chat",
            "reason": "forced-offline; fresh measured quality winner",
            "benchmark_age_seconds": 15,
            "outcome": "selected",
        }
    ]


def test_route_receipt_file_is_bounded_and_excludes_unknown_fields(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_FOLDER", str(tmp_path))
    _run(
        models.persist_model_route_receipt(
            {
                "selected_model_id": "model:local",
                "fallback_model_id": "model:backup",
                "role": "chat",
                "reason": "quality winner",
                "benchmark_age_seconds": 5,
                "outcome": "selected",
                "prompt": "do not retain me",
                "source_text": "do not retain me",
            }
        )
    )

    payload = json.loads(models.route_receipt_path().read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert "prompt" not in payload[0]
    assert "source_text" not in payload[0]
    assert payload[0]["selected_model_id"] == "model:local"


async def _async(value):
    return value
