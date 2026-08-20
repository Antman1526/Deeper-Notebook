# Local-First MCP-Enabled Chat Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every local model (chat, embed, STT, TTS, memory) end-to-end verified-working through the chat UI, and let those local models reach the internet through MCP servers — better than NotebookLM because every byte stays on the user's drive by default, with cloud-model fallback as opt-in rather than required.

**Architecture:** Three concentric loops:
1. **Health loop** — every local sidecar (llama-cpp chat/embed, whisper, piper, memory, openchronicle MCP) gets an active `/health` probe that the API aggregates into `/api/local-models/health`. The frontend renders per-model badges in the chat composer ("● Hermes-3 32k") so users see at a glance what's working.
2. **Chat tool loop** — the chat LangGraph node is taught two new tool calls (`mcp_search`, `mcp_fetch`) that route through a generic MCP-server registry. The LLM decides when to call them; results are stitched back into the response with citation markers.
3. **Routing loop** — the API's `provision_langchain_model` gains a smart-router shim: if the user has a healthy local chat model AND the request fits its context window AND `default_chat_model` is local, use local; otherwise fall back to the configured cloud credential.

**Tech Stack:** Existing — FastAPI + LangGraph + SurrealDB + PyWebView + Next.js. New deps: `mcp>=1.0` (already pinned v0.7.197), `tenacity` (already transitive), `duckduckgo-search` for the default web-search MCP server.

---

## File Structure

This plan touches a lot of files but each task is bounded. Group by phase.

### Phase 1: Local-model health verification
- **New:** `open_notebook/health/__init__.py`, `open_notebook/health/local_models.py` — module with one `probe_local_model(name, base_url)` per service that does an active liveness check (not just TCP).
- **New:** `api/routers/local_models.py` — exposes `GET /api/local-models/health` and `GET /api/local-models/test-roundtrip`.
- **New:** `frontend/src/lib/hooks/use-local-models.ts` — TanStack Query hook.
- **New:** `frontend/src/components/chat/LocalModelHealthBadges.tsx` — sidebar component rendering one badge per model with traffic-light status.
- **Modify:** `desktop/app.py` — call the health module once at the end of `_phase_auto_register` so the splash log shows the verification.
- **New tests:** `tests/test_phase1_local_model_health.py`.

### Phase 2: MCP integration in chat graph
- **New:** `open_notebook/mcp/__init__.py`, `open_notebook/mcp/client.py`, `open_notebook/mcp/registry.py` — generic MCP client with per-server connection pool + tool discovery.
- **Modify:** `open_notebook/graphs/chat.py` — register `mcp_search` and `mcp_fetch` as LangChain tools the model can call.
- **Modify:** `open_notebook/domain/credential.py` — add `MCPServer` record model (NOT a credential since it has no API key in the typical case).
- **New:** `api/routers/mcp.py` — CRUD endpoints for MCP server registration + `POST /api/mcp/{server_id}/test`.
- **Migration:** `migrations/NN_mcp_server.surql` — `DEFINE TABLE mcp_server` + minimal schema.
- **New:** `frontend/src/app/(dashboard)/settings/mcp/page.tsx` — Settings page to register MCP servers.
- **New:** `frontend/src/lib/hooks/use-mcp-servers.ts`.
- **New tests:** `tests/test_phase2_mcp_integration.py`.

### Phase 3: Smart routing local-vs-cloud
- **Modify:** `open_notebook/ai/provision.py` — wrap `provision_langchain_model()` so it picks local when healthy + small enough; falls back to cloud transparently.
- **Modify:** `frontend/src/components/common/ModelSelector.tsx` — show "Auto" option that respects the router decision.
- **New:** `open_notebook/ai/router.py` — pure function `pick_provider(content_tokens, model_health, defaults) -> ModelChoice`.
- **New tests:** `tests/test_phase3_smart_routing.py`.

### Phase 4: Citation markers + provenance
- **Modify:** `open_notebook/graphs/chat.py` write_response node — instruct the LLM to emit `[mcp:1]` / `[source:2]` citations.
- **Modify:** `frontend/src/components/source/ChatPanel.tsx` — render citations as clickable pills that expand into the MCP-pulled snippet or the source full-text excerpt.
- **New tests:** `tests/test_phase4_citation_rendering.py`.

Total: ~7 new files, ~6 modified, 1 SurrealDB migration, 4 test files.

---

## Bite-Sized Task Granularity

Each step is ≤5 minutes. TDD throughout: write the failing test, run it (verify the failure mode is what we expect), implement, run again, commit.

---

## Phase 1: Local-model health verification

### Task 1: Health probe module skeleton

**Files:**
- Create: `open_notebook/health/__init__.py` (empty)
- Create: `open_notebook/health/local_models.py`
- Test: `tests/test_phase1_local_model_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase1_local_model_health.py
"""Phase 1 — Local-model health module produces a structured
report the API can serve to the frontend."""

from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest


def test_probe_local_model_returns_unknown_for_zero_port():
    """A port of 0 means the supervisor never spawned this service;
    health must surface that as `status='not_configured'` rather
    than raising or returning a misleading 'down'."""
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="whisper",
        kind="openai_compatible",
        base_url="http://127.0.0.1:0/v1",
    )
    assert result["status"] == "not_configured"
    assert result["name"] == "whisper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase1_local_model_health.py::test_probe_local_model_returns_unknown_for_zero_port -v`
Expected: `ModuleNotFoundError: No module named 'open_notebook.health'`

- [ ] **Step 3: Implement minimum to pass**

```python
# open_notebook/health/local_models.py
"""Phase 1 — Active health probes for each local-model sidecar.

Distinct from /healthz/deep (which is the API's own readiness):
this module probes the local llama-cpp / whisper / piper / memory
shims to verify they actually respond, not just that their port
is bound.
"""

from __future__ import annotations
from typing import Literal, TypedDict


class HealthResult(TypedDict):
    name: str
    status: Literal["healthy", "unhealthy", "not_configured", "unknown"]
    detail: str | None
    latency_ms: float | None


def probe_local_model(
    *,
    name: str,
    kind: str,
    base_url: str,
) -> HealthResult:
    """Probe a single local sidecar. Returns a HealthResult dict.

    Phase 1 — only returns `not_configured` when the URL is
    clearly a placeholder (port 0). Future tasks add live HTTP probes.
    """
    if ":0/" in base_url or base_url.endswith(":0"):
        return {
            "name": name,
            "status": "not_configured",
            "detail": "port not allocated this session",
            "latency_ms": None,
        }
    return {
        "name": name,
        "status": "unknown",
        "detail": "no probe implemented yet",
        "latency_ms": None,
    }
```

```python
# open_notebook/health/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase1_local_model_health.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add open_notebook/health/ tests/test_phase1_local_model_health.py
git commit -m "Phase 1 task 1: skeleton local-model health probe module"
```

### Task 2: Active probe for openai_compatible kind

**Files:**
- Modify: `open_notebook/health/local_models.py`
- Test: `tests/test_phase1_local_model_health.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_phase1_local_model_health.py`:

```python
def test_probe_openai_compatible_healthy(httpx_mock):
    """A live llama-cpp server returns 200 on /models; probe
    must report status='healthy' with measured latency."""
    httpx_mock.add_response(
        url="http://127.0.0.1:5000/v1/models",
        json={"object": "list", "data": [{"id": "Hermes-3"}]},
    )
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="local_chat",
        kind="openai_compatible",
        base_url="http://127.0.0.1:5000/v1",
    )
    assert result["status"] == "healthy"
    assert result["latency_ms"] is not None
    assert "Hermes-3" in (result["detail"] or "")


def test_probe_openai_compatible_unhealthy_connect_refused():
    """When the port is closed (ConnectionRefused), probe must
    report status='unhealthy' with a connection-refused detail."""
    from open_notebook.health.local_models import probe_local_model

    # Use a port that's definitely unbound on the test runner.
    result = probe_local_model(
        name="local_chat",
        kind="openai_compatible",
        base_url="http://127.0.0.1:1/v1",
    )
    assert result["status"] == "unhealthy"
    assert "connect" in (result["detail"] or "").lower()
```

(Requires `pytest-httpx` — already in dev deps.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_phase1_local_model_health.py -v`
Expected: both new tests FAIL — the `unknown` placeholder returns instead of active probe.

- [ ] **Step 3: Implement active probe**

Replace `probe_local_model` body:

```python
import time
import httpx


_PROBE_TIMEOUT = httpx.Timeout(
    connect=2.0,
    read=5.0,
    write=2.0,
    pool=2.0,
)


def probe_local_model(
    *,
    name: str,
    kind: str,
    base_url: str,
) -> HealthResult:
    if ":0/" in base_url or base_url.endswith(":0"):
        return {
            "name": name,
            "status": "not_configured",
            "detail": "port not allocated this session",
            "latency_ms": None,
        }
    if kind == "openai_compatible":
        return _probe_openai_compatible(name=name, base_url=base_url)
    return {
        "name": name,
        "status": "unknown",
        "detail": f"no probe for kind={kind!r}",
        "latency_ms": None,
    }


def _probe_openai_compatible(*, name: str, base_url: str) -> HealthResult:
    url = f"{base_url.rstrip('/')}/models"
    start = time.monotonic()
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
            resp = client.get(url)
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "?") for m in data.get("data", [])]
                detail = ", ".join(models[:3]) if models else "no models listed"
                return {
                    "name": name,
                    "status": "healthy",
                    "detail": detail,
                    "latency_ms": latency_ms,
                }
            return {
                "name": name,
                "status": "unhealthy",
                "detail": f"HTTP {resp.status_code}",
                "latency_ms": latency_ms,
            }
    except httpx.ConnectError as exc:
        return {
            "name": name,
            "status": "unhealthy",
            "detail": f"connect refused: {exc}",
            "latency_ms": None,
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "unhealthy",
            "detail": f"{type(exc).__name__}: {exc}",
            "latency_ms": None,
        }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_phase1_local_model_health.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add open_notebook/health/local_models.py tests/test_phase1_local_model_health.py
git commit -m "Phase 1 task 2: openai_compatible active health probe"
```

### Task 3: Aggregation across all local sidecars + API endpoint

**Files:**
- Modify: `open_notebook/health/local_models.py` — add `probe_all_local_models(credentials)`
- Create: `api/routers/local_models.py`
- Modify: `api/main.py` — register router
- Test: extend `tests/test_phase1_local_model_health.py`

- [ ] **Step 1: Write the failing test**

```python
def test_probe_all_iterates_credentials():
    """Given a list of (name, kind, base_url) tuples, probe_all
    returns one HealthResult per tuple in input order."""
    from open_notebook.health.local_models import probe_all_local_models

    creds = [
        {
            "name": "chat",
            "kind": "openai_compatible",
            "base_url": "http://127.0.0.1:0/v1",
        },
        {
            "name": "embed",
            "kind": "openai_compatible",
            "base_url": "http://127.0.0.1:0/v1",
        },
    ]
    results = probe_all_local_models(creds)
    assert len(results) == 2
    assert [r["name"] for r in results] == ["chat", "embed"]
    assert all(r["status"] == "not_configured" for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase1_local_model_health.py::test_probe_all_iterates_credentials -v`
Expected: `AttributeError: module 'open_notebook.health.local_models' has no attribute 'probe_all_local_models'`

- [ ] **Step 3: Implement**

Append to `open_notebook/health/local_models.py`:

```python
def probe_all_local_models(credentials: list[dict]) -> list[HealthResult]:
    """Probe every local-sidecar credential. Sequential probes
    (each is ≤5s by timeout); for the typical 4-5 local sidecars
    this is 20-25s worst case. Concurrent probes could be a
    follow-up optimization."""
    out: list[HealthResult] = []
    for cred in credentials:
        out.append(
            probe_local_model(
                name=cred["name"],
                kind=cred["kind"],
                base_url=cred["base_url"],
            )
        )
    return out
```

- [ ] **Step 4: Test the router**

Add to `tests/test_phase1_local_model_health.py`:

```python
def test_router_returns_health_payload(monkeypatch):
    """GET /api/local-models/health returns the aggregated list."""
    from fastapi.testclient import TestClient
    from api.main import app

    # Stub the probe to avoid real HTTP.
    from open_notebook.health import local_models as hm

    monkeypatch.setattr(
        hm,
        "probe_all_local_models",
        lambda creds: [
            {"name": "chat", "status": "healthy", "detail": "ok", "latency_ms": 12.3}
        ],
    )
    # Stub the credential fetch (in-test we don't have SurrealDB).
    from api.routers import local_models as router_mod

    monkeypatch.setattr(
        router_mod,
        "_load_local_credentials",
        lambda: [
            {
                "name": "chat",
                "kind": "openai_compatible",
                "base_url": "http://127.0.0.1:1234/v1",
            }
        ],
    )
    client = TestClient(app)
    r = client.get("/api/local-models/health")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] in {"healthy", "degraded", "down"}
    assert body["models"][0]["name"] == "chat"
```

- [ ] **Step 5: Implement router**

```python
# api/routers/local_models.py
"""Phase 1 — local-model health endpoint."""

from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()


def _load_local_credentials() -> list[dict]:
    """Fetch credentials whose `provider == 'openai_compatible'`
    and whose `base_url` is a 127.0.0.1 URL (i.e., local sidecar)."""
    # Lazy import to keep test stubability easy.
    from open_notebook.domain.credential import Credential

    async def _fetch():
        creds = await Credential.get_all()
        return [
            {
                "name": c.name,
                "kind": c.provider,
                "base_url": c.base_url or "",
            }
            for c in creds
            if c.provider == "openai_compatible"
            and (c.base_url or "").startswith("http://127.0.0.1")
        ]

    import asyncio

    return asyncio.get_event_loop().run_until_complete(_fetch())


@router.get("/api/local-models/health")
def local_models_health():
    from open_notebook.health.local_models import probe_all_local_models

    creds = _load_local_credentials()
    results = probe_all_local_models(creds)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    total_configured = sum(1 for r in results if r["status"] != "not_configured")
    if total_configured == 0:
        overall = "down"
    elif healthy == total_configured:
        overall = "healthy"
    else:
        overall = "degraded"
    return {"overall": overall, "models": results}
```

```python
# api/main.py — add after other router registrations
from api.routers import local_models as _local_models_router

app.include_router(_local_models_router.router, tags=["health"])
```

Also add `/api/local-models/health` to `PasswordAuthMiddleware.excluded_paths` so the splash can hit it pre-auth.

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_phase1_local_model_health.py -v`
Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add open_notebook/health/local_models.py api/routers/local_models.py api/main.py tests/test_phase1_local_model_health.py
git commit -m "Phase 1 task 3: aggregate health endpoint + auth exclusion"
```

### Task 4: Frontend hook + sidebar badges

**Files:**
- Create: `frontend/src/lib/hooks/use-local-models.ts`
- Create: `frontend/src/components/chat/LocalModelHealthBadges.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx` — render badges above the version footer
- Test: `frontend/src/components/chat/LocalModelHealthBadges.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/chat/LocalModelHealthBadges.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LocalModelHealthBadges } from './LocalModelHealthBadges'

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => ({
    data: {
      overall: 'healthy',
      models: [
        { name: 'Local GGUF', status: 'healthy', detail: 'Hermes-3', latency_ms: 12 },
        { name: 'Local Embeddings', status: 'healthy', detail: 'nomic-embed', latency_ms: 8 },
      ],
    },
    isLoading: false,
  }),
}))

const qc = new QueryClient()

describe('LocalModelHealthBadges', () => {
  it('renders one badge per model with status colour', () => {
    render(
      <QueryClientProvider client={qc}>
        <LocalModelHealthBadges />
      </QueryClientProvider>
    )
    expect(screen.getByText(/Local GGUF/)).toBeInTheDocument()
    expect(screen.getByText(/Local Embeddings/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/chat/LocalModelHealthBadges.test.tsx`
Expected: import-resolution failure on `./LocalModelHealthBadges`.

- [ ] **Step 3: Implement the hook**

```typescript
// frontend/src/lib/hooks/use-local-models.ts
import { useQuery } from '@tanstack/react-query'
import apiClient from '@/lib/api/client'

export interface LocalModelHealth {
  name: string
  status: 'healthy' | 'unhealthy' | 'not_configured' | 'unknown'
  detail: string | null
  latency_ms: number | null
}

export interface LocalModelsHealthPayload {
  overall: 'healthy' | 'degraded' | 'down'
  models: LocalModelHealth[]
}

export function useLocalModelsHealth() {
  return useQuery<LocalModelsHealthPayload>({
    queryKey: ['local-models', 'health'],
    queryFn: async () => {
      const r = await apiClient.get('/local-models/health')
      return r.data
    },
    refetchInterval: 30_000,    // poll every 30s
    refetchOnWindowFocus: true,
  })
}
```

- [ ] **Step 4: Implement the badge component**

```typescript
// frontend/src/components/chat/LocalModelHealthBadges.tsx
'use client'
import { useLocalModelsHealth } from '@/lib/hooks/use-local-models'

const STATUS_DOT: Record<string, string> = {
  healthy: 'bg-emerald-500',
  unhealthy: 'bg-rose-500',
  not_configured: 'bg-muted-foreground/40',
  unknown: 'bg-amber-500',
}

export function LocalModelHealthBadges() {
  const { data, isLoading } = useLocalModelsHealth()
  if (isLoading || !data) return null
  return (
    <div className="space-y-1 text-[10px]">
      {data.models.map((m) => (
        <div key={m.name} className="flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full ${STATUS_DOT[m.status]}`}
            title={`${m.status}: ${m.detail ?? ''}`}
          />
          <span className="truncate text-muted-foreground">{m.name}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Wire into AppSidebar (above the version badge)**

In `AppSidebar.tsx`, just above the `{!isCollapsed && (` version-badge div, add:

```tsx
import { LocalModelHealthBadges } from '@/components/chat/LocalModelHealthBadges'

// ... inside the footer block, above the version badge:
{!isCollapsed && (
  <div className="mt-2">
    <LocalModelHealthBadges />
  </div>
)}
```

- [ ] **Step 6: Run test + frontend type check**

Run: `cd frontend && npm test -- --run src/components/chat/LocalModelHealthBadges.test.tsx`
Expected: PASS.
Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/hooks/use-local-models.ts frontend/src/components/chat/LocalModelHealthBadges.tsx frontend/src/components/chat/LocalModelHealthBadges.test.tsx frontend/src/components/layout/AppSidebar.tsx
git commit -m "Phase 1 task 4: frontend health badges in sidebar"
```

### Task 5: Phase 1 closeout — auto-probe at startup + commit

**Files:**
- Modify: `desktop/app.py` — call probe-all once at end of `_phase_auto_register`
- Modify: `desktop/CHANGELOG.md` — Phase 1 entry

- [ ] **Step 1: Add the startup probe**

In `desktop/app.py:_phase_auto_register`, after the existing auto-register block, add:

```python
# Phase 1 — Active probe each local sidecar so the launcher.log
# captures actual health (not just port-bind success). The
# frontend's /api/local-models/health endpoint re-runs these on
# demand from the badge component.
try:
    from open_notebook.health.local_models import (
        probe_all_local_models,
    )

    creds_for_probe = []
    if getattr(sv, "chat_llm_port", 0):
        creds_for_probe.append(
            {
                "name": "Local GGUF (llama.cpp)",
                "kind": "openai_compatible",
                "base_url": f"http://127.0.0.1:{sv.chat_llm_port}/v1",
            }
        )
    if getattr(sv, "embed_port", 0):
        creds_for_probe.append(
            {
                "name": "Local Embeddings (llama.cpp)",
                "kind": "openai_compatible",
                "base_url": f"http://127.0.0.1:{sv.embed_port}/v1",
            }
        )
    if creds_for_probe:
        results = probe_all_local_models(creds_for_probe)
        for r in results:
            log.info(
                "phase1.health %s: %s (%s, %.0fms)",
                r["name"],
                r["status"],
                r["detail"],
                r.get("latency_ms") or 0,
            )
except Exception as exc:
    log.warning("phase1.health probe failed (non-fatal): %s", exc)
```

- [ ] **Step 2: Commit Phase 1 + bump CHANGELOG**

```bash
git add desktop/app.py desktop/CHANGELOG.md
git commit -m "Phase 1 closeout: startup health probe + sidebar badges + /api/local-models/health"
```

---

## Phase 2: MCP integration in chat graph

### Task 6: MCP client skeleton + tool listing

**Files:**
- Create: `open_notebook/mcp/__init__.py` (empty)
- Create: `open_notebook/mcp/client.py`
- Test: `tests/test_phase2_mcp_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase2_mcp_integration.py
"""Phase 2 — MCP server client + chat-graph integration."""

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
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def list_tools(self):
            return type(
                "X",
                (),
                {
                    "tools": [
                        type(
                            "T",
                            (),
                            {"name": t["name"], "description": t["description"]},
                        )()
                        for t in fake_tools
                    ]
                },
            )()

    monkeypatch.setattr(
        "open_notebook.mcp.client._open_session",
        lambda url: FakeSession(),
    )
    client = MCPClient(url="http://127.0.0.1:8742/mcp")
    import asyncio

    names = asyncio.get_event_loop().run_until_complete(client.list_tool_names())
    assert names == ["web_search", "fetch_url"]
```

- [ ] **Step 2: Run test (failing)**

Run: `uv run pytest tests/test_phase2_mcp_integration.py -v`
Expected: `ModuleNotFoundError: No module named 'open_notebook.mcp.client'`.

- [ ] **Step 3: Implement**

```python
# open_notebook/mcp/client.py
"""Phase 2 — Generic MCP client wrapper.

Wraps `mcp.client.streamable_http.streamablehttp_client` so the
chat graph can call `await client.list_tool_names()` and
`await client.call_tool(name, args)` without dealing with the
session lifecycle directly.
"""

from __future__ import annotations
from contextlib import asynccontextmanager
from dataclasses import dataclass


@asynccontextmanager
async def _open_session(url: str):
    """Open an MCP ClientSession over streamable HTTP. Each call
    is a fresh session — MCP's streamable-http transport doesn't
    keep sessions across requests (per the openchronicle shim's
    inline comment in v0.4)."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@dataclass
class MCPClient:
    url: str

    async def list_tool_names(self) -> list[str]:
        async with _open_session(self.url) as s:
            result = await s.list_tools()
            return [t.name for t in result.tools]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        async with _open_session(self.url) as s:
            result = await s.call_tool(name, arguments=arguments)
            # MCP returns a list of content blocks; flatten to a
            # single text-or-data payload for our LLM tool-call
            # output.
            if result.content:
                first = result.content[0]
                if hasattr(first, "text"):
                    return {"ok": True, "text": first.text}
                return {"ok": True, "data": getattr(first, "data", None)}
            return {"ok": True, "text": ""}
```

- [ ] **Step 4: Run test (passing)**

Run: `uv run pytest tests/test_phase2_mcp_integration.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add open_notebook/mcp/ tests/test_phase2_mcp_integration.py
git commit -m "Phase 2 task 6: MCP client wrapper for streamable-http transport"
```

### Task 7: MCP server registry (DB-backed)

**Files:**
- Create: `open_notebook/mcp/registry.py`
- Create: `migrations/NN_mcp_server.surql` (replace NN with the next sequence number)
- Test: extend `tests/test_phase2_mcp_integration.py`

- [ ] **Step 1: Write the failing test**

```python
def test_mcp_registry_lists_enabled_servers(monkeypatch):
    """`list_enabled_servers()` returns only servers with
    `enabled=True`. Disabled servers are not used by the chat
    graph even if they're in the DB."""
    from open_notebook.mcp.registry import list_enabled_servers

    async def _fake_repo_query(q, params=None):
        return [
            {
                "id": "mcp_server:1",
                "name": "OpenChronicle",
                "url": "http://127.0.0.1:8742/mcp",
                "enabled": True,
            },
            {
                "id": "mcp_server:2",
                "name": "DuckDuckGo",
                "url": "http://127.0.0.1:8743/mcp",
                "enabled": False,
            },
        ]

    monkeypatch.setattr(
        "open_notebook.database.repository.repo_query",
        _fake_repo_query,
    )
    import asyncio

    servers = asyncio.get_event_loop().run_until_complete(list_enabled_servers())
    assert len(servers) == 1
    assert servers[0]["name"] == "OpenChronicle"
```

- [ ] **Step 2: Implement registry + migration**

```python
# open_notebook/mcp/registry.py
from __future__ import annotations


async def list_enabled_servers() -> list[dict]:
    from open_notebook.database.repository import repo_query

    rows = await repo_query(
        "SELECT id, name, url, enabled FROM mcp_server WHERE enabled = true",
    )
    return rows or []
```

```sql
-- migrations/NN_mcp_server.surql
DEFINE TABLE mcp_server SCHEMAFULL;
DEFINE FIELD name ON mcp_server TYPE string;
DEFINE FIELD url ON mcp_server TYPE string;
DEFINE FIELD enabled ON mcp_server TYPE bool DEFAULT true;
DEFINE FIELD created ON mcp_server TYPE datetime DEFAULT time::now();
DEFINE FIELD updated ON mcp_server TYPE datetime DEFAULT time::now();
DEFINE INDEX mcp_server_name_unique ON mcp_server FIELDS name UNIQUE;
```

- [ ] **Step 3: Run test + commit**

Run: `uv run pytest tests/test_phase2_mcp_integration.py -v`
Expected: PASS.

```bash
git add open_notebook/mcp/registry.py migrations/NN_mcp_server.surql tests/test_phase2_mcp_integration.py
git commit -m "Phase 2 task 7: MCP server DB registry + migration"
```

### Task 8: Chat-graph tool registration

**Files:**
- Modify: `open_notebook/graphs/chat.py` — add `mcp_search` + `mcp_fetch` tools
- Test: extend `tests/test_phase2_mcp_integration.py`

- [ ] **Step 1: Write the failing test**

```python
def test_chat_graph_exposes_mcp_tools_when_enabled(monkeypatch):
    """When at least one MCP server is enabled, the chat graph's
    tool registry must include `mcp_search` and `mcp_fetch`."""
    monkeypatch.setattr(
        "open_notebook.mcp.registry.list_enabled_servers",
        lambda: __import__("asyncio").Future(),
    )
    from open_notebook.graphs.chat import _resolve_chat_tools
    import asyncio

    tools = asyncio.get_event_loop().run_until_complete(
        _resolve_chat_tools(
            force_servers=[
                {
                    "id": "mcp_server:1",
                    "name": "test",
                    "url": "http://x",
                    "enabled": True,
                }
            ]
        )
    )
    tool_names = [t.name for t in tools]
    assert "mcp_search" in tool_names
    assert "mcp_fetch" in tool_names
```

- [ ] **Step 2: Implement `_resolve_chat_tools` + wire into chat graph**

Add to `open_notebook/graphs/chat.py`:

```python
async def _resolve_chat_tools(*, force_servers=None):
    """Return the LangChain `Tool` list for this chat invocation.

    Phase 2 — when at least one MCP server is enabled in the
    registry, expose `mcp_search` + `mcp_fetch` that route to
    the first enabled server. Future: per-server tool surfaces
    (one mcp_* function per server) for richer model decisions.
    """
    from langchain_core.tools import Tool
    from open_notebook.mcp.client import MCPClient
    from open_notebook.mcp.registry import list_enabled_servers

    servers = (
        force_servers if force_servers is not None else await list_enabled_servers()
    )
    if not servers:
        return []
    server = servers[0]
    client = MCPClient(url=server["url"])

    async def _search(query: str) -> str:
        result = await client.call_tool("web_search", {"query": query})
        return result.get("text") or "(no result)"

    async def _fetch(url: str) -> str:
        result = await client.call_tool("fetch_url", {"url": url})
        return result.get("text") or "(no result)"

    return [
        Tool(
            name="mcp_search", description="Search the web via MCP", coroutine=_search
        ),
        Tool(name="mcp_fetch", description="Fetch a URL via MCP", coroutine=_fetch),
    ]
```

Then wire into the chat node — `bind_tools(await _resolve_chat_tools())` on the LLM before the first invocation in the chat graph node.

- [ ] **Step 3: Test + commit**

Run: `uv run pytest tests/test_phase2_mcp_integration.py -v`
Expected: PASS.

```bash
git add open_notebook/graphs/chat.py tests/test_phase2_mcp_integration.py
git commit -m "Phase 2 task 8: chat-graph mcp_search + mcp_fetch tools"
```

### Task 9: `/api/mcp/*` CRUD endpoints

**Files:**
- Create: `api/routers/mcp.py`
- Modify: `api/main.py` — register router
- Test: extend `tests/test_phase2_mcp_integration.py`

- [ ] **Step 1: Write the failing test**

```python
def test_mcp_router_lists_and_creates(monkeypatch):
    """POST /api/mcp creates an enabled server row; GET /api/mcp
    returns it."""
    from fastapi.testclient import TestClient
    from api.main import app

    # In-memory stub for repo_query/upsert.
    state = {"rows": []}

    async def _q(query, params=None):
        if "SELECT" in query:
            return state["rows"]
        if "DELETE" in query:
            state["rows"] = [r for r in state["rows"] if r["id"] != params["id"]]
            return []
        return state["rows"]

    async def _u(table, data):
        data["id"] = f"mcp_server:{len(state['rows']) + 1}"
        state["rows"].append(data)
        return data

    monkeypatch.setattr(
        "open_notebook.database.repository.repo_query",
        _q,
    )
    monkeypatch.setattr(
        "open_notebook.database.repository.repo_upsert",
        _u,
    )
    client = TestClient(app)
    # Create
    r = client.post(
        "/api/mcp",
        json={
            "name": "OpenChronicle",
            "url": "http://127.0.0.1:8742/mcp",
            "enabled": True,
        },
    )
    assert r.status_code in (200, 201)
    # List
    r = client.get("/api/mcp")
    assert r.status_code == 200
    body = r.json()
    assert any(s["name"] == "OpenChronicle" for s in body)
```

- [ ] **Step 2: Implement router**

```python
# api/routers/mcp.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class MCPServerCreate(BaseModel):
    name: str
    url: str
    enabled: bool = True


@router.get("/api/mcp")
async def list_mcp_servers():
    from open_notebook.database.repository import repo_query

    rows = await repo_query("SELECT id, name, url, enabled FROM mcp_server")
    return rows or []


@router.post("/api/mcp")
async def create_mcp_server(body: MCPServerCreate):
    from open_notebook.database.repository import repo_upsert

    return await repo_upsert("mcp_server", body.model_dump())


@router.delete("/api/mcp/{server_id}")
async def delete_mcp_server(server_id: str):
    from open_notebook.database.repository import repo_query

    await repo_query("DELETE mcp_server WHERE id = $id", {"id": server_id})
    return {"ok": True}


@router.post("/api/mcp/{server_id}/test")
async def test_mcp_server(server_id: str):
    from open_notebook.database.repository import repo_query
    from open_notebook.mcp.client import MCPClient

    rows = await repo_query(
        "SELECT url FROM mcp_server WHERE id = $id LIMIT 1",
        {"id": server_id},
    )
    if not rows:
        raise HTTPException(404, "MCP server not found")
    client = MCPClient(url=rows[0]["url"])
    try:
        names = await client.list_tool_names()
        return {"ok": True, "tools": names}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
```

```python
# api/main.py — register
from api.routers import mcp as _mcp_router

app.include_router(_mcp_router.router, tags=["mcp"])
```

- [ ] **Step 3: Test + commit**

Run: `uv run pytest tests/test_phase2_mcp_integration.py -v`
Expected: all PASS.

```bash
git add api/routers/mcp.py api/main.py tests/test_phase2_mcp_integration.py
git commit -m "Phase 2 task 9: /api/mcp CRUD + test endpoints"
```

### Task 10: Settings page for MCP servers

**Files:**
- Create: `frontend/src/lib/hooks/use-mcp-servers.ts`
- Create: `frontend/src/app/(dashboard)/settings/mcp/page.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx` — add link
- Test: `frontend/src/app/(dashboard)/settings/mcp/page.test.tsx`

- [ ] **Step 1: Implement hook + page**

```typescript
// frontend/src/lib/hooks/use-mcp-servers.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/lib/api/client'

export interface MCPServer {
  id: string
  name: string
  url: string
  enabled: boolean
}

export function useMCPServers() {
  return useQuery<MCPServer[]>({
    queryKey: ['mcp', 'servers'],
    queryFn: async () => (await apiClient.get('/mcp')).data,
  })
}

export function useCreateMCPServer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<MCPServer, 'id'>) =>
      apiClient.post('/mcp', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mcp', 'servers'] }),
  })
}

export function useTestMCPServer() {
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/mcp/${id}/test`).then(r => r.data),
  })
}
```

```tsx
// frontend/src/app/(dashboard)/settings/mcp/page.tsx
'use client'
import { useState } from 'react'
import { useMCPServers, useCreateMCPServer, useTestMCPServer } from '@/lib/hooks/use-mcp-servers'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AppShell } from '@/components/layout/AppShell'

export default function MCPSettingsPage() {
  const { data: servers = [] } = useMCPServers()
  const create = useCreateMCPServer()
  const test = useTestMCPServer()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  return (
    <AppShell>
      <div className="container mx-auto p-6 max-w-2xl">
        <h1 className="text-3xl font-semibold mb-4">MCP Servers</h1>
        <p className="text-muted-foreground mb-6">
          Connect Model Context Protocol servers so the chat model
          can search the web, fetch URLs, or call any MCP tool.
        </p>
        <div className="space-y-3 mb-8">
          <Input placeholder="Server name" value={name}
                 onChange={(e) => setName(e.target.value)} />
          <Input placeholder="https://example.com/mcp" value={url}
                 onChange={(e) => setUrl(e.target.value)} />
          <Button onClick={() => {
            create.mutate({ name, url, enabled: true })
            setName(''); setUrl('')
          }} disabled={!name || !url}>
            Add server
          </Button>
        </div>
        <ul className="space-y-2">
          {servers.map(s => (
            <li key={s.id} className="flex items-center justify-between border rounded p-3">
              <div>
                <div className="font-medium">{s.name}</div>
                <div className="text-xs text-muted-foreground">{s.url}</div>
              </div>
              <Button size="sm" variant="outline"
                onClick={() => test.mutate(s.id)}>
                Test
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  )
}
```

- [ ] **Step 2: Commit Phase 2 closeout**

```bash
git add frontend/src/lib/hooks/use-mcp-servers.ts frontend/src/app/(dashboard)/settings/mcp/ frontend/src/components/layout/AppSidebar.tsx
git commit -m "Phase 2 closeout: MCP settings page + sidebar link"
```

---

## Phase 3: Smart routing local-vs-cloud

### Task 11: `pick_provider` pure function

**Files:**
- Create: `open_notebook/ai/router.py`
- Test: `tests/test_phase3_smart_routing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase3_smart_routing.py
def test_router_prefers_local_when_healthy_and_fits():
    from open_notebook.ai.router import pick_provider, ModelChoice

    choice = pick_provider(
        content_tokens=2000,
        local_chat_healthy=True,
        local_chat_n_ctx=32768,
        cloud_model_id="model:gpt-4o",
        local_model_id="model:hermes-3",
        default_provider="auto",
    )
    assert choice == ModelChoice(
        model_id="model:hermes-3",
        reason="local: healthy + fits in n_ctx",
    )


def test_router_falls_back_to_cloud_when_too_big_for_local():
    from open_notebook.ai.router import pick_provider, ModelChoice

    choice = pick_provider(
        content_tokens=50_000,
        local_chat_healthy=True,
        local_chat_n_ctx=32768,
        cloud_model_id="model:gpt-4o",
        local_model_id="model:hermes-3",
        default_provider="auto",
    )
    assert choice.model_id == "model:gpt-4o"
    assert "exceeds n_ctx" in choice.reason
```

- [ ] **Step 2: Implement**

```python
# open_notebook/ai/router.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelChoice:
    model_id: str
    reason: str


def pick_provider(
    *,
    content_tokens: int,
    local_chat_healthy: bool,
    local_chat_n_ctx: int,
    cloud_model_id: str | None,
    local_model_id: str | None,
    default_provider: str = "auto",
) -> ModelChoice:
    if default_provider == "cloud" and cloud_model_id:
        return ModelChoice(cloud_model_id, "user-forced cloud")
    if default_provider == "local" and local_model_id:
        return ModelChoice(local_model_id, "user-forced local")
    if (
        local_chat_healthy
        and local_model_id
        and content_tokens < local_chat_n_ctx - 1000
    ):
        return ModelChoice(local_model_id, "local: healthy + fits in n_ctx")
    if cloud_model_id:
        return ModelChoice(
            cloud_model_id,
            f"cloud: content {content_tokens}t exceeds n_ctx {local_chat_n_ctx}t"
            if local_chat_healthy
            else "cloud: local unavailable",
        )
    # No cloud configured — best-effort local even if too big; the
    # llama-cpp server will return its own 400 if truly oversized.
    if local_model_id:
        return ModelChoice(
            local_model_id,
            "local fallback (no cloud configured)",
        )
    raise ValueError("No model available — neither local nor cloud")
```

- [ ] **Step 3: Commit**

```bash
git add open_notebook/ai/router.py tests/test_phase3_smart_routing.py
git commit -m "Phase 3 task 11: pick_provider pure router"
```

### Task 12: Wire router into `provision_langchain_model`

**Files:**
- Modify: `open_notebook/ai/provision.py` — call `pick_provider`
- Test: extend `tests/test_phase3_smart_routing.py`

- [ ] **Step 1: Write test + implement**

Test that `provision_langchain_model(content="...", default_type="chat")` calls the router when `default_chat_model` is set to `"auto"` in DefaultModels. Implement the wiring (pull health from `/api/local-models/health` cache; fetch DefaultModels; call router; pass model_id through to existing flow).

- [ ] **Step 2: Commit Phase 3 closeout**

```bash
git commit -m "Phase 3 closeout: router wired into provision_langchain_model"
```

---

## Phase 4: Citation markers + provenance

### Task 13: System prompt teaches the LLM to cite

Modify `open_notebook/prompts/chat/system.md` (or wherever the chat system prompt lives) to instruct: "When you call mcp_search or mcp_fetch, emit `[mcp:N]` after the relevant sentence. When you reference a source from the notebook context, emit `[source:ID]`."

### Task 14: Frontend renders citations as expandable pills

Modify `ChatPanel.tsx` to post-process the streamed text, regex-match `[mcp:\d+]` and `[source:[a-z0-9]+]`, and render each as a clickable badge that expands a popover with the MCP snippet or the source-text excerpt.

### Task 15: Phase 4 tests

`tests/test_phase4_citation_rendering.py` — parse a synthetic assistant reply with both citation types and assert the resulting React component has the right number of pills with the right href targets.

---

## Phase 5: End-to-end manual verification + commit

### Task 16: Manual happy-path script

A bash script `scripts/verify-chat-platform.sh` that:
1. Curls `/api/local-models/health` and asserts `overall != "down"`.
2. Curls `/api/mcp` and asserts at least one enabled server.
3. POSTs a chat message that should trigger `mcp_search`, asserts the response contains `[mcp:1]`.
4. POSTs a chat message that fits the local n_ctx, asserts the response model is the local one.
5. POSTs a chat message that overflows local n_ctx, asserts the response model is the cloud one.

Each assertion failure echoes the failing curl + the response body so the user can debug.

### Task 17: CHANGELOG + tag

Bump to `v0.8.0` since this is a feature release (not a bugfix line). Tag the commit. Update README's "Why open-notebook-Plus over NotebookLM?" section with: (a) local-first chat, (b) MCP servers, (c) smart routing, (d) source-grounded citations, (e) full data ownership.

---

## Self-Review

Per the writing-plans skill:

1. **Spec coverage:**
   - "All local models work and produce data through chat" → Phase 1 (health) + Phase 3 (routing) + Phase 5 (e2e verify).
   - "Use/connect to MCP servers when chat needs internet data" → Phase 2 (full).
   - "Better than NotebookLM" → Phase 4 (citation provenance) + Phase 5 (README pitch).
   - "Focus on local + cloud" → Phase 3 (smart router).

2. **Placeholder scan:** Task 13/14/15 are described less fully than Tasks 1-10 because Phase 4 depends on prompt-iteration that's hard to specify until we see live results. Acceptable trade-off; the implementer will iterate within Phase 4 with the implementer subagent.

3. **Type consistency:**
   - `HealthResult` TypedDict used consistently in Python + mirrored as `LocalModelHealth` TS interface.
   - `ModelChoice` dataclass used consistently in router.
   - `MCPServer` is a plain dict in Python (registry layer) but a TS interface in frontend — boundary at the API.

If you find issues, fix them inline. No need to re-review.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-25-local-models-mcp-chat-platform.md`.** Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
