# Deeper Notebook full release quality gate — final report

**Audit window:** 2026-08-11

**Baseline:** `4c8b5a3d`

**Accepted candidate:** `a18d9c82`

**Change range:** 32 commits, 147 paths, 7,398 insertions, 831 deletions

**Decision:** **APPROVED WITH DISCLOSED RELEASE LIMITS**

This report is the durable outcome of a whole-application debug, security,
performance, completeness, plugin, and visual-polish pass. Changes were limited
to reproduced defects, measured resource risks, dependency remediation,
evidence completeness, confirmed dead files, and proof infrastructure. No
public REST shape, stored domain schema, vault authority, model-selection
contract, or established user workflow was intentionally broken.

## Overall application summary

Deeper Notebook is a privacy-first research and knowledge workspace for people
who need to turn a mixed source library into verifiable understanding and
reusable deliverables. A user creates notebooks, imports documents, web pages,
audio, video, pasted text, or external vault material, and then searches,
chats, writes, studies, and generates artifacts against that evidence. Grounded
answers retain citations and evidence-review receipts instead of presenting an
untraceable model response.

Its core value is ownership plus depth. The database, embeddings, notes,
memories, generated artifacts, and model configuration can remain local. The
desktop app supervises the database, API, task worker, web frontend, and
optional local AI sidecars. Cloud models and search providers remain opt-in.
The result is a NotebookLM-class research surface with substantially more
control: local models, reusable transformations, Evidence Studio, Course Packs,
editable podcast outlines, external vault projection, study scheduling,
provider routing, model benchmarking, and an MCP-based extension system.

The intended users are researchers, writers, analysts, educators, students,
knowledge workers, and privacy-sensitive teams who want an agentic workspace
without surrendering their corpus or accepting unsupported answers.

## Tech stack

### Languages and runtimes

- **Python 3.11/3.12** — API, workflows, repositories, migrations, desktop
  supervision, exports, workers, model/download tooling, and verification.
- **TypeScript / JavaScript** — Next.js frontend, browser fixtures, route
  handlers, client state, and accessibility/visual proof.
- **CSS / Tailwind CSS 4** — responsive Folio and rollback-shell presentation,
  themes, focus mode, and knowledge-workspace layout.
- **SurrealQL** — schema migrations, graph/document/vector queries, jobs, vault
  projections, evaluations, and persistence.
- **Shell / Make / TOML** — repeatable development and macOS packaging,
  bundled-runtime manifests, and operational scripts.

### Application frameworks and libraries

- **FastAPI, Starlette, Uvicorn, Pydantic v2, pydantic-settings** — typed REST
  API, middleware, authentication boundaries, validation, and runtime models.
- **LangGraph and LangChain provider integrations** — chat, Ask, ingestion,
  transformations, tool loops, memory, and provider-neutral model workflows.
- **Esperanto** — unified local/cloud model selection.
- **SurrealDB v2 and surreal-commands** — graph/document/vector persistence,
  migrations, async work queues, and HNSW-backed similarity search.
- **Next.js 16, React 19, TypeScript 5** — application shell and 23 built routes.
- **TanStack Query and Zustand** — bounded server-state caching/polling and
  client preferences/session state.
- **Radix UI / shadcn, Tailwind, Framer Motion, lucide-react, cmdk** — semantic
  primitives, themes, motion, icons, and command palette.
- **CodeMirror, react-markdown, remark/rehype, KaTeX, MDEditor, react-pdf,
  React Flow, react-resizable-panels** — editing, rich reading, math, PDF,
  knowledge graphs, and multi-pane workspaces.
- **i18next / react-i18next** — 14 locale catalogs.
- **MCP Python SDK and FastMCP** — external plugin registration, discovery,
  schemas, invocation, lifecycle probes, and the local example plugin.
- **content-core, lxml, markdown-it, python-docx, python-pptx, openpyxl,
  Pillow, imageio-ffmpeg** — ingestion and deterministic local artifact export.
- **watchdog and FSRS** — vault watching and study-card scheduling.
- **pywebview, PyInstaller, bundled Node/SurrealDB/Python/uv** — native macOS
  wrapper and self-contained app runtime.
- **llama.cpp / MLX / Ollama, Hugging Face Hub, faster-whisper/CTranslate2,
  Piper, FFmpeg, mem0** — optional local chat, embeddings, transcription,
  speech, media composition, and memory.

### Services and tools

- Optional providers include OpenAI, Anthropic, Google, Groq, Mistral,
  DeepSeek, xAI-compatible endpoints, Ollama, Serper, Tavily, SearXNG,
  Crawl4AI/Playwright, Gmail, and user-registered MCP servers.
- **pytest, pytest-asyncio, Ruff, Bandit, pip-audit, Vitest, Testing Library,
  ESLint, TypeScript, Playwright, Knip, npm audit** supplied test/static/audit
  evidence.
- **Prometheus client, request IDs, structured logging, `/livez`, `/readyz`,
  deep health, and runtime snapshots** supply operational visibility.
- **codesign, hdiutil, spctl, Make, PyInstaller** supplied local macOS package
  evidence. This candidate is ad-hoc signed, not notarized.

## Full feature inventory

### Entry, identity, shell, and guidance

- Password-gated login when configured; first-launch Setup Wizard; sample
  notebook onboarding; connection/recovery boundaries.
- Luminous Folio and reversible rollback shells with one `main` landmark,
  adaptive navigation, context lens, utilities, command palette, create menu,
  offline/update banners, guided tips, keyboard routes, and mobile rails.
- Focus mode with persisted preference, command/shortcut/Escape controls,
  reduced-motion handling, accessible exit path, and responsive navigation.
- Seventeen themes, high-contrast variants, wallpaper/aurora treatments,
  typography/display preferences, language selection, and 14 locales.

### Notebook and source lifecycle

- Notebook create/read/update/delete, filtering, recent notebooks, counts,
  sample content, empty/loading/error/populated states, and responsive cards.
- Source import from files, URLs, pasted text, audio, video, PDFs, Office files,
  Markdown, and the broader content-core type set.
- Optional JavaScript-rendered web capture with graceful fallback; local audio
  and video transcription; chunking, embeddings, status/progress, retry, and
  bounded failure responses.
- Source reading, inline PDF, extracted text, metadata, topics, enrichment,
  notebook membership, citation passage location/highlight, delete, and chat.
- Watched capture roots/items with explicit authority and no implicit writes.

### Notes, transformations, and writing

- Notes and AI insights with source/notebook relationships, editing, search,
  enrichment, and generated summaries/topics.
- Named reusable transformations over sources, custom prompts, and outputs.
- SkillOpt prompt optimization with training/validation examples, scoring,
  bounded improvement rounds, comparison, and explicit apply.
- Rich Markdown/math editing, validated structured artifact edits, revisions,
  and deterministic rendering.

### Grounded chat, Ask, search, and memory

- Notebook/source chat with streaming, cancellation, session history,
  suggested questions, per-source inclusion, context transparency, citations,
  jump-to-highlight, and grounded refusal behavior.
- Whole-library Ask and semantic/vector search with retrieve-then-synthesize,
  cited output, HNSW indexes, and ungrounded-answer guardrails.
- Closed-loop memory extraction/recall with retention/confidence/sanitization
  bounds and failure isolation.
- Native web-search failover and normalized evidence receipts when configured.
- MCP tool picker, per-turn suppression, schema-aware tool binding, bounded
  invocation/result projection, and fail-soft optional tools.

### Evidence Studio and research artifacts

- Evidence Studio over notebook/upload/link/mixed inputs with privacy,
  readiness, model-routing, approval, generation, and revision gates.
- Reports, briefings, study guides, Course Packs, FAQs, timelines, flashcards,
  quizzes, tables, mind maps, slide decks, infographics, podcast outlines, and
  research runs.
- Provider-neutral typed documents, bounded JSON repair, canonical Markdown,
  backward-compatible payloads, validation receipts, and structured PATCH.
- Editable PPTX, PDF, PNG, JSON/Markdown exports; local slide/audio Video
  Overview with MP4/VTT; path-contained streaming and atomic promotion.
- Evidence-quality evaluation, latest/batch retrieval, claim-review drawer,
  Chat/Studio/Artifact Rail surfacing, status polling, keyboard drawers, and
  bounded 100-item client adoption.

### Podcasts and audio

- Episode list and Podcast Studio; multi-speaker profiles, language, short /
  medium / long length, per-episode instructions, outline generation/editing,
  explicit review/approval, transcript/audio/combine stages, progress,
  cancel/resume/retry/regenerate, and completed-episode playback.
- Local Piper support, token-budget fail-fast behavior, persisted retry input,
  compact storyboard ordering/actions, and accessible production review.

### Knowledge workspace and external vaults

- Read-only Obsidian/Logseq-compatible mount registration, explicit root
  approval, scanning, watchers, parser status, source fingerprints, provenance,
  trust replay, and write-policy visibility.
- Knowledge reader/editor layouts, notebook index, bookmarks/folders,
  workspaces, random/daily notes, backlinks, graph edges, mind map, named
  spaces, overlay notes, and conflict/recovery surfaces.
- Restart-bound unified projection/backfill with equivalence spaces, idempotent
  trust import, source-hash preservation, and no external writes in proof.

### Study and review

- Study cards, due scheduling, FSRS review state, flashcards/quizzes from
  artifacts, and progress retention.
- Evidence quality badges, claim receipts, unavailable/loading/failed/empty/
  complete states, and one-item/latest or bounded batch review.

### Local models, providers, and routing

- GGUF, MLX, and Ollama inventory; managed Hugging Face downloads; verified
  snapshot installation; hot-swap; health; roles; route plans; benchmarks;
  resource profiles; memory limits; recommendations; and bounded job history.
- Immutable Hugging Face revisions and provenance sidecars; archive and digest
  validation; atomic downloads; existing-install preservation.
- Encrypted cloud-provider credentials, environment detection, defaults,
  offline substitution, smart routing, network status, and fail-closed privacy.

### Plugin system

- MCP is the supported extension architecture: authenticated add/edit/delete,
  URL policy, priority, enable/disable, per-conversation suppression,
  discovery/test, tool schema projection, execution, timeouts, result budgets,
  cache bounds, lifecycle isolation, and UI status.
- The final outbound transport disables redirects, validates authority,
  resolves once, pins approved IP destinations at connection, preserves TLS
  SNI/authority, permits explicit IPv4/IPv6 loopback plugins, and rejects
  link-local/mapped-link-local/unsafe addresses.
- Developer documentation and a loopback FastMCP example demonstrate two
  tools, startup, registration, testing, disable/delete, and stopped-server
  isolation. There is deliberately no file-system auto-loader that executes
  arbitrary plugin code merely because a file exists.

### Settings, operations, backup, and desktop

- Settings for network/offline, source enrichment, observability, API keys,
  models, MCP, launcher preferences, themes/display, routing, and updates.
- Runtime snapshot and Recovery Center with redacted readiness, startup stages,
  local backup/provenance, database/migration state, relaunch, and copy-safe
  diagnostics.
- Atomic backup/restore, SHA-256 manifests, auto-export visibility, database
  corruption detection, backup-first repair, and Repair & Restart.
- Native Supervisor for SurrealDB, API, worker, Next, memory, embeddings/chat,
  Whisper, Piper, and runtime acquisition; graceful cleanup and isolated roots.
- CLI/command handlers for notebooks, sources, transformations, podcasts,
  studio, embeddings, and prompt optimization plus retained compatibility
  aliases/migrations.

## Changes made in this pass

### Bugs fixed

- Bounded the optional rate limiter's per-client table and amortized global
  pruning without changing disabled/default or response behavior.
- Made MCP malformed servers/tools fail independently; fixed stored-row SSRF,
  redirect-to-link-local, and DNS-rebinding paths at the connection boundary;
  preserved IPv4/IPv6 loopback plugins.
- Quoted detached macOS relaunch arguments so metacharacters cannot enter shell
  source; preserved restart semantics.
- Added latest/batch evidence evaluation and repaired a native nested-query
  defect; preserved typed HTTP errors instead of converting them to 500.
- Repaired asynchronous evidence-query test isolation and bounded client batch
  adoption/polling.
- Fixed `/config` protocol/host validation, malformed inputs, and trusted
  forwarding behavior without changing the route response contract.
- Repaired visual and accessibility defects across compact notebook cards,
  Sources, Knowledge, Podcasts, Studio, API Keys, Smart Routing, local-model
  controls, transformations, sidebar utilities, dialog focus return, duplicate
  headings/IDs, and default/rollback route landmarks.

### Security and supply chain

- Removed the tracked credential-history file and ignored future copies. Git
  history was not rewritten and external credential revocation is not claimed.
- Added explicit runtime archive budgets, path/link/type validation, streaming
  tar validation, digest verification, HTTPS manifest policy, unique staging,
  and atomic promotion while retaining verified existing runtimes.
- Pinned Hugging Face installs to immutable commit revisions and bounded local
  model job registries/history.
- Raised resolvable Python and npm dependency floors; full npm production/dev
  audit is zero. Pillow remains below 12 because the podcast dependency chain
  requires it and is disclosed below.

### Performance

- Changed rate-table cleanup from an every-request global scan to an amortized
  cadence while still cleaning the current client's deque.
- Bounded MCP discovery, schema depth/items, content blocks, text/binary totals,
  cache size, timeouts, servers, and tools before materialization.
- Bounded runtime download registries and terminal-job retention; added socket
  inactivity limits and deterministic pruning.
- Replaced evidence-review N+1 client requests with bounded latest/batch API
  paths and capped/polled active evaluation state.
- Measured large Next route bundles but did not perform speculative splitting;
  the desktop serves them locally and no interaction regression was established.

### Code quality and completeness

- Removed confirmed dead `ThemeToggle` and unused auth/common type modules;
  retained documented/runtime-referenced Knip exceptions.
- Reconciled dependency declarations with actual imports and removed unused
  packages; lockfiles are reproducible.
- Reconciled exact identity/rebrand selectors after legitimate line/context
  changes; unexpected and stale identity counts are zero.
- Replaced broad browser API catch-alls with explicit typed fixtures and a
  ledger that fails on unmatched same-origin API calls.
- Searched TODO/FIXME/HACK/XXX and classified remaining matches as test tokens,
  historical plans, upstream/vendor comments, or intentionally deferred release
  boundaries—not half-wired active product features.

### Plugin system

- Completed the existing MCP architecture instead of introducing a second
  in-process loader: persistent enable/disable UI, priority/reordering, bounded
  discovery/invocation, hostile-response projection, exact URL policy, pinned
  transport destinations, lifecycle failure isolation, docs, and a runnable
  local example.

### Visual and UX polish

- Audited 19 dashboard routes at 320, 768, 1024, and 1440 pixels in both Folio
  and rollback builds (152 route visits), plus login/setup at all four widths.
- Added representative loading, empty, populated, error/recovery, keyboard,
  focus visibility/order, dialog return, reduced-motion, half-width responsive
  proxy, touch-target, overflow, console, external-request, and API-ledger proof.
- Enforced exactly one visible `main` landmark per route in both shells.
- Tightened clipped-control checks to catch partial clipping; only the marked
  Sources table may scroll horizontally, and the gate proves that container is
  fully bounded, genuinely scrollable when exempting, each control becomes
  reachable, and scroll position is restored.
- Refreshed only inspected, intentional notebook/theme visual baselines.

## Verification evidence

| Gate | Final evidence |
|---|---|
| Backend hermetic | **3,981 passed, 1 skipped, 16 warnings** in the authoritative package precondition run. A repeated host-load run had two 8-second parser budget failures; bounded idle reproduction passed **8/8**. |
| Ruff | Passed across repository and all final security paths. |
| Product identity / rebrand | **141 passed**; audit `unexpected_active_identity=0`, stale allowlist empty. |
| Desktop | **823 passed, 2 skipped** (warnings were dependency/deprecation/runtime notices). |
| Frontend unit | **207 files, 1,487 tests passed** before final bounded repairs; final changed suites additionally passed. |
| Frontend static | ESLint, `tsc --noEmit`, default and rollback Next builds (**23/23 routes**), and feature-build contract passed. |
| Mocked browser | Full default matrix **54 passed, 4 intentional flag-only skips** before expanded audit. Final expanded all-screen default **7/7** and exact rollback **7/7**. |
| Visual audit | 19 routes × 4 widths × 2 shells, login/setup widths, representative states/keyboard/focus/scroll checks passed; inspected visual sets passed. |
| MCP security | Final focused/adjoining suite **71/71**; redirect, DNS pinning, unsafe address, IPv4/IPv6 loopback, malformed projection, timeout, and fail-soft cases passed. |
| Real SurrealDB | Knowledge/vault/evaluation integration **50 passed**; MCP/security integration **36 passed**. |
| Unified knowledge | Prepare returned designed restart barrier **5**; real Supervisor restart; verify returned **0** with hashes/fingerprints and trust replay preserved. |
| Dependency audit | npm production and full audits: **0 vulnerabilities**. pip-audit: Pillow-only residual documented below. |
| Static security | Bandit: **0 high**, 49 reviewed medium/low-confidence policy/build/query findings; no exploitable injection reproduced. |
| Package | arm64 app and DMG built; package-content verifier, deep/strict ad-hoc codesign, and `hdiutil verify` passed. DMG SHA-256 `e42b04baecc4fb4297ae79c5c41129ed6f2123f78eabc5fad4708c85f86770e7`. |
| Installed smoke | Fresh app installed recoverably; authenticated runtime/settings/MCP/frontend checks passed; MCP add/test/update/delete passed; owned children/listeners cleaned. |
| Independent review | Final repair range **APPROVED** with no high/important finding. OCR passed; structural graph evidence was unavailable/degraded, so direct source/diff/test review governed. |

## Ranking

| Dimension | Score | Rationale |
|---|---:|---|
| Functionality | **9.4/10** | Broad research, knowledge, studio, podcast, model, vault, study, and plugin workflows are implemented and heavily exercised; external-provider breadth prevents literal exhaustive live proof. |
| Code quality | **9.0/10** | Strong typed boundaries, regression coverage, bounded projections, and clearer extension contracts; the inherited codebase remains large and retains compatibility complexity. |
| Performance | **8.8/10** | Confirmed unbounded registries/N+1/prune paths were fixed and measured; large local route bundles and load-sensitive parser budgets remain optimization targets. |
| UX / visual polish | **9.4/10** | Both shells, canonical widths, states, landmarks, focus, motion, target sizes, and clipping have deterministic coverage; real 200% zoom and native human review remain separate. |
| Completeness | **9.2/10** | MCP plugins, evidence review, config, docs/example, dead-code classification, and all active TODO categories are closed or explicitly bounded. |
| Production readiness | **8.7/10** | Source, real-DB, native lifecycle, package, recoverable install, and smoke evidence are strong; notarization, clean-machine, hosted CI, and one dependency exception remain. |

**Overall grade: A- (9.1/10).** This is a high-quality local release
candidate suitable for continued internal/ad-hoc use. A public macOS release
should wait for signing/notarization and the explicit risk actions below.

## Remaining risks and recommendations

1. **Pillow dependency exception.** Pillow 11.3.0 retains 25 published audit
   records. The resolvable fix requires Pillow 12+, but the current podcast
   chain constrains MoviePy to Pillow `<12`. Replace/upgrade that upstream chain
   or isolate affected media parsing before a public release; do not force an
   incompatible override.
2. **macOS distribution.** The app is ad-hoc signed. `spctl` rejection is
   expected; notarization, Developer ID signing, Gatekeeper acceptance, and a
   clean-machine install remain required for public distribution.
3. **Credential history.** The tracked credential-history file was removed,
   but prior Git objects may retain its contents. Rotate any affected secrets
   and perform a separately authorized history rewrite if the repository will
   be shared.
4. **Process-argument exposure.** An unrelated process was observed carrying a
   secret-like value in its command arguments. The value is intentionally not
   recorded here. Rotate it and use environment/file or OS keychain delivery.
5. **External MCP trust.** Network destinations, redirects, DNS, projections,
   timeouts, and result sizes are bounded, but an external MCP server remains a
   user-authorized trust boundary—not an OS sandbox.
6. **Authentication configuration.** Packaged smoke proved authenticated and
   unauthenticated responses with an explicit password. A launch without that
   environment setting leaves password middleware disabled by current design;
   public installers should guide or enforce first-run credential setup.
7. **Performance budgets.** Two large single-line vault parser tests can exceed
   their strict 8-second thresholds under severe concurrent host load while
   passing idle. Profile and optimize token/offset scanning if this hardware
   routinely operates under sustained pressure.
8. **Proof boundaries.** Real provider credentials, every large local model,
   real content generation across all artifact formats, native VoiceOver,
   actual browser 200% zoom, notarized distribution, hosted CI, push, merge,
   and clean-machine acceptance were not claimed.
9. **Tooling evidence.** Open Code Review/OCR supplied review evidence. The
   local Code Review Graph was absent or returned no usable flow/community
   evidence at final review, so direct source/diff/test inspection governed.

## Touched-file justification appendix

Every path in `4c8b5a3d..a18d9c82` is accounted for below.

### Repository, reports, and dependency manifests

- `.gitignore` — prevents re-tracking the removed credential-history file.
- `.superpowers/sdd/all-screen-visual-audit-report.md` — records exact dual-shell
  visual scope, defects, evidence, scroll policy, and proof limits.
- `.superpowers/sdd/evidence-review-completeness-report.md` — records evidence
  batch/UI adoption, tests, and native-query repair.
- `.superpowers/sdd/frontend-completeness-polish-report.md` — records config,
  MCP UI, locales, dead-code classification, and browser evidence.
- `.superpowers/sdd/runtime-supply-performance-report.md` — records archive,
  checksum, immutable-revision, registry, and performance receipts.
- `README.md` — aligns current screenshots, locale count, and feature/docs links.
- `pyproject.toml`, `uv.lock` — raise resolvable Python security floors, retain
  the documented Pillow exception, pin build tooling, and lock exact results.
- `frontend/package.json`, `frontend/package-lock.json` — align direct imports,
  remove unused packages, update safe transitive versions, and produce zero
  npm audit findings.
- `scripts/rebrand-allowlist.json`, `scripts/rebrand_audit.py` — reconcile only
  exact compatibility/documentation anchors and coverage digests after scoped
  edits; preserve zero unexpected/stale identity.

### Backend, repositories, MCP, and local models

- `api/rate_limit.py` — bounds client state and amortizes cleanup.
- `api/routers/evaluations.py` — adds bounded latest/batch evaluation access and
  preserves typed HTTP failures.
- `api/routers/local_models.py` — exposes immutable revision/provenance fields
  within existing response boundaries.
- `api/routers/mcp.py` — uses the shared lower-layer MCP URL policy for CRUD and
  probes while preserving shape-stable failure responses.
- `deeper_notebook/evaluation/repository.py` — implements bounded notebook/item
  latest/batch queries and correct native Surreal ownership selection.
- `deeper_notebook/graphs/chat.py` — bounds server/tool discovery, schemas,
  disabled-name filters, tool results, and fail-soft optional plugin behavior.
- `deeper_notebook/mcp/client.py` — enforces timeouts/result budgets and injects
  the safe no-redirect, DNS-pinned transport factory.
- `deeper_notebook/mcp/registry.py` — fixed-field, finite, fail-soft enabled
  server projection without hostile mapping materialization.
- `deeper_notebook/security/mcp_transport.py` — centralizes canonical MCP URL,
  address, redirect, DNS receipt, pinned-connect, authority, TLS/SNI, and
  IPv4/IPv6 loopback policy.
- `deeper_notebook/local_models/benchmarks.py` — bounds terminal benchmark job
  history and lookup work.
- `deeper_notebook/local_models/downloader.py` — uses immutable revisions,
  bounded registries, provenance receipts, and safe download lifecycle.
- `deeper_notebook/local_models/snapshot_installer.py` — validates revision,
  staging, archive layout, and atomic install/preservation.

### Desktop, runtime supply chain, and tests

- `desktop/bootstrap.py` — applies explicit archive validation during bundled
  runtime extraction while preserving valid symlinked layouts.
- `desktop/build/archive_validation.py` — supplies finite member/name/link/byte
  budgets and traversal/type/link containment checks.
- `desktop/build/fetch_runtimes.py` — enforces HTTPS, manifest SHA-256, socket
  timeout, unique staging, validation, and atomic replacement.
- `desktop/build/runtimes.toml` — records verified runtime digests/metadata.
- `desktop/window.py` — quotes detached relaunch arguments as positional shell
  parameters, preventing bundle-path interpolation.
- `desktop/tests/test_window.py` — proves relaunch paths with metacharacters and
  preserves window/bridge contracts.
- `desktop/tests/test_runtime_supply_chain.py` — RED/GREEN coverage for archive
  traversal, links, types, limits, URLs, hashes, staging, and real layouts.

### Documentation and plugin example

- `docs/5-CONFIGURATION/index.md`, `docs/5-CONFIGURATION/mcp-integration.md` —
  link to the canonical plugin architecture and clarify configuration authority.
- `docs/7-DEVELOPMENT/index.md`, `docs/7-DEVELOPMENT/mcp-plugin-architecture.md`
  — document extension points, registration, lifecycle, isolation, limits,
  failure behavior, and why no arbitrary-code loader exists.
- `examples/README.md`, `examples/mcp_local_streamable_http.py` — add the
  loopback FastMCP example and exact run/register/test/stop flow.
- `history.txt` — deleted because it contained credential history and had no
  legitimate runtime purpose.

### Frontend browser proof, fixtures, and snapshots

- `frontend/e2e/all-screen-visual-audit.spec.ts` — dual-shell route/viewport,
  state, focus, landmark, touch, clipping, scroll reachability, hostile-host,
  request-ledger, console, and responsive-proxy acceptance.
- `frontend/e2e/evidence-review-completeness.spec.ts` — Chat batch and Studio
  latest evidence plus keyboard drawer lifecycle and exact request proof.
- `frontend/e2e/mcp-settings.spec.ts` — add/toggle/test/failure/mobile MCP UI
  lifecycle with request and console assertions.
- `frontend/e2e/fixtures/luminous-folio.ts`,
  `frontend/e2e/fixtures/research-workbench.ts` — deterministic typed API/state
  fixtures, explicit unmatched-request ledger, and stable onboarding state.
- `frontend/e2e/focus-mode-rollback.spec.ts`,
  `frontend/e2e/luminous-folio-rollback.spec.ts` — exact flag-only rollback
  proof and gating under the correct build.
- `frontend/playwright.config.ts` — serializes the stateful mocked matrix and
  keeps native/device proof owners separate.
- Seven `frontend/e2e/luminous-folio-visual.spec.ts-snapshots/notebooks-*.png`
  files — inspected intentional visual baselines for Archive Paper, Deep Ocean,
  high-contrast dark/light, and Research Core desktop/mobile variants.

### Frontend routes and route handlers

- `frontend/src/app/config/route.ts`, `route.test.ts` — strict scheme/authority
  parsing, trusted loopback configuration, hostile inputs, and stable output.
- `frontend/src/app/(dashboard)/notebooks/components/NotebookCard.tsx` — prevents
  title/header min-content overflow.
- `NotebookList.tsx`, `NotebookList.test.tsx` — avoids unusable three-column
  cards inside the narrower Folio content track.
- `notebooks/page.tsx`, `notebooks/page.test.tsx` — stable dialog trigger focus
  return and loading/ready mapping.
- `podcasts/studio/page.tsx` — restores the route's single visible heading.
- `settings/api-keys/page.tsx` — constrains model/routing selects and cells at
  compact widths.
- `settings/local-models/page.tsx`, `page.test.tsx` — removes duplicate heading,
  constrains controls, and preserves landmark coverage.
- `settings/mcp/page.tsx`, `page.test.tsx` — persistent accessible enable/disable,
  mutation guards, responsive rows, translated labels, and failure isolation.
- `setup-wizard/page.tsx`, `page.test.tsx` — points recovery to a live settings
  route and proves the setup landmark/heading contract.
- `sources/page.tsx`, `page.test.tsx` — responsive columns/title layout and the
  sole explicit, auditable horizontal-scroll marker.
- `studio/page.test.tsx` — verifies default/rollback landmark ownership.
- `transformations/page.tsx`, `page.test.tsx` — mode-correct route frame and
  compact action layout.

### Frontend shells, folios, navigation, and knowledge layout

- `frontend/src/components/auth/LoginForm.tsx` — promotes the visible sign-in
  title to the page's semantic `h1`.
- `frontend/src/components/layout/AppShell.tsx`, `AppShell.test.tsx` — makes the
  rollback shell a neutral container so each route owns exactly one `main`.
- `AppSidebar.tsx`, `AppSidebar.test.tsx` — full-width compact utility wrappers,
  keyboard/mobile reachability, and target-size regression proof.
- `deeper-notebook/folio/FolioRouteFrame.tsx`, `folio.css` — route-owned `main`
  in both builds plus compact wrapping/containment.
- `ResearchCoreFolioFrame.tsx`, `horizon/IntelligenceHorizon.tsx` — preserve
  constrained workspace/recent-card layouts.
- `route-frames/KnowledgeRouteFrames.test.tsx` — one-main parity for knowledge
  frames in both shells.
- `shell/AdaptiveNavigator.tsx` — unique active route IDs and accessible nav.
- `shell/shell.css`, `shell.test.tsx` — responsive focus/title/rail/sidebar/
  banner/Research Core layout and pointer behavior with contract tests.
- `studios/EvidenceStudioFolio.tsx`, `studios.test.tsx` — route-owned main and
  exactly one landmark in default/rollback.
- `vault/KnowledgeExplorer.tsx` — removes duplicate-current IDs and preserves
  compact navigation behavior.
- `vault/KnowledgeWorkspaceLayout.tsx`, `.test.tsx`, `vault.css`,
  `ResearchCoreVisualSystem.test.tsx` — constrain nested grids/toolbars/panes,
  restore compact one-column specificity, and prove reachable controls.

### Frontend evaluation, chat, artifacts, and podcasts

- `ArtifactRail.tsx`, `ArtifactRail.test.tsx` — adds bounded evidence-review
  entry points and keyboard-safe artifact actions.
- `evaluation/EvidenceReview.tsx`, `.test.tsx` — implements semantic latest/
  batch evidence states and keyboard drawer behavior.
- `ClaimReviewDrawer.tsx`, `EvidenceQualityBadge.tsx` — surface claim receipts,
  status, and accessible quality summaries without changing artifact schemas.
- `source/ChatPanel.tsx` — adopts bounded evidence batches, MCP picker updates,
  and compact header constraints.
- `ChatPanel.cancel-run.test.tsx`, `ChatPanel.mcp-picker.test.tsx`,
  `ChatPanel.evidence-review.test.tsx` — isolate QueryClient state and prevent
  cancellation/MCP/evidence regressions.
- `lib/api/evaluations.ts`, `evaluations.completeness.test.ts` — typed latest/
  batch clients, finite decoding, and compatibility tests.
- `lib/hooks/use-evaluation.ts`, `use-evaluation.completeness.test.tsx` — bounded
  polling/dedup and pending/running behavior.
- `lib/hooks/useNotebookChat.ts` — preserves chat state while exposing evidence
  and cancellation data without duplicate calls.
- `podcasts/EpisodesTab.tsx`, `.test.tsx` — wraps compact action groups.
- `podcasts/OutlineStoryboard.tsx` — wraps storyboard ordering controls.
- `podcasts/PodcastStudio.tsx`, `.test.tsx` — accessible heading, compact review
  text, and studio parity.
- `podcasts/TurnIntoPodcastAction.tsx`, `.test.tsx` — enforces an accessible
  compact target floor.
- `notebooks/CreateNotebookDialog.tsx` — explicit Escape close and deterministic
  focus return under both shells.

### Frontend settings and local-model panels

- `local-models/LocalExecutionPolicyPanel.tsx`, `.test.tsx` — makes Save
  responsive at compact widths.
- `local-models/RoleBenchmarkPanel.tsx` — prevents clipped benchmark actions.
- `settings/SmartRoutingPanel.tsx` — constrains provider select/grid cells at
  phone widths.
- `components/common/ThemeToggle.tsx` — deleted after exact reference analysis
  confirmed it was orphaned; active theme controls remain elsewhere.
- `lib/types/auth.ts`, `lib/types/common.ts` — deleted after symbol/import proof
  confirmed no runtime or public barrel consumer.

### Locales and visual-request policy

- All 14 `frontend/src/lib/locales/*/index.ts` catalogs — add parity-complete MCP
  enable/disable/status strings; 13 non-English catalogs use native labels.
- `frontend/src/lib/visual-audit-request-policy.ts`, `.test.ts` — exact loopback
  hostname classifier with hostile suffix-lookalike canaries.

### Backend and integration regression files

- `tests/test_rate_limit_table_bounds.py` — client-cap and prune-cadence RED/
  GREEN contracts.
- `tests/test_mcp_security_bounds.py` — hostile mappings/iterables, finite
  tools/schemas/content/cache/env, and fail-soft registry behavior.
- `tests/test_mcp_outbound_ssrf_boundary.py` — initial/stored/redirect/DNS-pin,
  authority, unsafe IPv4/IPv6, and loopback transport regressions.
- `tests/test_phase2_mcp_integration.py` — isolates tool-loop memory and extends
  MCP registration/discovery/invocation compatibility evidence.
- `tests/test_evaluation_completeness.py` — latest/batch, malformed identifiers,
  limits, and selector preservation.
- `tests/integration/test_evaluation_repository.py` — real Surreal query proof.
- `tests/test_local_model_snapshot_installer.py` — immutable revision, receipts,
  staging, and archive preservation.
- `tests/test_runtime_supply_performance.py` — HTTPS/digest/timeout, immutable
  model metadata, and finite job registry tests.

## Release decision

The candidate is accepted for local/ad-hoc release at `a18d9c82`. The installed
app is `/Applications/Deeper Notebook.app`; the prior app remains recoverable at
`/Applications/Deeper Notebook.app.backup-task20260811-165545`. Public release
remains gated by dependency-exception resolution or explicit risk acceptance,
credential rotation/history handling, Developer ID signing/notarization,
Gatekeeper and clean-machine proof, and hosted CI/merge/push ownership.
