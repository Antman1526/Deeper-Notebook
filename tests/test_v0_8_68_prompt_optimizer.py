"""v0.8.68 — SkillOpt prompt-optimizer integration tests.

No live LLM calls: the adapter is exercised with patched chat functions and
the config assembly runs against the vendored base YAML. The library's
surface (trainer signature, flat-config keys) is pinned so a skillopt
upgrade that breaks the integration fails here with a clear message.
"""

from __future__ import annotations

import asyncio
import inspect
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent

skillopt = pytest.importorskip("skillopt", reason="skillopt not installed")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ------------------------------------------------------------- library pins


def test_trainer_accepts_programmatic_adapter():
    from skillopt.engine.trainer import ReflACTTrainer

    params = list(inspect.signature(ReflACTTrainer.__init__).parameters)
    assert params[1:3] == ["cfg", "adapter"], (
        "ReflACTTrainer no longer takes (cfg, adapter) — the integration "
        "in deeper_notebook/prompt_optimizer must be updated"
    )


def test_vendored_base_config_flattens_with_required_keys():
    from skillopt.config import flatten_config, load_config

    flat = flatten_config(
        load_config(
            str(_REPO / "deeper_notebook" / "prompt_optimizer" / "skillopt_base.yaml")
        )
    )
    for key in (
        "num_epochs",
        "batch_size",
        "edit_budget",
        "skill_init",
        "out_root",
        "target_model",
        "optimizer_model",
    ):
        assert key in flat or any(k.endswith("." + key) for k in flat), (
            f"flattened skillopt config lost key {key!r}"
        )


# ------------------------------------------------------------- judge parsing


def test_parse_judge_score():
    from deeper_notebook.prompt_optimizer.adapter import parse_judge_score

    assert parse_judge_score('{"score": 0.85, "reason": "good"}') == 0.85
    assert parse_judge_score('garbage {"score": 1.4}') == 1.0  # clamped
    assert parse_judge_score("no json at all") == 0.0
    assert parse_judge_score("") == 0.0
    assert parse_judge_score('{"score": .5}') == 0.5


# ------------------------------------------------------------- dataloader


def test_examples_dataloader_split_and_batches():
    from deeper_notebook.prompt_optimizer.adapter import ExamplesDataLoader

    items = [{"id": f"s{i}", "input_text": f"text {i}"} for i in range(6)]
    dl = ExamplesDataLoader(items, seed=1)
    assert len(dl.train_items) + len(dl.val_items) == 6
    assert dl.val_items, "validation split must be non-empty"

    train = dl.build_train_batch(batch_size=3, seed=7)
    assert train.phase == "train" and len(train.payload) == 3
    ev = dl.build_eval_batch(env_num=0, split="valid", seed=7)
    assert ev.phase == "eval" and len(ev.payload) == len(dl.val_items)


def test_single_item_still_yields_val():
    from deeper_notebook.prompt_optimizer.adapter import ExamplesDataLoader

    dl = ExamplesDataLoader([{"id": "only", "input_text": "x"}])
    assert dl.train_items and dl.val_items


# ------------------------------------------------------------- rollout


def test_rollout_scores_with_judge(monkeypatch, tmp_path):
    from deeper_notebook.prompt_optimizer import adapter as ad

    def _fake_target(system, user, max_completion_tokens=0, **kw):
        return (f"OUTPUT for {user[:10]}", {})

    def _fake_optimizer(system, user, max_completion_tokens=0, **kw):
        return ('{"score": 0.9, "reason": "matches criteria"}', {})

    monkeypatch.setattr(ad, "chat_target", _fake_target)
    monkeypatch.setattr(ad, "chat_optimizer", _fake_optimizer)

    adapter = ad.TransformationAdapter(
        items=[{"id": "a", "input_text": "alpha"}, {"id": "b", "input_text": "beta"}],
        criteria="Be concise.",
        workers=2,
    )
    results = adapter.rollout(
        [{"id": "a", "input_text": "alpha"}],
        "PROMPT",
        str(tmp_path / "po-test-out"),
    )
    assert results[0]["soft"] == 0.9
    assert results[0]["hard"] == 1
    assert results[0]["task_type"] == "transformation"


def test_rollout_target_failure_scores_zero(monkeypatch, tmp_path):
    from deeper_notebook.prompt_optimizer import adapter as ad

    def _boom(system, user, max_completion_tokens=0, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ad, "chat_target", _boom)
    adapter = ad.TransformationAdapter(
        items=[{"id": "a", "input_text": "alpha"}],
        criteria="c" * 20,
    )
    results = adapter.rollout(
        [{"id": "a", "input_text": "alpha"}],
        "PROMPT",
        str(tmp_path / "po-test-out"),
    )
    assert results[0]["hard"] == 0 and results[0]["soft"] == 0.0


# ------------------------------------------------------------- backends


def test_resolve_backend_local(monkeypatch):
    from deeper_notebook.podcasts import models as pm
    from deeper_notebook.prompt_optimizer import runner

    async def _fake_resolve(model_id):
        return (
            "openai_compatible",
            "gemma-4-E4B",
            {"base_url": "http://127.0.0.1:59998/v1"},
        )

    monkeypatch.setattr(pm, "_resolve_model_config", _fake_resolve)
    out = _run(runner.resolve_backend("model:x"))
    assert out["endpoint"] == "http://127.0.0.1:59998/v1"
    assert out["model_name"] == "gemma-4-E4B"
    assert out["api_key"] == "sk-local"


def test_resolve_backend_rejects_incompatible(monkeypatch):
    from deeper_notebook.podcasts import models as pm
    from deeper_notebook.prompt_optimizer import runner

    async def _fake_resolve(model_id):
        return ("anthropic", "claude-haiku-4-5", {})

    monkeypatch.setattr(pm, "_resolve_model_config", _fake_resolve)
    with pytest.raises(runner.PromptOptimizerError):
        _run(runner.resolve_backend("model:x"))


def test_build_flat_config_wires_endpoints(tmp_path):
    from deeper_notebook.prompt_optimizer.runner import build_flat_config

    flat = build_flat_config(
        run_dir=str(tmp_path),
        skill_init_path=str(tmp_path / "skill.md"),
        target={"model_name": "gemma", "endpoint": "http://t/v1", "api_key": "k1"},
        optimizer={"model_name": "hermes", "endpoint": "http://o/v1", "api_key": "k2"},
        epochs=2,
        batch_size=4,
        edit_budget=3,
    )

    def _get(key):
        if key in flat:
            return flat[key]
        return next(v for k, v in flat.items() if k.endswith("." + key))

    assert _get("target_model") == "gemma"
    assert _get("optimizer_model") == "hermes"
    assert _get("target_azure_openai_endpoint") == "http://t/v1"
    assert _get("optimizer_azure_openai_endpoint") == "http://o/v1"
    assert _get("target_azure_openai_auth_mode") == "openai_compatible"
    assert _get("num_epochs") == 2
    assert _get("edit_budget") == 3
    assert _get("out_root") == str(tmp_path)


# ------------------------------------------------------------- API + wiring


def test_optimize_request_schema():
    from api.routers.transformations import OptimizePromptRequest

    req = OptimizePromptRequest(
        source_ids=["source:1", "source:2"],
        criteria="Summaries must be under 100 words and cite the source.",
    )
    assert req.epochs == 2
    with pytest.raises(Exception):
        OptimizePromptRequest(source_ids=["source:1"], criteria="x" * 20)
    with pytest.raises(Exception):
        OptimizePromptRequest(source_ids=["a", "b"], criteria="short")


def test_command_registered():
    import commands

    assert hasattr(commands, "optimize_prompt_command")


def test_offline_gate_blocks_cloud_models(monkeypatch):
    from commands import prompt_optimizer_commands as poc
    from deeper_notebook.health import network
    from deeper_notebook.health.network import NetworkState

    async def _offline():
        return NetworkState(
            status="offline", forced_offline=False, checked_at=0.0, source="probe"
        )

    monkeypatch.setattr(network, "get_network_state_with_settings", _offline)

    from deeper_notebook.podcasts import models as pm

    async def _cloud(model_id):
        return ("openai", "gpt-4o-mini", {})

    monkeypatch.setattr(pm, "_resolve_model_config", _cloud)

    with pytest.raises(ValueError, match="offline"):
        _run(poc._gate_offline(["model:cloud"]))


def test_requirements_carry_skillopt():
    req = (_REPO / "desktop" / "requirements.txt").read_text()
    assert "skillopt" in req


def test_all_command_input_schemas_resolve():
    """v0.8.68 — `from __future__ import annotations` in a @command module
    turns the handler's type hints into strings that LangChain's
    RunnableLambda-generated input schema cannot resolve at submit time
    ("<name>_command_input is not fully defined" → 500 on the API route,
    caught live). Force-resolve every registered command's input schema so
    the next module added with the future import fails here, not in prod."""
    from surreal_commands.core.registry import CommandRegistry

    import commands  # noqa: F401 — triggers registration

    registry = CommandRegistry()
    cmds = registry._commands  # no public enumeration API in 1.x
    assert "open_notebook.optimize_prompt" in cmds
    assert "open_notebook.generate_studio_artifact" in cmds
    for key, cmd in cmds.items():
        runnable = getattr(cmd, "runnable", cmd)  # dict stores RunnableLambda
        schema = runnable.get_input_schema()
        schema.model_json_schema()  # raises if forward refs are unresolved


def test_dataloader_reports_train_size_to_trainer():
    """v0.8.68 — BaseDataLoader.get_train_size() returns None and, because
    it exists, the trainer's `train_items` fallback never runs; without an
    override the run dies with "Unable to determine train_size
    automatically" (caught live). Pin both our override and the trainer's
    resolution path."""
    from skillopt.engine.trainer import _resolve_train_size

    from deeper_notebook.prompt_optimizer.adapter import ExamplesDataLoader

    items = [{"id": f"s{i}", "input_text": f"text {i}"} for i in range(5)]
    dl = ExamplesDataLoader(items, seed=1)
    assert dl.get_train_size() == len(dl.train_items) > 0
    assert _resolve_train_size({}, dl) == len(dl.train_items)


def test_vendored_prompts_cover_patch_mode_pipeline():
    """The names the reflection + aggregate stages load in our (patch-mode)
    config must all be vendored — each was a live mid-training crash."""
    vendored = {
        p.name
        for p in (
            _REPO / "deeper_notebook" / "prompt_optimizer" / "skillopt_prompts"
        ).glob("*.md")
    }
    for name in (
        "analyst_error",
        "analyst_success",
        "merge_failure",
        "merge_success",
        "merge_final",
    ):
        assert f"{name}.md" in vendored, f"vendored prompt {name}.md missing"


def test_ensure_skillopt_prompts_backfills_missing_only(tmp_path):
    from deeper_notebook.prompt_optimizer.runner import ensure_skillopt_prompts

    (tmp_path / "analyst_error.md").write_text("EXISTING — do not clobber")
    copied = ensure_skillopt_prompts(dest_dir=tmp_path)
    assert copied > 0
    assert (tmp_path / "analyst_success.md").exists()
    assert (tmp_path / "merge_final.md").exists()
    assert not (tmp_path / "README.md").exists()  # attribution stays vendored
    assert (tmp_path / "analyst_error.md").read_text() == "EXISTING — do not clobber"
    assert ensure_skillopt_prompts(dest_dir=tmp_path) == 0  # idempotent


def test_ensure_skillopt_prompts_fixes_disposable_package(monkeypatch, tmp_path):
    """Backfill must satisfy SkillOpt's loader without mutating site-packages."""
    import skillopt.prompts as skillopt_prompts

    from deeper_notebook.prompt_optimizer.runner import ensure_skillopt_prompts

    installed_prompts = Path(skillopt_prompts.__file__).parent
    installed_snapshot = {
        path.name: path.read_bytes() for path in installed_prompts.glob("*.md")
    }
    disposable_prompts = tmp_path / "skillopt" / "prompts"
    shutil.copytree(installed_prompts, disposable_prompts)
    for prompt in disposable_prompts.glob("*.md"):
        prompt.unlink()

    ensure_skillopt_prompts(dest_dir=disposable_prompts)
    monkeypatch.setattr(
        skillopt_prompts,
        "_PROMPTS_DIR",
        str(disposable_prompts),
    )
    for name in (
        "analyst_error",
        "analyst_success",
        "merge_failure",
        "merge_success",
        "merge_final",
    ):
        assert skillopt_prompts.load_prompt(name).strip(), (
            f"load_prompt({name!r}) empty"
        )
    assert {
        path.name: path.read_bytes() for path in installed_prompts.glob("*.md")
    } == installed_snapshot
