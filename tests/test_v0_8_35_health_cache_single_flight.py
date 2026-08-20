"""v0.8.35 audit — _local_chat_healthy_cached() single-flight guard.

Found during the chat-stream `selected_provider` audit. The TTL cache at
`deeper_notebook/ai/provision.py:_local_chat_healthy_cached` lacks a
single-flight guard: when multiple concurrent chat requests hit a
cache-miss (cold start, or every 30s when the TTL expires), each
coroutine independently enters the inline `if _health_cache is None or
... TTL_S` branch and calls `await asyncio.to_thread(probe_all_local_models, ...)`.
The probe takes up to ~9s (httpx default structured timeout) so a user
with 5 concurrent chat tabs hits the local sidecar 5× per cache window
instead of once.

This isn't a correctness bug — all writers stamp the same dict — but
it's wasted work and an unnecessary load spike on the local sidecar
every TTL boundary. The existing `TestHealthCacheTTL` test only drives
the helper sequentially, so it never caught the race.

This test drives the helper concurrently from N coroutines with the
probe slowed down so the race window is wide enough to deterministically
trigger N probes without the fix, and exactly 1 with the fix.
"""

from __future__ import annotations

import asyncio
import time


def test_health_cache_single_flight_under_concurrency(monkeypatch):
    """N concurrent cache-miss callers must share exactly 1 probe call.

    Without the single-flight guard each coroutine sees `_health_cache is
    None`, enters the probe branch, and calls `probe_all_local_models`
    independently. The slow-probe stub below makes the race window wide
    enough that all N coroutines start their probe before any one
    finishes. The assertion is `probe_call_count == 1` — anything > 1
    means the race exists.
    """
    import deeper_notebook.ai.provision as provision_mod

    # Start cold so every concurrent caller sees a cache-miss.
    monkeypatch.setattr(provision_mod, "_health_cache", None)

    probe_call_count = [0]

    def _slow_probe(creds):
        # Increment under no lock — we want to count exactly how many
        # parallel entries happen.
        probe_call_count[0] += 1
        # Sleep ~100ms so coroutines reliably overlap. The probe runs
        # via asyncio.to_thread so this sync sleep doesn't block the
        # event loop.
        time.sleep(0.1)
        return [{"name": "Local GGUF (llama.cpp)", "status": "healthy"}]

    import deeper_notebook.health.local_models as health_mod

    monkeypatch.setattr(health_mod, "probe_all_local_models", _slow_probe)
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", "http://localhost:8080")

    async def _drive() -> list[bool]:
        # Fire 5 concurrent calls. Without single-flight, all 5 see
        # cache=None and run the probe in parallel → probe_call_count == 5.
        # With single-flight, the first acquirer probes, the other 4
        # await the lock; when they enter under the lock the cache is
        # already populated and they return its value → probe_call_count == 1.
        return await asyncio.gather(
            *[provision_mod._local_chat_healthy_cached() for _ in range(5)]
        )

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_drive())
    finally:
        loop.close()

    # All callers got the same healthy answer.
    assert all(r is True for r in results), (
        f"Expected all callers to see healthy=True, got {results}"
    )
    # And only ONE probe ran despite 5 concurrent callers.
    assert probe_call_count[0] == 1, (
        f"Expected single-flight (1 probe), got {probe_call_count[0]} "
        f"— concurrent cache-miss callers thundering-herded the probe"
    )


def test_health_cache_single_flight_does_not_serialize_cache_hits(monkeypatch):
    """The single-flight lock must only gate cache-MISS callers. A
    cache-HIT path must not wait on the lock — otherwise every chat
    turn pays lock-acquisition latency, even though the TTL hasn't
    expired. Verify by pre-populating the cache and asserting that
    a slow-probe stub is NEVER called."""
    import deeper_notebook.ai.provision as provision_mod

    # Pre-populate with a fresh entry (well within TTL).
    monkeypatch.setattr(
        provision_mod,
        "_health_cache",
        (time.monotonic(), {"Local GGUF (llama.cpp)": True}),
    )

    probe_called = [False]

    def _probe_should_not_run(creds):
        probe_called[0] = True
        return []

    import deeper_notebook.health.local_models as health_mod

    monkeypatch.setattr(health_mod, "probe_all_local_models", _probe_should_not_run)
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", "http://localhost:8080")

    async def _drive() -> list[bool]:
        return await asyncio.gather(
            *[provision_mod._local_chat_healthy_cached() for _ in range(3)]
        )

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_drive())
    finally:
        loop.close()

    assert all(r is True for r in results)
    assert probe_called[0] is False, "Cache-hit path must not call the probe at all"
