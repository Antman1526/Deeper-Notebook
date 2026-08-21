# Phase 5 — Advanced Memory, Privacy & Agent Reliability

**Status:** Design approved · 5.1 memory line COMPLETE (retention v0.8.50, batched extraction v0.8.54, confidence v0.8.55) · 5.2a privacy-gate seam (v0.8.51) · 5.2b-1 model-classifier plumbing (v0.8.57) · 5.2b-2 sidecar-as-classifier (v0.8.59) · 5.2c gate-decision surfacing (v0.8.58) + UI badge (v0.8.61) · 5.3c-full chat-loop FSM (v0.8.60) · 5.3a agent-FSM core (v0.8.52) · 5.3b ask-graph FSM gate (v0.8.53) · 5.3c truncation observability (v0.8.56) · remaining: 5.2b-2 endpoint wiring, 5.2c redaction UI, 5.3c-full FSM loop driver
**Owner:** desktop fork (`open-notebook-Plus`, branch `desktop-app`)
**Relates to:** the Osaurus-integration plan (Phases 0–4 shipped), Finding #3 (unbounded memory growth), v0.7.70 (session summaries), v0.8.49 (episode recall)

---

## 1. Why this phase exists

Phases 0–4 made local models first-class (Osaurus detection, smart-routing UI,
sidecar visibility, GGUF manager). Phase 5 takes the three Osaurus capabilities
that were deliberately deferred because each is a standalone project rather than
a bounded fix:

1. **Distill-and-score memory pipeline** — make the memory *write* path bounded
   and high-signal (today it is per-turn, eager, and unbounded).
2. **Fail-closed privacy filter** — gate cloud fallback on a local
   sensitivity check so private content never leaves the machine by accident.
3. **Agent-loop state machine** — give multi-step/tool work explicit
   `todo → working → complete | clarify` states so the agent can't hallucinate
   "done".

These are sequenced by payoff and risk: **#1 first** (closes an open audit
finding, builds on shipped recall work, no new model/UI), **#3 next** (bounded,
graph-only), **#2 last** (largest — ships a classifier model + a redaction UI).

### Guiding principles (carried from the rest of the project)

- **Local-first / privacy-first.** No feature may silently send user content to
  a cloud provider. Defaults respect that posture.
- **Incremental & independently shippable.** Each sub-phase ends with a tested,
  CHANGELOG'd `v0.8.NN` increment. No big-bang merge.
- **Flow within existing patterns.** Reuse: `checkpoint_prune.py`'s retention
  model, the `surreal_commands` worker for memory jobs, the smart-router
  (`open_notebook/ai/router.py`) seam for routing decisions, the SSE event
  contract for streaming agent state, `_sanitize_memory_text` for prompt safety.
- **Testable without live services.** SurrealDB/mem0/model calls are mocked;
  pure logic (query builders, classifiers' decision functions, FSM transitions)
  is unit-tested. Live behavior is covered by the integration suite.
- **Version-tagged inline comments** (`# v0.8.NN — …`) on every change.

---

## 2. Current-state map (what exists today)

| Concern | Where | State |
|---|---|---|
| Memory write (per-turn) | `desktop/memory/writer.py:extract_turn` | Eager `mem_client.add()` per `<tool_call>`; **no dedup beyond mem0's own, no retention** |
| Memory write (session end) | `desktop/memory/writer.py:summarize_session` + `api/routers/chat.py:_fire_memory_summarize_session` | One `episode` per session delete |
| Memory store | `desktop/memory/surreal_store.py` (`SurrealMemoryStore`) | 3 tables (`memory_fact`/`preference`/`episode`), `created_at` on each; `_exec` + `from_test_client` for tests |
| Memory recall | `open_notebook/utils/memory_recall.py` | Reads all 3 layers (facts/prefs since v0.7.71, **episodes since v0.8.49**); recency + semantic; sanitized via `_sanitize_memory_text` (v0.8.47) |
| Routing decision | `open_notebook/ai/router.py:pick_provider` + `open_notebook/ai/provision.py` | Picks local vs cloud by context size + `auto_route_cloud`; **no content gate** |
| Agent / tool loop | `open_notebook/graphs/chat.py` (MCP tool loop), `open_notebook/graphs/ask.py` | Runs to a token budget; no explicit completion state |
| Streaming contract | `api/routers/chat.py:_stream_chat_events` | NDJSON `start`/`token`/`mcp_tool_calls`/`done`/`error` |
| Prune precedent | `open_notebook/utils/checkpoint_prune.py` + `api/main.py` scheduler | Per-thread retention via `ROW_NUMBER()`; background loop |

**Open finding addressed here (Finding #3):** the `memory_*` tables grow without
bound (recall caps *results*, not *rows*), and the semantic path does an O(N)
full-table cosine scan every turn. mem0's internal add-pipeline dedups somewhat
but does not enforce a ceiling.

---

## 3. Item #1 — Distill-and-score memory pipeline

### 3.1 Target architecture

```
            ┌─────────────── per turn ───────────────┐
chat turn ─►│ _fire_memory_extract_turn (fire&forget) │
            └───────────────┬─────────────────────────┘
                            │ surreal_commands queue
                            ▼
              memory_extract_turn worker
                            │
          ┌─────────────────┼──────────────────────────┐
   (5.1b) │ buffer turns (per session, ~60s / N turns)  │
          └─────────────────┬──────────────────────────┘
                            ▼
          ┌──────────── distill (one LLM call) ─────────┐
   (5.1c) │ extract candidate facts/prefs + SCORE each  │
          │ dedup vs existing (cosine) → ADD/UPDATE/NOOP │
          └─────────────────┬──────────────────────────┘
                            ▼
                    SurrealMemoryStore.insert/update
                            │
   (5.1a) ────────► prune(keep_per_table)  ◄── retention ceiling
                            │
            session end ─►  summarize_session → episode + prune
```

Three sub-phases, each shippable:

#### 5.1a — Retention ceiling (**v0.8.50 — IMPLEMENTED**)

The minimum that closes Finding #3 without reworking extraction.

- `SurrealMemoryStore.prune(keep_per_table)` — per table, keep the newest
  `keep_per_table` rows by `created_at`, delete the rest.
  - **Query shape is deliberate:** `SELECT id, created_at FROM <t> ORDER BY
    created_at DESC` then slice in Python and `DELETE <t> WHERE id IN $ids`.
    This sidesteps the SurrealDB *"missing order idiom"* family that bit recall
    in v0.8.19/v0.8.30 (`SELECT VALUE id … ORDER BY created_at` is rejected; the
    ORDER BY field must be in the projection). `DELETE … WHERE id IN $ids` is the
    safe v0.7.184 idiom already used by the notebook-delete cascade.
- `desktop/memory/writer.py:prune_memories(mem_client, keep_per_table)` — thin,
  defensive wrapper: `getattr(mem_client, "vector_store", None)`, call `.prune`
  if present. Never raises (best-effort, mirrors the rest of the writer).
- **Triggers (both, so the ceiling holds regardless of usage pattern):**
  1. `summarize_session` — prune at every conversation boundary (natural, rare).
  2. `extract_turn` — a *throttled high-water* prune: only when a cheap
     `count()` exceeds `keep × HIGH_WATER` (default 1.5×), so a user who never
     deletes sessions still stays bounded, but the common path pays nothing.
- **Config:** `ONP_MEMORY_KEEP_PER_TABLE` (default **500** — generous; ~500
  facts is months of use and ≈ a few MB).
- **Test:** `SurrealMemoryStore.from_test_client(mock)` asserts the select +
  delete queries and that nothing is deleted under the ceiling; writer wrapper
  tested with a fake `mem_client.vector_store`.

#### 5.1b — Batch buffering (**v0.8.54 — IMPLEMENTED**)

Shipped a turn-count buffer rather than the originally-sketched 60s debounce +
DB `memory_buffer` table — simpler, and the worker is already off the hot path.
`extract_turn` buffers turns in a process-local, lock-guarded per-session dict
and runs ONE combined extraction (`render_extract_user_batch`) every
`ONP_MEMORY_BATCH_TURNS` turns; `summarize_session` drains the buffer at
session end via `flush_session_buffer`. The extract→parse→apply→prune body was
refactored into a shared `_extract_and_apply` so single-turn (default) and
batched paths can't drift. **Default `ONP_MEMORY_BATCH_TURNS=1` = unchanged
per-turn behaviour.** A time-debounce flush + a DB-backed buffer (surviving
worker restarts) remain possible future refinements.

#### 5.1c — Scoring + dedup (**v0.8.55 — confidence shipped; weighted eviction later**)

Shipped the scoring half: `apply_tool_call` reads the model's per-candidate
`confidence`, drops anything below `ONP_MEMORY_CONFIDENCE_FLOOR` (default 0.0 →
keep all), and persists the real score (metadata → `surreal_store.insert`'s
`confidence` column, previously always 1.0). Dedup is already handled by mem0's
own ADD/UPDATE/NOOP pipeline on write. **Still later:** (b) confidence-weighted
retention — `prune` evicting lowest-confidence-oldest first instead of pure
recency; (c) confidence as a recall ranking signal in `memory_recall`.

### 3.2 Files touched (Item #1)

- `desktop/memory/surreal_store.py` — `prune()` (+ `count()` helper). *(5.1a)*
- `desktop/memory/writer.py` — `prune_memories()`, calls in
  `summarize_session`/`extract_turn`; later the buffer/distill rework. *(5.1a→c)*
- `desktop/memory/memory_commands.py` — later: `memory_distill_session`. *(5.1b)*
- `tests/test_memory_retention.py` (new). *(5.1a)*
- `docs/5-CONFIGURATION` — document `ONP_MEMORY_KEEP_PER_TABLE`.

### 3.3 Risks

- Pruning the *wrong* rows = silent memory loss → recency keep + generous
  default + best-effort (never blocks writes) + log counts.
- A huge first-run `DELETE … IN $ids` list → batch the delete if `len > 1000`
  (noted; steady-state excess is small).

---

## 4. Item #2 — Fail-closed privacy filter before cloud fallback

### 4.1 Target architecture

```
turn ─► pick_provider(context_size)            (open_notebook/ai/router.py)
          │ decision = "cloud"?
          ├─ no  ─► local (unchanged)
          └─ yes ─► privacy_gate.classify(text) ── sensitive? ──┐
                        │ clean                                   │ yes
                        ▼                                         ▼
                   allow cloud                         BLOCK (fail-closed):
                                                       • fall back to local, OR
                                                       • return a redaction-review
                                                         payload to the client
```

- **Local classifier** (`open_notebook/ai/privacy_gate.py`, new): a small local
  model (~2.8GB GGUF, served by the existing llama-cpp sidecar, or a lightweight
  regex+NER pre-filter for the no-model case) returns a sensitivity verdict +
  spans. Fully local — the gate must never call out.
- **Seam:** `pick_provider` (or `provision_langchain_chat_model`) consults the
  gate *only when the decision is cloud*. Default behavior when the gate model
  is absent: **fail closed → stay local** (configurable).
- **UX:** a redaction-review sheet (frontend) shows flagged spans; the user
  approves/redacts before the cloud hop. Reuses the existing dialog/sheet
  primitives.
- **Config:** `ONP_PRIVACY_GATE` (`off` | `local-only` | `review`),
  `ONP_PRIVACY_GATE_MODEL`.

### 4.2 Files

- `open_notebook/ai/privacy_gate.py` (new) — `classify(text) -> Verdict`.
- `open_notebook/ai/router.py` / `provision.py` — consult the gate on cloud.
- `api/routers/chat.py` — emit a `privacy_review` SSE event / 409-style payload.
- frontend: redaction-review sheet + a settings card (extends the Phase-2
  smart-routing card).
- model provisioning: bundle/download the gate GGUF (reuse Phase-4b downloader).

### 4.3 Phasing & risks

- **5.2a** regex/structured-secret pre-filter + fail-closed routing seam (no
  model, testable). **SHIPPED v0.8.51** — `open_notebook/ai/privacy_gate.py`
  (`detect_sensitive` + `apply_privacy_gate`), wired at the `pick_provider`
  call site in `provision.py`, gated by `ONP_PRIVACY_GATE` (default off),
  metric `onp_privacy_gate_redirects_total`. Catches structured secrets only;
  the model handles unstructured PII in 5.2b.
- **5.2b** model-backed PII layer. **Reframed** from "bundle a ~2.8 GB GGUF" to
  "point at any local OpenAI-compatible endpoint" (leaner, BYO-model). Slices:
  - **5.2b-1 plumbing — SHIPPED v0.8.57.** `open_notebook/ai/privacy_classifier.py`
    `classify_via_model_async(text)` (httpx.AsyncClient → `{ONP_PRIVACY_CLASSIFIER_URL}/chat/completions`,
    PII-classification prompt, tolerant JSON-array parse, best-effort `[]`).
    `apply_privacy_gate` gained `extra_findings`; the async call lives in
    `provision.py` (only when gate-on + cloud-bound) so the event loop stays
    free and the gate stays sync/pure. Additive: UNIONed with the regex floor,
    so it can only catch MORE. Default (`ONP_PRIVACY_CLASSIFIER_URL` unset) →
    exactly the v0.8.51 regex behaviour.
  - **5.2b-2 endpoint wiring — SHIPPED v0.8.59.** `ONP_PRIVACY_CLASSIFIER_URL=auto`
    (aliases `sidecar`/`chat-sidecar`/`local`) reuses the running chat sidecar
    (`OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL`) as the classifier — no second model to
    provision. Explicit opt-in.
- **5.2c** redaction-review UI — surface flagged categories/spans; let the user
  approve or redact before the cloud hop. (Frontend; depends on 5.2b.)
  - **Backend SHIPPED v0.8.58 + frontend badge SHIPPED v0.8.61.** The gate
    decision is surfaced on `ExecuteChatResponse` + the `/chat/stream` `done`
    event as `privacy_gated` + `privacy_categories` (label-only), and the chat
    UI renders an `🛡 On-device` chip (`ChatMessagePrivacyBadge`) with the
    detected categories in its tooltip.
  - **Interactive review sheet SHIPPED v0.8.63.** The badge opens a popover
    (categories + explanation) with a "Re-ask allowing cloud" action that
    re-sends the question with a per-request `bypass_privacy_gate` flag
    (default off; explicit user consent; audit-logged). The agent-FSM
    `clarify`/`truncated` indicator shipped v0.8.62
    (`ChatMessageAgentStateBadge`). **Phase 5.2 + 5.3 UI complete.**
- Risks: classifier latency on the hot path (cache verdict per turn; only run on
  cloud decisions), model size (opt-in download), false negatives (fail closed).

---

## 5. Item #3 — Agent-loop state machine

### 5.1 Target

A small FSM wrapping the agent: `todo → working → (clarify ↔ working) →
complete`. The model must emit an explicit terminal state; "complete" requires
the declared todo items to be satisfied, preventing hallucinated done-claims.

- **Where:** `open_notebook/graphs/ask.py` (multi-search/synthesis) and the chat
  MCP tool loop in `open_notebook/graphs/chat.py`. State lives in LangGraph
  `ThreadState` (new `agent_state`, `todo`, `clarification` fields).
- **Streaming:** new SSE event types `agent_state` / `clarify` so the UI shows
  real progress and can prompt the user mid-task.
- **Config:** `DEEPER_NOTEBOOK_AGENT_FSM` (default **on** after bake-in;
  compatibility aliases remain supported). Set `0`/`false`/`off` for the
  explicit rollback to the pre-FSM behavior.

### 5.2 Files & phasing

- **5.3a** define the FSM + transitions as a pure module
  (`open_notebook/graphs/agent_fsm.py`) — unit-test transitions in isolation.
  **SHIPPED v0.8.52** — `AgentState`/`can_transition`/`is_terminal`,
  `parse_state`, `TodoItem`/`completion_satisfied`, and the pure
  `AgentLoop.advance` driver (anti-hallucinated-done + max-steps backstop),
  27 unit tests. Nothing wires it yet (5.3b/c).
- **5.3b** wire into `ask.py`; emit `agent_state`. **SHIPPED v0.8.53** —
  `write_final_answer` adopts the FSM state vocabulary: when `ONP_AGENT_FSM`
  is on and no search produced grounded content, it declares `CLARIFY` and
  returns a refine-your-question message instead of an ungrounded synthesis
  (skips the LLM call); otherwise tags `complete`. Default on; explicit
  `DEEPER_NOTEBOOK_AGENT_FSM=0` restores the pre-FSM path. The `ask` DAG
  doesn't loop, so the FSM's loop driver is unused here — that's 5.3c.
- **5.3c** wire the FSM loop *driver* + backstop into the chat MCP tool loop;
  frontend progress + clarify prompt.
  - **Observability slice SHIPPED v0.8.56** — `bind_mcp_and_run_tool_loop` now
    classifies its terminal state (`complete` vs `truncated` = hit the
    `max_iterations` cap with pending tool calls) and emits
    `onp_agent_tool_loop_outcomes_total` + a WARNING. Pure observation, no
    behavior change.
  - **5.3c-full SHIPPED v0.8.60 (lightweight realization).** When
    `ONP_AGENT_FSM` is on, the chat tool loop offers the model a `<state>`
    contract and classifies the terminal state (`complete`/`clarify`/
    `truncated`) via `agent_fsm.parse_state`, surfaced as `agent_state` on the
    chat response + stream `done` event (clarify = model paused to ask the
    user). We deliberately did NOT drive/redesign the loop — it's a
    tool-calling loop, not a plan-execute agent; the loop terminates as before.
    A full plan-execute agent (todo plan + anti-hallucinated-done loop driver)
    would be a separate graph, out of scope for retrofitting chat.
- Risks: weak local models follow state instructions poorly → keep a token-budget
  backstop so the loop always terminates; the explicit `0` rollback remains
  available if a deployment needs the pre-FSM behavior.

---

## 6. Cross-cutting

- **Env flags introduced:** `ONP_MEMORY_KEEP_PER_TABLE` (5.1a, live),
  `ONP_MEMORY_DISTILL_*` (5.1b/c), `ONP_PRIVACY_GATE[_MODEL]` (5.2),
  `ONP_AGENT_FSM` (5.3). All documented in `docs/5-CONFIGURATION`.
- **CHANGELOG:** one `v0.8.NN` bullet per sub-phase, severity-tagged.
- **i18n:** new UI strings (privacy review, agent state) get keys in all locales
  or rely on `defaultValue`.
- **Testing gate:** each sub-phase ships with `uv run pytest tests/` green +
  (where UI) `pnpm test --run`.

## 7. Sequencing

| Sub-phase | Ship | Risk | Closes |
|---|---|---|---|
| **5.1a retention** | **v0.8.50 (now)** | low | Finding #3 |
| 5.1b batch buffering | next | med | LLM-call volume |
| 5.1c scoring/dedup | next | med | memory quality |
| 5.3a FSM core | after 5.1 | low | — |
| 5.3b/c FSM wiring | — | med | hallucinated-done |
| 5.2a routing seam | after 5.3 | low | privacy posture |
| 5.2b/c classifier + UI | — | high | private-data leak |

This document is the spec; each row above becomes its own tested increment.
