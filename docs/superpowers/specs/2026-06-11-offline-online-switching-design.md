# Offline/Online Smart Switching + Offline Mode — Design Spec

**Date:** 2026-06-11
**Status:** Approved by user (Approach C: network-state service + forced offline-mode toggle)
**Target:** open-notebook-Plus desktop app (macOS .dmg / Windows local-dev install)

## Problem

Open Notebook Plus is local-first but hybrid: local llama.cpp/Ollama models coexist
with cloud providers (OpenAI, Anthropic, Google, …), web search (Serper/Tavily/SearXNG),
Gmail digests, and cloud TTS. Today the app has **no network-state awareness**:

- A chat turn on a cloud model with no internet hangs up to 300 s
  (`ONP_CHAT_MODEL_TIMEOUT_SEC`) before failing.
- Nothing in the UI indicates the machine is offline.
- Gmail digests fail silently when offline (scheduler logs and drops).
- The `web_search` tool burns its full 25 s failover budget before returning empty.
- There is no way to force the app to never touch the internet.

## Goals

1. Chat never stalls offline: instant substitution of the best registered **local**
   chat model, with a visible per-message indicator. Cloud model resumes
   automatically when connectivity returns (per-turn re-check; nothing sticky).
2. Proactive offline badge in the app shell.
3. Gmail digests defer and retry instead of silently dropping.
4. Web search short-circuits offline.
5. A persisted **Offline mode** toggle in Settings that force-disables all outbound
   network use (cloud AI, web search, Gmail send) even when online.

## Non-goals

- Remote access to the app over the internet (inbound; separate project).
- Offline caching of web-search results.
- Changing default model assignment logic or the llama.cpp sidecar lifecycle.
- Network-gating cloud TTS for podcasts (episodes already fail visibly and are
  retryable; may reuse the service later).

## Architecture

### 1. Network-state service — `open_notebook/health/network.py` (new)

```python
@dataclass(frozen=True)
class NetworkState:
    status: Literal["online", "offline", "unknown"]
    forced_offline: bool          # user toggle active
    checked_at: float             # monotonic timestamp
    source: Literal["probe", "call-failure", "call-success", "override", "init"]

async def get_network_state(*, max_age_sec: float | None = None) -> NetworkState
def report_network_failure() -> None   # called by error-classified NetworkError sites
def report_network_success() -> None   # called after any successful cloud call
```

- **Probe:** TCP connect (2 s timeout) to two hosts, first success wins:
  `1.1.1.1:443`, `8.8.8.8:443` (overridable via `ONP_NET_PROBE_HOSTS`,
  comma-separated `host:port`). Runs in a thread (`asyncio.to_thread`) so the
  event loop never blocks. Any probe exception → `unknown`.
- **Cache:** module-level state with TTL, default 20 s
  (`ONP_NETWORK_STATE_TTL_SEC`). Passive reports update the cache immediately
  and reset its age.
- **Semantics:** `unknown` is treated as **online** by all consumers — we never
  block cloud calls on a flaky probe; a real call failure flips the state via
  `report_network_failure()`.
- **Forced offline:** when the settings toggle is on, `get_network_state()`
  returns `offline` with `forced_offline=True` without probing.
- Concurrency: a single in-flight probe guarded by an `asyncio.Lock`; concurrent
  callers await the same result.

### 2. Offline-mode setting

- New boolean field `offline_mode` (default `false`) on the existing app-settings
  record in SurrealDB, following the `ContentSettings` pattern
  (`open_notebook/domain/content_settings.py`) — same record/migration approach
  as previous settings additions.
- Exposed through the existing settings API (GET/PUT); no new router.
- Settings UI: a switch labeled "Offline mode" with help text
  "Never use the internet. Cloud models, web search, and email digests are
  disabled; local models keep working." New i18n keys in all locale files.
- The network service reads it via a small cached accessor (30 s TTL, refreshed
  on settings save via the existing settings-update path).

### 3. Provisioning fallback — `provision_langchain_model()`

Location: the existing provisioning helper used by all LangGraph workflows.

- Before constructing a **cloud-provider** model: `await get_network_state()`.
  - `offline` (real or forced) → resolve the local fallback chat model:
    the DefaultModels chat slot if its provider is local (llamacpp/ollama/
    openai-compatible-localhost), else the first registered local chat model.
    Substitute it and attach `fallback_info = {from_model, to_model, reason}`
    to the provisioning result.
  - No local model registered → raise `ConfigurationError` immediately with an
    actionable message ("You're offline and no local model is installed…").
  - Local-provider models are never gated — offline mode must not break them.
- **Mid-turn failure leg:** in the chat graph, a `NetworkError` from a cloud
  call triggers `report_network_failure()` and **one** retry of that node with
  the local fallback model (same `fallback_info` tagging). No retry loops.
- Successful cloud calls invoke `report_network_success()` (cheap; updates cache).

### 4. API + frontend

- **`GET /api/system/network-status`** (added to the existing system router):
  `{status, forced_offline, last_checked_epoch_ms, local_fallback_model: str | null}`.
  Never 500s; on any internal error returns `{"status": "unknown", ...}`.
- **`use-network-status` hook:** polls every 15 s (pause when tab hidden),
  modeled on `use-db-repair-status` (v0.8.67q).
- **App-shell badge:** small persistent indicator when `status == "offline"`:
  "Offline — local models active" (distinct copy when `forced_offline`:
  "Offline mode on"). Rendered in `AppShell` next to the existing banners.
- **Chat fallback pill:** the chat SSE stream emits a `fallback_used` event
  carrying `{to_model, reason}`; both chat hooks (`useChat`, `useSourceChat`)
  surface it as a per-message pill: "Answered with {model} (offline)".
- All new strings via i18n keys in every locale file (repo i18n rule).

### 5. Gmail digest deferral

In the digest scheduler path (`_send_digest_now` caller, under the existing
v0.8.67w `_SEND_LOCK` single-flighting):

- Before sending: check network state. Offline → set an in-memory
  `pending_digest` marker (with the scheduled date) and schedule retries every
  10 min (`ONP_DIGEST_RETRY_MINUTES`) until a send succeeds or the day rolls
  over (a day-old pending digest is dropped with a WARNING log — sending two
  digests at once the next day is worse than skipping one).
- A send that fails with a network-classified error gets the same pending+retry
  treatment (plus `report_network_failure()`).
- Status surfaced in the existing `/api/onp/gmail/status` payload
  (`pending_digest: bool`) so the Settings page can show "digest queued —
  waiting for connection".

### 6. Web-search short-circuit

In `open_notebook/tools/web_search.py`: first line of the tool body checks
network state; `offline` → return the empty-results shape immediately with
`reason: "offline"` (the model sees "no results — device offline"), skipping
the 25 s provider budget entirely.

## Error handling and edge cases

| Case | Behavior |
|---|---|
| Probe host unreachable but internet fine (corp firewall blocks 1.1.1.1) | `unknown` → treated online; configurable `ONP_NET_PROBE_HOSTS` |
| Captive portal (TCP connects, API calls fail) | First cloud call fails → passive flip to offline → next turn falls back instantly |
| Offline + no local model | Fast `ConfigurationError`, actionable message, no hang |
| Forced offline + user explicitly picks a cloud model in the picker | Turn answered by local fallback with pill (same path); picker unchanged |
| Probe exception/timeout storm | Single-flight lock + TTL cache bound probe frequency |
| Settings record unreadable | `offline_mode` defaults to `false` (never brick cloud access on a DB hiccup) |

## Testing

All offline-mockable (probe injected as a callable; no live network in tests):

- `tests/test_network_state.py` — TTL/cache, single-flight, unknown-is-online,
  passive report precedence, forced-offline override, env-var host parsing.
- `tests/test_provisioning_fallback.py` — cloud→local substitution offline,
  local models never gated, no-local-model fast error, fallback_info shape,
  mid-turn NetworkError single retry.
- Gmail: pending/retry/day-rollover-drop logic.
- Web search: offline short-circuit returns instantly.
- Frontend (`pnpm test --run`): hook polling/pause, badge render states,
  fallback pill render.
- Changelog: one bullet per logical change under `## Unreleased`, with the
  `# v0.8.NN — ...` inline code-comment convention in touched files.

## Rollout / compatibility

- Pure additive: no migrations beyond the settings field default; no behavior
  change when online with the toggle off (probe runs only when a cloud call or
  the status endpoint asks).
- Desktop bundle unaffected (no new dependencies).
- Env knobs: `ONP_NET_PROBE_HOSTS`, `ONP_NETWORK_STATE_TTL_SEC`,
  `ONP_DIGEST_RETRY_MINUTES`.
