"""v0.8.68 — async worker command: optimize a Transformation's prompt with
SkillOpt (microsoft/SkillOpt, MIT).

Mirrors the podcast command patterns: surreal-commands job, env-tunable
timeout, ValueError = permanent user error, offline gate for cloud models.

NOTE: no `from __future__ import annotations` here — it turns the handler's
type hints into strings that LangChain's RunnableLambda-generated input
schema cannot resolve at submit time ("optimize_prompt_command_input is not
fully defined" → 500). @command modules must use runtime annotations.
"""

import asyncio
import os
import time
import uuid
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field
from surreal_commands import CommandInput, CommandOutput, command

from deeper_notebook.config import DATA_FOLDER
from deeper_notebook.domain.transformation import Transformation
from deeper_notebook.environment import resolve_env
from deeper_notebook.prompt_optimizer import skillopt_available

_MAX_EXAMPLES = 10
_MAX_INPUT_CHARS = 6000


class OptimizePromptInput(CommandInput):
    transformation_id: str
    source_ids: list[str]
    criteria: str
    epochs: int = 2
    edit_budget: int = 4
    # Optional explicit models; default to the transformation flow's models.
    target_model_id: Optional[str] = None
    optimizer_model_id: Optional[str] = None


class OptimizePromptOutput(CommandOutput):
    success: bool
    transformation_id: Optional[str] = None
    original_prompt: Optional[str] = None
    optimized_prompt: Optional[str] = None
    changed: bool = False
    processing_time: float = 0.0
    error_message: Optional[str] = None


async def _default_model_ids() -> tuple[str, str]:
    """Target = the transformation default model; optimizer = chat default.
    Both fall back to the chat default (the registry guarantees neither is
    None only when configured — raise a clear error otherwise)."""
    from deeper_notebook.ai.models import model_manager

    target = await model_manager.get_default_model_id("transformation")
    optimizer = await model_manager.get_default_model_id("chat")
    if not target or not optimizer:
        raise ValueError(
            "No default transformation/chat model configured. Set them in "
            "Settings → Models before running prompt optimization."
        )
    return target, optimizer


async def _gate_offline(model_ids: list[str]) -> None:
    """Fail fast when offline and any involved model is a cloud model.
    Optimization runs dozens of LLM calls — starting it against an
    unreachable provider would burn the whole timeout."""
    try:
        from deeper_notebook.ai.offline_gate import LOCAL_PROVIDERS
        from deeper_notebook.health.network import get_network_state_with_settings
        from deeper_notebook.podcasts.models import _resolve_model_config

        state = await get_network_state_with_settings()
        if state.status != "offline":
            return
        cloud = []
        for mid in model_ids:
            try:
                provider, name, _ = await _resolve_model_config(mid)
            except Exception:
                continue
            if (provider or "").strip().lower().replace(
                "-", "_"
            ) not in LOCAL_PROVIDERS:
                cloud.append(f"{name} ({provider})")
        if cloud:
            raise ValueError(
                f"You're offline and prompt optimization would use cloud "
                f"models: {', '.join(cloud)}. Reconnect or pick local models."
            )
    except ValueError:
        raise
    except Exception as exc:
        logger.debug(f"prompt-optimizer offline gate skipped: {exc}")


async def _load_example_items(source_ids: list[str]) -> list[dict]:
    from deeper_notebook.domain.notebook import Source

    items: list[dict] = []
    for sid in source_ids[:_MAX_EXAMPLES]:
        try:
            source = await Source.get(sid)
        except Exception as exc:
            logger.warning(f"prompt-optimizer: could not load source {sid}: {exc}")
            continue
        text = (getattr(source, "full_text", None) or "").strip()
        if not text:
            continue
        items.append(
            {
                "id": str(sid).replace(":", "_"),
                "input_text": text[:_MAX_INPUT_CHARS],
            }
        )
    return items


@command("optimize_prompt", app="open_notebook", retry={"max_attempts": 1})
async def optimize_prompt_command(
    input_data: OptimizePromptInput,
) -> OptimizePromptOutput:
    start = time.time()
    try:
        if not skillopt_available():
            raise ValueError(
                "The 'skillopt' package is not installed in the app "
                "environment — prompt optimization is unavailable. It ships "
                "with the next app update."
            )
        transformation = await Transformation.get(input_data.transformation_id)
        if not transformation:
            raise ValueError(
                f"Transformation '{input_data.transformation_id}' not found"
            )
        prompt_text = (getattr(transformation, "prompt", None) or "").strip()
        if not prompt_text:
            raise ValueError("The transformation has no prompt to optimize")
        if not (input_data.criteria or "").strip():
            raise ValueError("Optimization criteria are required")

        items = await _load_example_items(input_data.source_ids)
        if len(items) < 2:
            raise ValueError(
                "Prompt optimization needs at least 2 sources with extracted "
                "text as examples (one trains, one validates)."
            )

        if input_data.target_model_id and input_data.optimizer_model_id:
            target_id, optimizer_id = (
                input_data.target_model_id,
                input_data.optimizer_model_id,
            )
        else:
            target_id, optimizer_id = await _default_model_ids()
        await _gate_offline([target_id, optimizer_id])

        run_dir = os.path.join(DATA_FOLDER, "prompt_optimizer", str(uuid.uuid4()))

        from deeper_notebook.prompt_optimizer.runner import (
            PromptOptimizerError,
            run_prompt_optimization,
        )

        timeout = float(
            resolve_env("DEEPER_NOTEBOOK_PROMPT_OPT_TIMEOUT_SEC", "1800").strip()
            or 1800
        )
        try:
            result = await asyncio.wait_for(
                run_prompt_optimization(
                    prompt_text=prompt_text,
                    items=items,
                    criteria=input_data.criteria,
                    target_model_id=target_id,
                    optimizer_model_id=optimizer_id,
                    run_dir=run_dir,
                    epochs=input_data.epochs,
                    edit_budget=input_data.edit_budget,
                ),
                timeout=timeout,
            )
        except PromptOptimizerError as exc:
            raise ValueError(str(exc)) from exc
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"Prompt optimization timed out after {timeout:.0f}s. Use "
                f"fewer/shorter sources or local models, or raise "
                f"DEEPER_NOTEBOOK_PROMPT_OPT_TIMEOUT_SEC."
            ) from exc

        elapsed = time.time() - start
        logger.info(
            f"prompt-optimizer: finished in {elapsed:.1f}s "
            f"(changed={result['changed']})"
        )
        return OptimizePromptOutput(
            success=True,
            transformation_id=str(transformation.id),
            original_prompt=prompt_text,
            optimized_prompt=result["optimized_prompt"],
            changed=bool(result["changed"]),
            processing_time=elapsed,
        )
    except ValueError:
        raise  # permanent (surreal-commands does not retry these)
    except Exception as exc:
        logger.exception(exc)
        raise RuntimeError(str(exc)) from exc
