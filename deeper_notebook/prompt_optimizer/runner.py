"""v0.8.68 — drives a SkillOpt training run over a Transformation prompt.

Bridges the app's model registry (record<model> + encrypted credentials) to
SkillOpt's backend configuration: both the target (runs the prompt) and the
optimizer (judges + proposes edits) are configured as openai-compatible
endpoints, which covers the local llama.cpp sidecar AND cloud
OpenAI/Azure-style providers. Runs fully local with local models — in
keeping with the app's privacy-first stance, no data leaves the machine
unless the chosen models are cloud models (the caller gates that).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from loguru import logger

_BASE_YAML = Path(__file__).parent / "skillopt_base.yaml"
_VENDORED_PROMPTS = Path(__file__).parent / "skillopt_prompts"


def ensure_skillopt_prompts(dest_dir: Optional[Path] = None) -> int:
    """v0.8.68 — backfill skillopt's missing prompt templates (caught live).

    The skillopt 0.1.0 wheel ships the ``skillopt/prompts`` package but NOT
    its ``.md`` template files, so ``load_prompt("analyst_success")`` (and
    the merge_* prompts in the aggregate stage) raise FileNotFoundError
    mid-training. Copy the vendored upstream files (MIT) into the installed
    package for any name that's missing; never overwrite an existing file,
    so a fixed upstream wheel automatically takes precedence. Returns the
    number of files copied.
    """
    if dest_dir is None:
        import skillopt.prompts as _sp

        dest_dir = Path(_sp.__file__).parent
    copied = 0
    for src in sorted(_VENDORED_PROMPTS.glob("*.md")):
        if src.name == "README.md":
            continue
        dest = dest_dir / src.name
        if dest.exists():
            continue
        try:
            dest.write_text(src.read_text())
            copied += 1
        except OSError as exc:
            # Read-only site-packages (system installs): surface clearly —
            # training WILL fail later at load_prompt with a worse message.
            raise PromptOptimizerError(
                f"skillopt is missing its prompt templates and "
                f"{dest_dir} is not writable ({exc}). Reinstall skillopt "
                f"from a wheel that includes its prompts/*.md files."
            ) from exc
    if copied:
        logger.info(
            f"prompt-optimizer: backfilled {copied} missing skillopt "
            f"prompt template(s) into {dest_dir}"
        )
    return copied


# Providers whose esperanto config carries an OpenAI-compatible base_url we
# can hand straight to SkillOpt's openai_chat backend.
_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openai_compatible",
    "ollama",
    "azure",
    "deepseek",
    "groq",
    "mistral",
    "xai",
    "openrouter",
}

_PROVIDER_DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


class PromptOptimizerError(RuntimeError):
    """User-actionable failure (bad model choice, missing package, ...)."""


def _endpoint_for(provider: str, config: dict) -> str:
    base_url = (config or {}).get("base_url") or ""
    if base_url:
        return str(base_url)
    default = _PROVIDER_DEFAULT_ENDPOINTS.get(provider)
    if default:
        return default
    raise PromptOptimizerError(
        f"Model provider {provider!r} has no OpenAI-compatible endpoint — "
        f"pick an OpenAI-compatible or local (llama.cpp/Ollama) model for "
        f"prompt optimization."
    )


async def resolve_backend(model_id: str) -> dict:
    """Resolve a registry model id to {model_name, endpoint, api_key}."""
    from deeper_notebook.podcasts.models import _resolve_model_config

    provider, model_name, config = await _resolve_model_config(model_id)
    provider_norm = (provider or "").strip().lower().replace("-", "_")
    if provider_norm not in _OPENAI_COMPATIBLE_PROVIDERS:
        raise PromptOptimizerError(
            f"Provider {provider!r} is not OpenAI-compatible. Prompt "
            f"optimization supports local (llama.cpp/Ollama) and "
            f"OpenAI-compatible cloud models."
        )
    if provider_norm == "ollama":
        # esperanto stores the ollama base without /v1; its OpenAI shim
        # lives at /v1.
        base = (config or {}).get("base_url") or "http://localhost:11434"
        endpoint = base.rstrip("/")
        if not endpoint.endswith("/v1"):
            endpoint = endpoint + "/v1"
    else:
        endpoint = _endpoint_for(provider_norm, config or {})
    api_key = (config or {}).get("api_key") or "sk-local"
    return {"model_name": model_name, "endpoint": endpoint, "api_key": str(api_key)}


def build_flat_config(
    *,
    run_dir: str,
    skill_init_path: str,
    target: dict,
    optimizer: dict,
    epochs: int,
    batch_size: int,
    edit_budget: int,
) -> dict:
    """Assemble SkillOpt's flat config from the vendored base YAML."""
    from skillopt.config import flatten_config, load_config

    cfg = load_config(str(_BASE_YAML))
    flat = flatten_config(cfg)

    def _set(key: str, value) -> None:
        # flatten_config produces bare leaf keys; tolerate future dotted
        # variants and fail LOUDLY if a key vanishes in an upgrade.
        if key in flat:
            flat[key] = value
            return
        dotted = [k for k in flat if k.endswith("." + key)]
        if dotted:
            flat[dotted[0]] = value
            return
        raise PromptOptimizerError(
            f"SkillOpt config key {key!r} not found — the skillopt package "
            f"layout changed; update deeper_notebook/prompt_optimizer."
        )

    _set("model_backend", "azure_openai")
    _set("optimizer_backend", "openai_chat")
    _set("target_backend", "openai_chat")
    _set("optimizer_model", optimizer["model_name"])
    _set("target_model", target["model_name"])
    _set("target_azure_openai_endpoint", target["endpoint"])
    _set("target_azure_openai_api_key", target["api_key"])
    _set("target_azure_openai_auth_mode", "openai_compatible")
    _set("optimizer_azure_openai_endpoint", optimizer["endpoint"])
    _set("optimizer_azure_openai_api_key", optimizer["api_key"])
    _set("optimizer_azure_openai_auth_mode", "openai_compatible")

    _set("num_epochs", max(1, int(epochs)))
    _set("batch_size", max(1, int(batch_size)))
    _set("edit_budget", max(1, int(edit_budget)))
    _set("env", "transformation")
    _set("skill_init", skill_init_path)
    _set("out_root", run_dir)
    # Optional knobs — present in some skillopt versions; our runs are
    # interactive-sized so trim the heavy extras when available. The judge
    # produces soft scores, so prefer a soft gate when the key exists.
    for key, value in (
        ("use_slow_update", False),
        ("use_meta_skill", False),
        ("eval_test", False),
        ("gate_metric", "soft"),
    ):
        try:
            _set(key, value)
        except PromptOptimizerError:
            logger.debug(f"optional skillopt key {key!r} missing; skipping")
    return flat


async def run_prompt_optimization(
    *,
    prompt_text: str,
    items: list[dict],
    criteria: str,
    target_model_id: str,
    optimizer_model_id: str,
    run_dir: str,
    epochs: int = 2,
    batch_size: Optional[int] = None,
    edit_budget: int = 4,
) -> dict:
    """Run the SkillOpt loop; return the optimized prompt + score history.

    Blocking library call runs on a worker thread. Caller owns timeout
    and cancellation policy.
    """
    try:
        from skillopt.engine.trainer import ReflACTTrainer
    except ImportError as exc:
        raise PromptOptimizerError(
            "The 'skillopt' package is not installed in the app environment. "
            "It ships with the next app update; for source installs run "
            "`pip install skillopt`."
        ) from exc

    from deeper_notebook.prompt_optimizer.adapter import TransformationAdapter

    ensure_skillopt_prompts()

    if not items:
        raise PromptOptimizerError("No example items provided")
    if not (criteria or "").strip():
        raise PromptOptimizerError("Optimization criteria are required")

    target = await resolve_backend(target_model_id)
    optimizer = await resolve_backend(optimizer_model_id)

    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    skill_init_path = run_path / "skill_init.md"
    skill_init_path.write_text(prompt_text)

    flat = build_flat_config(
        run_dir=str(run_path),
        skill_init_path=str(skill_init_path),
        target=target,
        optimizer=optimizer,
        epochs=epochs,
        batch_size=batch_size or len(items),
        edit_budget=edit_budget,
    )

    adapter = TransformationAdapter(
        items=items,
        criteria=criteria,
        edit_budget=edit_budget,
        minibatch_size=min(4, max(1, len(items))),
    )

    def _train() -> None:
        trainer = ReflACTTrainer(flat, adapter)
        trainer.train()

    logger.info(
        f"prompt-optimizer: starting SkillOpt run "
        f"(items={len(items)}, epochs={epochs}, target={target['model_name']}, "
        f"optimizer={optimizer['model_name']})"
    )
    await asyncio.to_thread(_train)

    # Collect artifacts. best_skill.md is the deployment artifact; history
    # carries per-step scores for the before/after display.
    best = _find_artifact(run_path, "best_skill.md")
    history = _find_artifact(run_path, "history.json")
    optimized_prompt = best.read_text().strip() if best else prompt_text
    history_data = []
    if history:
        try:
            history_data = json.loads(history.read_text())
        except Exception:
            history_data = []

    return {
        "optimized_prompt": optimized_prompt,
        "changed": optimized_prompt.strip() != prompt_text.strip(),
        "history": history_data,
        "run_dir": str(run_path),
    }


def _find_artifact(run_path: Path, name: str) -> Optional[Path]:
    direct = run_path / name
    if direct.exists():
        return direct
    matches = sorted(run_path.rglob(name), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None
