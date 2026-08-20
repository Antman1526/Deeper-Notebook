"""v0.7.32 — regression tests for Source.delete() cancelling in-flight commands.

Before v0.7.32, deleting a source while an embedding/processing command
was mid-flight left the worker running against a now-dead source. The
worker would later write a fresh source_embedding row referencing the
deleted source — orphan data, wasted GPU, potential FK errors on later
migrations.

`Source.delete()` now:
- Checks self.command first
- If command is in {'new', 'running', 'queued'}, calls
  CommandService.update_command_result(..., status='canceled')
- Falls through (continues with deletion) on any cancel error so the
  primary deletion path is unaffected
- No-op when self.command is None
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from surrealdb import RecordID

from deeper_notebook.domain.notebook import Source


@pytest.mark.asyncio
async def test_delete_cancels_running_command(monkeypatch):
    """A source with an in-flight 'running' command gets it cancelled
    before deletion proceeds."""
    cancelled_with = {}

    async def fake_get_status(command_id):
        class _R:
            value = "running"

        return _R()

    fake_svc = AsyncMock()

    async def _update(*args, **kwargs):
        cancelled_with["args"] = args
        cancelled_with["kwargs"] = kwargs

    fake_svc.update_command_result = _update

    monkeypatch.setattr(
        "surreal_commands.get_command_status", fake_get_status, raising=False
    )
    monkeypatch.setattr(
        "surreal_commands.core.service.get_command_service",
        lambda: fake_svc,
        raising=False,
    )

    src = Source(
        id="source:test_cancel",
        title="Test",
        asset=None,
        command=RecordID.parse("command:abc"),
    )
    with patch.object(
        Source.__bases__[0], "delete", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value = True
        await src.delete()

    assert "args" in cancelled_with, (
        "update_command_result was never called for a running command"
    )
    # The cancel uses status=canceled
    kw = cancelled_with["kwargs"]
    assert kw.get("status") == "canceled", (
        f"expected status=canceled, got {kw.get('status')}"
    )
    # The error_message mentions the source id
    assert "source:test_cancel" in (kw.get("error_message") or "")


@pytest.mark.asyncio
async def test_delete_skips_cancel_for_completed_command(monkeypatch):
    """Completed/failed commands need no cancel — leave them alone."""
    cancel_calls = []

    async def fake_get_status(command_id):
        class _R:
            value = "completed"

        return _R()

    fake_svc = AsyncMock()

    async def _update(*args, **kwargs):
        cancel_calls.append((args, kwargs))

    fake_svc.update_command_result = _update

    monkeypatch.setattr(
        "surreal_commands.get_command_status", fake_get_status, raising=False
    )
    monkeypatch.setattr(
        "surreal_commands.core.service.get_command_service",
        lambda: fake_svc,
        raising=False,
    )

    src = Source(
        id="source:done",
        title="Test",
        asset=None,
        command=RecordID.parse("command:done"),
    )
    with patch.object(
        Source.__bases__[0], "delete", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value = True
        await src.delete()

    assert cancel_calls == [], (
        f"update_command_result should not run for completed cmds, got {cancel_calls}"
    )


@pytest.mark.asyncio
async def test_delete_with_no_command_doesnt_touch_surreal_commands(monkeypatch):
    """When self.command is None, the cancel path is a no-op — no
    accidental call into surreal_commands."""
    raised = {"v": False}

    async def boom(*a, **kw):
        raised["v"] = True
        raise RuntimeError("should not be called")

    monkeypatch.setattr("surreal_commands.get_command_status", boom, raising=False)

    src = Source(
        id="source:no_cmd",
        title="Test",
        asset=None,
        command=None,
    )
    with patch.object(
        Source.__bases__[0], "delete", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value = True
        await src.delete()

    assert raised["v"] is False, (
        "Source with no command should not touch surreal_commands"
    )


@pytest.mark.asyncio
async def test_delete_continues_if_cancel_raises(monkeypatch):
    """If the cancel attempt itself raises (surreal_commands down,
    API drift), we MUST still delete the source. The orphan-data
    failure mode is no worse than pre-v0.7.32; refusing to delete
    is worse than that."""

    async def fake_get_status(command_id):
        raise RuntimeError("surreal_commands unreachable")

    monkeypatch.setattr(
        "surreal_commands.get_command_status", fake_get_status, raising=False
    )

    src = Source(
        id="source:flaky",
        title="Test",
        asset=None,
        command=RecordID.parse("command:flaky"),
    )
    with patch.object(
        Source.__bases__[0], "delete", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value = True
        result = await src.delete()

    # Source.delete still completed
    mock_super.assert_called_once()
    assert result is True
