# Open Notebook Plus — Changelog

The desktop-app fork's version history. Upstream `open-notebook` releases
are tracked in [`../CHANGELOG.md`](../CHANGELOG.md); this file covers
the Plus-specific commits on top of upstream.

Format: each release is grouped by theme. Severity tags:
- 🔒 **Security/safety**
- 🐛 **Bug fix**
- 🎨 **UX/UI**
- ⚡ **Performance**
- 🛠 **Infra/tooling**
- ✨ **Feature**

Versions reflect commit cadence, not strict semver — this is a desktop
fork on its own release rhythm. Patch numbers (`v0.7.N`) increment per
focused commit; each ships with regression tests.

---

## Unreleased — v0.7.36 → v0.7.76 (in flight)

Planned cycle covering native async LangGraph (v0.7.37), real token
streaming via SSE (v0.7.38), list virtualization (v0.7.39), component
splitting for the four 500+ LOC files (v0.7.40), and sub-`lg`
responsive polish (v0.7.41). Tuned for local-LLM deploys with 2–5
test users.

Hardening run (v0.7.49–v0.7.56) closed eight reliability bugs
uncovered by a follow-up audit pass:

- **v0.7.49** useSourceChat streaming — TextDecoder `{stream:true}`
  for UTF-8, cross-read line buffer, per-send `crypto.randomUUID()`
  IDs, AbortError filter by exact id pair, 4 MiB defensive cap.
- **v0.7.50** useNotebookChat — AbortController + mid-stream
  mountedRef guard; chat.ts `reader.cancel()` before `releaseLock()`
  so FastAPI's `is_disconnected()` actually fires.
- **v0.7.51** SourcesColumn infinite-scroll — read scroll metrics
  from `e.currentTarget` instead of a ref pinned to CardContent;
  fixes silently-dead infinite scroll past the 50-source
  virtualization threshold.
- **v0.7.52** API lifespan + chat graph — `asyncio.wait_for(timeout=10)`
  around DB pool warm-up acquires; chat-stream `on_chain_end` accepts
  Pydantic state shape via `getattr` fallback; dead `last_token_idx`
  removed.
- **v0.7.53** /search/ask — `is_disconnected()` per astream_events
  tick (parity with /chat/stream).
- **v0.7.54** Propagate v0.7.49/v0.7.50 fixes to useSourceChat error
  path + use-ask reader.cancel.
- **v0.7.55** podcast_service + command_service — `asyncio.to_thread`
  wrap around synchronous `submit_command`; /search/ask/simple gets
  disconnect check + state-shape guard.
- **v0.7.56** source_chat state-shape guard; SourceCard
  refresh-timeout ref+cleanup.
- **v0.7.57** repository `_release` decrements `_pool_total` under
  `_pool_lock` (matches v0.7.24 acquire-side discipline). Closed a
  slow drift that could wedge the pool under concurrent broken
  releases.
- **v0.7.58** Launcher drain threads now joined before log files
  close (preserves crash-cause tails of surreal/api logs). Bare
  `except: pass` in stop_all replaced with debug logging.
  podcast_service maps ValueError → 400 instead of swallowing into
  500.
- **v0.7.59** useTheme computes effectiveTheme client-side
  post-mount (no more SSR hydration mismatch). NoteEditorDialog
  MutationObserver scoped to the editor wrapper instead of
  document.body. useNotebookChat deleteSession reads from the
  TanStack cache instead of a stale outer closure.
- **v0.7.60** Two pre-existing edge-table query bugs uncovered by
  the third audit pass: the `add source to notebook` idempotency
  check on `reference` was inverted (every link call created a
  fresh duplicate edge → source_count inflated forever); the
  source-retry endpoint queried non-existent `source`/`notebook`
  columns on the `reference` edge table so EVERY retry hit the
  "not associated with any notebooks" 400 and retry was
  effectively dead.
- **v0.7.61** `graphs/source.transform_content` returned None when
  `source.full_text` was empty — LangGraph then tried `[] + None`
  for the `Annotated[list, operator.add]` reducer and crashed the
  whole graph run, leaving sources half-saved. Now returns
  `{"transformation": []}`. Notebook.delete cascades chat sessions
  (was orphaning `chat_session` records with dangling notebook
  references after deletion).
- **v0.7.62** Connection-pool shutdown safety: close_pool waits up
  to ~2 s for checked-out connections to drain before nulling
  state, and `_release` no longer asserts on `_pool is None` (it
  just closes the conn directly), so FastAPI lifespan shutdown
  exits cleanly even when requests are mid-flight. Plus one more
  asyncio.to_thread wrap on a sync surreal_commands.submit_command
  call in the run-transformation endpoint.
- **v0.7.63** `require_encryption_key` + provider-status reporting
  accept either OPEN_NOTEBOOK_ENCRYPTION_KEY (singular) or
  OPEN_NOTEBOOK_ENCRYPTION_KEYS (plural rotation list), matching
  the encryption utility and the lifespan check. Rotation-only
  deployments no longer hit phantom "Encryption key not configured"
  errors on migration endpoints.
- **v0.7.64** NotebookPage contextSelections is now pruned to the
  current sources/notes list on every render and fully cleared on
  notebookId change — stale IDs from navigation or deletion no
  longer leak into chat context-building. GET /insights/{id} now
  returns 404 (not 500) when the referenced source has been
  deleted out from under the insight (orphan-record case).
- **v0.7.65** chat.py + source_chat.py size their LLM-budget
  check against the actual message text (`.content` joined), not
  `str(payload)`'s repr of the Message list. The wrapper repr
  added ~80-120 chars of boilerplate per message — 50-turn
  sessions overshot the 105k large_context cutoff by ~5k phantom
  "tokens" and got rerouted to the long-context fallback model
  earlier than necessary.
- **v0.7.66** Local-LLM hardening: per-message char cap
  (default 24k chars ≈ 6k tokens, overridable via
  ONP_CHAT_MESSAGE_CHAR_CAP) inside trim_message_history. A single
  giant paste no longer crashes a 16k-context local model
  mid-stream — the message is kept but its content is truncated
  with a "[…content truncated…]" marker. Two new error_classifier
  rules: explicit "model is still loading" mapping (HTTP 503 cold-
  start during weight load, or 200 with JSON `{"error":"model not
  loaded"}` from LM Studio / vLLM) → "Please wait a few seconds
  and try again", and an updated NetworkError message that
  mentions local servers explicitly.
- **v0.7.67** Launcher now logs a clear WARNING when it skips
  spawning the chat LLM server (no chat GGUF configured, or file
  missing at the configured path). Previously it silently
  returned and the user got no signal that memory-writer features
  would be inert.
- **v0.7.68 + v0.7.70** Memory writer fully wired into the chat
  router. The `memory_extract_turn` + `memory_summarize_session`
  handlers were registered at the worker side since v0.7.47 but
  NOTHING in the chat path ever submitted them — the feature was
  inert. /chat/execute and /chat/stream now fire
  memory_extract_turn fire-and-forget after each turn's
  session.save(); DELETE /chat/sessions/{id} fires
  memory_summarize_session before deleting the session record.
  Both helpers gate on the MEMORY_* env vars being set so upstream
  non-desktop builds silently no-op, run via asyncio.to_thread to
  keep the event loop free, and swallow all failures at debug
  level (memory is best-effort).
- **v0.7.69** Hardened podcast `generate_podcast_command`'s return
  block against None or partial-shape result from podcast-creator's
  create_podcast(). The earlier `episode.audio_file = ...` block
  was fixed in v0.7.3 but the function's terminal output
  construction still used `result["transcript"]` / `result["outline"]`
  subscript inside a `result.get(...)`-truthy ternary — would
  AttributeError when `result is None`, masking a successful-but-
  transcript-less generation as a worker crash that retry=1
  couldn't recover from.
- **v0.7.71** Memory READ path. Chat now injects the most recent
  facts + preferences (capped 15 + 10) into the system prompt via
  a new `# WHAT YOU REMEMBER ABOUT THE USER` section in
  `chat/system.jinja`. With v0.7.68/70 the writer was already
  populating `memory_fact` / `memory_preference` tables every
  turn; this commit closes the loop so the assistant actually
  recalls them on the next turn. Direct SurrealQL SELECT … LIMIT
  for safety + speed (no embedder round-trip, tolerates missing
  tables on fresh installs). Single-user deploys with tens of
  facts get "what I've learned about you lately" — no semantic
  filtering needed.
- **v0.7.72** Podcast retry validates the referenced episode +
  speaker profiles BEFORE the destructive audio/episode deletes.
  Previously a rename or delete of the profile after the original
  submission meant the user lost their failed episode record AND
  couldn't retry — the 400 from submit_generation_job's
  EpisodeProfile.get_by_name fired after the cleanup had already
  run. Now the 400 lands without side effects, naming the missing
  profile and pointing the user at the fix.
- **v0.7.73** Defensive dedup at the domain layer for
  `Source.add_to_notebook` and `Note.add_to_notebook`. v0.7.60
  fixed the idempotency check on the HTTP endpoint but the domain
  methods still called `self.relate()` unconditionally — direct
  calls from upload / studio / notes-create paths could create
  duplicate reference / artifact edges on retry. Now both check
  for an existing edge with the same in/out pair before
  relating; same query direction as the HTTP endpoint so behavior
  is symmetric. (Existing dupes in old DBs are NOT cleaned by
  this commit; that would be a separate migration.)
- **v0.7.74** 14 new unit tests for v0.7.71's memory_recall
  (pure-render path). Tests caught a real bug in `_coerce_text` —
  `{"text": None}` returned the string "None" because the dict
  branch unconditionally `str()`-coerced the inner value. Now
  explicit None check ⇒ empty string ⇒ filtered out upstream so
  the prompt never gets a `- None` bullet line. Backend suite
  now 416 passing.
- **v0.7.75** Finishing sweep of v0.7.65's str(payload) sizing
  fix: transformation.py + prompt.py both still passed
  `str(payload)` to provision_langchain_model, overcounting by
  the same ~80-120 chars of wrapper boilerplate per message.
  Both now extract `.content` per message and pass the plain
  string. /transformations/execute endpoint also gets the
  isinstance/getattr dual-path output access from v0.7.52/55/56
  for symmetry.
- **v0.7.76** Domain hardening in open_notebook/domain/notebook.py:
  Source.vectorize, Source.add_insight, and Note.save all called
  the sync surreal_commands.submit_command directly inside
  `async def` (same blocking-event-loop bug as v0.7.55/57/62) —
  all three now wrap in asyncio.to_thread. Plus Source.delete
  now cascades `reference` edges (was already cleaning
  source_embedding + source_insight) so the notebook sources
  view doesn't crash on `Source(**None)` after a delete. Note
  gets a new delete override that cascades `artifact` edges +
  `note_embedding` rows — symmetric to Source and to the v0.7.61
  Notebook.delete chat_session cascade.

---

## v0.7 — Local-deploy hardening + podcast workflow + UX

The v0.7 line was an audit-driven sweep. Every release pinned a
single concern, shipped with regression tests, and (almost) never
touched files outside its scope. Suite grew from ~485 → 626 backend
tests + 29 frontend tests.

### v0.7.36 — CHANGELOG.md (this file)
🛠 Introduces a Plus-fork-scoped changelog. The 64 commits between
v0.6.0 and v0.7.35 were well-described per-commit but unrepresented
at the project level.

### v0.7.35 — Power-user polish
🎨 Filter row on `/settings/api-keys` (substring + status chips: All /
Has credential / From env / Unconfigured).
🎨 Three keyboard shortcuts beyond `⌘K`:
- `⌘N` → new notebook
- `⌘U` → upload source
- `⌘/` → jump to `/search`

### v0.7.34 — App UX gaps
🎨 `/sources` empty state has a CTA; header has an "Add" button.
🐛 Chat session-delete jumps to next session inline (was flicker
through empty state).
🐛 Central 5xx error toasts at axios interceptor (deduped 5s window),
points users at the rotated log file.

### v0.7.33 — Podcast UX
🎨 Episode duration in header (`~14 min` estimate from
`num_segments × 2`, replaced by real `M:SS` once metadata loads).
🎨 Generation-stage indicator under title: "Generating outline…" →
"Drafting transcript (3/7 segments)…" → "Synthesizing speech…".
Derived from existing fields; zero backend change.

### v0.7.32 — Three critical bugs
🐛 **Speaker presets**: cloud-only migration 7 presets broke every
podcast generation on local Piper installs. New
`desktop/auto_register/speaker_profile.py` registers 4 local-Piper
presets (Local Duo / Solo / Debate / Interview).
🐛 **SQLite WAL + integrity check**: both chat graphs opened
unsynchronised `sqlite3.connect()` → concurrent writers hit
`database is locked`. New shared
`open_notebook/utils/sqlite_checkpoint.py` enforces WAL +
`busy_timeout=5000` + corruption rename-aside recovery.
🐛 **Source.delete cancels in-flight commands**: deleting mid-embed
left worker writing fresh `source_embedding` rows pointing at a
now-dead source. `update_command_result(status="canceled")` fires
before file/embedding cleanup.

### v0.7.31 — Podcast auto-suggest
✨ `POST /api/podcasts/suggest` — heuristic recommender. Returns
best-fit episode profile + length + title + briefing addition based
on source titles + topics + total content volume. No LLM call —
pure keyword scoring. Frontend "✨ Auto-fill from sources" button.

### v0.7.30 — Podcast preset library expansion
✨ Auto-register seeds 9 episode profiles instead of 1: Open Notebook
Plus Local, Deep Dive, Quick Brief, Debate, Tutorial, Story Mode,
News Roundup, Q&A Interview, Recap & Review. Each carries a
distinct `default_briefing` shaping outline LLM behavior.

### v0.7.29 — Dashboard Command Center
✨ `(dashboard)/page.tsx` was `redirect('/notebooks')`. Now a real
landing page: quick actions (Studio / Notebook / Podcast / Ask), live
system status from `/readyz` (30s refresh), recent notebooks with
relative timestamps, ⌘K hint + data-location footer.

### v0.7.27 + v0.7.28 — Design system + sidebar polish
🎨 Semantic tokens (`--success`, `--warning`, `--info`), motion scale
(`--motion-fast/base/slow/spring`), elevation scale (`--shadow-xs`
through `--shadow-xl`). Sidebar refined: 3px left-edge accent bar
(replacing broken `scale-[1.02]`), exact-or-child route matching,
SSR-safe `⌘K` keyboard hint.

### v0.7.23 + v0.7.25 + v0.7.26 — UX bug pass
🎨 Studio wrapped in AppShell (was the only dashboard page without
a sidebar).
🐛 v0.7.25 fixed 10 visual bugs: notebook-detail loading drops sidebar,
GeneratePodcastDialog clips body, `break-all` in chat bubbles,
hardcoded blue link contrast, AddSourceDialog no max-height, sidebar
hover scale tear, notebook column flex math overflow at 1024px,
CommandPalette orphan heading + missing empty state, Studio drop
zone missing focus ring, SetupBanner hardcoded palette colors.
🐛 v0.7.26: chat optimistic rollback uses `crypto.randomUUID()` (was
`Date.now()` → duplicate keys + cross-message wipe on partial fail).

### v0.7.24 — Backend bug batch (7 bugs)
🐛 Worker process never used v0.7.14 file logger.
🐛 Startup encryption check ignored v0.7.17 plural env var.
🐛 DB pool race grew `_pool_total` beyond cap.
🐛 Source retry double-prefixed `command:` RecordID.
🐛 Launcher polled `/health` (always 200) instead of `/readyz`.
🐛 MultiFernet cache survived uvicorn reload (rotation bug).
🐛 Log fallback put logs at `cwd/.logs` inside Docker.

### v0.7.14 → v0.7.22 — Reliability foundation

| Tag | Theme |
|---|---|
| v0.7.14 🛠 | Rotated file logging via loguru (`~/.open-notebook-plus/logs/api.log`, 20 MB rotation, 14d retention, gzip). |
| v0.7.15 🛠 | `/livez` + `/readyz` real health probes (DB ping + migration check). |
| v0.7.16 🔒 | `/api/sources` upload byte cap (default 500 MB, `ONP_SOURCE_UPLOAD_MAX_BYTES`). |
| v0.7.17 🔒 | Encryption key rotation via `MultiFernet` + `OPEN_NOTEBOOK_ENCRYPTION_KEYS=new,old` + sweep. |
| v0.7.18 ⚡ | SurrealDB connection pool (default 4). 50-200ms saved per chat turn. |
| v0.7.19 🔒 | CVE bumps: `aiohttp` ≥3.11.18, `llama-cpp-python` ≥0.3.16, `pyinstaller` ≥6.13.0. |
| v0.7.20 🛠 | All 22 `ONP_*` env vars documented in `.env.example` + `docs/5-CONFIGURATION/onp-env-reference.md`. |
| v0.7.21 🛠 | Deleted 12 dead service modules + `api/client.py` (~1832 LOC removed). |
| v0.7.22 🛠 | Operator runbook at `desktop/operating-locally.md`. |

### v0.7.0 → v0.7.13 — LLM context-overflow caps

The headline v0.7 capability: every LLM-bound prompt is now bounded
by an env-configurable char cap. No more silent context overflows on
a 16k-token local server.

| Tag | What got capped / what shipped |
|---|---|
| v0.7.0 ✨ | Studio one-shot workflow (upload → notebook or podcast). |
| v0.7.1 🔒 | Studio code-review fixes (7 issues, 6 tests). |
| v0.7.2 🔒 | Podcast audio path-traversal hardening; 404 preservation on delete. |
| v0.7.3 🐛 | podcast_commands KeyError + orphan output dir cleanup. |
| v0.7.4 ⚡ | Studio file/combined char caps env-configurable (15k / 60k defaults). |
| v0.7.5 🐛 | Memory writer LLM-call robustness (broad except + defensive `.get()`). |
| v0.7.6 🐛 | Legacy SurrealDB WebSocket URL (`ws://host:port/rpc`, was malformed). |
| v0.7.7 🔒 | Piper TTS input cap (50k chars / ~10 min audio). |
| v0.7.8 ⚡ | Chat LLM `n_ctx` env-configurable (`ONP_CHAT_LLM_CTX`, default 16384). |
| v0.7.9 🐛 | Ask graph per-result content cap (1500 chars × 10 results default). |
| v0.7.10 🐛 | Transformation input cap (12k chars default). |
| v0.7.11 🐛 | Chat message history cap (12k chars, oldest dropped with marker). |
| v0.7.12 🐛 | source_chat: source + per-insight + max-insight count caps. |
| v0.7.13 🐛 | source_chat history cap + shared helper extraction. |

---

## v0.6 — 35-commit bug-fix run

A single sprint closing 35 concrete bugs surfaced by code review +
operator pain. Highlights:

- **v0.6.34** 🔒 `Source.delete()` refuses to unlink files outside `UPLOADS_FOLDER`.
- **v0.6.32** 🐛 `useSourceChat` wired the AbortController it had been creating but never assigning.
- **v0.6.31** 🔒 `model_manager` DELETE path-traversal hardening via `is_relative_to`.
- **v0.6.30** 🐛 `_ensure_credential` no longer silently falls through to duplicate-create.
- **v0.6.27** 🔒 Atomic write for `capture_state.json`.
- **v0.6.24** 🐛 `useNotebookChat` — out-of-order race in context-count effect.
- **v0.6.21** 🐛 Voice idempotency — was creating duplicates on every launch.
- **v0.6.20** 🐛 `/login → /login` redirect loop guard.
- **v0.6.16** ⚡ Stream file uploads in 1 MiB chunks (was buffering entire file).
- **v0.6.11** 🐛 Cross-platform RAM probe — Windows chat-model regression.
- **v0.6.10** ⚡ Stop chat/source-chat invoke from blocking the event loop.
- **v0.6.8** 🔒 `config.toml` perms restricted to `0600` + atomic write.
- **v0.6.7** 🔒 Constant-time password comparison + Unicode crash fix.

Run `git log --oneline --grep "v0.6\." desktop-app` for the full list.

---

## Conventions

- Versioning: per-commit patch increments; major boundaries reserved
  for substantial user-facing shape changes.
- Tests: every commit ships regression coverage. Suite grew from
  ~485 → 626 backend tests + 29 frontend tests across the session.
- For env-var documentation: [`docs/5-CONFIGURATION/onp-env-reference.md`](../docs/5-CONFIGURATION/onp-env-reference.md).
- For the operator runbook: [`operating-locally.md`](operating-locally.md).
- For upstream changelog: [`../CHANGELOG.md`](../CHANGELOG.md).
