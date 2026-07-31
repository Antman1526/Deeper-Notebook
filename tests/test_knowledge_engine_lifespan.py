from __future__ import annotations

import ast
import asyncio
import inspect
from types import SimpleNamespace

import pytest

from api import main


class _Service:
    def __init__(self, coordinator: object) -> None:
        self.coordinator = coordinator
        self.started = asyncio.Event()

    async def run_backfill(self) -> None:
        self.started.set()
        await asyncio.Event().wait()


def _app():
    return SimpleNamespace(state=SimpleNamespace())


@pytest.mark.asyncio
async def test_disabled_flags_create_no_engine_service_or_backfill_task(monkeypatch):
    app = _app()
    monkeypatch.setattr(main, "enabled_setting", lambda _name: False)

    coordinator, task = await main._start_knowledge_engine(app)

    assert coordinator is None
    assert task is None
    assert not hasattr(app.state, "knowledge_engine_service")


@pytest.mark.asyncio
async def test_shadow_enabled_sets_service_and_returns_its_single_coordinator(monkeypatch):
    app = _app()
    coordinator = object()
    service = _Service(coordinator)
    monkeypatch.setattr(
        main,
        "enabled_setting",
        lambda name: name.endswith("SHADOW_ENABLED"),
    )

    returned, task = await main._start_knowledge_engine(
        app,
        runtime_factory=lambda: service,
    )

    assert returned is coordinator
    assert task is None
    assert app.state.knowledge_engine_service is service
    await main._stop_knowledge_engine(app, task)
    assert not hasattr(app.state, "knowledge_engine_service")


@pytest.mark.asyncio
async def test_backfill_without_shadow_logs_stable_configuration_code_and_keeps_legacy_mode(monkeypatch):
    app = _app()
    monkeypatch.setattr(
        main,
        "enabled_setting",
        lambda name: name.endswith("BACKFILL_ENABLED"),
    )
    messages: list[str] = []
    monkeypatch.setattr(main.logger, "warning", lambda message, *_args: messages.append(message))

    coordinator, task = await main._start_knowledge_engine(app)

    assert coordinator is None
    assert task is None
    assert not hasattr(app.state, "knowledge_engine_service")
    assert messages == ["knowledge_engine_configuration_invalid ({})"]


@pytest.mark.asyncio
async def test_shutdown_cancels_and_awaits_only_the_engine_backfill_task(monkeypatch):
    app = _app()
    coordinator = object()
    service = _Service(coordinator)
    monkeypatch.setattr(main, "enabled_setting", lambda _name: True)
    untouched = asyncio.create_task(asyncio.sleep(10))

    _returned, task = await main._start_knowledge_engine(
        app,
        runtime_factory=lambda: service,
    )
    assert task is not None
    await service.started.wait()

    await main._stop_knowledge_engine(app, task)

    assert task.cancelled()
    assert not untouched.cancelled()
    untouched.cancel()
    with pytest.raises(asyncio.CancelledError):
        await untouched


@pytest.mark.asyncio
async def test_shutdown_retrieves_completed_backfill_task_results(monkeypatch):
    app = _app()
    app.state.knowledge_engine_service = object()
    messages: list[str] = []
    monkeypatch.setattr(main.logger, "warning", lambda message, *_args: messages.append(message))

    async def _failed_backfill() -> None:
        raise RuntimeError("private detail")

    completed = asyncio.create_task(asyncio.sleep(0))
    failed = asyncio.create_task(_failed_backfill())
    await asyncio.sleep(0)

    await main._stop_knowledge_engine(app, completed)
    await main._stop_knowledge_engine(app, failed)

    assert completed.done()
    assert failed.done()
    assert messages == ["knowledge_engine_backfill_shutdown_unavailable ({})"]
    assert not hasattr(app.state, "knowledge_engine_service")


@pytest.mark.asyncio
async def test_engine_startup_failure_is_contained_with_stable_code(monkeypatch):
    app = _app()
    monkeypatch.setattr(main, "enabled_setting", lambda _name: True)
    messages: list[str] = []
    monkeypatch.setattr(main.logger, "warning", lambda message, *_args: messages.append(message))

    coordinator, task = await main._start_knowledge_engine(
        app,
        runtime_factory=lambda: (_ for _ in ()).throw(RuntimeError("private detail")),
    )

    assert coordinator is None
    assert task is None
    assert not hasattr(app.state, "knowledge_engine_service")
    assert messages == ["knowledge_engine_startup_unavailable ({})"]


def test_lifespan_injects_the_same_shadow_coordinator_into_legacy_services():
    tree = ast.parse(inspect.getsource(main.lifespan))
    keywords = [
        keyword
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"OverlayService", "VaultService"}
        for keyword in node.keywords
        if keyword.arg == "shadow_projector"
    ]

    assert len(keywords) == 2
    assert all(
        isinstance(keyword.value, ast.Name)
        and keyword.value.id == "knowledge_shadow_coordinator"
        for keyword in keywords
    )


def test_importing_engine_modules_cannot_start_a_backfill_task():
    tree = ast.parse(inspect.getsource(main))
    module_calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr | ast.Assign | ast.AnnAssign)
    ]

    assert not any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"create_task", "run_backfill"}
        for node in module_calls
        for call in ast.walk(node)
    )
