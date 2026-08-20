# Deeper Notebook Productization Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete every safe, locally verifiable priority item today, while leaving credential rotation, destructive remote-history mutation, notarization, Windows proof, and public release explicitly blocked unless their exact external authority is available.

**Architecture:** Preserve the existing feature-flag rollback model: stable features become default-on, while an explicit canonical `0` remains authoritative and backend runtime state can disable frontend controls. Data correctness is repaired at the query boundary, not by per-row N+1 calls. Search and dependency changes require measurements before production mutation. Security remediation uses secret-free receipts, recoverable backups, and rotation-before-purge ordering.

**Tech Stack:** Python 3.12, FastAPI, SurrealDB 2.6.5, Next.js/React/TypeScript, Vitest, Playwright, pytest, Ruff, Gitleaks, macOS packaging.

## Global Constraints

- Work only in `/Users/Antman/Documents/Open%20Notebook/Deeper-Notebook/.worktrees/today-productization` on `codex/today-productization` until reviewed (the encoded segment denotes the literal space in the local folder name).
- Preserve the supplied untracked `.codex/agent-context/deeper-notebook-search-repair-2026-08-20.md` in the main checkout.
- Never print, commit, log, or persist the leaked Google API key.
- Rotation must precede any claim that history cleanup remediated the live credential.
- Never rewrite or force-push remote history without an independently verified backup bundle and exact ref inventory.
- Every behavior change follows strict test-first RED, minimal GREEN, focused regression, then adjoining/full gates.
- Every default-on feature retains an explicit `0` rollback path.
- Do not add cloud dependencies, model downloads, public releases, signing identities, or Windows mutations without verified local authority.
- Do not treat optional model-cost features as stable merely because their code exists; prove failure isolation and user rollback first.

---

### Task 1: Establish security and rollback authority

**Files:**
- Create: `.codex/agent-context/today-productization-2026-08-20.md` (ignored durable receipt)
- Modify: `docs/TODO.md` only after evidence changes
- Create outside repository only if safe: a timestamped bare backup bundle and redacted receipt under `/Users/Antman/Downloads/`

**Interfaces:**
- Consumes: Git remote `origin`, Gitleaks findings, authenticated `gcloud`/`gh` metadata.
- Produces: exact affected refs, key-management authority result, backup SHA-256, and a rotation-before-purge decision.

- [ ] Record worktree HEAD, branch, status, remotes, all affected refs, and baseline test results without secret values.
- [ ] Verify whether the currently authenticated Google account can resolve/manage the leaked key; record only permission and resource metadata.
- [ ] Verify whether the historical key is still accepted using a status-only request that never prints its value.
- [ ] If key authority exists, create a replacement, update known authorized consumers, verify them, and disable/delete the exposed key; otherwise record the exact IAM blocker and Google Console action required.
- [ ] Inventory `history.txt` and the exact leaked key across every remote branch/tag using redacted Gitleaks output.
- [ ] Before rewriting anything, create a full-ref backup bundle, hash it, clone/verify it, and record a tested restore command.
- [ ] Rewrite and force-update remote refs only if rotation is verified and the backup/restore proof is green; otherwise prepare but do not execute the destructive remote step.
- [ ] Re-run full-history Gitleaks and prove the targeted key and `history.txt` are absent from every rewritten ref before claiming purge completion.

**Verification:**
- [ ] `gitleaks git --redact --log-opts='--all'`
- [ ] `git bundle verify <backup>`
- [ ] `git fsck --full` in the sanitized mirror
- [ ] Exact remote ref comparison before any push

**Dependencies:** None.

### Task 2: Make the Gemini-forward visual experience stable by default

**Files:**
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/lib/features.ts`
- Modify: `tests/test_evidence_studio_foundation.py`
- Modify: `deeper_notebook/feature_flags.py`
- Modify: `deeper_notebook/environment.py`
- Modify as required by registered-setting contracts: environment/rebrand tests and allowlist metadata

**Interfaces:**
- Consumes: `resolve_env(name)`, frontend runtime feature overrides, `/api/features`.
- Produces: `isVisualSystemV2Enabled() -> true` and `source_visuals_enabled() -> true` when unset; explicit canonical `0` remains false; canonical aliases outrank legacy aliases.

- [ ] Change tests first so unset Visual System V2 and Source Visuals are expected true, while explicit `0` is false.
- [ ] Add backend tests proving the canonical long/short source-visual setting names and both deprecated product-prefix aliases follow canonical precedence and warnings policy.
- [ ] Run focused tests and capture strict RED from the current defaults/unregistered setting.
- [ ] Register `SOURCE_VISUALS_ENABLED` in canonical environment settings and route `source_visuals_enabled()` through `_env_flag(..., default=True)`.
- [ ] Change frontend inlined defaults to true without weakening runtime backend rollback.
- [ ] Run focused unit tests, runtime-feature tests, source-gallery consumer tests, TypeScript, and rollback Playwright cells.
- [ ] Commit atomically after review.

**Verification:**
- [ ] `uv run pytest -q tests/test_evidence_studio_foundation.py tests/test_environment_aliases.py tests/test_v0_8_107_runtime_features.py`
- [ ] `cd frontend && npx vitest run src/lib/features.test.ts src/lib/hooks/use-source-visuals.test.tsx`
- [ ] Explicit `0/0` and unset/default browser cells both pass.

**Dependencies:** Task 1 inventory only; no secret rotation dependency.

### Task 3: Return truthful source embedding metadata

**Files:**
- Modify: `tests/test_sources_api.py`
- Modify: `api/routers/sources.py`

**Interfaces:**
- Consumes: `source_embedding` records related by `source`.
- Produces: `SourceListResponse.embedded_chunks` equal to the authoritative count and `embedded == (embedded_chunks > 0)` in both notebook-filtered and all-source list queries.

- [ ] Add tests with nonzero counts for both list query branches and assert no per-row `Source.get_embedded_chunks()` calls.
- [ ] Run the selectors and capture RED showing `embedded_chunks == 0`.
- [ ] Add a bounded count subquery to both list projections, return that count, and derive `embedded` consistently.
- [ ] Run focused sources API and real-Surreal source list tests.
- [ ] Commit atomically after review.

**Verification:**
- [ ] `uv run pytest -q tests/test_sources_api.py`
- [ ] Relevant real-Surreal source projection/list integration selector.

**Dependencies:** None.

### Task 4: Productize remaining implemented feature gates safely

**Files:**
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/lib/features.ts`
- Modify: `tests/test_evidence_studio_foundation.py`
- Modify: `deeper_notebook/feature_flags.py`
- Modify: `tests/test_v0_8_60_agent_fsm_tool_loop.py`
- Modify: `tests/test_agent_fsm_ask_gate.py`
- Modify only if proven safe: `deeper_notebook/graphs/chat.py`, `deeper_notebook/graphs/ask.py`, `deeper_notebook/domain/content_settings.py`, corresponding settings/ingest tests

**Interfaces:**
- Produces: Research Runs and Agent FSM default-on with explicit `0` rollback if their complete suites and failure paths pass.
- Preserves: auto-summary/key-topics user controls and local-model cost boundary unless tests prove default-on enrichment cannot fail ingestion, block offline use, or impose an unapproved model call.

- [ ] Add default/rollback tests for Research Runs and Agent FSM and capture RED.
- [ ] Audit auto-summary and key-topics command failure isolation using tests before changing defaults.
- [ ] Enable Research Runs and Agent FSM minimally if all focused/adjoining tests pass.
- [ ] Enable ingest enrichments only if both are nonblocking under missing-model, offline, timeout, and explicit-off cases; otherwise keep opt-in and document the evidence-based product decision instead of silently raising cost.
- [ ] Run chat/ask, research-run, settings, source-ingest, and browser settings tests.
- [ ] Commit each independently reviewable behavior atomically.

**Verification:**
- [ ] Agent FSM focused suites and chat/ask adjoining suites.
- [ ] Research Run backend/frontend suites.
- [ ] Auto-summary/key-topic source-ingest and settings suites.

**Dependencies:** Task 2 flag convention.

### Task 5: Measure and resolve search-quality uncertainties

**Files:**
- Modify/create only after RED measurement: integration benchmark tests or `scripts/` measurement receipt
- Modify: `docs/TODO.md` with exact measured conclusions
- Production migrations/search code only if a benchmark proves a defect and a focused regression exists

**Interfaces:**
- Measures: BM25 after realistic notebook/source deletion, embedding L2 norms, HNSW recall/latency over multiple EF values, and optional reranker delta.

- [ ] Build deterministic real-Surreal fixtures with non-vacuous relevance judgments.
- [ ] Measure realistic delete paths before/after index rebuild; add production rebuild only if product deletion degrades scores.
- [ ] Measure stored embedding norms; if normalization is not within a documented tolerance, test and implement normalization or distance alignment with migration/rebuild proof.
- [ ] Benchmark EF values using fixed queries and report recall/latency; change the default only for a measured improvement within the latency budget.
- [ ] Evaluate reranking using existing local models only; do not download or ship a new model without a measured benefit and separate authority.
- [ ] Update TODO items to complete, implemented, or blocked with commands and numbers.

**Verification:**
- [ ] Fresh disposable SurrealDB 2.6.5 namespaces.
- [ ] At least two fresh benchmark runs with stable conclusions.
- [ ] Full real-Surreal integration suite after any production query/index change.

**Dependencies:** Baseline real-Surreal health.

### Task 6: Remove actionable React warnings and audit Pillow

**Files:**
- Modify only affected test/component clusters under `frontend/src/components/guided-tips/` and exact Radix/async test owners
- Modify: `docs/TODO.md`
- Dependency files only if an official compatible Pillow/MoviePy release exists and full media tests pass

**Interfaces:**
- Produces: warning inventory by unique stack owner, corrected awaited/`act()` boundaries, and an upstream-authoritative Pillow decision.

- [ ] Run the relevant frontend suite with warnings captured and deduplicated by stack owner.
- [ ] For each application-owned warning, add/adjust a test that reproduces the missing await/act boundary, confirm warning RED, then fix the test or component without suppressing console output.
- [ ] Do not patch Radix internals; update application test interactions or document upstream-only warnings.
- [ ] Check current official MoviePy/PyPI/GitHub constraints and Pillow advisories; upgrade only if a compatible release exists.
- [ ] Run media extraction, image, frontend, typecheck, lint, and dependency audit gates.

**Verification:**
- [ ] Warning count before/after with exact remaining upstream stacks.
- [ ] `npm audit` has zero critical/high findings.
- [ ] `uv lock --check`/frozen sync and media tests pass if dependencies change.

**Dependencies:** None.

### Task 7: Native packaging and release evidence

**Files:**
- Modify verification documentation only after fresh evidence
- Package/build artifacts remain untracked

**Interfaces:**
- Consumes: final reviewed source HEAD, macOS signing identities/notary profiles, available Windows runner/host, GitHub release authority.

- [ ] Run full backend/desktop/frontend, feature contract, real-Surreal, and browser matrices at final HEAD.
- [ ] Build the native macOS app and DMG; verify bundle identity, architecture, hashes, package manifest, deep signature, and DMG integrity.
- [ ] If a Developer ID and notary profile are available, sign/notarize/staple and verify with `spctl`; otherwise record the missing identities without substituting ad-hoc proof.
- [ ] Run Windows packaged proof only on an available authorized Windows runner; otherwise record the exact platform blocker.
- [ ] Do not create a public release without a version decision, signed/notarized artifacts, release notes, and explicit final artifact hashes.

**Verification:**
- [ ] Fresh package smoke with Visual System V2 and Source Gallery default-on and explicit rollback.
- [ ] No app-owned process/listener/data residue after smoke cleanup.

**Dependencies:** Tasks 2–6 reviewed and green.

### Task 8: Final review, integration, and handoff

**Files:**
- Modify: `docs/TODO.md`
- Create/update: verification receipt and ignored task context

**Interfaces:**
- Produces: reviewed atomic commits, merge/rollback instructions, completed goal status or exact external blockers.

- [ ] Generate a complete branch diff package and obtain fresh code/security review.
- [ ] Repair all Critical/Important findings and re-review.
- [ ] Run final full gates at exact HEAD, staged/range Gitleaks, rebrand audit, and diff checks.
- [ ] Merge only reviewed commits to `main`; preserve the original worktree until final verification.
- [ ] Mark the goal complete only if all locally authorized work is complete and every external blocker has an actionable owner/path.

**Verification:**
- [ ] Tracked worktree clean; unrelated untracked context preserved.
- [ ] Every completion claim cites a fresh command result.

**Dependencies:** Tasks 1–7.

## Execution outcome — 2026-08-20

- Tasks 2–6 and the source/build/integration/browser portions of Task 7 are
  implemented, committed, reviewed, and green.
- Task 1 is complete as far as repository and available credential authority
  permit: the key is externally invalid, the backup/restore proof is green,
  and eight writable affected branch heads are sanitized. Google Cloud owner
  confirmation and nine GitHub-generated pull refs remain external actions.
- Cumulative graph-assisted review found one Important partial runtime-feature
  rollback loss; commit `2622ce0e` repaired it with a strict RED and focused
  59-test GREEN. No remaining Critical or Important source finding is known.
- Native package proof is blocked only while the user-installed Deeper Notebook
  app remains running. The app was observed read-only and never signalled,
  replaced, or installed over. Developer ID/notary, Windows-runner proof, and
  public-release authority also remain external gates.
- Exact continuation is recorded in
  `/Users/Antman/Downloads/DEEPER-NOTEBOOK-CLOSEOUT-HANDOFF-2026-08-20.md`.
