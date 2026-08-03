"""Local model role recommendations.

This is a read-only planning layer: it recommends which installed local model
fits each product role, but it does not mutate defaults or start/stop runtimes.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from deeper_notebook.local_models.contracts import (
    LocalModelRouteCandidate,
    ModelRoutePlan,
    RouteRequest,
)
from deeper_notebook.local_models.inventory import LocalModelInfo
from deeper_notebook.local_models.planner import plan_model_route


@dataclass(frozen=True)
class ModelRoleRecommendation:
    role: str
    label: str
    model: LocalModelInfo | None
    confidence: float
    reason: str


_ROLE_LABELS = {
    "chat": "Default chat",
    "source_synthesis": "Source synthesis",
    "coding_research": "Coding and technical research",
    "study_fast": "Fast study tools",
    "embedding": "Embedding and retrieval",
}

_EMBEDDING_MARKERS = (
    "bge",
    "e5",
    "embed",
    "embedding",
    "jina-embeddings",
    "nomic",
    "snowflake-arctic-embed",
)
_CODE_MARKERS = ("code", "coder", "codestral", "devstral", "deepseek")
_INSTRUCT_MARKERS = ("instruct", "it", "chat", "hermes", "qwen", "llama", "gemma")
_SMALL_FAST_MARKERS = ("gemma", "phi", "qwen", "mini", "small")
_LOCAL_LANGUAGE_PROVIDERS = frozenset({"ollama", "openai_compatible"})
BENCHMARK_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class MeasuredModelRoute:
    """A deterministic, privacy-safe local language-model route.

    The route contains identifiers and measurement metadata only. It is safe to
    persist or expose to settings UI because prompts, source text, and provider
    responses are intentionally not part of this contract.
    """

    selected_model_id: str
    fallback_model_id: str | None
    role: str
    reason: str
    benchmark_age_seconds: int
    outcome: str = "selected"

    def receipt(self) -> dict[str, object]:
        return {
            "selected_model_id": self.selected_model_id,
            "fallback_model_id": self.fallback_model_id,
            "role": self.role,
            "reason": self.reason,
            "benchmark_age_seconds": self.benchmark_age_seconds,
            "outcome": self.outcome,
        }


def recommend_model_roles(
    models: list[LocalModelInfo],
    benchmark_results: list[object] | None = None,
    manifest_entries: list[object] | None = None,
) -> list[ModelRoleRecommendation]:
    """Recommend installed local models for the main NotebookLM-style roles."""
    return [
        _recommend("chat", models, benchmark_results, manifest_entries),
        _recommend("source_synthesis", models, benchmark_results, manifest_entries),
        _recommend("coding_research", models, benchmark_results, manifest_entries),
        _recommend("study_fast", models, benchmark_results, manifest_entries),
        _recommend("embedding", models, benchmark_results, manifest_entries),
    ]


def plan_local_model_route(
    candidates: list[LocalModelRouteCandidate],
    request: RouteRequest,
    **planner_kwargs: object,
) -> ModelRoutePlan:
    """Adapt the approved role surface to the side-effect-free route planner.

    The established heuristic recommendations above remain inventory guidance;
    execution-facing callers must use this measured, verified route contract.
    """
    return plan_model_route(candidates, request, **planner_kwargs)


def model_match_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def inventory_model_match_keys(name: str, path: str) -> set[str]:
    path_obj = Path(path)
    path_name = path_obj.name
    path_stem = path_obj.stem
    candidates = {
        name,
        name.split("/")[-1],
        path_name,
        path_stem,
        path_name.replace("__", "/", 1),
        path_stem.replace("__", "/", 1),
    }
    if path_obj.suffix.lower() == ".gguf":
        candidates.add(path_obj.with_suffix("").name)
    return {model_match_key(candidate) for candidate in candidates if candidate}


def select_measured_model_route(
    role: str,
    *,
    benchmark_results: list[object],
    registered_models: list[object],
    local_models: list[LocalModelInfo],
    health_by_model_id: Mapping[str, bool] | None = None,
    required_context_tokens: int = 0,
    requires_structured_output: bool = False,
    benchmarked_at: float | None = None,
    now: float | None = None,
    explicit_model_id: str | None = None,
    forced_offline: bool = False,
) -> MeasuredModelRoute | None:
    """Choose a healthy, fresh, compatible local model for a product role.

    A speed-only legacy row is deliberately not eligible: a route advertised as
    quality-aware needs a real quality measurement. When historic rows do not
    include their own timestamp, callers can supply the benchmark-history file
    timestamp through ``benchmarked_at``. This preserves old history while
    making it safe rather than silently treating unknown-age results as fresh.
    """
    current_time = time.time() if now is None else now
    health = health_by_model_id or {}
    local_by_key = _on_disk_local_models(local_models)
    registered_by_id = {
        str(getattr(model, "id", "") or ""): model
        for model in registered_models
        if str(getattr(model, "id", "") or "")
        and getattr(model, "type", "language") == "language"
        and _is_local_language_provider(getattr(model, "provider", None))
    }

    candidates: list[tuple[float, int, str, int]] = []
    for result in benchmark_results:
        if _result_value(result, "role") != role:
            continue
        if _result_value(result, "status") != "completed":
            continue
        if not _has_quality_measurement(result):
            continue

        model_id = str(_result_value(result, "model_id") or "")
        registered = registered_by_id.get(model_id)
        if registered is None:
            continue
        if health.get(model_id) is False:
            continue

        local = _matching_on_disk_model(result, local_by_key)
        if local is None:
            continue
        context_length = getattr(local.metadata, "context_length", None)
        if required_context_tokens and (
            not isinstance(context_length, int)
            or context_length < required_context_tokens
        ):
            continue
        if (
            requires_structured_output
            and getattr(registered, "supports_structured_output", None) is False
        ):
            continue
        if forced_offline and not _is_local_language_provider(
            getattr(registered, "provider", None)
        ):
            continue

        benchmark_time = _benchmark_time(result, benchmarked_at)
        if benchmark_time is None:
            continue
        age_seconds = max(0, int(current_time - benchmark_time))
        if age_seconds > BENCHMARK_MAX_AGE_SECONDS:
            continue
        try:
            score = float(_result_value(result, "score") or 0)
        except (TypeError, ValueError):
            continue
        if score <= 0:
            continue
        latency = _latency_for_sort(_result_value(result, "latency_ms"))
        candidates.append((score, latency, model_id, age_seconds))

    if not candidates:
        return None

    # Explicit selection is honored only while it still clears every health,
    # on-disk, recency, context, and offline gate above.
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    if explicit_model_id:
        explicit = next(
            (
                candidate
                for candidate in candidates
                if candidate[2] == explicit_model_id
            ),
            None,
        )
        if explicit is not None:
            candidates.remove(explicit)
            candidates.insert(0, explicit)

    selected = candidates[0]
    fallback = candidates[1][2] if len(candidates) > 1 else None
    selected_by_explicit_choice = bool(
        explicit_model_id and selected[2] == explicit_model_id
    )
    reason = (
        "explicit model remains healthy, on-disk, fresh, and compatible"
        if selected_by_explicit_choice
        else "fresh measured quality winner (quality, latency, model id)"
    )
    if forced_offline:
        reason = f"forced-offline {reason}"
    return MeasuredModelRoute(
        selected_model_id=selected[2],
        fallback_model_id=fallback,
        role=role,
        reason=reason,
        benchmark_age_seconds=selected[3],
    )


def retry_measured_model_route_once(
    route: MeasuredModelRoute,
    outcome: str,
) -> MeasuredModelRoute | None:
    """Return the sole allowed fallback for a recoverable route failure.

    Callers should invoke this only for schema failures, context overflows, or
    provider errors. The replacement route has no further fallback, so an
    outage cannot become an unbounded retry loop.
    """
    if outcome not in {"schema_failure", "context_overflow", "provider_error"}:
        return None
    if not route.fallback_model_id:
        return None
    return MeasuredModelRoute(
        selected_model_id=route.fallback_model_id,
        fallback_model_id=None,
        role=route.role,
        reason=f"one fallback after {outcome}: {route.selected_model_id}",
        benchmark_age_seconds=route.benchmark_age_seconds,
        outcome=outcome,
    )


def _on_disk_local_models(
    local_models: list[LocalModelInfo],
) -> dict[str, LocalModelInfo]:
    matched: dict[str, LocalModelInfo] = {}
    for model in local_models:
        try:
            exists = Path(model.path).expanduser().exists()
        except OSError:
            exists = False
        if not exists:
            continue
        for key in inventory_model_match_keys(model.name, model.path):
            matched.setdefault(key, model)
    return matched


def _matching_on_disk_model(
    result: object,
    local_by_key: Mapping[str, LocalModelInfo],
) -> LocalModelInfo | None:
    keys = inventory_model_match_keys(
        str(_result_value(result, "model_name") or ""),
        str(_result_value(result, "model_path") or ""),
    )
    for key in sorted(keys):
        if key in local_by_key:
            return local_by_key[key]
    return None


def _has_quality_measurement(result: object) -> bool:
    quality = _result_value(result, "quality")
    if quality is not None:
        return True
    metrics = _result_value(result, "normalized_metrics")
    return isinstance(metrics, dict) and any(
        key in metrics
        for key in (
            "correctness",
            "citation",
            "schema",
            "instruction",
            "tool",
            "context",
        )
    )


def _benchmark_time(result: object, fallback: float | None) -> float | None:
    for key in ("completed_at", "benchmarked_at", "created_at"):
        value = _result_value(result, key)
        if isinstance(value, (int, float)):
            return float(value)
    return fallback


def _latency_for_sort(value: object) -> int:
    try:
        latency = int(value)
    except (TypeError, ValueError):
        return 2**31 - 1
    return latency if latency >= 0 else 2**31 - 1


def _is_local_language_provider(provider: object) -> bool:
    return str(provider or "").strip().lower() in _LOCAL_LANGUAGE_PROVIDERS


def _recommend(
    role: str,
    models: list[LocalModelInfo],
    benchmark_results: list[object] | None,
    manifest_entries: list[object] | None,
) -> ModelRoleRecommendation:
    measured = _measured_candidates(role, models, benchmark_results or [])
    if measured:
        score, model, reason = measured[0]
        return ModelRoleRecommendation(
            role=role,
            label=_ROLE_LABELS[role],
            model=model,
            confidence=min(1.0, round(score / 100.0, 2)),
            reason=reason,
        )

    manifest_candidates = _manifest_candidates(role, models, manifest_entries or [])
    if manifest_candidates:
        score, model, reason = manifest_candidates[0]
        return ModelRoleRecommendation(
            role=role,
            label=_ROLE_LABELS[role],
            model=model,
            confidence=min(1.0, round(score / 100.0, 2)),
            reason=reason,
        )

    scored: list[tuple[float, LocalModelInfo, str]] = []
    for model in models:
        score, reason = _score(role, model)
        if score > 0:
            scored.append((score, model, reason))

    if not scored:
        return ModelRoleRecommendation(
            role=role,
            label=_ROLE_LABELS[role],
            model=None,
            confidence=0.0,
            reason=_empty_reason(role),
        )

    scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
    score, model, reason = scored[0]
    return ModelRoleRecommendation(
        role=role,
        label=_ROLE_LABELS[role],
        model=model,
        confidence=min(1.0, round(score / 100.0, 2)),
        reason=reason,
    )


def _measured_candidates(
    role: str,
    models: list[LocalModelInfo],
    benchmark_results: list[object],
) -> list[tuple[float, LocalModelInfo, str]]:
    candidates: list[tuple[float, LocalModelInfo, str]] = []
    for result in benchmark_results:
        if _result_value(result, "role") != role:
            continue
        if _result_value(result, "status") != "completed":
            continue
        try:
            score = float(_result_value(result, "score") or 0)
        except (TypeError, ValueError):
            score = 0
        if score <= 0:
            continue
        result_keys = inventory_model_match_keys(
            str(_result_value(result, "model_name") or ""),
            str(_result_value(result, "model_path") or ""),
        )
        for model in models:
            model_keys = inventory_model_match_keys(model.name, model.path)
            if result_keys & model_keys:
                speed = _result_value(result, "tokens_per_second")
                latency = _result_value(result, "latency_ms")
                detail = []
                if speed:
                    detail.append(f"{float(speed):.0f} tok/s")
                if latency:
                    detail.append(f"{int(latency)} ms")
                suffix = f" ({', '.join(detail)})" if detail else ""
                candidates.append(
                    (
                        100 + score,
                        model,
                        f"Measured benchmark winner for this role{suffix}.",
                    )
                )
    candidates.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return candidates


def _manifest_candidates(
    role: str,
    models: list[LocalModelInfo],
    manifest_entries: list[object],
) -> list[tuple[float, LocalModelInfo, str]]:
    candidates: list[tuple[float, LocalModelInfo, str]] = []
    for entry in manifest_entries:
        relevance = _manifest_role_relevance_score(role, entry)
        if relevance <= 0:
            continue
        entry_keys = inventory_model_match_keys(
            str(_entry_value(entry, "repo") or ""),
            str(_entry_value(entry, "local_path") or ""),
        )
        entry_path = _resolved_path(str(_entry_value(entry, "local_path") or ""))
        for model in models:
            if model.runtime.lower() not in {"gguf", "mlx"}:
                continue
            model_path = _resolved_path(model.path)
            model_keys = inventory_model_match_keys(model.name, model.path)
            if (
                entry_path
                and model_path
                and entry_path != model_path
                and not (entry_keys & model_keys)
            ):
                continue
            if not entry_path and not (entry_keys & model_keys):
                continue
            runtime_bonus = 10 if model.runtime.lower() == "mlx" else 4
            status_bonus = (
                6
                if "verified"
                in str(_entry_value(entry, "estimated_status") or "").lower()
                else 0
            )
            score = relevance + runtime_bonus + status_bonus
            role_text = str(_entry_value(entry, "role") or "curated")
            candidates.append(
                (
                    score,
                    model,
                    (
                        f"Curated {role_text} manifest row for "
                        f"{_entry_value(entry, 'category') or model.name}."
                    ),
                )
            )
    candidates.sort(
        key=lambda item: (
            -item[0],
            0 if item[1].runtime.lower() == "mlx" else 1,
            item[1].name.lower(),
        )
    )
    return candidates


def _result_value(result: object, key: str):
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def _entry_value(entry: object, key: str):
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _resolved_path(value: str) -> str | None:
    if not value:
        return None
    try:
        return str(Path(value).expanduser().resolve())
    except OSError:
        return value


def _manifest_role_relevance_score(role: str, entry: object) -> float:
    text = (
        f"{_entry_value(entry, 'category') or ''} "
        f"{_entry_value(entry, 'role') or ''} "
        f"{_entry_value(entry, 'notes') or ''}"
    ).lower()
    runtime = str(_entry_value(entry, "runtime_type") or "").lower()
    if runtime not in {"gguf", "mlx"}:
        return 0

    if role == "embedding":
        score = 78 if _has_any(text, _EMBEDDING_MARKERS) else 0
    elif role == "coding_research":
        score = (
            72
            if _has_any(text, ("coding", "coder", "debugging", "agentic", "terminal"))
            else 0
        )
    elif role == "source_synthesis":
        score = (
            62
            if _has_any(text, ("research", "reasoning", "synthesis", "general chat"))
            else 0
        )
    elif role == "study_fast":
        score = (
            60
            if _has_any(text, ("study", "fast", "general chat", "creative", "fable"))
            else 0
        )
    elif role == "chat":
        score = (
            58
            if _has_any(text, ("chat", "instruct", "research", "reasoning", "creative"))
            else 0
        )
    else:
        score = 0

    if score <= 0:
        return 0
    role_text = str(_entry_value(entry, "role") or "").lower()
    if role_text.startswith("primary"):
        score += 18
    elif role_text.startswith("backup"):
        score += 10
    elif role_text.startswith("priority"):
        score += 8
    elif role_text.startswith("requested"):
        score += 5
    return score


def _score(role: str, model: LocalModelInfo) -> tuple[float, str]:
    name = model.name.lower()
    params = model.metadata.parameter_count_b
    context = model.metadata.context_length or 0
    runtime = model.runtime.lower()
    is_embedding = _has_any(name, _EMBEDDING_MARKERS)
    is_code = _has_any(name, _CODE_MARKERS)

    if runtime not in {"gguf", "mlx"}:
        return 0, ""

    if role == "embedding":
        if not is_embedding:
            return 0, ""
        score = 55 + _marker_bonus(name, _EMBEDDING_MARKERS, 20)
        if "nomic" in name or "bge" in name:
            score += 10
        return score, "Embedding-style model name matches retrieval use."

    if is_embedding:
        return 0, ""

    if role == "coding_research":
        if not is_code:
            return 0, ""
        score = 50 + _size_score(params, preferred_min=7, preferred_max=34)
        score += _context_score(context)
        if "coder" in name or "code" in name:
            score += 20
        if runtime == "mlx":
            score += 4
        return score, "Code/reasoning markers and capacity fit technical work."

    if role == "source_synthesis":
        score = 35 + _size_score(params, preferred_min=7, preferred_max=34)
        score += _context_score(context) * 1.4
        score += _marker_bonus(name, _INSTRUCT_MARKERS, 8)
        if runtime == "mlx":
            score += 4
        return (
            score,
            "Higher context and instruction tuning fit multi-source synthesis.",
        )

    if role == "study_fast":
        score = 35 + _marker_bonus(name, _SMALL_FAST_MARKERS, 8)
        if params is not None:
            if 2 <= params <= 8:
                score += 30
            elif params < 2:
                score += 12
            elif params > 14:
                score -= 25
        if context >= 32768:
            score += 8
        if runtime == "mlx":
            score += 8
        if is_code:
            score -= 18
        return max(
            0, score
        ), "Smaller local model should be quick for flashcards and quizzes."

    if role == "chat":
        score = 35 + _size_score(params, preferred_min=4, preferred_max=14)
        score += _marker_bonus(name, _INSTRUCT_MARKERS, 10)
        if context >= 32768:
            score += 8
        if runtime == "mlx":
            score += 6
        if is_code:
            score -= 4
        return score, "General instruction model fits everyday local chat."

    return 0, ""


def _size_score(
    params: float | None, *, preferred_min: float, preferred_max: float
) -> float:
    if params is None:
        return 10
    if preferred_min <= params <= preferred_max:
        return 28
    if params < preferred_min:
        return max(4, 18 - ((preferred_min - params) * 3))
    return max(8, 28 - ((params - preferred_max) * 1.5))


def _context_score(context: int) -> float:
    if context >= 131072:
        return 24
    if context >= 65536:
        return 18
    if context >= 32768:
        return 12
    if context >= 8192:
        return 6
    return 0


def _marker_bonus(name: str, markers: tuple[str, ...], amount: float) -> float:
    return amount if _has_any(name, markers) else 0


def _has_any(name: str, markers: tuple[str, ...]) -> bool:
    return any(marker in name for marker in markers)


def _empty_reason(role: str) -> str:
    if role == "embedding":
        return "No embedding-oriented local model was found."
    return "No local language model was found for this role."
