from types import SimpleNamespace

import pytest

from deeper_notebook.domain.notebook import Source


@pytest.mark.asyncio
async def test_source_processing_progress_includes_command_progress(monkeypatch):
    async def fake_get_command_status(command_id: str):
        assert "source-progress" in command_id
        return SimpleNamespace(
            status="running",
            progress={"processed": 2, "total": 4, "percentage": 50},
            result={"execution_metadata": {"started_at": "2026-06-23T10:00:00Z"}},
            error_message=None,
        )

    monkeypatch.setattr("surreal_commands.get_command_status", fake_get_command_status)

    source = Source(
        id="source:progress",
        title="Progress source",
        command="command:source-progress",
    )

    progress = await source.get_processing_progress()

    assert progress == {
        "status": "running",
        "started_at": "2026-06-23T10:00:00Z",
        "completed_at": None,
        "error": None,
        "progress": {"processed": 2, "total": 4, "percentage": 50},
        "result": {"execution_metadata": {"started_at": "2026-06-23T10:00:00Z"}},
    }
