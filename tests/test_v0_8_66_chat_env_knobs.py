"""v0.8.66 — guarded env knobs for the chat tool loop.

A-3: DEEPER_NOTEBOOK_AGENT_MAX_ITERATIONS — the iteration cap was hardcoded to 4 with no
     override, though the v0.8.56 truncation notice tells users to raise it.
MCP-3: DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC was parsed UNGUARDED inside the per-call loop;
     a malformed value crashed the whole batch and 0/negative gave an instant
     timeout. Now parsed once via a guarded+clamped helper.
"""

from __future__ import annotations

import pytest

from deeper_notebook.graphs.chat import _agent_max_iterations, _mcp_tool_timeout_sec


@pytest.mark.parametrize(
    "val,expected",
    [
        (None, 4),
        ("8", 8),
        ("1", 1),
        ("0", 4),
        ("-3", 4),
        ("abc", 4),
        ("", 4),
        ("  ", 4),
    ],
)
def test_agent_max_iterations(monkeypatch, val, expected):
    if val is None:
        monkeypatch.delenv("DEEPER_NOTEBOOK_AGENT_MAX_ITERATIONS", raising=False)
    else:
        monkeypatch.setenv("DEEPER_NOTEBOOK_AGENT_MAX_ITERATIONS", val)
    assert _agent_max_iterations() == expected


@pytest.mark.parametrize(
    "val,expected",
    [
        (None, 30.0),
        ("5", 5.0),
        ("12.5", 12.5),
        ("0", 30.0),
        ("-1", 30.0),
        ("abc", 30.0),
        ("", 30.0),
    ],
)
def test_mcp_tool_timeout_sec(monkeypatch, val, expected):
    if val is None:
        monkeypatch.delenv("DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC", raising=False)
    else:
        monkeypatch.setenv("DEEPER_NOTEBOOK_MCP_TOOL_TIMEOUT_SEC", val)
    assert _mcp_tool_timeout_sec() == expected
