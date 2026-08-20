# Offline/Online Smart Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make open-notebook-Plus degrade gracefully offline — instant local-model fallback with UI indicators, deferred Gmail digests, web-search short-circuit — plus a persisted "Offline mode" toggle that force-disables all outbound network use.

**Architecture:** A cached network-state service (`open_notebook/health/network.py`) feeds an offline gate in the model-provisioning funnel (`provision_langchain_model`), a status endpoint, the web-search tool, and the Gmail digest scheduler. The chat graph threads fallback info to the existing `selected_provider` response plumbing; the frontend extends the existing `ChatMessageProviderBadge` and the v0.8.67q polling-banner pattern.

**Tech Stack:** Python 3.12 / FastAPI / SurrealDB RecordModel pattern / pytest; Next.js + TanStack Query + i18n locale maps.

**Spec:** `docs/superpowers/specs/2026-06-11-offline-online-switching-design.md`
**Version label for code comments / changelog:** `v0.8.68`
**Test runner:** `.venv-py312/bin/python -m pytest <file> -q` from repo root. Frontend: `pnpm test --run` from `frontend/`.

---

### Task 1: Network-state service

**Files:**
- Create: `open_notebook/health/network.py`
- Test: `tests/test_network_state.py`

- [x] **Step 1: Write the failing tests**

`tests/test_network_state.py`:

```python
"""v0.8.68 — network-state service tests. No live network: the TCP probe is
injected. Each test resets the module cache via the public reset helper."""

from __future__ import annotations

import asyncio

import pytest

from open_notebook.health import network


@pytest.fixture(autouse=True)
def _reset_state():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_online_when_probe_succeeds(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: True)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: False))
    assert state.status == "online"
    assert state.forced_offline is False


def test_offline_when_probe_fails(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: False)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: False))
    assert state.status == "offline"


def test_unknown_on_probe_exception(monkeypatch):
    def _boom():
        raise OSError("probe broke")

    monkeypatch.setattr(network, "_probe_once", _boom)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: False))
    assert state.status == "unknown"


def test_cache_hit_skips_probe(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_probe_once", lambda: calls.append(1) or True)

    async def scenario():
        await network.get_network_state(forced_offline_lookup=lambda: False)
        await network.get_network_state(forced_offline_lookup=lambda: False)

    _run(scenario())
    assert len(calls) == 1  # second call served from TTL cache


def test_report_failure_flips_state_immediately(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: True)

    async def scenario():
        first = await network.get_network_state(forced_offline_lookup=lambda: False)
        assert first.status == "online"
        network.report_network_failure()
        second = await network.get_network_state(forced_offline_lookup=lambda: False)
        return second

    state = _run(scenario())
    assert state.status == "offline"
    assert state.source == "call-failure"


def test_report_success_flips_back(monkeypatch):
    monkeypatch.setattr(network, "_probe_once", lambda: False)

    async def scenario():
        await network.get_network_state(forced_offline_lookup=lambda: False)
        network.report_network_success()
        return await network.get_network_state(forced_offline_lookup=lambda: False)

    assert _run(scenario()).status == "online"


def test_forced_offline_wins_without_probe(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_probe_once", lambda: calls.append(1) or True)
    state = _run(network.get_network_state(forced_offline_lookup=lambda: True))
    assert state.status == "offline"
    assert state.forced_offline is True
    assert calls == []  # probe never ran


def test_probe_host_env_parsing(monkeypatch):
    monkeypatch.setenv("ONP_NET_PROBE_HOSTS", "example.com:443, 10.0.0.1:8443")
    assert network._probe_targets() == [("example.com", 443), ("10.0.0.1", 8443)]


def test_probe_host_env_malformed_falls_back(monkeypatch):
    monkeypatch.setenv("ONP_NET_PROBE_HOSTS", "garbage,:,nohost:notaport")
    assert network._probe_targets() == network._DEFAULT_PROBE_TARGETS
```

- [x] **Step 2: Run tests — expect import failure**

Run: `.venv-py312/bin/python -m pytest tests/test_network_state.py -q`
Expected: errors — `ModuleNotFoundError: No module named 'open_notebook.health.network'`

- [x] **Step 3: Implement `open_notebook/health/network.py`**

```python
"""v0.8.68 — process-wide network-state service.

Answers "does this machine currently have internet?" for the offline
gate (open_notebook/ai/offline_gate.py), the web_search tool, the Gmail
digest scheduler, and GET /api/system/network-status.

Design (spec 2026-06-11):
  - 2s TCP probe to two well-known hosts (override: ONP_NET_PROBE_HOSTS),
    run via asyncio.to_thread so the event loop never blocks.
  - TTL cache (default 20s, ONP_NETWORK_STATE_TTL_SEC) with a single-flight
    lock — concurrent cache-misses share one probe (same pattern as
    provision.py's _health_cache_lock, v0.8.35).
  - Passive updates: report_network_failure()/report_network_success()
    flip the cache immediately when a real cloud call fails/succeeds —
    this also covers captive portals where the TCP probe lies.
  - "unknown" (probe exception) is treated as ONLINE by consumers: we
    never block cloud calls on a flaky probe; real failures correct it.
  - forced_offline_lookup: callers pass a callable for the user's
    Offline-mode toggle so this module has no settings/DB dependency.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from dataclasses import dataclass
from typing import Callable, Literal

from loguru import logger

_DEFAULT_PROBE_TARGETS: list[tuple[str, int]] = [("1.1.1.1", 443), ("8.8.8.8", 443)]
_PROBE_TIMEOUT_S = 2.0
_DEFAULT_TTL_S = 20.0


@dataclass(frozen=True)
class NetworkState:
    status: Literal["online", "offline", "unknown"]
    forced_offline: bool
    checked_at: float  # time.monotonic()
    source: Literal["probe", "call-failure", "call-success", "override", "init"]


_state: NetworkState | None = None
_probe_lock: "asyncio.Lock | None" = None


def _get_probe_lock() -> asyncio.Lock:
    # Lazy init — same rationale as provision.py _get_health_cache_lock:
    # imports stay side-effect-free, no event loop needed at import time.
    global _probe_lock
    if _probe_lock is None:
        _probe_lock = asyncio.Lock()
    return _probe_lock


def _ttl_s() -> float:
    try:
        v = float(os.environ.get("ONP_NETWORK_STATE_TTL_SEC") or _DEFAULT_TTL_S)
        return v if v > 0 else _DEFAULT_TTL_S
    except ValueError:
        return _DEFAULT_TTL_S


def _probe_targets() -> list[tuple[str, int]]:
    raw = (os.environ.get("ONP_NET_PROBE_HOSTS") or "").strip()
    if not raw:
        return _DEFAULT_PROBE_TARGETS
    targets: list[tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        host, _, port_s = part.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            continue
        if host and 0 < port < 65536:
            targets.append((host, port))
    return targets or _DEFAULT_PROBE_TARGETS


def _probe_once() -> bool:
    """Blocking TCP probe — first target that connects wins. Runs on a
    worker thread (see get_network_state). Raises on unexpected errors
    so the caller can map them to 'unknown'."""
    last_exc: Exception | None = None
    for host, port in _probe_targets():
        try:
            with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
                return True
        except OSError as exc:
            last_exc = exc
            continue
    if last_exc is not None and not isinstance(
        last_exc, (socket.timeout, ConnectionError, OSError)
    ):
        raise last_exc
    return False


def report_network_failure() -> None:
    """A real outbound call failed with a network-classified error."""
    global _state
    _state = NetworkState(
        status="offline",
        forced_offline=False,
        checked_at=time.monotonic(),
        source="call-failure",
    )
    logger.info("v0.8.68 network-state: flipped OFFLINE (cloud call failed)")


def report_network_success() -> None:
    """A real outbound call succeeded — we are definitely online."""
    global _state
    _state = NetworkState(
        status="online",
        forced_offline=False,
        checked_at=time.monotonic(),
        source="call-success",
    )


def reset_network_state_for_tests() -> None:
    global _state, _probe_lock
    _state = None
    _probe_lock = None


async def get_network_state(
    *,
    forced_offline_lookup: Callable[[], bool] | None = None,
) -> NetworkState:
    """Current network state. Forced-offline check first (no probe), then
    TTL cache, then a single-flight thread-side TCP probe."""
    global _state
    if forced_offline_lookup is not None:
        try:
            forced = bool(forced_offline_lookup())
        except Exception:
            forced = False  # settings hiccup must never brick cloud access
        if forced:
            return NetworkState(
                status="offline",
                forced_offline=True,
                checked_at=time.monotonic(),
                source="override",
            )

    now = time.monotonic()
    if _state is not None and now - _state.checked_at < _ttl_s():
        return _state

    async with _get_probe_lock():
        now = time.monotonic()
        if _state is not None and now - _state.checked_at < _ttl_s():
            return _state
        try:
            up = await asyncio.to_thread(_probe_once)
            status: Literal["online", "offline", "unknown"] = (
                "online" if up else "offline"
            )
        except Exception as exc:
            logger.debug(f"v0.8.68 network probe errored ({exc!r}) → unknown")
            status = "unknown"
        _state = NetworkState(
            status=status,
            forced_offline=False,
            checked_at=time.monotonic(),
            source="probe",
        )
    return _state
```

- [x] **Step 4: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_network_state.py -q`
Expected: 9 passed

- [x] **Step 5: Commit**

```bash
git add open_notebook/health/network.py tests/test_network_state.py
git commit -m "feat: v0.8.68 network-state service (probe + TTL cache + passive reports)"
```

---

### Task 2: `offline_mode` setting

**Files:**
- Modify: `open_notebook/domain/content_settings.py` (add field)
- Modify: `api/models.py` (`SettingsResponse`, `SettingsUpdate` — find both classes; they hold the five existing settings fields)
- Modify: `api/routers/settings.py` (GET + PUT wiring)
- Create helper in: `open_notebook/health/network.py` (cached settings accessor)
- Test: `tests/test_offline_mode_setting.py`

- [x] **Step 1: Add the field to ContentSettings**

In `open_notebook/domain/content_settings.py`, append to the class:

```python
    # v0.8.68 — user-forced offline mode. When true the app behaves as if
    # disconnected even when online: cloud chat falls back to the local
    # model, web search short-circuits, Gmail digests defer. Local-provider
    # models are never affected. Read via the network-state service.
    offline_mode: Optional[bool] = Field(
        False, description="Force offline: never use the internet"
    )
```

- [x] **Step 2: Add to API schemas**

In `api/models.py`, add to BOTH `SettingsResponse` and `SettingsUpdate` (locate via `grep -n "class SettingsResponse\|class SettingsUpdate" api/models.py`):

```python
    # v0.8.68 — forced offline mode toggle (spec 2026-06-11).
    offline_mode: Optional[bool] = None
```

- [x] **Step 3: Wire GET/PUT in `api/routers/settings.py`**

In `get_settings()` add to the `SettingsResponse(...)` kwargs:
```python
offline_mode = (settings.offline_mode,)
```
In `update_settings()` add with the other `if ... is not None` blocks (before `await settings.update()`):
```python
if settings_update.offline_mode is not None:
    settings.offline_mode = settings_update.offline_mode
    # v0.8.68 — bust the network-state cache so the toggle takes
    # effect on the next chat turn, not after the 30s accessor TTL.
    from open_notebook.health.network import invalidate_forced_offline_cache

    invalidate_forced_offline_cache()
```
and add `offline_mode=settings.offline_mode,` to the PUT's returned `SettingsResponse(...)`.

- [x] **Step 4: Add the cached accessor to `open_notebook/health/network.py`**

Append:

```python
# ---------------------------------------------------------------------------
# v0.8.68 — forced-offline (Offline mode toggle) accessor.
# ContentSettings lives in SurrealDB; we cache the boolean for 30s so the
# per-turn gate doesn't add a DB read to every provisioning call. The
# settings PUT handler calls invalidate_forced_offline_cache() on change.
_FORCED_TTL_S = 30.0
_forced_cache: "tuple[float, bool] | None" = None


def invalidate_forced_offline_cache() -> None:
    global _forced_cache
    _forced_cache = None


async def forced_offline_enabled() -> bool:
    global _forced_cache
    now = time.monotonic()
    if _forced_cache is not None and now - _forced_cache[0] < _FORCED_TTL_S:
        return _forced_cache[1]
    try:
        from open_notebook.domain.content_settings import ContentSettings

        settings = await ContentSettings.get_instance()
        value = bool(getattr(settings, "offline_mode", False))
    except Exception:
        value = False  # DB hiccup must never brick cloud access (spec table)
    _forced_cache = (now, value)
    return value


async def get_network_state_with_settings() -> NetworkState:
    """get_network_state honoring the persisted Offline-mode toggle.
    The toggle check is async (DB-backed) so it can't be passed as the
    sync forced_offline_lookup callable — resolve it first."""
    if await forced_offline_enabled():
        return NetworkState(
            status="offline",
            forced_offline=True,
            checked_at=time.monotonic(),
            source="override",
        )
    return await get_network_state()
```

Also extend `reset_network_state_for_tests()`:
```python
def reset_network_state_for_tests() -> None:
    global _state, _probe_lock, _forced_cache
    _state = None
    _probe_lock = None
    _forced_cache = None
```

- [x] **Step 5: Write tests** — `tests/test_offline_mode_setting.py`

```python
"""v0.8.68 — Offline-mode toggle: schema field, forced accessor caching."""

from __future__ import annotations

import asyncio

import pytest

from open_notebook.health import network


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_content_settings_has_offline_mode_default_false():
    from open_notebook.domain.content_settings import ContentSettings

    assert ContentSettings.model_fields["offline_mode"].default is False


def test_settings_schemas_carry_offline_mode():
    from api.models import SettingsResponse, SettingsUpdate

    assert "offline_mode" in SettingsResponse.model_fields
    assert "offline_mode" in SettingsUpdate.model_fields


def test_forced_offline_enabled_reads_settings(monkeypatch):
    class _FakeSettings:
        offline_mode = True

    async def _fake_get_instance():
        return _FakeSettings()

    from open_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _fake_get_instance)
    assert _run(network.forced_offline_enabled()) is True


def test_forced_offline_db_error_defaults_false(monkeypatch):
    async def _boom():
        raise RuntimeError("db down")

    from open_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _boom)
    assert _run(network.forced_offline_enabled()) is False


def test_forced_offline_cached_until_invalidated(monkeypatch):
    calls = []

    class _FakeSettings:
        offline_mode = False

    async def _fake_get_instance():
        calls.append(1)
        return _FakeSettings()

    from open_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _fake_get_instance)

    async def scenario():
        await network.forced_offline_enabled()
        await network.forced_offline_enabled()  # cache hit
        network.invalidate_forced_offline_cache()
        await network.forced_offline_enabled()  # re-read

    _run(scenario())
    assert len(calls) == 2


def test_state_with_settings_forced(monkeypatch):
    class _FakeSettings:
        offline_mode = True

    async def _fake_get_instance():
        return _FakeSettings()

    from open_notebook.domain.content_settings import ContentSettings

    monkeypatch.setattr(ContentSettings, "get_instance", _fake_get_instance)
    state = _run(network.get_network_state_with_settings())
    assert state.status == "offline" and state.forced_offline is True
```

- [x] **Step 6: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_offline_mode_setting.py tests/test_network_state.py -q`
Expected: all pass. Also run `.venv-py312/bin/python -m pytest tests/ -q -k "settings"` to confirm no settings-router regression.

- [x] **Step 7: Commit**

```bash
git add open_notebook/domain/content_settings.py api/models.py api/routers/settings.py open_notebook/health/network.py tests/test_offline_mode_setting.py
git commit -m "feat: v0.8.68 persisted Offline-mode toggle (settings field + forced-offline accessor)"
```

---

### Task 3: Offline gate module

**Files:**
- Create: `open_notebook/ai/offline_gate.py`
- Test: `tests/test_offline_gate.py`

- [x] **Step 1: Write failing tests** — `tests/test_offline_gate.py`

```python
"""v0.8.68 — offline gate: cloud language models substitute local offline."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from open_notebook.ai import offline_gate
from open_notebook.exceptions import ConfigurationError
from open_notebook.health import network
from open_notebook.health.network import NetworkState


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _state(status):
    return NetworkState(
        status=status, forced_offline=False, checked_at=0.0, source="probe"
    )


def _model(id, provider, type="language", name="m"):
    return SimpleNamespace(id=id, provider=provider, type=type, name=name)


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def _patch_state(monkeypatch, status):
    async def _fake():
        return _state(status)

    monkeypatch.setattr(offline_gate, "get_network_state_with_settings", _fake)


def _patch_model_get(monkeypatch, table):
    async def _fake_get(model_id):
        return table.get(model_id)

    monkeypatch.setattr(offline_gate, "_get_model_record", _fake_get)


def test_none_candidate_passes_through(monkeypatch):
    _patch_state(monkeypatch, "offline")
    assert _run(offline_gate.gate_language_model_id(None)) is None


def test_local_candidate_never_gated(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(
        monkeypatch, {"model:local": _model("model:local", "openai_compatible")}
    )
    assert _run(offline_gate.gate_language_model_id("model:local")) == "model:local"


def test_cloud_candidate_online_passes(monkeypatch):
    _patch_state(monkeypatch, "online")
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})
    assert _run(offline_gate.gate_language_model_id("model:gpt")) == "model:gpt"


def test_unknown_treated_as_online(monkeypatch):
    _patch_state(monkeypatch, "unknown")
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})
    assert _run(offline_gate.gate_language_model_id("model:gpt")) == "model:gpt"


def test_cloud_offline_substitutes_local(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(
        monkeypatch, {"model:gpt": _model("model:gpt", "openai", name="gpt-4o")}
    )

    async def _fake_find():
        return _model("model:gemma", "openai_compatible", name="gemma-4-E4B")

    monkeypatch.setattr(offline_gate, "find_local_language_model", _fake_find)

    out: dict = {}
    got = _run(offline_gate.gate_language_model_id("model:gpt", fallback_out=out))
    assert got == "model:gemma"
    assert out == {
        "offline_fallback": True,
        "from_model_id": "model:gpt",
        "to_model_id": "model:gemma",
        "to_model_name": "gemma-4-E4B",
        "reason": "offline",
    }


def test_cloud_offline_no_local_raises_fast(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})

    async def _fake_find():
        return None

    monkeypatch.setattr(offline_gate, "find_local_language_model", _fake_find)

    with pytest.raises(ConfigurationError):
        _run(offline_gate.gate_language_model_id("model:gpt"))


def test_record_load_failure_passes_through(monkeypatch):
    _patch_state(monkeypatch, "offline")

    async def _boom(model_id):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(offline_gate, "_get_model_record", _boom)
    # Gate must never turn a DB hiccup into a blocked turn.
    assert _run(offline_gate.gate_language_model_id("model:gpt")) == "model:gpt"


def test_non_language_candidate_never_gated(monkeypatch):
    _patch_state(monkeypatch, "offline")
    _patch_model_get(
        monkeypatch, {"model:emb": _model("model:emb", "openai", type="embedding")}
    )
    assert _run(offline_gate.gate_language_model_id("model:emb")) == "model:emb"


def test_find_local_prefers_default_chat(monkeypatch):
    async def _fake_defaults():
        return SimpleNamespace(default_chat_model="model:gemma")

    monkeypatch.setattr(offline_gate, "_get_defaults", _fake_defaults)
    _patch_model_get(
        monkeypatch, {"model:gemma": _model("model:gemma", "openai_compatible")}
    )
    got = _run(offline_gate.find_local_language_model())
    assert got.id == "model:gemma"


def test_find_local_falls_back_to_query(monkeypatch):
    async def _fake_defaults():
        return SimpleNamespace(default_chat_model="model:gpt")

    monkeypatch.setattr(offline_gate, "_get_defaults", _fake_defaults)
    _patch_model_get(monkeypatch, {"model:gpt": _model("model:gpt", "openai")})

    async def _fake_by_type(t):
        return [
            _model("model:zeta", "ollama", name="zeta"),
            _model("model:alpha", "openai_compatible", name="alpha"),
            _model("model:cloudy", "anthropic", name="cloudy"),
        ]

    monkeypatch.setattr(offline_gate, "_get_language_models", _fake_by_type)
    got = _run(offline_gate.find_local_language_model())
    assert got.id == "model:alpha"  # local providers only, name-sorted
```

- [x] **Step 2: Run — expect `ModuleNotFoundError`**

Run: `.venv-py312/bin/python -m pytest tests/test_offline_gate.py -q`

- [x] **Step 3: Implement `open_notebook/ai/offline_gate.py`**

```python
"""v0.8.68 — offline gate for language-model provisioning.

Sits in provision_langchain_model's resolution path (the funnel every
LangGraph workflow uses). When the machine is offline (real probe or the
user's Offline-mode toggle) and the candidate model's provider is a cloud
provider, the gate substitutes the best registered LOCAL language model so
the turn answers instantly instead of hanging to the provider timeout.

Local providers (never gated): ollama and openai_compatible — in this
desktop app both point at machine-local sidecars (the llama.cpp chat
sidecar registers as openai_compatible; see desktop/auto_register/).
Everything else (openai, anthropic, google, groq, mistral, deepseek, xai,
openrouter, azure, vertex, ...) is treated as cloud.

Fail-open by design: any internal error (DB hiccup loading the Model
record, defaults fetch failure) returns the original candidate — the gate
must never be the thing that breaks a chat turn. The ONLY raise is
ConfigurationError when we are offline, the candidate is cloud, and no
local model exists: that turn was going to fail anyway, so fail fast with
an actionable message instead of a 300s hang.
"""

from __future__ import annotations

from loguru import logger

from open_notebook.exceptions import ConfigurationError
from open_notebook.health.network import get_network_state_with_settings

LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai_compatible"})


# --- thin indirections so tests can patch without touching domain models ---


async def _get_model_record(model_id: str):
    from open_notebook.ai.models import Model

    return await Model.get(model_id)


async def _get_defaults():
    from open_notebook.ai.models import model_manager

    return await model_manager.get_defaults()


async def _get_language_models(model_type: str):
    from open_notebook.ai.models import Model

    return await Model.get_models_by_type(model_type)


def _is_local(provider: str | None) -> bool:
    return (provider or "").strip().lower() in LOCAL_PROVIDERS


async def find_local_language_model():
    """Best local fallback Model record, or None.

    Preference order (spec §3): the DefaultModels chat slot when it points
    at a local-provider model (the user's deliberate choice), else the
    first registered local-provider language model, name-sorted for
    determinism (mirrors the assigner's deterministic tie-breaks).
    """
    try:
        defaults = await _get_defaults()
        chat_id = getattr(defaults, "default_chat_model", None)
        if chat_id:
            rec = await _get_model_record(chat_id)
            if rec is not None and _is_local(getattr(rec, "provider", None)):
                return rec
    except Exception as exc:
        logger.debug(f"v0.8.68 offline-gate: defaults lookup failed ({exc!r})")

    try:
        candidates = [
            m
            for m in await _get_language_models("language")
            if _is_local(getattr(m, "provider", None))
        ]
        candidates.sort(key=lambda m: (getattr(m, "name", "") or "").lower())
        return candidates[0] if candidates else None
    except Exception as exc:
        logger.debug(f"v0.8.68 offline-gate: local-model query failed ({exc!r})")
        return None


async def gate_language_model_id(
    candidate_id: str | None,
    *,
    fallback_out: dict | None = None,
) -> str | None:
    """Return candidate_id, or a substituted local model id when offline.

    Ordering note: the Model record is loaded BEFORE the network state is
    consulted, so local-provider candidates never pay the probe cost —
    a fully-local setup runs zero probes.
    """
    if not candidate_id:
        return candidate_id

    try:
        record = await _get_model_record(candidate_id)
    except Exception as exc:
        logger.debug(
            f"v0.8.68 offline-gate: could not load {candidate_id} ({exc!r}) — "
            f"passing through (provisioning will surface the real error)"
        )
        return candidate_id
    if record is None:
        return candidate_id
    if getattr(record, "type", None) != "language":
        return candidate_id  # spec non-goal: embeddings/TTS/STT not gated
    if _is_local(getattr(record, "provider", None)):
        return candidate_id

    state = await get_network_state_with_settings()
    if state.status != "offline":  # online AND unknown both pass (spec §1)
        return candidate_id

    fallback = await find_local_language_model()
    if fallback is None:
        raise ConfigurationError(
            "You're offline and no local model is installed. Connect to the "
            "internet, or add a local model (Settings → Models) so chat can "
            "work offline."
        )
    reason = "forced-offline" if state.forced_offline else "offline"
    logger.info(f"v0.8.68 offline-gate: {candidate_id} → {fallback.id} ({reason})")
    if fallback_out is not None:
        fallback_out.update(
            {
                "offline_fallback": True,
                "from_model_id": candidate_id,
                "to_model_id": fallback.id,
                "to_model_name": getattr(fallback, "name", None),
                "reason": reason,
            }
        )
    return fallback.id
```

- [x] **Step 4: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_offline_gate.py -q`
Expected: 11 passed
(Note: the substitution test asserts reason == "offline" because the patched state has forced_offline=False.)

- [x] **Step 5: Commit**

```bash
git add open_notebook/ai/offline_gate.py tests/test_offline_gate.py
git commit -m "feat: v0.8.68 offline gate — substitute local model for cloud candidates when offline"
```

---

### Task 4: Wire the gate into `provision_langchain_model`

**Files:**
- Modify: `open_notebook/ai/models.py` (extract `get_default_model_id` from `get_default_model` — DRY)
- Modify: `open_notebook/ai/provision.py` (resolve-then-gate-then-instantiate)
- Test: `tests/test_provisioning_fallback.py`

- [x] **Step 1: Extract `get_default_model_id` on ModelManager**

In `open_notebook/ai/models.py`, inside `ModelManager`, add ABOVE `get_default_model` and rewrite `get_default_model` to use it (behavior-preserving refactor):

```python
async def get_default_model_id(self, model_type: str) -> Optional[str]:
    """v0.8.68 — id-only resolution extracted from get_default_model so
    the offline gate (open_notebook/ai/offline_gate.py) can inspect the
    candidate's provider BEFORE instantiation. Mapping unchanged."""
    defaults = await self.get_defaults()
    model_id = None
    if model_type == "chat":
        model_id = defaults.default_chat_model
    elif model_type == "transformation":
        model_id = defaults.default_transformation_model or defaults.default_chat_model
    elif model_type == "tools":
        model_id = defaults.default_tools_model or defaults.default_chat_model
    elif model_type == "embedding":
        model_id = defaults.default_embedding_model
    elif model_type == "text_to_speech":
        model_id = defaults.default_text_to_speech_model
    elif model_type == "speech_to_text":
        model_id = defaults.default_speech_to_text_model
    elif model_type == "large_context":
        model_id = defaults.large_context_model
    return model_id
```

Then replace the body of `get_default_model` so the mapping lives in ONE place:

```python
    async def get_default_model(self, model_type: str, **kwargs) -> Optional[ModelType]:
        """
        Get the default model for a specific type.

        Args:
            model_type: The type of model to retrieve (e.g., 'chat', 'embedding', etc.)
            **kwargs: Additional arguments to pass to the model constructor
        """
        # v0.8.68 — id resolution extracted to get_default_model_id (one
        # mapping, shared with the offline gate). Behavior unchanged.
        model_id = await self.get_default_model_id(model_type)

        if not model_id:
            logger.warning(
                f"No default model configured for type '{model_type}'. "
                f"Please go to Settings → Models and set a default model."
            )
            return None

        try:
            return await self.get_model(model_id, **kwargs)
        except (ValueError, ConfigurationError) as e:
            logger.error(
                f"Failed to load default model for type '{model_type}': {e}. "
                f"The configured model_id '{model_id}' may have been deleted or misconfigured. "
                f"Please go to Settings → Models and reconfigure the default model."
            )
            return None
```

- [x] **Step 2: Run the existing suite to prove the refactor is safe**

Run: `.venv-py312/bin/python -m pytest tests/ -q -k "model or provision or routing or chat" --ignore=tests/integration`
Expected: same pass count as before the edit (no regressions).

- [x] **Step 3: Write failing tests** — `tests/test_provisioning_fallback.py`

```python
"""v0.8.68 — provision_langchain_model consults the offline gate."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from open_notebook.ai import provision
from open_notebook.exceptions import ConfigurationError


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeLangchain:
    pass


class _FakeEsperantoModel:
    def to_langchain(self):
        return _FakeLangchain()


def _patch_manager(monkeypatch, *, default_id="model:gpt", got=None):
    """Patch model_manager: id resolution + instantiation recording."""
    got = got if got is not None else {}

    async def _fake_default_id(model_type):
        return default_id

    async def _fake_get_model(model_id, **kwargs):
        got["model_id"] = model_id
        from esperanto import LanguageModel

        fake = _FakeEsperantoModel()
        # provision checks isinstance(model, LanguageModel)
        monkeypatch.setattr(provision, "LanguageModel", object, raising=False)
        return fake

    monkeypatch.setattr(
        provision.model_manager, "get_default_model_id", _fake_default_id
    )
    monkeypatch.setattr(provision.model_manager, "get_model", _fake_get_model)
    # isinstance check: make every object pass for these unit tests
    monkeypatch.setattr(provision, "LanguageModel", object)
    return got


def test_gate_substitution_flows_through(monkeypatch):
    got = _patch_manager(monkeypatch)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        if fallback_out is not None:
            fallback_out["offline_fallback"] = True
            fallback_out["to_model_id"] = "model:gemma"
        return "model:gemma"

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    out: dict = {}
    model = _run(
        provision.provision_langchain_model(
            "hello",
            None,
            "chat",
            fallback_out=out,
        )
    )
    assert isinstance(model, _FakeLangchain)
    assert got["model_id"] == "model:gemma"
    assert out.get("offline_fallback") is True


def test_gate_passthrough_keeps_candidate(monkeypatch):
    got = _patch_manager(monkeypatch)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        return candidate_id

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    _run(provision.provision_langchain_model("hello", "model:explicit", "chat"))
    assert got["model_id"] == "model:explicit"


def test_gate_configuration_error_propagates(monkeypatch):
    _patch_manager(monkeypatch)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        raise ConfigurationError("offline, no local model")

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    with pytest.raises(ConfigurationError):
        _run(provision.provision_langchain_model("hello", None, "chat"))


def test_no_candidate_still_raises_configuration_error(monkeypatch):
    _patch_manager(monkeypatch, default_id=None)

    async def _fake_gate(candidate_id, *, fallback_out=None):
        return candidate_id

    monkeypatch.setattr(provision, "gate_language_model_id", _fake_gate)

    with pytest.raises(ConfigurationError):
        _run(provision.provision_langchain_model("hello", None, "chat"))
```

- [x] **Step 4: Rewrite `provision_langchain_model` in `open_notebook/ai/provision.py`**

Add import near the top of the file (module level, with the other open_notebook imports):

```python
from open_notebook.ai.offline_gate import gate_language_model_id
```

Replace the whole `provision_langchain_model` function with:

```python
async def provision_langchain_model(
    content, model_id, default_type, fallback_out: "dict | None" = None, **kwargs
) -> BaseChatModel:
    """
    Returns the best model to use based on the context size and on whether there is a specific model being requested in Config.
    If context > 105_000, returns the large_context_model
    If model_id is specified in Config, returns that model
    Otherwise, returns the default model for the given type

    v0.8.68 — resolution now happens in two phases (id, then instance) so
    the offline gate can substitute a LOCAL model id when the machine is
    offline (probe or Offline-mode toggle) and the candidate is a cloud
    provider. `fallback_out` (optional dict, NOT forwarded to the model
    constructor) is populated by the gate when a substitution happens —
    chat callers thread it into the response for the UI pill.
    """
    tokens = token_count(content)
    selection_reason = ""

    if tokens > 105_000:
        selection_reason = f"large_context (content has {tokens} tokens)"
        logger.debug(
            f"Using large context model because the content has {tokens} tokens"
        )
        candidate_id = await model_manager.get_default_model_id("large_context")
    elif model_id:
        selection_reason = f"explicit model_id={model_id}"
        candidate_id = model_id
    else:
        selection_reason = f"default for type={default_type}"
        candidate_id = await model_manager.get_default_model_id(default_type)

    # v0.8.68 — offline gate. No-op when online / candidate is local /
    # candidate is None. Raises ConfigurationError fast (instead of a
    # provider-timeout hang) when offline with no local model.
    candidate_id = await gate_language_model_id(candidate_id, fallback_out=fallback_out)

    model = None
    if candidate_id:
        if model_id and candidate_id == model_id:
            # Explicit-id path: keep get_model's typed errors verbatim
            # (pre-v0.8.68 behavior for explicit ids).
            model = await model_manager.get_model(candidate_id, **kwargs)
        else:
            # Default-resolution path: keep get_default_model's historical
            # log-and-return-None on load failure.
            try:
                model = await model_manager.get_model(candidate_id, **kwargs)
            except (ValueError, ConfigurationError) as e:
                logger.error(
                    f"Failed to load model for {selection_reason}: {e}. "
                    f"The configured model_id '{candidate_id}' may have been "
                    f"deleted or misconfigured. Please go to Settings → Models "
                    f"and reconfigure the default model."
                )
                model = None

    logger.debug(f"Using model: {model}")

    if model is None:
        logger.error(
            f"Model provisioning failed: No model found. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}. "
            f"Please check Settings → Models and ensure a default model is configured for '{default_type}'."
        )
        raise ConfigurationError(
            f"No model configured for {selection_reason}. "
            f"Please go to Settings → Models and configure a default model for '{default_type}'."
        )

    if not isinstance(model, LanguageModel):
        logger.error(
            f"Model type mismatch: Expected LanguageModel but got {type(model).__name__}. "
            f"Selection reason: {selection_reason}. "
            f"model_id={model_id}, default_type={default_type}."
        )
        raise ConfigurationError(
            f"Model is not a LanguageModel: {model}. "
            f"Please check that the model configured for '{default_type}' is a language model, not an embedding or speech model."
        )

    return model.to_langchain()
```

- [x] **Step 5: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_provisioning_fallback.py tests/test_offline_gate.py -q`
Expected: all pass.
Then full backend regression: `.venv-py312/bin/python -m pytest tests/ -q --ignore=tests/integration`
Expected: same pass count as the pre-change baseline (record it before starting).

- [x] **Step 6: Commit**

```bash
git add open_notebook/ai/models.py open_notebook/ai/provision.py tests/test_provisioning_fallback.py
git commit -m "feat: v0.8.68 wire offline gate into provision_langchain_model (resolve-then-gate)"
```

---

### Task 5: Thread fallback info through the chat graph → API responses + mid-turn retry

**Files:**
- Modify: `open_notebook/graphs/chat.py` (`call_model_with_messages`: pass `fallback_out`, mid-turn NetworkError retry, return key)
- Modify: `api/models.py` (`ExecuteChatResponse`: add `offline_fallback` field — locate via `grep -n "selected_provider" api/models.py`, add alongside)
- Modify: `api/routers/chat.py` (execute path ~line 921-993; stream done payload ~line 1298-1340 and ~1415-1441)
- Test: extend `tests/test_chat_stream.py` patterns in a new file `tests/test_chat_offline_fallback_plumbing.py`

- [x] **Step 1: Chat node — pass fallback_out and return it**

In `open_notebook/graphs/chat.py` `call_model_with_messages`, replace the provisioning block (currently lines ~784-797):

```python
# v0.8.68 — offline-fallback info from the provisioning gate. Empty
# dict when no substitution happened; threaded into the node result
# (same pattern as selection_out / v0.8.1) so the router can show
# "Answered with <local model> (offline)" in the UI.
offline_fallback_out: dict = {}
selection_out: dict = {}
if model_id:
    model = await provision_langchain_model(
        content_for_sizing,
        model_id,
        "chat",
        fallback_out=offline_fallback_out,
        max_tokens=8192,
    )
else:
    model = await provision_langchain_chat_model(
        content_for_sizing,
        selection_out=selection_out,
        max_tokens=8192,
        # v0.8.63 — honor the user's explicit "send to cloud anyway"
        # consent for this turn (skips the privacy gate).
        privacy_gate_bypass=bool(state.get("bypass_privacy_gate")),
    )
```

NOTE: `selection_out: dict = {}` already exists just above this block — do not duplicate it; move/merge so it is declared once.

- [x] **Step 2: Mid-turn NetworkError retry (captive-portal leg, spec §3)**

Still in `call_model_with_messages`, wrap the tool-loop call (currently `ai_message, mcp_captures = await bind_mcp_and_run_tool_loop(...)` at ~line 825):

```python
# v0.8.68 — mid-turn offline retry (spec §3 "mid-turn failure leg").
# A captive portal / mid-session drop passes the TCP probe or the
# TTL cache but fails the real provider call. When that failure is
# network-classified AND this turn wasn't already on a local model,
# flip the network state and retry ONCE with the gated (now local)
# model. Any other error — or a second failure — propagates to the
# existing classify_error leg below.
try:
    ai_message, mcp_captures = await bind_mcp_and_run_tool_loop(
        model,
        payload,
        exclude_server_names=state.get("disabled_mcp_servers") or None,
        agent_state_out=agent_state_out,
        notebook_id=notebook_id,
    )
except Exception as e:
    from open_notebook.exceptions import NetworkError
    from open_notebook.health.network import report_network_failure

    error_class, _ = classify_error(e)
    already_local = bool(offline_fallback_out.get("offline_fallback"))
    if error_class is not NetworkError or already_local:
        raise
    report_network_failure()
    _logger.warning(
        "v0.8.68 — cloud call failed mid-turn with a network error; "
        "retrying once on the local fallback model"
    )
    retry_fallback: dict = {}
    model = await provision_langchain_model(
        content_for_sizing,
        model_id,
        "chat",
        fallback_out=retry_fallback,
        max_tokens=8192,
    )
    if not retry_fallback.get("offline_fallback"):
        raise  # gate didn't substitute (no local model) — original error stands
    offline_fallback_out.update(retry_fallback)
    ai_message, mcp_captures = await bind_mcp_and_run_tool_loop(
        model,
        payload,
        exclude_server_names=state.get("disabled_mcp_servers") or None,
        agent_state_out=agent_state_out,
        notebook_id=notebook_id,
    )
```

(`agent_state_out: dict = {}` is declared just above the original call — keep that declaration before this block.)

- [x] **Step 3: Return the new key from the node**

In the node's `return { ... }` dict (currently ~line 845), add after `"selected_model_id"`:

```python
            # v0.8.68 — offline-fallback info (None when no substitution).
            "offline_fallback": offline_fallback_out or None,
```

- [x] **Step 4: API schema + router plumbing**

In `api/models.py`, in `ExecuteChatResponse` next to `selected_provider` (~line 311), add:

```python
    # v0.8.68 — set when the offline gate answered this turn with a local
    # model: {"offline_fallback": true, "from_model_id", "to_model_id",
    # "to_model_name", "reason": "offline"|"forced-offline"}. None otherwise.
    offline_fallback: Optional[dict] = Field(
        None, description="Offline local-model fallback info for this turn"
    )
```

In `api/routers/chat.py` `/chat/execute` handler (~line 921), add alongside the other dual-guard reads:

```python
# v0.8.68 — offline-fallback info (None when the gate didn't act).
offline_fallback = (
    result.get("offline_fallback")
    if isinstance(result, dict)
    else getattr(result, "offline_fallback", None)
)
```

and add `offline_fallback=offline_fallback,` to the `ExecuteChatResponse(...)` construction (~line 984).

In `_stream_chat_events`: at the done-payload build (~line 1298-1340, where `selected_provider_raw` is read from `output`), add the same dual-guard read:

```python
offline_fallback_raw = (
    output.get("offline_fallback")
    if isinstance(output, dict)
    else getattr(output, "offline_fallback", None)
)
```

and `"offline_fallback": offline_fallback_raw,` in the emitted done-event dict next to `"selected_provider"`. Repeat for the second read site (~line 1415-1441, `final_result`): add `offline_fallback_out = final_result.get("offline_fallback") ...` with the dual guard and include it in that payload dict too. Mirror exactly how `selected_provider` flows in both places.

- [x] **Step 5: Plumbing test** — `tests/test_chat_offline_fallback_plumbing.py`

```python
"""v0.8.68 — offline_fallback flows node-result → ExecuteChatResponse."""

from __future__ import annotations

from api.models import ExecuteChatResponse


def test_execute_chat_response_carries_offline_fallback():
    resp = ExecuteChatResponse(
        session_id="s1",
        messages=[],
        offline_fallback={
            "offline_fallback": True,
            "from_model_id": "model:gpt",
            "to_model_id": "model:gemma",
            "to_model_name": "gemma-4-E4B",
            "reason": "offline",
        },
    )
    assert resp.offline_fallback["to_model_name"] == "gemma-4-E4B"


def test_execute_chat_response_defaults_none():
    resp = ExecuteChatResponse(session_id="s1", messages=[])
    assert resp.offline_fallback is None
```

- [x] **Step 6: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_chat_offline_fallback_plumbing.py tests/test_chat_stream.py -q`
Expected: all pass (existing stream tests confirm the done-event change didn't break the wire format).

- [x] **Step 7: Commit**

```bash
git add open_notebook/graphs/chat.py api/models.py api/routers/chat.py tests/test_chat_offline_fallback_plumbing.py
git commit -m "feat: v0.8.68 thread offline-fallback info through chat graph + responses; mid-turn network retry"
```

---

### Task 6: `GET /api/system/network-status` endpoint

**Files:**
- Modify: `api/routers/system.py` (add endpoint below `db_repair_needed`, same style)
- Test: `tests/test_network_status_endpoint.py`

- [x] **Step 1: Write failing test**

```python
"""v0.8.68 — /api/system/network-status: never 500s, reports gate state."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import system as system_router
from open_notebook.health import network
from open_notebook.health.network import NetworkState


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(system_router.router)
    return TestClient(app)


def test_online_payload(client, monkeypatch):
    async def _fake():
        return NetworkState(
            status="online", forced_offline=False, checked_at=1.0, source="probe"
        )

    monkeypatch.setattr(system_router, "get_network_state_with_settings", _fake)
    body = client.get("/api/system/network-status").json()
    assert body["status"] == "online"
    assert body["forced_offline"] is False


def test_offline_includes_fallback_model(client, monkeypatch):
    async def _fake():
        return NetworkState(
            status="offline",
            forced_offline=False,
            checked_at=1.0,
            source="call-failure",
        )

    class _Rec:
        name = "gemma-4-E4B"

    async def _fake_find():
        return _Rec()

    monkeypatch.setattr(system_router, "get_network_state_with_settings", _fake)
    monkeypatch.setattr(system_router, "find_local_language_model", _fake_find)
    body = client.get("/api/system/network-status").json()
    assert body["status"] == "offline"
    assert body["local_fallback_model"] == "gemma-4-E4B"


def test_internal_error_returns_unknown_not_500(client, monkeypatch):
    async def _boom():
        raise RuntimeError("probe machinery exploded")

    monkeypatch.setattr(system_router, "get_network_state_with_settings", _boom)
    r = client.get("/api/system/network-status")
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
```

- [x] **Step 2: Run — expect 404/AttributeError failures**

Run: `.venv-py312/bin/python -m pytest tests/test_network_status_endpoint.py -q`

- [x] **Step 3: Implement the endpoint**

In `api/routers/system.py`, add module-level imports near the top:

```python
from open_notebook.ai.offline_gate import find_local_language_model
from open_notebook.health.network import get_network_state_with_settings
```

and append below `db_repair_needed`:

```python
@router.get("/api/system/network-status")
async def network_status() -> dict:
    """v0.8.68 — current network state for the frontend offline badge.

    Drives use-network-status / NetworkStatusBadge (same polling-banner
    pattern as db_repair_needed above). Never 500s: any internal error
    degrades to {"status": "unknown"} so a probe bug can't paint the UI
    red or break the shell render."""
    import time as _time

    try:
        state = await get_network_state_with_settings()
        fallback_name = None
        if state.status == "offline":
            try:
                rec = await find_local_language_model()
                fallback_name = getattr(rec, "name", None) if rec else None
            except Exception:
                fallback_name = None
        return {
            "status": state.status,
            "forced_offline": state.forced_offline,
            "local_fallback_model": fallback_name,
            "checked_epoch_ms": int(_time.time() * 1000),
        }
    except Exception:
        return {
            "status": "unknown",
            "forced_offline": False,
            "local_fallback_model": None,
            "checked_epoch_ms": int(_time.time() * 1000),
        }
```

- [x] **Step 4: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_network_status_endpoint.py -q` → 3 passed

- [x] **Step 5: Commit**

```bash
git add api/routers/system.py tests/test_network_status_endpoint.py
git commit -m "feat: v0.8.68 GET /api/system/network-status (never-500, fallback model name)"
```

---

### Task 7: Web-search short-circuit

**Files:**
- Modify: `open_notebook/tools/web_search.py` (first lines of the tool body)
- Test: append to existing `tests/test_v0_8_64_web_search.py` style in new file `tests/test_web_search_offline.py`

- [x] **Step 1: Write failing test** — `tests/test_web_search_offline.py`

```python
"""v0.8.68 — web_search returns empty immediately when offline (no 25s
provider budget). Find the tool's async entry function in
open_notebook/tools/web_search.py (the one decorated/bound for the chat
loop, named `web_search`) and assert the offline early-return."""

from __future__ import annotations

import asyncio

import pytest

from open_notebook.health import network
from open_notebook.health.network import NetworkState
from open_notebook.tools import web_search as ws


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    yield
    network.reset_network_state_for_tests()


def test_offline_short_circuits(monkeypatch):
    async def _fake():
        return NetworkState(
            status="offline", forced_offline=False, checked_at=0.0, source="probe"
        )

    monkeypatch.setattr(ws, "get_network_state_with_settings", _fake)

    called = []
    # Whatever provider-attempt helper the module defines must NOT run.
    # (Patch the module's outbound HTTP entry; adjust the attribute name to
    # the real provider-dispatch function found in the module — it is the
    # function the failover loop calls per provider.)
    result = asyncio.new_event_loop().run_until_complete(
        ws._search_impl_for_tests("query")  # added in Step 2 for testability
    )
    assert result == []
    assert called == []
```

- [x] **Step 2: Implement the short-circuit**

In `open_notebook/tools/web_search.py`, add the import at module level:

```python
from open_notebook.health.network import get_network_state_with_settings
```

At the TOP of the provider-failover function body (the async function that runs the Serper→Tavily→SearXNG chain — identify it by the total-budget timeout logic around `ONP_WEB_SEARCH_TOTAL_BUDGET_SEC`), insert as the first statements:

```python
    # v0.8.68 — offline short-circuit (spec §6). Without this, an offline
    # machine burned the full 25s provider-failover budget per tool call
    # before returning empty. The model still gets the standard empty-result
    # shape; the log line tells the operator why.
    _net = await get_network_state_with_settings()
    if _net.status == "offline":
        logger.info("v0.8.68 web_search skipped: device offline")
        return []
```

Expose a thin test seam if the failover function is a closure (only if needed):

```python
# v0.8.68 — module-level alias so tests can drive the failover body
# without binding the chat tool. Same coroutine the tool calls.
_search_impl_for_tests = <name-of-the-failover-async-function>
```

(Replace `<name-of-the-failover-async-function>` with the actual function name found in Step 2 — it exists today; this alias line is the only permitted point of adaptation in this task.)

- [x] **Step 3: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_web_search_offline.py tests/test_v0_8_64_web_search.py -q`
Expected: all pass (existing web-search tests prove online behavior unchanged — conftest strips provider keys so they exercise the no-provider path deterministically).

- [x] **Step 4: Commit**

```bash
git add open_notebook/tools/web_search.py tests/test_web_search_offline.py
git commit -m "feat: v0.8.68 web_search short-circuits offline instead of burning the failover budget"
```

---

### Task 8: Gmail digest deferral

**Files:**
- Modify: `open_notebook/digest/scheduler.py` (defer + retry around the `_send_digest_now` call site, ~line 89)
- Modify: `api/routers/gmail.py` (status payload gains `pending_digest`)
- Test: `tests/test_digest_offline_deferral.py`

- [x] **Step 1: Read `open_notebook/digest/scheduler.py` in full** (it is small) to locate the tick loop and the `_should_send` helper. The deferral state lives in this module.

- [x] **Step 2: Write failing tests** — `tests/test_digest_offline_deferral.py`

```python
"""v0.8.68 — digest scheduler defers sends while offline, retries, and
drops a day-old pending digest (sending two at once next day is worse)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from open_notebook.digest import scheduler
from open_notebook.health import network
from open_notebook.health.network import NetworkState


@pytest.fixture(autouse=True)
def _reset():
    network.reset_network_state_for_tests()
    scheduler.reset_pending_digest_for_tests()
    yield
    network.reset_network_state_for_tests()
    scheduler.reset_pending_digest_for_tests()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _offline():
    async def _fake():
        return NetworkState(
            status="offline", forced_offline=False, checked_at=0.0, source="probe"
        )

    return _fake


def _online():
    async def _fake():
        return NetworkState(
            status="online", forced_offline=False, checked_at=0.0, source="probe"
        )

    return _fake


def test_offline_defers_and_marks_pending(monkeypatch):
    monkeypatch.setattr(scheduler, "get_network_state_with_settings", _offline())
    sent = []

    async def _fake_send(g, label="Digest"):
        sent.append(label)
        return (True, "ok", 1)

    deferred = _run(scheduler.send_or_defer(object(), _fake_send))
    assert deferred is True
    assert sent == []
    assert scheduler.pending_digest_info()["pending"] is True


def test_online_sends_and_clears_pending(monkeypatch):
    monkeypatch.setattr(scheduler, "get_network_state_with_settings", _online())
    sent = []

    async def _fake_send(g, label="Digest"):
        sent.append(label)
        return (True, "ok", 1)

    deferred = _run(scheduler.send_or_defer(object(), _fake_send))
    assert deferred is False
    assert sent == ["Digest"]
    assert scheduler.pending_digest_info()["pending"] is False


def test_network_failed_send_marks_pending(monkeypatch):
    monkeypatch.setattr(scheduler, "get_network_state_with_settings", _online())

    async def _fake_send(g, label="Digest"):
        from open_notebook.exceptions import NetworkError

        raise NetworkError("no route to host")

    deferred = _run(scheduler.send_or_defer(object(), _fake_send))
    assert deferred is True
    assert scheduler.pending_digest_info()["pending"] is True


def test_day_old_pending_dropped(monkeypatch):
    monkeypatch.setattr(scheduler, "get_network_state_with_settings", _offline())

    async def _never(g, label="Digest"):
        raise AssertionError("must not send")

    _run(scheduler.send_or_defer(object(), _never))
    # Age the pending marker by >24h.
    info = scheduler.pending_digest_info()
    scheduler._pending_digest = scheduler._PendingDigest(  # type: ignore[attr-defined]
        since=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    monkeypatch.setattr(scheduler, "get_network_state_with_settings", _online())
    sent = []

    async def _fake_send(g, label="Digest"):
        sent.append(label)
        return (True, "ok", 1)

    _run(scheduler.retry_pending_if_any(object(), _fake_send))
    assert sent == []  # dropped, not double-sent
    assert scheduler.pending_digest_info()["pending"] is False
```

- [x] **Step 3: Implement in `open_notebook/digest/scheduler.py`**

Add near the top of the module:

```python
# v0.8.68 — offline deferral (spec §5). A digest due while offline is
# marked pending and retried by the scheduler loop (see send_or_defer /
# retry_pending_if_any) instead of silently dropping. A pending digest
# older than 24h is dropped with a WARNING — two digests at once the next
# day is worse than skipping one.
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from open_notebook.health.network import get_network_state_with_settings


@dataclass
class _PendingDigest:
    since: datetime


_pending_digest: "_PendingDigest | None" = None
_PENDING_MAX_AGE = timedelta(hours=24)


def reset_pending_digest_for_tests() -> None:
    global _pending_digest
    _pending_digest = None


def pending_digest_info() -> dict:
    """Read-only view for /api/onp/gmail/status."""
    if _pending_digest is None:
        return {"pending": False, "since": None}
    return {"pending": True, "since": _pending_digest.since.isoformat()}


async def send_or_defer(g, send_fn) -> bool:
    """Send the digest, or defer when offline / network-failed.

    Returns True when deferred (pending set), False when the send ran
    (success or a NON-network failure — those keep the historical
    log-and-move-on behavior). send_fn is the existing _send_digest_now
    (injected for testability)."""
    global _pending_digest
    state = await get_network_state_with_settings()
    if state.status == "offline":
        if _pending_digest is None:
            _pending_digest = _PendingDigest(since=datetime.now(timezone.utc))
        log.info("digest-scheduler: offline — digest deferred (will retry)")
        return True
    try:
        await send_fn(
            g,
            label=getattr(g, "frequency", "digest").title()
            if getattr(g, "frequency", None)
            else "Digest",
        )
    except Exception as exc:
        from open_notebook.exceptions import NetworkError
        from open_notebook.utils.error_classifier import classify_error
        from open_notebook.health.network import report_network_failure

        error_class, _ = classify_error(exc)
        if error_class is NetworkError or isinstance(exc, NetworkError):
            report_network_failure()
            if _pending_digest is None:
                _pending_digest = _PendingDigest(since=datetime.now(timezone.utc))
            log.warning("digest-scheduler: send failed with a network error — deferred")
            return True
        raise
    _pending_digest = None
    return False


async def retry_pending_if_any(g, send_fn) -> None:
    """Called from the scheduler tick — retry (or expire) a pending digest."""
    global _pending_digest
    if _pending_digest is None:
        return
    if datetime.now(timezone.utc) - _pending_digest.since > _PENDING_MAX_AGE:
        log.warning(
            "digest-scheduler: pending digest older than 24h — dropped "
            "(next scheduled digest will cover the gap)"
        )
        _pending_digest = None
        return
    await send_or_defer(g, send_fn)
```

(`log` is the module's existing logger name — match whatever the file imports; if it uses `logger`, rename accordingly.)

Then, at the existing fire site (~line 89), replace the direct call:

```python
# Lazy import to avoid circular (router imports digest module)
from api.routers.gmail import _send_digest_now

log.info("digest-scheduler: firing %s send for %s", g.frequency, g.email_address)
ok, msg, n = await _send_digest_now(g, label=g.frequency.title())
```

with:

```python
# Lazy import to avoid circular (router imports digest module)
from api.routers.gmail import _send_digest_now

log.info("digest-scheduler: firing %s send for %s", g.frequency, g.email_address)


# v0.8.68 — offline-aware: defer instead of silently failing.
async def _send(gi, label="Digest"):
    return await _send_digest_now(gi, label=label)


await send_or_defer(g, _send)
```

And in the scheduler's periodic tick loop (the function that sleeps and re-checks — found in Step 1), add a retry call each tick BEFORE the `_should_send` check:

```python
# v0.8.68 — flush a deferred digest as soon as we're back online.
try:
    from api.routers.gmail import _send_digest_now as _sdn

    gi = await GmailIntegration.get()

    async def _send(g2, label="Digest"):
        return await _sdn(g2, label=label)

    await retry_pending_if_any(gi, _send)
except Exception as exc:
    log.warning("digest-scheduler: pending-retry pass failed: %s", exc)
```

(Use the module's existing way of obtaining `GmailIntegration` in the loop — mirror the surrounding code.)

- [x] **Step 4: Surface in gmail status**

In `api/routers/gmail.py`, find the `/status` endpoint's response dict and add:

```python
        # v0.8.68 — deferred-digest indicator for the Settings page.
        "pending_digest": pending_digest_info()["pending"],
```

with the import `from open_notebook.digest.scheduler import pending_digest_info` at module level.

- [x] **Step 5: Run tests**

Run: `.venv-py312/bin/python -m pytest tests/test_digest_offline_deferral.py -q` → 4 passed
Then: `.venv-py312/bin/python -m pytest tests/ -q -k "gmail or digest" --ignore=tests/integration` — no regressions.

- [x] **Step 6: Commit**

```bash
git add open_notebook/digest/scheduler.py api/routers/gmail.py tests/test_digest_offline_deferral.py
git commit -m "feat: v0.8.68 Gmail digest defers offline and retries instead of silently dropping"
```

---

### Task 9: Frontend — badge, pill, settings toggle, i18n

**Files:**
- Create: `frontend/src/lib/hooks/use-network-status.ts`
- Create: `frontend/src/components/layout/NetworkStatusBadge.tsx`
- Modify: `frontend/src/components/layout/AppShell.tsx`
- Modify: `frontend/src/components/chat/ChatMessageProviderBadge.tsx` (+ its cache type + test)
- Modify: `frontend/src/app/(dashboard)/settings/components/SettingsForm.tsx` (Offline-mode switch)
- Modify: `frontend/src/lib/types/api.ts` (settings + chat response types)
- Modify: all 7 locale files under `frontend/src/lib/locales/*/index.ts`
- Test: `frontend/src/components/layout/NetworkStatusBadge.test.tsx`

- [x] **Step 1: Hook** — `frontend/src/lib/hooks/use-network-status.ts`

```typescript
// v0.8.68 — poll the backend's network state (offline probe + the user's
// Offline-mode toggle). Drives NetworkStatusBadge. Same shape as
// use-db-repair-status (v0.8.67q): TanStack Query polling against the
// system router.
'use client'

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export const NETWORK_STATUS_QUERY_KEY = ['system', 'network-status'] as const

export interface NetworkStatus {
  status: 'online' | 'offline' | 'unknown'
  forced_offline: boolean
  local_fallback_model: string | null
  checked_epoch_ms: number
}

export function useNetworkStatus() {
  return useQuery<NetworkStatus>({
    queryKey: NETWORK_STATUS_QUERY_KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<NetworkStatus>(
        '/system/network-status'
      )
      return data
    },
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    retry: 1,
  })
}
```

- [x] **Step 2: Badge** — `frontend/src/components/layout/NetworkStatusBadge.tsx`

```typescript
'use client'

import { WifiOff } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNetworkStatus } from '@/lib/hooks/use-network-status'

// v0.8.68 — persistent offline indicator (spec §4). Renders nothing while
// online/unknown. Two copies: real offline ("local models active") vs the
// user's own Offline-mode toggle. Informational, not dismissible — it
// self-clears when connectivity returns (the hook keeps polling).
export function NetworkStatusBadge() {
  const { t } = useTranslation()
  const { data } = useNetworkStatus()

  if (!data || data.status !== 'offline') return null

  const label = data.forced_offline
    ? t('network.forcedOffline', { defaultValue: 'Offline mode on' })
    : data.local_fallback_model
      ? t('network.offlineWithFallback', {
          defaultValue: 'Offline — answering with {{model}}',
          model: data.local_fallback_model,
        })
      : t('network.offline', { defaultValue: 'Offline — local features only' })

  return (
    <div className="px-4 pt-2">
      <div className="flex items-center gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-1.5 text-sm text-amber-700 dark:text-amber-400">
        <WifiOff className="h-4 w-4 shrink-0" />
        <span>{label}</span>
      </div>
    </div>
  )
}
```

- [x] **Step 3: AppShell** — render the badge under the existing banners:

```typescript
import { NetworkStatusBadge } from './NetworkStatusBadge'
// ... inside <main>, after <DbRepairBanner />:
        <NetworkStatusBadge />
```

- [x] **Step 4: Chat pill — extend `ChatMessageProviderBadge`**

Read `frontend/src/components/chat/ChatMessageProviderBadge.tsx` fully first. Extend its cache-entry type with `offline_fallback?: { to_model_name?: string | null; reason?: string } | null` (mirroring where `selected_provider` is written into the cache from the execute/stream responses — update those write sites in `useNotebookChat.ts`/`useSourceChat.ts`, found via `grep -n "selected_provider" frontend/src/lib/hooks/*.ts`). Render rule: when `offline_fallback` is set, show an amber pill BEFORE the provider badge:

```tsx
  if (cached?.offline_fallback) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400">
        <WifiOff className="h-3 w-3" />
        {t('network.answeredWithLocal', {
          defaultValue: 'Answered with {{model}} (offline)',
          model: cached.offline_fallback.to_model_name ?? t('common.model', { defaultValue: 'local model' }),
        })}
      </span>
    )
  }
```

Add a matching case to `ChatMessageProviderBadge.test.tsx` following its existing test fixtures (copy the `selected_provider: 'local'` test, set `offline_fallback: { to_model_name: 'gemma-4-E4B', reason: 'offline' }`, assert the rendered text contains "gemma-4-E4B").

- [x] **Step 5: Settings toggle**

In `frontend/src/app/(dashboard)/settings/components/SettingsForm.tsx`, mirror an existing boolean-ish control (`auto_delete_files` uses yes/no select; use the project's `Switch` component from `@/components/ui/switch` if present, else a two-option select like `auto_delete_files`). Bind to the settings object's new `offline_mode` field (extend the settings type in `frontend/src/lib/types/api.ts` with `offline_mode?: boolean | null`). Labels:

```typescript
label: t('settings.offlineMode', { defaultValue: 'Offline mode' })
help:  t('settings.offlineModeHelp', { defaultValue:
  'Never use the internet. Cloud models, web search, and email digests are disabled; local models keep working.' })
```

- [x] **Step 6: i18n keys (all 7 locales)**

Add a `network` section + the two settings keys to every locale file (`en-US`, `pt-BR`, `zh-CN`, `zh-TW`, `ja-JP`, `ru-RU`, `bn-IN` under `frontend/src/lib/locales/*/index.ts`). en-US:

```typescript
  network: {
    offline: "Offline — local features only",
    offlineWithFallback: "Offline — answering with {{model}}",
    forcedOffline: "Offline mode on",
    answeredWithLocal: "Answered with {{model}} (offline)",
  },
```

and in the settings section: `offlineMode: "Offline mode"`, `offlineModeHelp: "Never use the internet. Cloud models, web search, and email digests are disabled; local models keep working."` Translate per-locale (pt-BR: "Modo offline" / "Offline — respondendo com {{model}}" etc.; zh-CN: "离线模式" / "离线 — 使用 {{model}} 回答"; ja-JP: "オフラインモード" / "オフライン — {{model}} で回答中"; ru-RU: "Офлайн-режим"; zh-TW: "離線模式"; bn-IN: "অফলাইন মোড" — complete each section consistently with the file's existing translation style).

- [x] **Step 7: Badge test** — `frontend/src/components/layout/NetworkStatusBadge.test.tsx`

Mirror `ChatMessageProviderBadge.test.tsx`'s harness (same render/query-client setup). Cases: (1) renders nothing when `status: 'online'`; (2) renders offline text with the fallback model name; (3) renders the forced-offline copy when `forced_offline: true`. Mock `useNetworkStatus` via `vi.mock('@/lib/hooks/use-network-status', ...)`.

- [x] **Step 8: Run frontend checks**

Run: `cd frontend && pnpm test --run && pnpm exec tsc --noEmit`
Expected: all tests pass, typecheck clean.

- [x] **Step 9: Commit**

```bash
git add frontend/src
git commit -m "feat: v0.8.68 frontend — offline badge, chat fallback pill, Offline-mode toggle, i18n"
```

---

### Task 10: Changelog + full verification

**Files:**
- Modify: `desktop/CHANGELOG.md` (Unreleased section)

- [x] **Step 1: Changelog entry** (top of `## Unreleased`):

```markdown
- **✨ v0.8.68 — Offline/online smart switching + Offline-mode toggle**
  - **✨ Network-state service (`open_notebook/health/network.py`):** 2s TCP probe + 20s TTL cache + passive flips from real cloud-call failures/successes; `ONP_NET_PROBE_HOSTS` / `ONP_NETWORK_STATE_TTL_SEC` tunable. "unknown" is treated as online — a flaky probe can never block cloud calls.
  - **✨ Offline gate (`open_notebook/ai/offline_gate.py`):** when offline (real or forced) and the turn's model is a cloud provider, provisioning substitutes the best local model instantly (DefaultModels chat slot if local, else first registered local language model) — no more 300s hangs. Offline with no local model fails fast with an actionable message. Local-provider models are never gated; a mid-turn cloud NetworkError retries once on the local model.
  - **✨ Offline-mode toggle:** persisted `offline_mode` on ContentSettings + Settings UI switch — forces the app fully local even when online (cloud chat, web search, Gmail send all gated).
  - **🎨 UI:** `GET /api/system/network-status` + `use-network-status` drive an amber "Offline" badge in the app shell; chat messages answered by the fallback get an "Answered with <model> (offline)" pill (extends ChatMessageProviderBadge). i18n'd across all 7 locales.
  - **🐛 Gmail digests no longer silently drop offline:** the scheduler defers and retries the pending digest until back online (day-old pending is dropped with a warning, surfaced as `pending_digest` in /gmail/status).
  - **⚡ web_search short-circuits offline** instead of burning its 25s provider-failover budget.
```

- [x] **Step 2: Full verification**

```bash
.venv-py312/bin/python -m pytest tests/ -q --ignore=tests/integration
.venv-py312/bin/python -m pytest desktop/tests -q
cd frontend && pnpm test --run && pnpm exec tsc --noEmit
```
Expected: everything passes; backend count = baseline + new tests.

- [x] **Step 3: Commit**

```bash
git add desktop/CHANGELOG.md
git commit -m "docs: v0.8.68 changelog — offline/online smart switching"
```

---

## Self-review notes

- **Spec coverage:** §1 network service → Task 1+2; §2 toggle → Task 2+9; §3 provisioning fallback + mid-turn retry → Tasks 3-5; §4 endpoint+UI → Tasks 6+9; §5 Gmail → Task 8; §6 web search → Task 7; testing section → per-task tests + Task 10. Edge-case table: probe-env override (T1), captive portal (T5 retry), no-local-model fast error (T3), forced+cloud-picker (gate applies on explicit model_id path, T4), settings-unreadable default-false (T2).
- **Known adaptation points (explicitly bounded):** Task 7's failover-function name and Task 8's scheduler-tick insertion are anchored by grep instructions with the exact code to insert; Task 9 Step 4's cache-write sites are located by `grep -n "selected_provider"`. These are discovery-of-location only — the code to write is fully specified.
- **Type consistency check:** `fallback_out` dict keys (`offline_fallback`, `from_model_id`, `to_model_id`, `to_model_name`, `reason`) are identical in offline_gate.py (writer), chat.py (pass-through), api/models.py docstring, and the frontend pill (`to_model_name`). `get_network_state_with_settings` is the single consumer-facing entry everywhere (gate, web_search, scheduler, endpoint); bare `get_network_state` is only used by tests and the settings-free path.
