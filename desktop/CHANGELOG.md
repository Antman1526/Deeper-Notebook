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

## Unreleased — v0.7.36 → v0.7.123 (in flight)

- **v0.7.123** 🔒 **PBKDF2 key-derivation option for credential
  encryption.** Adds an opt-in stronger KDF for the
  `OPEN_NOTEBOOK_ENCRYPTION_KEY` passphrase → Fernet-key derivation.

  **Threat model:** The original v0.7.0 derivation was a single
  SHA-256 of the passphrase (~instant). If an attacker exfiltrates
  the SurrealDB file (containing encrypted credentials), they can
  brute-force weak passphrases at billions of guesses per second.
  PBKDF2-HMAC-SHA256 with 600,000 iterations adds ~250ms cost per
  guess — slows offline brute-force by ~9 orders of magnitude.

  **New env knob:** `ONP_ENCRYPTION_KDF` = `sha256` (default,
  back-compat) | `pbkdf2` (recommended). 600,000 iterations is the
  OWASP 2024 recommendation for PBKDF2-HMAC-SHA256.

  **Migration design — `get_multi_fernet()` tries both KDFs:**

  - **New encryption** uses whichever KDF the env knob selects.
  - **Decryption** builds a MultiFernet wrapping each configured
    key × each known KDF, in preference order. Existing
    sha256-encrypted data continues to decrypt after migrating to
    pbkdf2 — no re-encrypt sweep required.
  - **Rotation** (the v0.7.17 `_ENCRYPTION_KEYS` plural form) still
    works — the matrix is `(keys × kdfs)` so any combination
    decrypts.

  **Deterministic salt:** PBKDF2 uses a deterministic 16-byte salt
  derived from the passphrase + a version-tagged constant
  (`onp-kdf-salt-v1`). Required for the derivation to be
  reproducible across restarts (we don't store a per-key salt blob
  anywhere). The version tag allows future salt-scheme rotation
  without breaking existing data.

  **No new dependency** — uses Python stdlib `hashlib.pbkdf2_hmac`.
  Argon2id would be marginally stronger but requires `argon2-cffi`
  (~150KB binary wheels) and a separate migration path. Deferred to
  v0.7.124+ if there's demand.

  **9 new tests** in `tests/test_encryption_kdf_v0_7_123.py`:
  default-is-sha256, pbkdf2-mode-uses-pbkdf2, deterministic
  derivation, unknown-KDF actionable error, round-trip × 2 KDFs,
  sha256→pbkdf2 migration, pbkdf2→sha256 reverse, rotation +
  cross-KDF combined.

  Backend suite: 552 → **561** (+9). Ruff clean. Argon2id KDF
  remains deferred (would need new `argon2-cffi` dep).
- **v0.7.122** 🔒 **Dependency CVE remediation: 16 backend + 7 frontend
  → 0 frontend, 8 backend remaining (upstream-blocked).** Ran
  `pip-audit` + `npm audit` against the locked dependency tree and
  remediated everything resolvable without breaking the app.

  **Backend** (`pyproject.toml` + `uv.lock`):
  - `langgraph`: `>=1.0.5` → `>=1.0.10` (CVE-2026-28277)
  - `python-dotenv`: `>=1.0.1` → `>=1.2.2` (CVE-2026-28684)
  - Added explicit pins for transitive deps with published fixes:
    - `langchain-core>=1.3.3` (CVE-2026-44843)
    - `langsmith>=0.8.0` (CVE-2026-45134)
    - `lxml>=6.1.0` (CVE-2026-41066) — XML parser hardening
    - `urllib3>=2.7.0` (CVE-2026-44431 + CVE-2026-44432) — HTTP client
    - `python-multipart>=0.0.27` (CVE-2026-42561) — file-upload library
  - **Remediated: 8 of 16 backend CVEs eliminated.**

  **Backend NOT remediated (upstream-blocked):**
  - `pillow 11.3.0` → 6 CVEs (CVE-2026-25990 + 40192 + 42308 + 42309
    + 42310 + 42311). Fix requires `pillow>=12.1.1` but
    `podcast-creator==0.12.0` pins `pillow<12.0`. Lower impact in
    our pipeline: pillow only sees images that content-core
    extracted from user-uploaded PDFs/DOCX — constrained attack
    surface. Will revisit when podcast-creator publishes a newer
    version compatible with pillow>=12.
  - `pip 26.0` → CVE-2026-3219, CVE-2026-6357 (dev tool only — not
    in runtime; only relevant to operators running `pip install`).

  **Frontend** (`frontend/package.json` + `package-lock.json`):
  - `npm audit fix` auto-resolved 5 of 7 CVEs (Next.js middleware
    bypass × 4 + `ws` uninitialized-memory disclosure) by bumping
    the affected packages to their published-fix versions.
  - Added `overrides.postcss: "^8.5.10"` to force the
    Next.js-bundled postcss to the fixed version
    (GHSA-qx2v-qp2m-jg93 — XSS via unescaped `</style>` in CSS
    stringify output). The npm-suggested "fix" of downgrading to
    `next@9.3.3` was unacceptable (would lose Next.js 16 App
    Router); `overrides` is the canonical npm mechanism for
    forcing a nested transitive without touching the parent.
  - **Remediated: 7 of 7 frontend CVEs eliminated. `npm audit`
    reports `found 0 vulnerabilities`.**

  **Net cycle delta:**
  - 23 CVEs detected → 8 remaining (all upstream-blocked or dev-only).
  - 65% reduction; 100% of the runtime-exploitable findings closed.
  - Two HIGH-severity Next.js middleware bypasses fixed (directly
    relevant to v0.7.117's Setup Wizard middleware).

  **Tests pass after upgrade:** 552 backend (unchanged) + 65 frontend
  (unchanged). Ruff clean. tsc clean.
- **v0.7.121** 🔒🎨 **Security headers expansion + cookie hardening +
  visual a11y polish.** Follow-up to v0.7.120's middleware
  groundwork. Two axes shipped together:

  **Security:**

  1. **HSTS conditional on HTTPS** — `Strict-Transport-Security:
     max-age=63072000; includeSubDomains` set ONLY when the request
     scheme is `https://`. Plaintext HTTP responses get no HSTS
     header (sending it on HTTP would teach the browser to
     force-upgrade future requests even when no TLS terminator
     exists). Respects `X-Forwarded-Proto` via uvicorn's
     `--proxy-headers`.

  2. **Permissions-Policy** denies browser features the API has no
     business using: camera, microphone, geolocation, payment,
     accelerometer, gyroscope, USB, MIDI, display-capture, XR. 14
     features explicitly disabled.

  3. **X-XSS-Protection: 0** — modern best practice. The legacy
     IE-era heuristic filter caused universal-XSS in older browsers
     and has zero benefit in modern ones; explicitly disabling tells
     browsers not to attempt heuristic sanitization.

  4. **Wizard cookie hardened** — `wizard_completed` cookie now
     written with `SameSite=Strict` (was Lax) and `Secure` (when on
     HTTPS, detected via `window.location.protocol`). Skipped on
     `http://localhost` to keep dev unbroken (browsers reject
     Secure cookies on plaintext localhost).

  5. **Dangerous-config ERROR at startup** — when `CORS_ORIGINS='*'`
     AND `OPEN_NOTEBOOK_PASSWORD` is unset, the API logs an
     ERROR-level message naming the foot-gun. That combo means
     anyone on the internet can read/write every notebook. Existing
     v0.6.7 WARNING for just-CORS-default was preserved; the new
     ERROR fires only on the dangerous overlap.

  **Visual (accessibility):**

  6. **`prefers-reduced-motion` respect** in `globals.css` —
     slams all animations + transitions to ~0ms duration when the
     user has the OS-level reduce-motion setting on. Satisfies WCAG
     2.1 SC 2.3.3 (Animation from Interactions). Without this, every
     hover transform, page transition, and shadcn animation ignored
     the user's preference.

  7. **Stronger `:focus-visible` ring** — 3px outline + 2px offset
     for keyboard users. Only applies to `:focus-visible` (keyboard
     focus), not `:focus` (which fires on mouse click). Helps users
     with low vision distinguish the focused element.

  **Audit context (verified clean this pass):**
  - No bare `except:` clauses anywhere
  - No SQL injection via f-string in repo_query
  - No log-secret-leak patterns
  - Password comparison still uses `secrets.compare_digest` (v0.6.7)
  - Zip-symlink rejection still in place (v0.7.117)
  - `rel="noopener noreferrer"` still on external HTML-export links
    (v0.7.118)
  - No frontend `aria-label` regressions on icon-only buttons

  **Tests:** 4 new in `tests/test_middleware_v0_7_120.py`:
  - Permissions-Policy present + names key denials
  - X-XSS-Protection: 0 set
  - HSTS absent on http://
  - HSTS present on https:// with correct max-age + includeSubDomains

  Backend suite: 548 → **552** (+4). Frontend: 65 pass (unchanged,
  no test-affecting changes). Ruff + tsc clean.
- **v0.7.120** 🛠⚡🔒 **Cross-cutting middleware + slow-query log +
  pre-commit.** One focused commit shipping five lightweight wins that
  came out of the post-v0.7.119 audit. ~7 hours of work; high
  signal-to-noise.

  **1. Request-ID correlation** (`api/middleware/request_id.py`):
  Every request gets a UUID4 (or accepts an inbound `X-Request-ID`
  from upstream proxies, capped at 128 chars). The id is set as the
  response `X-Request-ID` header AND bound into loguru's context via
  `logger.contextualize(request_id=...)`. The log format
  (`open_notebook/logging.py`) gained a `req=<id>` column, so every
  log line during a request flow carries the same id. Operators can
  `grep <id>` to follow a single request across files. Helper
  `current_request_id()` lets handler code surface the id in error
  responses or slow-query warnings.

  **2. GZip middleware**: FastAPI's built-in
  `GZipMiddleware(minimum_size=1000)`. Bodies ≥ 1 KB get compressed
  when `Accept-Encoding: gzip` is set (every modern browser + httpx
  client). Free perf win on notebook lists, search results, the
  `/healthz/deep` body, OpenAPI spec.

  **3. Security headers middleware**
  (`api/middleware/security_headers.py`): Defense-in-depth baseline
  on every API response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy:
  strict-origin-when-cross-origin`, and a strict `Content-Security-
  Policy` (`default-src 'none'; script-src 'self'; …`) — skipped on
  `/docs`, `/redoc`, `/openapi.json` because Swagger UI pulls CDN
  resources. Uses set-if-absent semantics so handlers that build
  their own JSONResponse with explicit headers aren't clobbered.

  **4. Slow-query log threshold** (`repo_query` in
  `open_notebook/database/repository.py`): Times every SurrealQL
  query; logs a WARNING when elapsed exceeds
  `ONP_SLOW_QUERY_LOG_MS` (default 500ms). Logs the elapsed time,
  threshold, and a 300-char truncation of the query. The `finally:`
  ensures slow queries that ALSO errored still log — timing info is
  doubly useful when something's broken. Combined with v0.7.114's
  silent memory-recall fall-through, this surfaces which queries are
  actually slow without polluting normal logs.

  **5. Pre-commit hooks** (`.pre-commit-config.yaml`): ruff check +
  ruff format on staged Python files; check-yaml + check-json +
  check-toml + end-of-file-fixer + trailing-whitespace +
  check-merge-conflict + 1 MB file-size cap. Pytest deliberately
  NOT in the gate (too slow); CI runs it. One-time setup: `uv run
  pre-commit install`.

  **Middleware order** (Starlette wraps in reverse of registration):
  CORS (outermost) → RequestID → SecurityHeaders → GZip →
  PasswordAuth (innermost) → handler. Documented inline in
  `api/main.py`.

  **Tests**: 14 new in `tests/test_middleware_v0_7_120.py` —
  5 RequestID (inbound + cap + contextvar + outside-scope fallback),
  4 SecurityHeaders (baseline + CSP on/off docs + idempotent
  handler-overrides), 2 GZip (compress / skip), 3 slow-query
  (warning / silent / error-still-logs).

  Backend suite: **548 pass** (was 534, +14). Ruff clean. New env
  knob `ONP_SLOW_QUERY_LOG_MS` (default 500).
- **v0.7.119** ✅ **Wrap-up: regression-test gaps + maintainer docs +
  frontend polish.** Closes the testing + docs gaps left open after
  the v0.7.88 → v0.7.118 hardening run.

  **Backend:**
  - **`tests/test_transformation_execute_timeout.py`** — 4 new tests
    covering v0.7.95's `/transformations/execute` timeout: 504 with
    env-knob hint, fast-path returns 200, 404 for missing
    transformation, 404 for missing model. Companion to v0.7.108's
    `test_chat_execute_timeout.py`. The 404 tests also cover v0.7.109's
    `except HTTPException: raise` invariant — typed status codes now
    survive the outer `except Exception` block.
  - **`tests/test_studio_e2e_multipage.py`** — 2 graph-level E2E
    tests for the v0.7.89 multi-page Studio pipeline: full
    overview-plus-N-pages plan rendered + saved in render order,
    `note_id` back-compat with the v0.7.105 frontend (points at
    Overview). Mocks at the LLM-provision + content-extract +
    save boundaries — catches state-shape regressions in the four
    stages (_generate_outline → _generate_all_pages →
    _save_notebook_notes → _render_overview_note) that the per-unit
    `test_studio_router.py` tests don't fully cover together.

  **Docs:**
  - **`docs/7-DEVELOPMENT/maintainer-guide.md`** — Plus-specific
    "operational quick-reference" section appended: symptom-→-knob
    table for every timeout / cap added in v0.7.88+, healthcheck
    endpoint summary, export/import endpoint summary, the
    `except HTTPException: raise` invariant explained, release
    checklist, test-suite catalog.

  **Frontend** (landed as the v0.7.119 frontend commit):

  - **Export dialog**: format selector now exposes all six backend
    formats (`folder` / `zip` / `html_folder` / `html_zip` /
    `combined_md` / `combined_html`). New `include_sources` checkbox
    (gated to formats that honour it) and `compression` Select
    (gated to zip variants). Existing `overwrite` retained. Submit
    body now only sends `compression` for zip formats and skips
    `include_sources` for `combined_html` (backend ignores it
    there anyway).
  - **Import dialog** (`ImportNotebookDialog.tsx`, new): dry-run
    preview flow consuming `POST /notebooks/import/preview` then
    `POST /notebooks/import`. Surfaces detected kind badge,
    editable notebook name / description (prefilled from manifest
    hints), notes + sources lists with overview flag (📋), backend
    warnings as a yellow Alert, and new-vs-existing mode selector.
    On success, navigates to the new/target notebook.
  - **Import entry point**: new "Import" button in the notebooks
    list page header, next to "New Notebook".
  - **Bulk vectorize** (`BulkVectorizeButton.tsx`, new): button in
    the Sources column header opens a confirm dialog with the
    `only_missing` checkbox (default true) and POSTs to
    `/notebooks/{id}/vectorize_sources`. Toast surfaces the
    `queued / skipped` tally plus any `warnings[]`.
  - **Setup Wizard auto-advance**: when the first `/healthz/deep`
    response comes back `healthy`, the wizard self-dismisses via
    `router.replace('/')` and sets the wizard-completed cookie +
    localStorage flag. Guarded by a `useRef` so the auto-advance
    only fires once per mount (manual back-navigation won't loop).
  - **DirectoryPicker**: gained a `selectionMode='any'` mode used
    by the Import dialog — single-clicking a file (.zip / .md)
    selects it; folders still navigate as before.
  - **i18n**: ~37 new keys added to all 10 locales
    (`notebooks.export.format.*`, `notebooks.export.compression.*`,
    `notebooks.export.includeSources`, `notebooks.import.*`,
    `notebooks.bulkVectorize.*`). The flat `notebooks.export`
    button-label string was promoted to `notebooks.export.button`
    so the new nested namespace can coexist; callsites updated.
    Locale-parity + unused-key tests pass.

  Test counts (post v0.7.119 backend): 528 → **534** (+6).
  Frontend tests: 57 → **65** (+8: 1 in `ExportNotebookDialog`
  expansion, 2 in `ImportNotebookDialog`, 2 in
  `BulkVectorizeButton`, 2 wizard auto-advance, plus refresh of
  existing export-dialog assertions). `npx tsc --noEmit` clean,
  `npm run lint` clean on touched files.

  **Deferred (truly):**
  - Real-SurrealDB integration test for delete cascade — needs
    test-infra (docker-compose SurrealDB CI fixture). Mocked tests
    in v0.7.116 cover the orchestration logic.
  - README screenshots refresh — requires generating real images
    of the running app; not feasible in a code-change PR.

  **The v0.7.88 → v0.7.118 cycle is now release-ready.** Tag and
  ship.



- **v0.7.118** 🔒 **rel="noopener noreferrer" on external links in HTML
  exports.** Follow-up to v0.7.117's XSS hardening.

  HTML exports (`html_folder`, `html_zip`, `combined_html`) are
  specifically designed to be shared — emailed, dropped into Drive,
  printed to PDF. The rendered `<a href="https://...">` tags had no
  `rel` attribute, which left two small but real risks for recipients:

  1. **Tabnabbing** if the recipient's email client / browser opens
     the export with `target="_blank"`-like behavior — the destination
     site could manipulate `window.opener` and redirect the user's
     browser back to a phishing page.
  2. **Referer leak** when the export is opened locally (file://) and
     the user clicks an external link — the browser would send a
     `Referer: file:///Users/.../...` header to the destination,
     exposing the recipient's local filesystem path.

  Fix: Custom token renderer on markdown-it's `link_open` rule adds
  `rel="noopener noreferrer"` to any link with `http://`, `https://`,
  `mailto:`, or `ftp://` scheme. Internal anchors (`#section`) and
  relative paths (`./other.md`) are left untouched.

  Audit context — also verified clean in this pass:
  - Frontend Setup Wizard middleware has explicit exempt prefixes
    (`/setup-wizard`, `/login`, `/api`, `/_next`) so it can't
    redirect-loop the wizard or block static assets.
  - `Source.delete()` cascade fully cleans up: source_embedding,
    source_insight, reference edges, in-flight commands cancelled,
    uploaded file unlinked with UPLOADS_FOLDER containment check.
  - `Note.delete()` cascades artifact + note_embedding (v0.7.76).

  +1 test (external vs internal link rel attribute). Full suite:
  528 pass (was 527).
- **v0.7.117** 🔒 **XSS hardening + zip-symlink rejection** (two real
  security findings from another audit pass).

  - **XSS via raw HTML in markdown notes** — `_markdown_to_html()`
    (used by v0.7.97 per-page + v0.7.111 combined HTML exports)
    rendered `<script>` and other raw HTML tags VERBATIM. Self-
    hosted single-user is mostly safe (author == user), but the
    combined_html export is specifically designed for share-by-
    email / Drive / link, so a malicious note author could craft
    payloads that execute when a recipient opens the file.

    Fix: pass `html=False` to MarkdownIt constructor AND disable
    both `html_inline` and `html_block` rules. Raw `<script>`,
    `<iframe>`, `<img onerror>`, `<svg onload>`, etc. are now
    rendered as escaped literal text. Legitimate markdown (bold,
    code, tables, lists, blockquotes, real https:// links) still
    works.

  - **Zip-symlink import** — `_validate_archive_member()` blocked
    path-traversal `..` segments but didn't check the Unix mode
    bits. A zip with a symlink "passwords.md" → "/etc/passwd"
    would have its 'content' read as the link-target string —
    silently importing garbage. Not directly exploitable (we
    don't extract to disk) but bad UX.

    Fix: new `_is_regular_file_entry()` discriminator inspects
    the S_IF* bits in `external_attr` and rejects symlinks
    (0o120000), FIFOs (0o010000), devices, sockets. Accepts
    regular files, directories, AND entries with no S_IF* bits
    set (Python `zipfile.writestr` default + DOS-only zips).

  - **Other audit angles verified clean:**
    - Edge-table direction (`reference`/`artifact`/`refers_to`):
      `in=child, out=notebook` consistent across `relate` →
      `get_X` traversals.
    - Password comparison uses `secrets.compare_digest` (v0.6.7
      already, confirmed still in place).
    - Connection pool warmup + shutdown drain still bounded.
    - No `eval`/`exec`/`pickle.loads` on user input.
    - No bare `except:` clauses.

  6 new tests: 3 for the XSS escaping, 2 for symlink rejection,
  1 unit test on the file-type discriminator. Full suite:
  527 pass (was 522).
- **v0.7.117 (frontend)** ✨🎨 **First-launch Setup Wizard consuming
  `/healthz/deep`.** Adds a `useDeepHealth` TanStack Query hook
  (`refetchOnWindowFocus`, 30s stale, axios `validateStatus < 600`
  so both 200 and 503 bodies are read) and a `/setup-wizard` route
  that renders a traffic-light view of the v0.7.112 deep health
  payload: ✅ for `ok: true`, ⚠️ for `missing`/`pending`,
  ❌ otherwise. Per-subsystem "Fix this" buttons deep-link to
  `/settings/models` (embedding + chat) or `/advanced` (command
  registry); database + migrations show the raw error string
  (no in-app fix). "Continue anyway" is disabled when overall
  status is `not_ready` (DB / migrations down — nothing renders
  past this gate) and sets a `wizard_completed` cookie +
  localStorage on click. New `src/middleware.ts` redirects to
  `/setup-wizard` on first launch when that cookie is absent.
  The existing `SetupBanner` is extended to surface a
  dismiss-for-the-session degraded banner pointing back at the
  wizard (suppressed on the wizard route itself to avoid the
  banner echoing the wizard's own card). All 14 new i18n leaf
  keys added to every locale (10/10 parity preserved). 13 new
  vitest tests (4 hook, 5 wizard, 4 banner); full frontend suite:
  58 pass (was 45).
- **v0.7.116** ✨🛠 **Per-provider connection-test timeouts + typing
  modernization + delete-cascade test + docs sync.** Four deferred
  improvements shipped together.

  - **Per-provider connection-test timeouts.** Replaces the v0.7.100
    single global `ONP_CONNECTION_TEST_TIMEOUT_SEC` (30s) with a
    three-tier resolver: per-provider env (`ONP_CONNECTION_TEST_
    TIMEOUT_SEC_<UPPER>`) → global env → per-provider default.
    Defaults: cloud APIs 10-15s, local servers (ollama,
    openai_compatible) 60s for cold-start. Local-bundle Ollama
    users get a working "Test connection" button OOTB.
  - **`typing.List/Dict/Optional` modernization.** Ran ruff with
    UP006 + UP007 — 293 auto-fixes across 13 files. Final non-auto
    fix: `Union[...]` alias in `open_notebook/ai/models.py`
    converted manually. Added `UP006,UP007` to `pyproject.toml`
    permanent rule set so future code stays modernized. Python
    3.10+ supports both PEP 585 generics and PEP 604 unions.
  - **Bulk delete-cascade integration test.** Added
    `tests/test_notebook_delete_cascade.py` with 5 tests covering
    v0.7.107's parallel cascade: every note gets `delete()`, one
    failure doesn't cancel siblings, calls run concurrently (peak
    in-flight > 1), defensive top-level `DELETE artifact` runs
    after the loop, empty notebook is safe. Uses class-level
    monkeypatching (Pydantic v2 doesn't allow instance attr
    assignment) + stubs `repo_query` + `repo_delete` so no real
    SurrealDB is needed.
  - **`docs/5-CONFIGURATION/onp-env-reference.md` sync.** Added 6
    new sections documenting the 16 env knobs introduced in
    v0.7.89-v0.7.115, plus a version-history row for each. Doc
    now matches the README's env-knob table.

  Test count: 517 → 522 backend (+5 delete-cascade tests). Frontend
  Setup Wizard task spawned for the remaining deferred frontend
  work.
- **v0.7.115** 🐛 **Submit-command timeout + defensive Azure migration.**
  Two more audit-uncovered issues.

  - **`CommandService.submit_command_job`** (`api/command_service.py:31`)
    and **`PodcastService.submit_generation_job`**
    (`api/podcast_service.py:103`) — both wrapped `submit_command` in
    `asyncio.to_thread` per v0.7.55 (good — doesn't block event loop),
    but had **no timeout** around the `await`. A hung SurrealDB pool
    or stuck WS handshake would cause the awaiting endpoint to wait
    indefinitely. Wrapped both in `asyncio.wait_for` with
    `ONP_SUBMIT_COMMAND_TIMEOUT_SEC` (default 10s — submits are
    normally <500ms; 10s is generous). Timeout → `ValueError` with
    actionable hint.
  - **`create_credential_from_env`** (`api/credentials_service.py:290`)
    used `os.environ["AZURE_OPENAI_API_KEY"]` (subscript) instead of
    `.get()`. Safe-by-construction today — `check_env_configured`
    gates the branch on all three required env vars being set — but
    a future refactor of `PROVIDER_ENV_CONFIG` could silently turn
    this into a 500. Replaced with `.get()` + explicit `ValueError`
    so the bug surface is closed.
  - Broader audit pass scanned `os.environ[...]` subscript-reads
    across the codebase: only this one was a bare read; the 10 other
    matches are all WRITES (setting env vars from DB credentials in
    `key_provider.py`) which are safe.
- **v0.7.114** 🐛 **Chat-hot-path memory-recall query timeout.**
  Companion to v0.7.113. `_safe_select()` (the helper that runs
  every memory-recall SurrealQL query — recency + semantic both
  fire two queries each) had no timeout. An overloaded connection
  pool, DB pause, or runaway vector-similarity scan could stall
  every chat turn waiting for the pool's own timeout (much longer
  than the 5s budget we want for memory).

  Wrapped with `ONP_MEMORY_RECALL_QUERY_TIMEOUT_SEC` (default 5s).
  Combined with v0.7.113's embed timeout, the whole memory-recall
  path is now bounded by ~15s worst-case before falling through to
  empty.

  README + CHANGELOG updated with the full env-knob inventory + the
  new API surface added since v0.7.87. Test count: 517 backend / 45
  frontend.

  2 new tests (timeout falls through to empty, fast query succeeds).
- **v0.7.113** 🐛 **Chat-hot-path memory-recall embed timeout.**
  `recall_relevant_memory()` runs on every chat turn (`recall_memory`
  orchestrator picks it once memory rows pass the semantic threshold).
  Its `aembed([query])` call had no timeout — a stuck local
  embedding model (cold-start, OOM, misconfigured base_url) would
  delay chat by up to `ONP_CHAT_TIMEOUT_SEC` (300s default before
  v0.7.99's outer wrap fires).

  Wrapped in `asyncio.wait_for(timeout=
  ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC)` (default 5s). On timeout we
  fall through to `recall_recent_memory()` which is DB-only — chat
  loses semantic recall for that turn but doesn't stall. This makes
  the memory feature truly **best-effort** end to end: read path
  matches the v0.7.68/v0.7.70 write path's fire-and-forget posture.

  2 new tests: timeout falls through to recency, fast embed
  completes normally.

  Audit context: scanned the rest of the memory pipeline (writer
  command submission already non-blocking via `asyncio.to_thread`,
  read-only SurrealQL queries already defensive with empty-on-
  failure). This was the last hot-path call without a timeout.
- **v0.7.112** ✨ **Deep healthcheck endpoint (`/healthz/deep`).**
  Existing `/livez` and `/readyz` cover liveness + must-have deps
  (DB, migrations). v0.7.112 adds a deeper probe that lets operators
  answer "is vector search broken?" / "is chat broken?" without
  grepping logs.

  - Probes each subsystem independently with a short timeout:
    - **Database** (must-have, 2s)
    - **Migrations** (must-have, 3s)
    - **Embedding model** (optional, 2s) — needed for vector search +
      chat-with-sources
    - **Chat model** (optional, 2s) — needed for `/chat`, `/studio`,
      `/search/ask`
    - **Command registry** (optional) — needed for async jobs
      (embeddings, podcast generation, source extract)
  - Returns three overall states:
    - `healthy` (200) — all subsystems up
    - `degraded` (200) — optional subsystems missing, must-haves OK
    - `not_ready` (503) — DB or migrations failed
  - Each subsystem report includes an **actionable error string**
    when broken. E.g. missing chat model: "Configure one in
    Settings → Models — without it, /chat, /studio, and /search/ask
    cannot generate responses."
  - Auth-exempt (added to `excluded_paths`) so monitoring tools and
    first-launch wizards can poll without credentials. Same exemption
    rationale as `/readyz`.
  - Audit pass during the build:
    - 0 sync I/O calls in async functions
    - 0 `time.sleep` in async paths
    - 0 unguarded `result[0]` accesses (all `if result:` checked)
    - 0 log-secret-leak patterns (api_key / password / secret never
      f-string'd into log messages)
  - 6 new tests cover healthy / not-ready (DB offline + migrations
    pending) / degraded (missing embedding / missing chat) / auth-
    exempt-status.
- **v0.7.111** ✨ **Combined single-file notebook export.** Two new
  formats: `combined_md` and `combined_html` concatenate every page
  (plus optional sources) into a single file rather than a
  folder/zip of per-page files. Better for share-by-email,
  Drive/Dropbox upload, print-to-PDF from the browser, or import
  into paperless-gpt as one entry.

  - **Markdown variant** (`combined_md`): cover page with notebook
    name + description, table of contents listing every page,
    each note rendered with horizontal-rule separators that act as
    page breaks in print-to-PDF.
  - **HTML variant** (`combined_html`): self-contained HTML5
    document with light/dark CSS, a styled cover page, TOC,
    `<hr class="onp-page-break">` separators, and **print CSS** that
    forces each note onto its own page when the user prints-to-PDF
    via their browser — getting most of the "PDF export" deferred
    item done without bundling weasyprint / wkhtmltopdf.
  - File extension auto-corrected if the caller omits one
    (`/exports/combined` → `combined.md` or `combined.html`).
  - 5 new tests cover happy-path markdown + html, auto-extension,
    include_sources, and directory-target rejection.
- **v0.7.110** 🐛 **Per-request caps + timeouts on bulk endpoints.**
  Audit-uncovered scaling/timeout gaps not present in earlier sweeps.

  - **Bulk vectorize** (`POST /notebooks/{id}/vectorize_sources`)
    capped at `ONP_BULK_VECTORIZE_MAX_SOURCES` sources per call
    (default 500). Truncation surfaces an actionable warning naming
    the env knob, so a 10k-source notebook can't pin the request.
  - **Discover models** (`POST /credentials/{id}/discover`) wrapped
    in `asyncio.wait_for` with `ONP_DISCOVER_MODELS_TIMEOUT_SEC`
    (default 30s). OpenRouter's list-models endpoint can paginate
    slowly through 300+ models; this prevents a stuck discovery
    from hanging the Settings UI. Timeout → 504 with env-knob hint.
  - Broader audit of `except Exception` clobber-pattern beyond
    routers (graph code, services, commands) found **0 additional
    instances** — v0.7.109's fix was complete for the typed-error
    surface. Documented in the source.
  - +1 new test (cap truncation warning).
- **v0.7.109** 🐛 **Widespread anti-pattern: `except Exception` clobbered
  typed `HTTPException(404/400/504/etc)` into generic 500s.** Found by
  v0.7.108's chat-timeout test — the v0.7.99 504 was being silently
  rewrapped as 500 by the outer `except Exception` in `execute_chat`.

  A grep audit turned up **25 functions across 13 router files** with
  the same shape:
    ```python
    try:
        ...
        raise HTTPException(status_code=404, ...)   # never reaches client
        ...
    except Exception as e:                          # catches the 404
        raise HTTPException(status_code=500, ...)   # ←  always 500
    ```
  Status codes that would have been lost: 400, 404, 413, 502, 504.
  This bug masked every typed error in the codebase since v0.6.x —
  the frontend's i18n error mapping (`getApiErrorMessage`) couldn't
  match on detail strings, so every failure looked the same.

  Fix: mechanical insertion of `except HTTPException: raise` before
  each unguarded `except Exception` — 89 guards added across
  `chat.py`, `credentials.py`, `embedding.py`, `exports.py`,
  `gmail.py`, `notebooks.py`, `onp.py`, `podcasts.py`, `search.py`,
  `source_chat.py`, `sources.py`, `studio.py`, `transformations.py`.
- **v0.7.108** ✨ **Test for v0.7.99 chat timeout path.** Was deferred —
  added `tests/test_chat_execute_timeout.py` with two tests:
  the 504 path (with env-knob + `/chat/stream` hint validated) and
  the negative-space happy path (fast response is NOT spuriously
  timeout-killed). Caught v0.7.109's pre-existing 500-clobber bug.
- **v0.7.107** ⚡ **Bulk-delete cascade optimization for notebooks.**
  `Notebook.delete()` was sequential `for note in notes: await
  note.delete()` — N+1 serialized roundtrips against the connection
  pool. Replaced with `asyncio.gather(*..., return_exceptions=True)`
  so per-note deletes interleave concurrently. Each `note.delete()`
  still does its own cascade (artifact + note_embedding) per v0.7.76,
  so observability + correctness are preserved. Failed note deletes
  log a warning but don't cancel siblings — partial cleanup is
  better than mid-cascade abort.
- **v0.7.106** ✨ **Bulk per-notebook source vectorize endpoint.**
  `POST /api/notebooks/{id}/vectorize_sources` body
  `{only_missing: bool}`. Recovers from cases where a notebook's
  sources didn't get embedded — v0.7.94 import-time vectorize
  failure, embedding model swap, upgrade from a version without
  semantic search.

  - Skips sources that already have embeddings by default
    (`only_missing=true`); pass `false` to force re-embed.
  - Skips sources with no `full_text` and emits an actionable
    warning ("re-process the source first").
  - Submit failures degrade gracefully — a single source's failure
    becomes a warning, others still queue.
  - Pre-flight check rejects 400 if no embedding model is
    configured (better than letting every queued job fail
    asynchronously).
  - Returns per-source entries with command_ids the caller can
    poll. 6 new tests cover 404 / 400 / only_missing on/off / no-text
    skip / submit-failure resilience.
- **v0.7.105** ✨ **Frontend Export UI** (committed separately by the
  spawned task — see commit 7b0aa34). Wires the v0.7.90 endpoints
  into the dashboard with a directory picker.
- **v0.7.104** 🐛 **Imported sources weren't getting embeddings.**
  v0.7.94 import created Source records via `await source.save()` but
  never called `await source.vectorize()`. Per
  `open_notebook/domain/CLAUDE.md`, `Source.save()` does NOT auto-embed
  (unlike `Note.save()` which does) — so imported sources were saved
  + linked but invisible to vector_search. The "import then chat-with-
  sources" promise was broken for vector-mode chat. Fix: added
  `await source.vectorize()` after `source.add_to_notebook()` with a
  non-fatal try/except wrapper. If the embedding backend is down, the
  import still succeeds with a warning that says how to backfill
  embeddings from Settings → Embeddings later. 2 new regression tests
  (vectorize called on success, vectorize failure surfaces actionable
  warning).
- **v0.7.103** 🛠 **Notebook delete cascade audit (multi-page output).**
  Verified that `Notebook.delete()` correctly cascades through the
  v0.7.89 multi-page notes by walking `self.get_notes()` and calling
  `note.delete()` per note. Each `Note.delete()` (v0.7.76) handles its
  own artifact-edge + note_embedding cascade. Defensive top-level
  `DELETE artifact WHERE out=$notebook_id` then handles any
  detached-but-edged notes. **No regression found.** Documented as
  audited; no code change.
- **v0.7.102** 🐛 **Timeouts on `/search` text + vector endpoints.**
  Vector search makes an embedding-model call on the query string
  (inherits provider-latency risk from v0.7.100); text search hits
  SurrealDB and can hang if the pool is overloaded. Both wrapped in
  `asyncio.wait_for` with `ONP_SEARCH_TIMEOUT_SEC` (default 60s).
  Timeout → 504 with the env-knob name in the detail.
- **v0.7.101** 🐛 **Per-file timeout on Studio `extract_content`.**
  `content_core.extract_content()` can hang on pathological inputs
  (encrypted PDFs missing a password handler, embedded JS in PPTX,
  slow OCR fallback). One bad upload would otherwise pin the entire
  Studio request. Wrapped per-file in `asyncio.wait_for` with
  `ONP_STUDIO_EXTRACT_TIMEOUT_SEC` (default 60s). Timeout → warning
  on that file, other files keep processing.
- **v0.7.100** 🐛 **Timeout on `/credentials/{id}/test`.** The Settings
  UI's "Test connection" button calls
  `connection_tester.test_provider_connection()` which invokes
  `lc_model.ainvoke("Hi")` or `model.aembed(["test"])` against the
  provider. A misconfigured slow provider (e.g. wrong base_url) hung
  the test endpoint indefinitely. Both wrapped with
  `ONP_CONNECTION_TEST_TIMEOUT_SEC` (default 30s — generous for any
  healthy provider including cold-start Ollama). Timeout returns
  `(False, "Connection test timed out…")` with hint to raise the env
  knob if the model legitimately takes longer than 30s for a "Hi"
  prompt.
- **v0.7.99** 🐛 **Audit-sweep timeouts on the last two unbounded LLM calls.**
  Continuation of v0.7.93 + v0.7.95: a broader grep for unbounded
  `ainvoke` calls turned up two more.

  - **`api/routers/studio.py`** legacy single-note fallback path (the
    one reached when the multi-page outline JSON fails to parse) was
    still unbounded. Wrapped in `asyncio.wait_for` re-using
    `_PAGE_TIMEOUT_SEC` (180s default). Timeout → 504 with
    actionable detail + notebook_id preserved for recovery.
  - **`api/routers/chat.py`** non-streaming `/chat` endpoint had no
    timeout. Wrapped with `ONP_CHAT_TIMEOUT_SEC` (default 300s — chat
    graphs do memory recall + tool calls + long generations). Timeout
    → 504 with hint to use `/chat/stream` for token-by-token responses.
  - The streaming SSE endpoints (`/chat/stream`, `/source/{id}/chat`,
    `/search/ask`) are intentionally NOT wrapped — they're naturally
    bounded by client-disconnect detection via `is_disconnected()`
    (v0.7.50+) and `reader.cancel()` (v0.7.50).
- **v0.7.98** ⚡ **Configurable zip compression for notebook export.**
  `NotebookExportRequest.compression: 'deflated' | 'stored' | 'bzip2'
  | 'lzma'` (default `'deflated'`, matching prior v0.7.90 behavior).
  Useful when the zip will itself be compressed downstream
  (`stored`), or when archive size matters more than write speed
  (`bzip2`, `lzma`). All four algorithms are stdlib — zero new deps.
  4 new tests cover each option + Pydantic rejection of typos.
- **v0.7.97** ✨ **HTML export format for notebooks.** `format='html_folder'`
  or `format='html_zip'` renders each note's markdown to HTML via
  `markdown-it-py` (already a transitive dep — zero new deps). Each
  file is a self-contained HTML5 document with a minimal stylesheet
  (light + dark mode) so users can double-click and read in a browser
  without a build step.

  - GFM features: tables, strikethrough enabled. `linkify` deliberately
    OFF because it requires an extra runtime package.
  - Frontmatter rendered as a styled `<div class="onp-frontmatter">`
    metadata block at the top — keeps parity with the markdown export.
  - `_html_escape` applied to titles + asset paths to prevent
    `<script>` injection through note titles.
  - Folder and zip variants share the same renderer-selection logic
    (`_retype` helper) so the on-disk layout matches the markdown
    counterpart with `.html` instead of `.md`.
  - 3 new tests cover html_folder + html_zip + attribute-position
    escaping.
- **v0.7.96** ✨ **Import preview endpoint (dry-run).** `POST
  /api/notebooks/import/preview` reads the source bundle (folder /
  zip / single .md), parses frontmatter, and returns the planned
  imports WITHOUT touching the database. Lets the frontend show a
  confirmation UI before the user commits.

  - Same caps + safety rails as v0.7.94 import (50 MB total, 5 MB
    per-file, 500-entry, zip-traversal rejection).
  - Surfaces manifest-derived hints (`notebook_name_hint`,
    `description_hint`) so the UI can pre-fill the rename form.
  - Flags overview-shaped notes (`is_overview: true`) for special UI
    treatment.
  - 5 new tests: folder + zip + single-md detection, missing-path 404,
    empty-bundle warning, and a test that asserts the preview NEVER
    calls Notebook/Note/Source `save()` (raising-stub harness).
- **v0.7.95** 🐛 **Timeouts on the two remaining unbounded LLM calls.**
  Audit pass after v0.7.93 found two more endpoints where a stuck
  local LLM could hang the request indefinitely (same class of bug,
  scope was Studio-only before).

  - **`POST /api/notes`** auto-title generation now wraps
    `prompt_graph.ainvoke` in `asyncio.wait_for` (default 60s,
    `ONP_NOTE_TITLE_TIMEOUT_SEC`). On timeout: graceful degradation
    — falls back to the first line of the note's content as the
    title rather than 500ing the create-note request. User still
    gets their note.
  - **`POST /api/transformations/execute`** wraps
    `transformation_graph.ainvoke` (default 180s,
    `ONP_TRANSFORMATION_TIMEOUT_SEC`). On timeout: returns 504
    Gateway Timeout with the env-knob name in the detail.
  - No new tests — existing transformation + notes tests don't mock
    the graph (they go straight to the real graph which would be too
    slow). The behavior is exercised by the same harness as v0.7.93
    once the codebase grows graph-level integration tests.
- **v0.7.94** ✨ **Notebook import endpoint** (reverse of v0.7.90 export).
  Folder, single .md, or .zip → new or existing Notebook. Closes the
  loop on the export feature for backup/restore + cross-machine
  workflows + Obsidian/Logseq library ingestion.

  - **`POST /api/notebooks/import`** body `{source_path, mode: 'new' |
    'into_existing', target_notebook_id?, new_name?, import_sources?}`
    → `{notebook_id, notebook_name, mode, note_ids, source_ids,
    file_count, items[], warnings[]}`
  - **Frontmatter round-trips**: `_render_note_content` (export) and
    `_parse_frontmatter` (import) agree on the YAML-ish title/type/
    created/updated/id format, so an export → import cycle preserves
    note titles (verified by a dedicated round-trip test).
  - **Manifest-aware**: if the import bundle contains a `manifest.json`
    (written by v0.7.90's export), the notebook's `name` and
    `description` are seeded from it.
  - **Safety caps**:
    - 50 MB total source cap (`_MAX_IMPORT_BYTES`)
    - 5 MB per-file cap (`_MAX_IMPORT_FILE_BYTES`)
    - 500-entry cap inside a folder/zip
    - Rejects zip members with absolute or `..` paths (traversal
      defense)
    - Skips non-UTF-8 files silently rather than crashing
  - **`import_sources=true`** rebuilds Source records from any
    `sources/` subfolder (text-only Sources, since the original binary
    file isn't shipped in the export).
  - **9 new tests**: happy-path folder/zip/single-md, mode='new' vs
    'into_existing', 404 / 400 / 413 guard rails, traversal zip
    rejected, round-trip preserves titles.
- **v0.7.93** 🐛 **Per-page generation timeout for Studio multi-page.**
  Local LLMs (especially the desktop bundle's llama-cpp chat server)
  can hang indefinitely mid-prompt-eval or while loading. Without a
  cap, ONE stuck page blocks the entire notebook-generation request
  including subsequent pages, the response, and the user's browser.

  - **Outline pass**: `asyncio.wait_for` with default 90s
    (`ONP_STUDIO_OUTLINE_TIMEOUT_SEC`). Timeout → `504 Gateway Timeout`
    with the env-knob name in the detail (actionable, not a wall of
    stack trace).
  - **Per-page generation**: default 180s (`ONP_STUDIO_PAGE_TIMEOUT_SEC`).
    Timeout → that page becomes a warning naming the page AND pointing
    at the env knob; other pages still ship.
  - **3 new tests** cover page-timeout-becomes-warning, outline-timeout
    returns 504 with actionable detail, and pre-existing pages survive
    a sibling page's timeout.
- **v0.7.92** ✨ **Optional parallel page generation for Studio.**
  `ONP_STUDIO_NOTEBOOK_PARALLEL_PAGES=true` runs page LLM calls
  concurrently via `asyncio.gather(return_exceptions=True)` for ~Nx
  speedup on cloud LLMs (OpenAI, Anthropic, etc.). Default OFF to
  protect local llama-cpp dual-server setups from OOM / token
  starvation. New `_generate_all_pages` helper extracted from
  `_dispatch_notebook_mode` so the loop body is testable in isolation.
  2 new tests verify the knob actually changes concurrency (peak
  in-flight > 1 when on, == 1 when off).
- **v0.7.91** 🐛 Fix loguru %-format bug across the codebase — 18
  occurrences in 8 files (`api/routers/studio.py`,
  `api/routers/chat.py`, `api/routers/podcasts.py`,
  `api/routers/source_chat.py`, `commands/podcast_commands.py`,
  `open_notebook/database/dedup_edges.py`,
  `open_notebook/utils/memory_recall.py`,
  `open_notebook/ai/models.py`) were logging the literal `%s` / `%r` /
  `%d` since v0.7.0 because loguru uses `str.format()` (`{}`-style),
  not `%`-style. Converted to `{}`-style placeholders with `{!r}` for
  repr. No behavior change beyond accurate log output. Full suite
  (469 tests) still passes.

- **v0.7.90** ✨ **Filesystem export + native directory access.** Users can
  now save notebooks and individual pages out of the app to anywhere on
  their host filesystem (the desktop bundle runs natively on macOS /
  Windows so file access is unrestricted; Docker deployments work too,
  bounded to mounted volumes).

  - **`POST /api/notebooks/{id}/export`** writes a notebook as a folder
    (one `.md` per note) or a single `.zip` archive.
    - Folder layout: `00-overview.md` (auto-detected from v0.7.89's
      "📋 00 · …" overview notes) + `01-{slug}.md` … `NN-{slug}.md` +
      optional `sources/{source-id}.md` + `manifest.json`.
    - Slug logic strips emoji, non-ASCII, AND leading numeric prefixes
      so v0.7.89 page titles ("📄 01 · Architecture") don't end up
      double-indexed (`01-01-architecture.md`).
    - Pre-flight overwrite check: refuses to half-clobber existing files
      unless `overwrite=true` is passed.
    - Manifest captures notebook + per-note metadata for downstream
      tools (Logseq, paperless-gpt, future ONP re-import).
  - **`POST /api/notes/{id}/export`** writes a single note as a `.md`
    file. Auto-appends `.md` if the caller omits the extension.
  - **`GET /api/fs/list?path=…`** lists a directory on the host
    filesystem (entries sorted dirs-first, capped at 500 to prevent
    huge-directory DoS, hidden files excluded by default).
  - **`GET /api/fs/home`** returns the user's home + Desktop /
    Documents / Downloads / default-exports paths in one call so the
    frontend picker doesn't have to figure them out per-platform.
  - **`POST /api/fs/mkdir`** creates a directory (idempotent — re-runs
    on an existing dir return `created=false`).
  - **Safety:** all paths normalized via `Path.resolve()` and rejected
    if they fall under a system-root prefix (`/etc`, `/System`, `/proc`,
    `/Windows`, etc.). Not a security boundary — the user owns the
    process — but prevents accidentally surfacing those locations in a
    picker UI. All routes are auth-gated by the existing
    `PasswordAuthMiddleware`.
  - **Tests:** 33 new tests across `tests/test_filesystem_router.py`
    and `tests/test_exports_router.py`. Folder + zip + single-note paths
    each have happy-path + overwrite + 404 + 409 + 403 coverage. Full
    suite: **465 pass, 0 fail.**
- **v0.7.90 audit findings (during the build):**
  - `api/routers/filesystem.py` deliberately exposes broad host-FS
    access. This is appropriate for the desktop bundle (user owns the
    machine) but **operators deploying the API publicly should ensure
    `OPEN_NOTEBOOK_PASSWORD` is set to a strong value** — otherwise an
    unauthenticated request can list arbitrary directories under the
    API process's UID. Filed as a doc-update task; the README already
    flags Docker compose as "set passwords + encryption key before
    exposing" but the new filesystem endpoints make that warning more
    pressing.



- **v0.7.89** ✨ **Studio multi-page notebook output.** When the user uploads
  one or more documents via `/studio/generate` (mode `notebook` or `both`),
  the API now produces a **structured multi-page brief** instead of a single
  blob of markdown.

  - **Outline pass:** one LLM call → JSON `{headline, summary, pages[],
    top_suggestions[]}`. Constrained to 3-{`ONP_STUDIO_NOTEBOOK_PAGES_MAX`,
    default 6} distinct pages.
  - **Per-page pass:** one LLM call per page (sequential — parallel would
    starve llama-cpp-python on the desktop bundle), each ending with a
    "💡 AI Suggestions for this page" block with 3-5 concrete recommendations.
  - **Persistence:** N+1 notes saved to the notebook — "📋 00 · {title} —
    Overview" (headline + executive summary + table of contents + top
    suggestions) followed by "📄 NN · {page title}" for each page.
  - **Graceful degradation:**
    - Outline JSON un-parseable → fall back to legacy single-note output,
      warning surfaced in response.
    - Individual page LLM call fails → that page becomes a warning, other
      pages still ship.
    - `ONP_STUDIO_NOTEBOOK_MULTIPAGE=false` → bypass multi-page entirely
      (kill switch for rollout).
  - **Response shape:** `StudioGenerateResponse` gains `note_ids: list[str]`.
    `note_id` still points at the Overview note for back-compat with the
    v0.7.88 frontend.
  - **Tests:** existing 19 studio router tests updated for the new
    multi-pass flow; 3 new tests cover multi-page happy path, JSON fallback,
    and the `_MULTIPAGE_ENABLED=False` kill switch. Full suite: **432 pass.**
- **v0.7.88** ✨ **Studio `mode="both"`.** Single upload can now generate
  BOTH a notebook AND a podcast. `_dispatch_both_modes` runs the notebook
  pipeline synchronously then submits the podcast job; either half can fail
  independently with the surviving artifact preserved and the failure
  reported in `warnings`. Validation gate ensures podcast profile fields
  are supplied when mode is `podcast` OR `both`. The frontend selects
  this mode via the existing mode picker.
- **v0.7.89 audit findings (intentionally noted, not fixed this turn):**
  - `api/routers/studio.py` lines 375, 389, 406-410, 421, 423 use
    `logger.{info,warning,exception}("…%s…%s…", a, b)` patterns — loguru
    uses `{}` formatting, NOT `%`. These messages have been logging the
    literal `%s` since v0.7.0. New v0.7.89 lines use `{}` correctly; the
    legacy `%s` lines are a separate cleanup. Filed.



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
- **v0.7.77** Four MORE sync submit_command sites in
  commands/embedding_commands.py: create_insight (per-insight
  fire-and-forget) and rebuild_embeddings' three submit loops
  (source / note / insight). The rebuild path under
  /advanced/rebuild-embeddings fired hundreds-to-thousands of
  sync SurrealDB WS handshakes back-to-back, blocking the
  worker's event loop for the entire rebuild and starving any
  concurrent commands (chat memory extracts, podcast generation)
  the same worker was servicing. All four now wrapped in
  asyncio.to_thread.
- **v0.7.78** Source-chat now recalls memory facts/preferences in
  its system prompt — parity with v0.7.71's wiring for the main
  chat. Without this, the assistant would surface a remembered
  preference inside the main chat but forget it the moment the
  user clicked into a source-chat session. Tighter prompt framing
  for source-chat ("Stay focused on the source; only weave a
  memory note in when it directly helps the answer") since the
  source-chat system prompt already carries up to ~3.5k tokens
  of source + insight context.
- **v0.7.79** Three bare setTimeout sites in the frontend now
  cancel cleanly on unmount: EmbeddingModelChangeDialog's
  500 ms pre-redirect timer, GeneratePodcastDialog's 500 ms
  post-submit close timer, and SourceDetailContent's 5 s
  insight-fallback refresh timer. Same defect pattern fixed in
  SourceCard (v0.7.56) — without cleanup the timer fired
  navigation / mutation / invalidate against an already-unmounted
  component when the user dismissed mid-window.
- **v0.7.80** `insightsApi.waitForCommand` now accepts an
  AbortSignal and uses an abortable-sleep helper between polling
  attempts. SourceDetailContent wires a per-component
  AbortController that gets aborted on unmount, so navigating
  away mid-poll stops the 4-minute polling loop within
  milliseconds instead of continuing to hit
  `/commands/jobs/{id}` and triggering downstream cache
  invalidation on a dead React subtree.
- **v0.7.81** Two more reliability fixes. `_send_digest_now` now
  wraps the post-send `g.save()` in try/except so a successful
  Gmail send followed by a DB persist failure doesn't cause the
  scheduler to send the same digest again on the next tick (the
  email already went out; the duplicate-send window is bounded
  to one tick instead of every tick until DB recovery).
  `notes.create_note` AI-title generation now uses the
  `isinstance(result, dict)` → `.get` / `getattr` dual-path on
  the prompt graph's ainvoke output, matching the standing
  state-shape guard pattern in chat.py / search.py /
  source_chat.py / transformations.py.
- **v0.7.82** Cleanup pass: 7 ruff E702 errors in
  desktop/tests/test_launcher.py fixed (split semicolon-style
  multi-statement lines). Launcher stop_all log lines now use
  `getattr(p, "pid", "?")` so MagicMock-spec'd Popens in the
  desktop test suite stop raising AttributeError on teardown
  (three desktop tests were broken since v0.7.58 — undetected
  because `desktop/tests/` isn't in the main pytest path). Two
  remaining cosmetic copy-success setTimeout sites
  (MessageActions.tsx, SourceDetailContent.tsx:324) now use the
  standard useRef + useEffect cleanup pattern — finishes the
  setTimeout sweep so every timer in the frontend has unmount
  cleanup.
- **v0.7.83** Memory worker inherits the session model_override
  (deferral #3 closed). `_fire_memory_extract_turn` and
  `_fire_memory_summarize_session` now accept an optional
  model_override and thread it through to the surreal_commands
  payload; `memory_extract_turn` / `memory_summarize_session`
  worker handlers accept it as an optional kwarg and pass it to
  `_build_clients`. Resolution: caller override → ONP_CHAT_MODEL_NAME
  → "default". Backward-compatible (older queued rows still
  dispatch).
- **v0.7.84** Semantic memory recall (deferral #2 closed). New
  `recall_relevant_memory(query)` does cosine similarity over
  mem0's embedding column using the same SurrealQL idiom
  (`vector::similarity::cosine`) the mem0 retriever already uses.
  New `recall_memory(query)` orchestrator picks recency vs
  semantic based on `ONP_MEMORY_RECALL_MODE` (recent | semantic |
  auto, default auto) and a row-count threshold (30) — small
  stores stay on recency (saves an embed round trip), large stores
  switch to semantic. Any semantic-path failure falls through to
  recency so chat never breaks. 7 new orchestrator tests in
  tests/test_memory_recall.py; total backend suite now 423.
- **v0.7.85** Legacy edge deduplicator (deferral #1 closed).
  New `open_notebook/database/dedup_edges.py` runs once per API
  startup, finds duplicate (in, out) groups on the `reference` and
  `artifact` edge tables, keeps the lexicographically-smallest id
  per group, and deletes the rest. Idempotent (clean DB → no-op
  one SELECT per table) and non-fatal (per-edge DELETE failures
  don't abort the rest of the cleanup; per-table SELECT failures
  don't block other tables). Runs in api/main.py lifespan after
  schema + podcast migrations. 7 new tests in
  tests/test_dedup_edges.py covering clean DB, single group,
  partial failure, multi-table isolation, and idempotent re-run.
  Backend suite now 430.
- **v0.7.86** Model.delete clears DefaultModels references +
  warns on profile use (improvement found during the models.py
  router audit — no bugs uncovered in the router itself, all
  standard patterns were clean). Previously deleting a model
  left dangling references in the `default_models` singleton
  and in any episode_profile / speaker_profile that used it.
  Override clears default-fields proactively (lookups land on
  the cleaner "no default configured" path instead of the
  dangling-fetch path) and warn-logs each podcast profile that
  still references the model — deliberately not auto-cleared
  since reassigning a profile's model is a UX choice the user
  should make.
- **v0.7.87** commands router audit uncovered three stub
  implementations returning success without doing the work:
  `cancel_command_job` was a no-op (frontend trusted "cancelled:
  true" and removed the job from the UI while the command kept
  running); `list_command_jobs` was a stub returning [] so the
  jobs panel was always empty; `get_command_status` returned a
  synthetic `{"status": "unknown"}` for missing jobs so the
  router served fake-OK 200 responses. Now: cancel writes the
  `canceled` signal via the same pattern Source.delete uses
  (v0.7.32), list queries the `command` table with SurrealQL
  filters, and missing jobs return real 404 (status endpoint)
  or 404/409 (cancel endpoint).

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
