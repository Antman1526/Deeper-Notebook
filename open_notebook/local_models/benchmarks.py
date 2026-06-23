"""Local model benchmark jobs."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Literal

from open_notebook.local_models.inventory import LocalModelInfo, enumerate_models
from open_notebook.local_models.role_routing import (
    inventory_model_match_keys,
    model_match_key,
    recommend_model_roles,
)
from open_notebook.utils.text_utils import extract_text_content

BenchmarkStatus = Literal["queued", "running", "completed", "failed"]
BenchmarkResultStatus = Literal["completed", "failed", "skipped"]


@dataclass(frozen=True)
class BenchmarkMeasurement:
    latency_ms: int
    tokens_per_second: float


@dataclass
class BenchmarkResult:
    role: str
    label: str
    status: BenchmarkResultStatus
    model_name: str | None = None
    model_path: str | None = None
    model_runtime: str | None = None
    model_id: str | None = None
    provider: str | None = None
    latency_ms: int | None = None
    tokens_per_second: float | None = None
    score: float = 0.0
    error: str | None = None


@dataclass
class BenchmarkJob:
    job_id: str
    roles: list[str]
    status: BenchmarkStatus = "queued"
    results: list[BenchmarkResult] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    _task: object | None = field(default=None, repr=False)


RegisteredModelsLoader = Callable[[], Awaitable[list[object]]]
BenchmarkRunner = Callable[[str, object, LocalModelInfo], Awaitable[BenchmarkMeasurement]]

_JOBS: dict[str, BenchmarkJob] = {}
_HISTORY_FILENAME = "open-notebook-plus-benchmarks.json"
_VALID_ROLES = {
    "chat",
    "source_synthesis",
    "coding_research",
    "study_fast",
    "embedding",
}


def clear_benchmark_jobs() -> None:
    _JOBS.clear()


def get_benchmark_job(job_id: str) -> BenchmarkJob | None:
    return _JOBS.get(job_id)


def list_benchmark_jobs() -> list[BenchmarkJob]:
    return sorted(_JOBS.values(), key=lambda job: job.created_at, reverse=True)


def benchmark_history_path(model_dir: Path) -> Path:
    return model_dir / "Manifests" / _HISTORY_FILENAME


def load_benchmark_history(model_dir: Path) -> list[BenchmarkResult]:
    path = benchmark_history_path(model_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    rows = payload.get("results", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    results: list[BenchmarkResult] = []
    allowed = set(BenchmarkResult.__dataclass_fields__)
    for row in rows:
        if not isinstance(row, dict):
            continue
        data = {key: value for key, value in row.items() if key in allowed}
        try:
            results.append(BenchmarkResult(**data))
        except TypeError:
            continue
    return results


def save_benchmark_history(model_dir: Path, results: list[BenchmarkResult]) -> None:
    path = benchmark_history_path(model_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"results": [asdict(result) for result in results[-200:]]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        return


async def resolve_measured_model_id(
    model_dir: Path,
    role: str,
    *,
    registered_models_loader: RegisteredModelsLoader | None = None,
) -> str | None:
    """Return the registered language model id for the best measured role winner.

    Benchmark history is a local file, while actual chat provisioning needs a
    registered SurrealDB model id. Resolve defensively: prefer the highest
    completed score for the role, validate it against registered language
    models, and fall through to lower-ranked completed rows when a history entry
    is stale.
    """
    candidates = [
        result
        for result in load_benchmark_history(model_dir)
        if result.role == role and result.status == "completed"
        and result.score > 0
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda result: result.score, reverse=True)
    try:
        registered_models = await (
            registered_models_loader or _load_registered_language_models
        )()
    except Exception:
        return None

    for result in candidates:
        registered = _find_registered_benchmark_result(result, registered_models)
        if registered is not None:
            model_id = str(getattr(registered, "id", "") or "")
            if model_id:
                return model_id
    return None


async def start_benchmark(
    model_dir: Path,
    *,
    roles: list[str] | None = None,
    registered_models_loader: RegisteredModelsLoader | None = None,
    benchmark_runner: BenchmarkRunner | None = None,
    run_inline: bool = False,
) -> BenchmarkJob:
    job = BenchmarkJob(
        job_id=f"benchmark_{secrets.token_hex(8)}",
        roles=_normalize_roles(roles),
    )
    _JOBS[job.job_id] = job

    async def _run() -> None:
        await _run_benchmark_job(
            job,
            model_dir,
            registered_models_loader=registered_models_loader
            or _load_registered_language_models,
            benchmark_runner=benchmark_runner or _invoke_registered_model,
        )

    if run_inline:
        await _run()
    else:
        job._task = asyncio.create_task(_run())
    return job


def _normalize_roles(roles: list[str] | None) -> list[str]:
    if not roles:
        return ["chat", "source_synthesis", "coding_research", "study_fast"]
    normalized: list[str] = []
    for role in roles:
        role = str(role).strip()
        if role in _VALID_ROLES and role not in normalized:
            normalized.append(role)
    return normalized or ["chat", "source_synthesis", "coding_research", "study_fast"]


async def _run_benchmark_job(
    job: BenchmarkJob,
    model_dir: Path,
    *,
    registered_models_loader: RegisteredModelsLoader,
    benchmark_runner: BenchmarkRunner,
) -> None:
    job.status = "running"
    try:
        local_models = await asyncio.to_thread(enumerate_models, model_dir)
        routes = await asyncio.to_thread(recommend_model_roles, local_models)
        routes_by_role = {route.role: route for route in routes}
        registered_models = await registered_models_loader()

        for role in job.roles:
            route = routes_by_role.get(role)
            if route is None or route.model is None:
                job.results.append(BenchmarkResult(
                    role=role,
                    label=role.replace("_", " ").title(),
                    status="skipped",
                    error="No local model recommendation is available for this role.",
                ))
                continue

            registered_model = _find_registered_model(route.model, registered_models)
            if registered_model is None:
                job.results.append(_skipped_result(
                    role=role,
                    label=route.label,
                    local_model=route.model,
                    error="Recommended local model is not registered as a language model.",
                ))
                continue

            try:
                measurement = await benchmark_runner(role, registered_model, route.model)
                job.results.append(BenchmarkResult(
                    role=role,
                    label=route.label,
                    status="completed",
                    model_name=route.model.name,
                    model_path=route.model.path,
                    model_runtime=route.model.runtime,
                    model_id=str(getattr(registered_model, "id", "") or ""),
                    provider=getattr(registered_model, "provider", None),
                    latency_ms=measurement.latency_ms,
                    tokens_per_second=round(measurement.tokens_per_second, 2),
                    score=_benchmark_score(measurement),
                ))
            except Exception as exc:
                job.results.append(BenchmarkResult(
                    role=role,
                    label=route.label,
                    status="failed",
                    model_name=route.model.name,
                    model_path=route.model.path,
                    model_runtime=route.model.runtime,
                    model_id=str(getattr(registered_model, "id", "") or "") or None,
                    provider=getattr(registered_model, "provider", None),
                    error=f"{exc.__class__.__name__}: {exc}",
                ))

        job.status = "completed"
    except Exception as exc:
        job.status = "failed"
        job.error = f"{exc.__class__.__name__}: {exc}"
    finally:
        job.completed_at = time.time()
        if job.results:
            history = load_benchmark_history(model_dir)
            history.extend(job.results)
            save_benchmark_history(model_dir, history)


def _skipped_result(
    *,
    role: str,
    label: str,
    local_model: LocalModelInfo,
    error: str,
) -> BenchmarkResult:
    return BenchmarkResult(
        role=role,
        label=label,
        status="skipped",
        model_name=local_model.name,
        model_path=local_model.path,
        model_runtime=local_model.runtime,
        error=error,
    )


def _find_registered_model(
    local_model: LocalModelInfo,
    registered_models: list[object],
) -> object | None:
    match_keys = inventory_model_match_keys(local_model.name, local_model.path)
    for registered in registered_models:
        if model_match_key(str(getattr(registered, "name", ""))) in match_keys:
            return registered
    return None


def _find_registered_benchmark_result(
    result: BenchmarkResult,
    registered_models: list[object],
) -> object | None:
    wanted_id = str(result.model_id or "")
    if wanted_id:
        for registered in registered_models:
            if str(getattr(registered, "id", "") or "") == wanted_id:
                return registered

    match_keys = inventory_model_match_keys(
        result.model_name or "",
        result.model_path or "",
    )
    for registered in registered_models:
        if model_match_key(str(getattr(registered, "name", ""))) in match_keys:
            return registered
    return None


def _benchmark_score(measurement: BenchmarkMeasurement) -> float:
    speed = max(0.0, measurement.tokens_per_second)
    latency_penalty = max(0.0, measurement.latency_ms / 1000.0)
    return round(max(0.0, speed - latency_penalty), 2)


async def _load_registered_language_models() -> list[object]:
    from open_notebook.ai.models import Model

    return await Model.get_models_by_type("language")


async def _invoke_registered_model(
    role: str,
    registered_model: object,
    _local_model: LocalModelInfo,
) -> BenchmarkMeasurement:
    from open_notebook.ai.models import model_manager

    prompt = _benchmark_prompt(role)
    model_id = str(getattr(registered_model, "id", "") or "")
    started = time.perf_counter()
    model = await model_manager.get_model(model_id, max_tokens=96)
    if model is None:
        raise RuntimeError(f"Could not load registered model {model_id}")
    response = await model.to_langchain().ainvoke(prompt)
    latency_ms = max(1, int((time.perf_counter() - started) * 1000))
    text = extract_text_content(getattr(response, "content", response))
    token_estimate = max(1, len(text.split()))
    return BenchmarkMeasurement(
        latency_ms=latency_ms,
        tokens_per_second=token_estimate / max(latency_ms / 1000.0, 0.001),
    )


def _benchmark_prompt(role: str) -> str:
    if role == "study_fast":
        return "Create three concise flashcards about retrieval augmented generation."
    if role == "coding_research":
        return "Explain the tradeoffs of local-first model routing in five bullets."
    if role == "source_synthesis":
        return "Summarize two short source notes into an executive briefing."
    return "Answer briefly: why does local-first AI matter for private notebooks?"
