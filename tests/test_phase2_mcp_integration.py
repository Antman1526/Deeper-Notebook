"""Phase 2 — MCP server client + chat-graph integration.

Task 9 additions (lines below the original 3 tests):
  * test_mcp_router_list_and_create  — GET /api/mcp returns [] initially;
    POST /api/mcp 201 with the new record.
  * test_mcp_router_duplicate_name_409 — second POST with the same name
    must return 409, not 500.
"""
from __future__ import annotations


def test_mcp_client_lists_tools_via_streamable_http(monkeypatch):
    """Given a working streamable-http MCP server URL, the client
    must `list_tools()` and return the discovered tool names."""
    from open_notebook.mcp.client import MCPClient

    fake_tools = [
        {"name": "web_search", "description": "Search the web"},
        {"name": "fetch_url", "description": "Fetch a URL"},
    ]

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def list_tools(self):
            return type("X", (), {"tools": [
                type("T", (), {"name": t["name"], "description": t["description"]})()
                for t in fake_tools
            ]})()

    monkeypatch.setattr(
        "open_notebook.mcp.client._open_session",
        lambda url: FakeSession(),
    )
    client = MCPClient(url="http://127.0.0.1:8742/mcp")
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        names = loop.run_until_complete(client.list_tool_names())
    finally:
        loop.close()
    assert names == ["web_search", "fetch_url"]


def test_chat_graph_exposes_mcp_tools_when_enabled(monkeypatch):
    """When at least one MCP server is enabled, the chat graph's
    tool registry must include `mcp_search` and `mcp_fetch`."""
    monkeypatch.setattr(
        "open_notebook.mcp.registry.list_enabled_servers",
        lambda: __import__("asyncio").Future(),
    )
    from open_notebook.graphs.chat import _resolve_chat_tools
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(
            _resolve_chat_tools(force_servers=[
                {"id": "mcp_server:1", "name": "test",
                 "url": "http://x", "enabled": True}
            ])
        )
    finally:
        loop.close()
    tool_names = [t.name for t in tools]
    assert "mcp_search" in tool_names
    assert "mcp_fetch" in tool_names


def test_mcp_registry_lists_enabled_servers(monkeypatch):
    """`list_enabled_servers()` returns only servers with
    `enabled=True`. Disabled servers are not used by the chat
    graph even if they're in the DB."""
    from open_notebook.mcp.registry import list_enabled_servers

    async def _fake_repo_query(q, params=None):
        return [
            {"id": "mcp_server:1", "name": "OpenChronicle",
             "url": "http://127.0.0.1:8742/mcp", "enabled": True},
            {"id": "mcp_server:2", "name": "DuckDuckGo",
             "url": "http://127.0.0.1:8743/mcp", "enabled": False},
        ]
    monkeypatch.setattr(
        "open_notebook.database.repository.repo_query",
        _fake_repo_query,
    )
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        servers = loop.run_until_complete(list_enabled_servers())
    finally:
        loop.close()
    assert len(servers) == 1
    assert servers[0]["name"] == "OpenChronicle"


# ---------------------------------------------------------------------------
# Task 9 — /api/mcp CRUD router
# Auth note: conftest.py sets OPEN_NOTEBOOK_PASSWORD="" so the middleware
# skips auth for all tests — no Authorization header needed.
# ---------------------------------------------------------------------------


def test_mcp_router_list_and_create(monkeypatch):
    """GET /api/mcp returns [] when the table is empty.
    POST /api/mcp 201 creates a server and returns the new record."""
    from fastapi.testclient import TestClient
    from api.main import app

    _created_record = {
        "id": "mcp_server:abc123",
        "name": "TestServer",
        "url": "http://127.0.0.1:8742/mcp",
        "enabled": True,
    }

    async def _fake_repo_query(q, params=None):
        return []

    async def _fake_repo_create(table, data):
        # Simulate SurrealDB returning the inserted record dict.
        return {**data, "id": "mcp_server:abc123"}

    # Patch at the source so the router's lazy import picks it up.
    import open_notebook.database.repository as _repo

    monkeypatch.setattr(_repo, "repo_query", _fake_repo_query)
    monkeypatch.setattr(_repo, "repo_create", _fake_repo_create)

    client = TestClient(app)

    # List — empty
    r_list = client.get("/api/mcp")
    assert r_list.status_code == 200
    assert r_list.json() == []

    # Create
    payload = {"name": "TestServer", "url": "http://127.0.0.1:8742/mcp", "enabled": True}
    r_create = client.post("/api/mcp", json=payload)
    assert r_create.status_code == 201, r_create.text
    body = r_create.json()
    assert body["name"] == "TestServer"
    assert "id" in body


def test_mcp_router_duplicate_name_409(monkeypatch):
    """POST /api/mcp with a duplicate name must return 409, not 500.

    The mcp_server_name_unique index in Migration 17 raises an exception
    whose message contains 'unique'. The router must catch that and raise
    HTTPException(409)."""
    from fastapi.testclient import TestClient
    from api.main import app

    async def _dup_repo_create(table, data):
        raise RuntimeError("Database error: unique index constraint violated")

    import open_notebook.database.repository as _repo

    monkeypatch.setattr(_repo, "repo_create", _dup_repo_create)

    client = TestClient(app)
    payload = {"name": "Dup", "url": "http://127.0.0.1:8742/mcp", "enabled": True}
    r = client.post("/api/mcp", json=payload)
    assert r.status_code == 409, r.text
    assert "already exists" in r.json()["detail"]


# ---------------------------------------------------------------------------
# v0.8.1 Item 5 — priority field + PATCH endpoint
# ---------------------------------------------------------------------------


def test_list_enabled_servers_sorts_by_priority(monkeypatch):
    """`list_enabled_servers()` returns rows sorted by priority ASC, then
    created ASC. Out-of-order rows from the DB are reordered by the SQL
    ORDER BY clause (tested by verifying the actual SELECT string the
    function passes to repo_query, plus the returned ordering).

    We provide rows already pre-ordered by the mock (mimicking SurrealDB's
    ORDER BY) to confirm that the Python-layer filter doesn't break it.
    The SQL clause is the source of truth; the integration test for a live
    DB is handled by the migration + manual QA."""
    from open_notebook.mcp.registry import list_enabled_servers

    # Rows as SurrealDB would return them after ORDER BY priority, created:
    # priority 10 → 50 → 100
    ordered_rows = [
        {"id": "mcp_server:3", "name": "FastOne",
         "url": "http://a/mcp", "enabled": True, "priority": 10,
         "created": "2026-01-01T00:00:00Z"},
        {"id": "mcp_server:1", "name": "MidOne",
         "url": "http://b/mcp", "enabled": True, "priority": 50,
         "created": "2026-01-02T00:00:00Z"},
        {"id": "mcp_server:2", "name": "SlowOne",
         "url": "http://c/mcp", "enabled": True, "priority": 100,
         "created": "2026-01-03T00:00:00Z"},
    ]

    async def _fake_repo_query(q, params=None):
        # Verify the query includes the ORDER BY clause.
        assert "ORDER BY priority ASC, created ASC" in q, (
            f"Expected ORDER BY in query but got: {q!r}"
        )
        return ordered_rows

    monkeypatch.setattr(
        "open_notebook.database.repository.repo_query",
        _fake_repo_query,
    )
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        servers = loop.run_until_complete(list_enabled_servers())
    finally:
        loop.close()

    assert len(servers) == 3
    assert servers[0]["name"] == "FastOne"
    assert servers[1]["name"] == "MidOne"
    assert servers[2]["name"] == "SlowOne"


def test_patch_mcp_server_updates_priority(monkeypatch):
    """PATCH /api/mcp/{id} with {priority: 5} must call repo_update with
    the correct arguments and return the updated record."""
    from fastapi.testclient import TestClient
    from api.main import app

    _updated = {"id": "mcp_server:p1", "name": "PriorityServer",
                "url": "http://x/mcp", "enabled": True, "priority": 5}

    async def _fake_repo_update(table, id_, data):
        assert table == "mcp_server"
        assert "priority" in data
        assert data["priority"] == 5
        return [_updated]

    import open_notebook.database.repository as _repo
    monkeypatch.setattr(_repo, "repo_update", _fake_repo_update)

    client = TestClient(app)
    r = client.patch("/api/mcp/mcp_server:p1", json={"priority": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["priority"] == 5


def test_patch_mcp_server_rejects_empty_body(monkeypatch):
    """PATCH /api/mcp/{id} with an empty body {} must return 400."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    r = client.patch("/api/mcp/mcp_server:x1", json={})
    assert r.status_code == 400, r.text
    assert "No fields to update" in r.json()["detail"]


# ---------------------------------------------------------------------------
# v0.8.1 Item 3 — _resolve_chat_tools captures accumulator
# ---------------------------------------------------------------------------


def test_resolve_chat_tools_captures_calls(monkeypatch):
    """When captures is provided, mcp_search appends one record per call
    with correct index, name, args, and text."""
    from open_notebook.graphs.chat import _resolve_chat_tools
    import asyncio

    # call_tool is an instance method — monkeypatching the class requires
    # the replacement to accept `self` as the first positional argument.
    async def fake_call_tool(self, name, args):
        return {"text": "fake search result"}

    monkeypatch.setattr(
        "open_notebook.mcp.client.MCPClient.call_tool",
        fake_call_tool,
    )

    captures: list = []
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(
            _resolve_chat_tools(
                force_servers=[{"id": "mcp_server:1", "name": "test",
                                "url": "http://x", "enabled": True}],
                captures=captures,
            )
        )
        # Invoke the mcp_search coroutine directly
        mcp_search = next(t for t in tools if t.name == "mcp_search")
        loop.run_until_complete(mcp_search.coroutine("test query"))
    finally:
        loop.close()

    assert len(captures) == 1
    assert captures[0]["index"] == 1
    assert captures[0]["name"] == "web_search"
    assert captures[0]["args"] == {"query": "test query"}
    assert captures[0]["text"] == "fake search result"


def test_resolve_chat_tools_increments_index_across_calls(monkeypatch):
    """Calling mcp_search twice yields index 1 then 2 in captures."""
    from open_notebook.graphs.chat import _resolve_chat_tools
    import asyncio

    async def fake_call_tool(self, name, args):
        return {"text": "result"}

    monkeypatch.setattr(
        "open_notebook.mcp.client.MCPClient.call_tool",
        fake_call_tool,
    )

    captures: list = []
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(
            _resolve_chat_tools(
                force_servers=[{"id": "mcp_server:1", "name": "test",
                                "url": "http://x", "enabled": True}],
                captures=captures,
            )
        )
        mcp_search = next(t for t in tools if t.name == "mcp_search")
        loop.run_until_complete(mcp_search.coroutine("first query"))
        loop.run_until_complete(mcp_search.coroutine("second query"))
    finally:
        loop.close()

    assert len(captures) == 2
    assert captures[0]["index"] == 1
    assert captures[1]["index"] == 2


def test_resolve_chat_tools_truncates_long_text(monkeypatch):
    """Text longer than 4000 chars is truncated to exactly 4000 chars."""
    from open_notebook.graphs.chat import _resolve_chat_tools
    import asyncio

    long_text = "x" * 10000

    async def fake_call_tool(self, name, args):
        return {"text": long_text}

    monkeypatch.setattr(
        "open_notebook.mcp.client.MCPClient.call_tool",
        fake_call_tool,
    )

    captures: list = []
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(
            _resolve_chat_tools(
                force_servers=[{"id": "mcp_server:1", "name": "test",
                                "url": "http://x", "enabled": True}],
                captures=captures,
            )
        )
        mcp_search = next(t for t in tools if t.name == "mcp_search")
        loop.run_until_complete(mcp_search.coroutine("any query"))
    finally:
        loop.close()

    assert len(captures) == 1
    assert len(captures[0]["text"]) == 4000


# ---------------------------------------------------------------------------
# v0.8.9 CRITICAL — chat graph in-node tool execution loop
# ---------------------------------------------------------------------------


def test_call_model_with_messages_executes_mcp_tool_calls(monkeypatch):
    """v0.8.9 — pre-fix, the chat graph was START → agent → END with no
    ToolNode. `bind_tools(mcp_tools)` exposed the tools to the LLM but
    nothing actually executed any `tool_calls` the LLM emitted. So the
    v0.8.1 Item 3 mcp_captures accumulator was always empty, [mcp:N]
    pill markers in the LLM text were hallucinated, and citation pill
    popovers always showed the placeholder. This test pins the in-node
    tool execution loop: when the model emits a tool_call, the node
    must (a) invoke the matching tool, (b) feed the result back as a
    ToolMessage, (c) re-invoke the model, (d) populate mcp_captures
    with the executed call's payload."""
    import asyncio
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage

    # Mock MCP server registry → one enabled server
    async def fake_list():
        return [{"id": "mcp_server:1", "name": "test",
                 "url": "http://x", "enabled": True}]
    monkeypatch.setattr(
        "open_notebook.mcp.registry.list_enabled_servers",
        fake_list,
    )

    # Mock MCPClient.call_tool → deterministic result
    async def fake_call_tool(self, name, args):
        return {"text": f"executed {name} with {args}"}
    monkeypatch.setattr(
        "open_notebook.mcp.client.MCPClient.call_tool",
        fake_call_tool,
    )

    # Fake model: first ainvoke returns an AIMessage with a tool_call,
    # second ainvoke returns a plain AIMessage with the final answer.
    call_count = {"n": 0}
    captured_payloads: list[list] = []

    async def fake_ainvoke(payload):
        captured_payloads.append(list(payload))
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call → emit a tool_call for mcp_search
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "mcp_search",
                    "args": {"query": "test query"},
                    "id": "call_abc",
                }],
            )
        # Second call (after tool result fed back) → final answer
        return AIMessage(
            content="Found the answer based on the search [mcp:1].",
        )

    fake_model = MagicMock()
    fake_model.ainvoke = fake_ainvoke
    fake_model.bind_tools = lambda tools: fake_model  # passthrough

    # Stub the provision so the node uses our fake model
    import open_notebook.graphs.chat as chat_mod
    async def fake_provision(content, model_id, default_type, **kw):
        return fake_model
    monkeypatch.setattr(chat_mod, "provision_langchain_model", fake_provision)

    # Run the node
    from langchain_core.messages import HumanMessage
    state = {
        "messages": [HumanMessage(content="search for something")],
        "notebook": None,
        "context": None,
        "context_config": None,
        "model_override": "model:test",   # bypass smart router for clean test
        "selected_provider": None,
        "selected_model_id": None,
        "mcp_tool_calls": None,
    }
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            chat_mod.call_model_with_messages(state, {"configurable": {}})
        )
    finally:
        loop.close()

    # Model must have been invoked TWICE — once to get the tool_call,
    # once with the tool result fed back.
    assert call_count["n"] == 2, (
        f"v0.8.9: model.ainvoke should run twice (tool_call → tool result "
        f"→ final answer); ran {call_count['n']} time(s). Tool loop is broken."
    )

    # mcp_captures (returned as mcp_tool_calls) must be populated.
    captures = result.get("mcp_tool_calls")
    assert captures is not None and len(captures) == 1, (
        f"v0.8.9: mcp_tool_calls must contain the executed call; got {captures!r}. "
        f"This means the tool closure never fired — chat graph isn't executing "
        f"tools despite the bind_tools call."
    )
    assert captures[0]["name"] == "web_search"  # _search calls call_tool("web_search", ...)
    assert captures[0]["args"] == {"query": "test query"}
    assert "executed web_search" in captures[0]["text"]

    # The second model invocation must have seen a ToolMessage in the payload.
    from langchain_core.messages import ToolMessage
    second_payload = captured_payloads[1]
    tool_msgs = [m for m in second_payload if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1, (
        f"v0.8.9: second model.ainvoke payload must include a ToolMessage "
        f"with the tool result; got {[type(m).__name__ for m in second_payload]}"
    )
    assert tool_msgs[0].tool_call_id == "call_abc"


def test_call_model_bounds_tool_loop_iterations(monkeypatch):
    """v0.8.9 — runaway protection. If the model keeps emitting
    tool_calls forever (broken prompt, faulty fine-tune, etc.), the
    loop must terminate at MAX_TOOL_ITERATIONS instead of infinite-
    looping the API. Pin the bound at <=4 model invocations."""
    import asyncio
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage, HumanMessage

    async def fake_list():
        return [{"id": "mcp_server:1", "name": "test",
                 "url": "http://x", "enabled": True}]
    monkeypatch.setattr(
        "open_notebook.mcp.registry.list_enabled_servers",
        fake_list,
    )

    async def fake_call_tool(self, name, args):
        return {"text": "result"}
    monkeypatch.setattr(
        "open_notebook.mcp.client.MCPClient.call_tool",
        fake_call_tool,
    )

    call_count = {"n": 0}

    async def fake_ainvoke(payload):
        call_count["n"] += 1
        # ALWAYS emit a tool_call → would loop forever without the bound
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "mcp_search",
                "args": {"query": f"iter{call_count['n']}"},
                "id": f"call_{call_count['n']}",
            }],
        )

    fake_model = MagicMock()
    fake_model.ainvoke = fake_ainvoke
    fake_model.bind_tools = lambda tools: fake_model

    import open_notebook.graphs.chat as chat_mod
    async def fake_provision(content, model_id, default_type, **kw):
        return fake_model
    monkeypatch.setattr(chat_mod, "provision_langchain_model", fake_provision)

    state = {
        "messages": [HumanMessage(content="loop")],
        "notebook": None, "context": None, "context_config": None,
        "model_override": "model:test",
        "selected_provider": None, "selected_model_id": None,
        "mcp_tool_calls": None,
    }
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            chat_mod.call_model_with_messages(state, {"configurable": {}})
        )
    finally:
        loop.close()

    # 1 initial + up to MAX_TOOL_ITERATIONS=4 re-invocations = 5 max.
    # Test that the bound holds and we don't keep spinning forever.
    assert call_count["n"] <= 5, (
        f"v0.8.9: tool loop must terminate at MAX_TOOL_ITERATIONS; "
        f"got {call_count['n']} model invocations (runaway)"
    )
