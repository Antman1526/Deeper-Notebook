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

## Unreleased — v0.7.36 → v0.7.41 (in flight)

Planned cycle covering native async LangGraph (v0.7.37), real token
streaming via SSE (v0.7.38), list virtualization (v0.7.39), component
splitting for the four 500+ LOC files (v0.7.40), and sub-`lg`
responsive polish (v0.7.41). Tuned for local-LLM deploys with 2–5
test users.

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
