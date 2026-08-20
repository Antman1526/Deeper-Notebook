"""v0.8.68 — SkillOpt EnvAdapter for optimizing Transformation prompts.

Modeled on skillopt.envs.searchqa (the library's QA-over-text benchmark):
the "environment" is a list of example items (source excerpts), a rollout
runs the current prompt (skill document) on each item with the target
model, and an LLM judge converts the output into the soft 0-1 score the
trainer's validation gate consumes. Reflection delegates to the library's
generic minibatch analyst.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from loguru import logger
from skillopt.datasets.base import BaseDataLoader
from skillopt.envs.base import EnvAdapter
from skillopt.gradient.reflect import run_minibatch_reflect
from skillopt.model import chat_optimizer, chat_target
from skillopt.types import BatchSpec

# The judge returns JSON; parse defensively (local models drift).
_JUDGE_SYSTEM = """You are a strict quality judge for AI-generated text.
You will be given: the INPUT a transformation ran on, the OUTPUT it
produced, and the CRITERIA the output must satisfy.
Score how well the OUTPUT satisfies the CRITERIA for this INPUT.
Respond with ONLY a JSON object: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}"""

_SCORE_RE = re.compile(r'"score"\s*:\s*([0-9]*\.?[0-9]+)')


def parse_judge_score(text: str) -> float:
    """Extract a 0-1 score from judge output; clamp; 0.0 on garbage."""
    try:
        m = _SCORE_RE.search(text or "")
        if not m:
            return 0.0
        return max(0.0, min(1.0, float(m.group(1))))
    except Exception:
        return 0.0


class ExamplesDataLoader(BaseDataLoader):
    """In-memory train/validation split over the user's example items.

    Items: {"id": str, "input_text": str}. No test split — the run is
    interactive (user reviews the optimized prompt), so train + val gate
    is the whole story.
    """

    def __init__(self, items: list[dict], val_ratio: float = 0.34, seed: int = 42):
        import random

        items = [dict(it) for it in items]
        rng = random.Random(seed)
        rng.shuffle(items)
        n_val = max(1, int(len(items) * val_ratio)) if len(items) > 1 else 0
        self.val_items = items[:n_val]
        self.train_items = items[n_val:] or items  # 1 item → train==val item
        if not self.val_items:
            self.val_items = list(self.train_items)

    def setup(self, cfg: dict) -> None:  # interface parity
        self._cfg = dict(cfg)

    def get_train_size(self) -> int:
        # v0.8.68 — REQUIRED override (caught by the live smoke test): the
        # BaseDataLoader default returns None, and because it exists the
        # trainer's `train_items` fallback never runs — train_size resolves
        # to nothing and training aborts with "Unable to determine
        # train_size automatically".
        return len(self.train_items)

    def build_train_batch(self, batch_size: int, seed: int, **kwargs) -> BatchSpec:
        import random

        rng = random.Random(seed)
        pool = list(self.train_items)
        rng.shuffle(pool)
        payload = pool[: max(1, min(batch_size, len(pool)))]
        return BatchSpec(
            phase="train",
            split="train",
            seed=seed,
            batch_size=len(payload),
            payload=payload,
        )

    def build_eval_batch(
        self, env_num: int, split: str, seed: int, **kwargs
    ) -> BatchSpec:
        pool = list(self.val_items)
        if env_num and env_num > 0:
            pool = pool[:env_num]
        return BatchSpec(
            phase="eval",
            split=split,
            seed=seed,
            batch_size=len(pool),
            payload=pool,
        )


class TransformationAdapter(EnvAdapter):
    """SkillOpt environment: 'apply this prompt to text, judged by criteria'."""

    def __init__(
        self,
        items: list[dict],
        criteria: str,
        *,
        judge_threshold: float = 0.7,
        workers: int = 4,
        analyst_workers: int = 2,
        minibatch_size: int = 4,
        edit_budget: int = 4,
        max_completion_tokens: int = 4096,
        seed: int = 42,
    ) -> None:
        self.criteria = criteria.strip()
        self.judge_threshold = judge_threshold
        self.workers = max(1, workers)
        self.analyst_workers = max(1, analyst_workers)
        self.minibatch_size = minibatch_size
        self.edit_budget = edit_budget
        self.max_completion_tokens = max_completion_tokens
        self.dataloader = ExamplesDataLoader(items, seed=seed)

    # ── plumbing (mirrors SearchQAAdapter) ─────────────────────────────
    def setup(self, cfg: dict) -> None:
        super().setup(cfg)
        self.dataloader.setup(cfg)

    def get_dataloader(self):
        return self.dataloader

    def build_env_from_batch(self, batch: BatchSpec, **kwargs):
        return list(batch.payload or [])

    def build_train_env(self, batch_size: int, seed: int, **kwargs):
        return self.build_env_from_batch(
            self.dataloader.build_train_batch(batch_size=batch_size, seed=seed)
        )

    def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs):
        return self.build_env_from_batch(
            self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed)
        )

    # ── rollout: run prompt → judge output ─────────────────────────────
    def _run_one(self, item: dict, skill_content: str, out_dir: str) -> dict:
        item_id = str(item.get("id"))
        input_text = str(item.get("input_text") or "")
        try:
            prediction, _meta = chat_target(
                system=skill_content,
                user=input_text,
                max_completion_tokens=self.max_completion_tokens,
            )
        except Exception as exc:
            logger.warning(f"prompt-optimizer rollout failed for {item_id}: {exc}")
            return {
                "id": item_id,
                "hard": 0,
                "soft": 0.0,
                "prediction": f"<target call failed: {exc}>",
                "question": input_text[:2000],
                "task_type": "transformation",
            }

        judge_user = (
            f"CRITERIA:\n{self.criteria}\n\n"
            f"INPUT:\n{input_text[:6000]}\n\n"
            f"OUTPUT:\n{(prediction or '')[:6000]}"
        )
        try:
            judge_raw, _ = chat_optimizer(
                system=_JUDGE_SYSTEM,
                user=judge_user,
                max_completion_tokens=512,
            )
            soft = parse_judge_score(judge_raw)
        except Exception as exc:
            logger.warning(f"prompt-optimizer judge failed for {item_id}: {exc}")
            soft = 0.0

        # Persist per-item artifacts for the reflection stage / debugging.
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f"{item_id}.json"), "w") as f:
                json.dump(
                    {"id": item_id, "prediction": prediction, "soft": soft},
                    f,
                    ensure_ascii=False,
                )
        except Exception:
            pass

        return {
            "id": item_id,
            "hard": 1 if soft >= self.judge_threshold else 0,
            "soft": soft,
            "prediction": (prediction or "")[:4000],
            "question": input_text[:2000],
            "task_type": "transformation",
        }

    def rollout(
        self, env_manager, skill_content: str, out_dir: str, **kwargs
    ) -> list[dict]:
        items: list[dict] = env_manager
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(
                pool.map(lambda it: self._run_one(it, skill_content, out_dir), items)
            )

    # ── reflection: the library's generic minibatch analyst ────────────
    def reflect(self, results, skill_content, out_dir, **kwargs):
        return run_minibatch_reflect(
            results=results,
            skill_content=skill_content,
            prediction_dir=kwargs.get(
                "prediction_dir", os.path.join(out_dir, "predictions")
            ),
            patches_dir=kwargs.get("patches_dir", os.path.join(out_dir, "patches")),
            workers=self.analyst_workers,
            failure_only=False,
            minibatch_size=self.minibatch_size,
            edit_budget=self.edit_budget,
            random_seed=kwargs.get("random_seed"),
            error_system=self.get_error_minibatch_prompt(),
            success_system=self.get_success_minibatch_prompt(),
            step_buffer_context=kwargs.get("step_buffer_context", ""),
            meta_skill_context=kwargs.get("meta_skill_context", ""),
            update_mode=getattr(self, "_cfg", {}).get("skill_update_mode", "patch"),
        )

    def get_task_types(self) -> list[str]:
        return ["transformation"]
