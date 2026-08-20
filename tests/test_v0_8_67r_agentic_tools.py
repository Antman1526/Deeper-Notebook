"""v0.8.67r — Unit tests for the new agentic chat tools (opencode_run and add_web_source_to_notebook)."""

from __future__ import annotations

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from deeper_notebook.graphs import chat as chat_mod
from deeper_notebook.tools.add_web_source import build_add_web_source_tool
from deeper_notebook.tools.opencode import (
    OPENCODE_TOOL_NAME,
    build_opencode_tool,
    opencode_bin_path,
    opencode_enabled,
    run_opencode,
)

# ---------------------------------------------------------------- opencode CLI tests


def test_opencode_path_detection(monkeypatch):
    monkeypatch.delenv("OPENCODE_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/mock/bin/opencode")
    monkeypatch.setattr(
        "os.path.exists", lambda path: True if path == "/mock/bin/opencode" else False
    )
    monkeypatch.setattr("os.access", lambda path, mode: True)
    assert opencode_bin_path() == "/mock/bin/opencode"
    assert opencode_enabled() is True

    monkeypatch.setenv("OPENCODE_BIN", "/custom/path/opencode")
    assert opencode_bin_path() == "/custom/path/opencode"


@pytest.mark.asyncio
async def test_run_opencode_success(monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", "/mock/bin/opencode")

    # Mock asyncio.create_subprocess_exec
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Hello Output", b"")
    mock_process.returncode = 0

    mock_exec = AsyncMock(return_value=mock_process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)

    out = await run_opencode(
        "print 'Hello'",
        project="/mock/proj",
        model="openai/gpt-4o",
        continue_session=True,
    )
    assert out == "Hello Output"

    # Check that it passed the correct arguments
    mock_exec.assert_called_once_with(
        "/mock/bin/opencode",
        "run",
        "print 'Hello'",
        "--model",
        "openai/gpt-4o",
        "--continue",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="/mock/proj",
        env=ANY,
    )


@pytest.mark.asyncio
async def test_run_opencode_failure(monkeypatch):
    monkeypatch.setenv("OPENCODE_BIN", "/mock/bin/opencode")

    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Partial output", b"Traceback error")
    mock_process.returncode = 1

    mock_exec = AsyncMock(return_value=mock_process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)

    out = await run_opencode("print 'Hello'")
    assert "Traceback error" in out
    assert "Partial output" in out


# ---------------------------------------------------------------- add_web_source tests


@pytest.mark.asyncio
async def test_add_web_source_tool_execution(monkeypatch):
    mock_extracted = MagicMock()
    mock_extracted.content = "Extracted Markdown Content"
    mock_extracted.title = "Page Title"

    # The tool delegates URL work to the same checked source-graph helper as
    # normal ingestion, so this remains hermetic without a network request.
    mock_extract_fn = AsyncMock(return_value=mock_extracted)
    monkeypatch.setattr(
        "deeper_notebook.graphs.source._extract_checked_url", mock_extract_fn
    )

    # Mock Source object
    mock_source_instance = MagicMock()
    mock_source_instance.id = "source:123"
    mock_source_instance.save = AsyncMock()
    mock_source_instance.add_to_notebook = AsyncMock()
    mock_source_instance.vectorize = AsyncMock()

    mock_source_class = MagicMock(return_value=mock_source_instance)
    monkeypatch.setattr(
        "deeper_notebook.tools.add_web_source.Source", mock_source_class
    )

    # Build tool and run
    captures = []
    tool = build_add_web_source_tool(notebook_id="notebook:456", captures=captures)
    assert tool.name == "add_web_source_to_notebook"

    result = await tool.coroutine(url="https://example.com/test", title="Custom Title")
    assert "Successfully imported" in result
    assert "Custom Title" in result

    # Verify mock interactions
    mock_extract_fn.assert_called_once()
    mock_source_class.assert_called_once()
    mock_source_instance.save.assert_called_once()
    mock_source_instance.add_to_notebook.assert_called_once_with("notebook:456")
    mock_source_instance.vectorize.assert_called_once()

    # Verify citation capture
    assert len(captures) == 1
    assert captures[0]["name"] == "add_web_source_to_notebook"
    assert captures[0]["args"] == {
        "url": "https://example.com/test",
        "title": "Custom Title",
    }


# --------------------------------------------------------- chat loop integration tests


class _FakeAIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.content = ""


class _RecordingModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.bound = None

    def bind_tools(self, tools):
        self.bound = tools
        return self

    async def ainvoke(self, payload):
        if not self._responses:
            return _FakeAIMessage([])
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_loop_binds_opencode_when_enabled(monkeypatch):
    monkeypatch.setattr(chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr("deeper_notebook.tools.opencode.opencode_enabled", lambda: True)

    model = _RecordingModel([_FakeAIMessage([])])
    await chat_mod.bind_mcp_and_run_tool_loop(model, [], max_iterations=2)
    assert model.bound is not None
    assert any(getattr(t, "name", None) == "opencode_run" for t in model.bound)


@pytest.mark.asyncio
async def test_loop_binds_add_web_source_when_notebook_id_present(monkeypatch):
    monkeypatch.setattr(chat_mod, "_resolve_chat_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "deeper_notebook.tools.opencode.opencode_enabled", lambda: False
    )

    model = _RecordingModel([_FakeAIMessage([])])
    await chat_mod.bind_mcp_and_run_tool_loop(
        model, [], max_iterations=2, notebook_id="notebook:123"
    )
    assert model.bound is not None
    assert any(
        getattr(t, "name", None) == "add_web_source_to_notebook" for t in model.bound
    )
