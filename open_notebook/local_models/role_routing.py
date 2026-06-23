"""Local model role recommendations.

This is a read-only planning layer: it recommends which installed local model
fits each product role, but it does not mutate defaults or start/stop runtimes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from open_notebook.local_models.inventory import LocalModelInfo


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


def recommend_model_roles(
    models: list[LocalModelInfo],
    benchmark_results: list[object] | None = None,
) -> list[ModelRoleRecommendation]:
    """Recommend installed local models for the main NotebookLM-style roles."""
    return [
        _recommend("chat", models, benchmark_results),
        _recommend("source_synthesis", models, benchmark_results),
        _recommend("coding_research", models, benchmark_results),
        _recommend("study_fast", models, benchmark_results),
        _recommend("embedding", models, benchmark_results),
    ]


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


def _recommend(
    role: str,
    models: list[LocalModelInfo],
    benchmark_results: list[object] | None,
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
                candidates.append((
                    100 + score,
                    model,
                    f"Measured benchmark winner for this role{suffix}.",
                ))
    candidates.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return candidates


def _result_value(result: object, key: str):
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


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
        return score, "Higher context and instruction tuning fit multi-source synthesis."

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
        return max(0, score), "Smaller local model should be quick for flashcards and quizzes."

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


def _size_score(params: float | None, *, preferred_min: float, preferred_max: float) -> float:
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
