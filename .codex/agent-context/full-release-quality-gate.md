# Full Release Quality Gate Context

## Authoritative task

Execute `docs/superpowers/plans/2026-08-11-full-release-quality-gate.md` for
Deeper Notebook. This is a whole-application audit and targeted polish pass, not
a rewrite.

## Fixed boundaries

- Starting branch/revision: `agent/documentation-reconstruction` at
  `4c8b5a3d1fe4`.
- Preserve public APIs, stored schemas/identifiers, vault authority, all user
  workflows, and unrelated dirty/untracked state.
- No real vault/model/credential/user-data mutation. Use disposable roots and
  namespaces for native proof.
- Each repair requires a reproduced defect and regression coverage.
- Each optimization requires before/after measurement.
- MCP registration is the existing candidate plugin system; prove or improve it
  before proposing a second extension runtime.
- Record meaningful milestones, exact commands/totals, touched-file reasons,
  open risks, and commit IDs here.

## 2026-08-11 visual Phase 7 repair milestone

- Expanded `frontend/e2e/all-screen-visual-audit.spec.ts` to a 19-route x
  4-viewport matrix (76 visits per shell), with login/setup at all widths,
  mode-aware legacy landmark counts, bounded loading/empty/error/recovery/
  populated states, keyboard/focus/dialog return, reduced motion,
  half-width zoom-equivalent overflow, target floors, console/page/request
  ledgers, and exact loopback hostname classification.
- Default mocked all-screen: 7 passed; exact rollback
  `NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0`: 7 passed. Focused Vitest: 11 files/32
  tests; lint, tsc, default/rollback builds, feature-build contract, and
  `python3 scripts/rebrand_audit.py` passed (0 unexpected active identities).
- Minimal UI repairs contain notebook/source/API-key/SmartRouting/podcast/local
  model controls, restore notebook dialog focus, and constrain rollback
  Research Core rails. Report updated with exact coverage and limits; no
  screenshots refreshed. Visual/evidence repair committed atomically as
  `a600a72c` (`fix(frontend): complete visual audit release proof`).

## Preserved pre-existing untracked state

- `.codex/agent-context/deeper-notebook-research-evidence-adoption.md`
- `.codex/agent-context/deeper-notebook-web-intelligence.md`
- `.codex/agent-context/luminous-research-folio.md`
- `.codex/agent-context/reliability-experience.md`
- `.codex/agent-context/research-evidence-ui.md`
- `.playwright-cli/`
- `desktop/build/__pycache__/`
- `frontend/test-results/focus-mode-rollback-*`
- repository-root `node_modules/`

Do not delete, reset, stage, or reinterpret these paths.

## Milestones

- 2026-08-11: Task opened; plan and constraints frozen. No product source edited.

## Security and plugin repair batch

Implement only reproduced, backward-compatible hardening in this batch:

1. Bound the optional in-memory rate limiter's client table so expired/inactive
   client keys cannot grow without limit. Add RED tests first; preserve the
   disabled-by-default contract and existing response shape.
2. Bound MCP plugin discovery and result projection: finite servers/tools,
   validated names/descriptions/schemas, finite content blocks/text/binary
   projection, finite timeout/iteration environment values, bounded discovery
   cache, and fail-soft behavior for malformed plugin data. Add RED tests first
   and preserve existing valid MCP tools and API shapes.
3. Remove shell interpolation of the macOS app-bundle path from the detached
   relaunch helper. Pass PID/path as positional shell parameters and add a RED
   regression using metacharacters in the bundle name.
4. Remove the tracked `history.txt` credential dump and ignore future copies.
   Do not rewrite Git history or claim external credential revocation.
5. Document MCP as Deeper Notebook's plugin architecture and add a minimal
   local streamable-HTTP example plugin with registration, lifecycle, failure,
   and isolation guidance. Do not add an in-process arbitrary-code loader.

Do not handle dependency upgrades, runtime archive checksums, or Hugging Face
revision pinning in this batch; those are separate reviewable changes.
- 2026-08-11 Phase 1 baseline: inventory recorded 21 frontend pages + 3 Next
  handlers; 265 FastAPI decorator endpoints across 45 endpoint-bearing router
  files and 40 registrations (including hidden `/api/onp` aliases); 191
  `deeper_notebook` modules/80 migrations; desktop lifecycle, 16 command
  registrations, workers, and proof owners documented in
  `.superpowers/sdd/full-release-quality-gate-phase-1-report.md`.
- Serial gates all passed: backend `uv run pytest tests/ -v
  --ignore=tests/integration` = 3948 passed/1 skipped/29 warnings;
  `uv run ruff check .` pass; rebrand audit pass (unexpected_active_identity=0,
  compatibility_alias=825, historical_reference=1747,
  migration_documentation=584, upstream_reference=99); desktop `.build-venv`
  pytest = 806 passed/2 skipped/5 warnings; frontend Vitest = 202 files/1452
  tests; lint, tsc, production build (23/23 static pages), and feature-build
  contract all pass. Existing frontend `.last-run.json` SHA stayed
  `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`.
- MCP trace found working CRUD/URL validation, enabled-row registry, priority/
  TTL discovery, per-turn/session exclusions, fenced fail-soft tool loop, and
  docs; open risks are no obvious persistent UI enable toggle, no local example
  plugin, no persisted health/latency/last-error lifecycle, serial discovery,
  and no generic typed-block result-size cap. Native/package/integration/browser
  gates remain open for later phases. Tracked tree stayed unchanged; only the
  generated report path was touched.
- 2026-08-11 security batch milestone: commit `618fd1d8` bounds the optional
  rate-limit middleware's client table at 4096 LRU entries and reclaims expired
  sliding-window deques. RED/GREEN `uv run pytest -q
  tests/test_rate_limit_table_bounds.py` = 2 passed; scoped Ruff passed.
- 2026-08-11 security/plugin batch completed in atomic commits:
  `15ba2a3c` amortizes full rate-table cleanup (RED cadence regression; 12 rate
  tests passed); `eb155880` bounds MCP discovery/schema/content/cache/env paths
  with fail-soft registry/chat projections (11 focused + 64 adjoining MCP
  tests passed); `8b546ee8` skips hostile per-tool mappings and adds 64 KiB
  result-text/4 MiB result-binary budgets (45 focused/phase2 MCP tests passed);
  `51ad0c27` passes relaunch PID/path as quoted shell positionals (desktop
  window suite 193 passed); `9464bad3` removes tracked credential `history.txt`
  and ignores future copies; `c03bba65` documents the external streamable-HTTP
  MCP plugin architecture and adds a loopback FastMCP example. Scoped Ruff,
  compile, and a clean loopback endpoint smoke (HTTP 406 then terminated)
  passed. Existing MCP integration runs emit noisy websocket/Surreal teardown
  warnings; no dependency, archive-checksum, or HF installer changes were made.
## 2026-08-11 static security classification

- Bandit scanned `api`, `deeper_notebook`, `desktop`, and `commands` (excluding
  vendored desktop binaries and test trees): 2 high-severity findings are the
  runtime archive extraction paths in `desktop/bootstrap.py` and
  `desktop/build/fetch_runtimes.py`. Tar extraction uses Python's data filter,
  but archive-layout validation and ZIP traversal rejection are not explicit;
  the runtime supply-chain batch owns the compatible repair and regressions.
- The medium `snapshot_download` revision warning is genuine and is owned by
  the same batch. Other reviewed medium flags are not exploitable application
  paths: vault/security.py contains literal forbidden-path policy entries;
  db_repair probes a fixed loopback URL; release_manifest executes the tracked
  desktop version module at build time; make_icon parses the tracked canonical
  SVG and verifies exact geometry/colors; fetch_runtimes uses fixed manifest
  URLs, which will additionally gain scheme and digest checks.
- Process inspection during the audit showed an unrelated long-running MCP
  process launched with a credential in its command-line arguments. This is
  outside the repository and was not stopped or modified. Do not record the
  value; recommend rotating it and switching that service to environment/file
  credential delivery because command-line arguments are visible to local
  process listings.

## 2026-08-11 performance inventory

- The successful Next 16 production build reports `.next` at 92 MiB. Its
  generated `diagnostics/route-bundle-stats.json` shows the largest uncompressed
  first-load route as `/knowledge` at 4,288,268 bytes, followed by
  `/notebooks/[id]` at 3,706,789 bytes and `/podcasts` at 3,583,687 bytes.
  These figures are uncompressed build diagnostics, not network-transfer size;
  the desktop app serves them locally. Do not perform speculative framework
  splitting without measuring interaction/startup impact. The confirmed memory
  leak is instead the unbounded terminal job registries, owned by the runtime
  performance batch, and the confirmed request amplification is the evidence
  review N+1 gap, owned by its bounded batch endpoint.

## 2026-08-11 controlled native/package/install acceptance (HEAD 559a5efc)

- Source boundary held exactly at `559a5efcff98c05552d14afabfbefdf37eae9095`; tracked-file
  fingerprint `e80e667545545db7073f588627b9519ad4c5b698c30380ca49d779a763a74f74` matched before/after.
  Real Surreal knowledge/vault/evaluation integration passed 50 (6 warnings); MCP/security integration
  passed 36 (7 warnings). Disposable Supervisor/API/worker/Next probes returned `/livez`, `/readyz`,
  authenticated runtime snapshot, settings, and frontend HTML; loopback FastMCP registration/test,
  priority/disable, delete, and stopped-endpoint isolation passed.
- Unified proof root `/Users/Shared/deeper-notebook-acceptance3-wsKCiA` used ports 62732/62733/62734;
  prepare returned designed restart barrier 5, real Supervisor restart occurred (prior API PID 87954,
  current 328), verify returned 0. Overlay + parsed child equivalence passed; trusted parent source was
  intentionally excluded. Source fingerprints and idempotent trust replay held. Report/state SHA-256:
  `f860e1ec7c2dcf166fa932cd78cce61bd9b24c66494a5f298239d31bc0faafe4` /
  `72b1207a1240d1e35533e4cb43113c5ef86d5924fa4cd77337ffffe958600027`.
- Exact `DEEPER_NOTEBOOK_CODESIGN_IDENTITY=- make build-mac` preconditions reached the authoritative
  backend `3981 passed/1 skipped/16 warnings`; a later host-load rerun had two 8-second parser timing
  failures (`3979 passed`) while the bounded idle focused repro passed 8/8. Per approved deviation,
  preconditions were not rerun; direct post-precondition stages with `PYTHONPATH=.` fetched/verified
  arm64 runtimes, built PyInstaller, re-sealed, and produced the DMG. Package-content verifier passed;
  app ID/version `com.antman1526.open-notebook-plus`/`0.8.95`, arm64 executable SHA-256
  `780f26e90d5f2c423bd5e2f2702bb56f905b5b417ebdf574b0d0257f4a312434`, DMG SHA-256
  `e42b04baecc4fb4297ae79c5c41129ed6f2123f78eabc5fad4708c85f86770e7`; deep/strict codesign and
  `hdiutil verify` passed; `spctl` ad-hoc rejection is expected. Build-generated lock drift
  (`577db8...`) was restored byte-for-byte to `4e29943ec6c649690120ad15ece85f0e154a7092f270ead8f4ef5b2e9fc7507a`.
- Validated app was atomically installed with recoverable backup
  `/Applications/Deeper Notebook.app.backup-task20260811-165545`; installed executable hash matched
  the fresh artifact and the prior backup hash was preserved. Isolated installed smoke used task-owned
  root `/Users/Shared/deeper-notebook-installed-smoke-wsKCiA`; after first-run venv provisioning,
  current-PID marker `44396` advertised API `57035` and frontend `57036`. With explicit task-owned
  `DEEPER_NOTEBOOK_PASSWORD`, authenticated snapshot returned 200 (startup ready, DB online,
  migrations applied), unauthenticated returned 401; frontend root/setup/settings/MCP routes returned
  200 with `__next_f`. Loopback FastMCP plugin was visible/tested and deleted; app SIGTERM stopped all
  owned children/listeners. Task roots were moved recoverably to Trash after receipts were captured.
- Concerns: ad-hoc signing is not notarization/clean-machine proof; PyInstaller emitted nonfatal
  `aiohttp._helpers` and sharp/libvips rpath warnings; parser timing gate is load-sensitive; normal
  packaged launch without an explicit `DEEPER_NOTEBOOK_PASSWORD` leaves API password middleware
  disabled (the authenticated smoke supplied the variable); no model/content workflow was invoked.

## 2026-08-11 final bounded repair round

- Security atomic commit `c6c1bfa4` pins approved MCP DNS resolutions at the
  httpcore connect seam, disables SDK redirect following, and keeps TLS/SNI
  authority intact. Boundary/adjoining MCP security suites passed 65 tests;
  Ruff and diff-check passed.
- Visual/accessibility repair is staged in the current worktree: LegacyAppShell
  outer wrapper is a div; shared route frames and Evidence Studio own one main
  in both shell modes; login title is a visible h1. The Sources table alone has
  the explicit horizontal-scroll marker. Its audit verifies marker containment,
  actual overflow, bounded control reachability, and an unmarked-overflow canary.
- Focused Vitest passed AppShell 3/3, Sources 1/1, Knowledge frames 7/7, Studio
  frames 3/3 in isolated runs. Default and exact rollback all-screen Playwright
  each passed 7/7. Default/rollback Next builds, lint, tsc, feature contract,
  rebrand audit, and diff-check passed. `.last-run.json` restored to baseline
  SHA `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`.
- Open item: visual/accessibility atomic commit still pending; no packaging,
  install, merge, or push performed.

## 2026-08-11 final repair re-entry

- Security commit `621dce56` restores explicit IPv6 loopback MCP support: `::1`
  is accepted before Python's reserved classification, mapped loopback remains
  allowed, and mapped/non-mapped link-local, unspecified, multicast, and
  reserved answers remain blocked. Direct validate/connect/factory and unsafe
  IPv4/IPv6 regressions are included. MCP focused/adjoining command passed
  71/71 with 7 warnings.
- Visual/test changes are pending atomic commit: the clipped-control helper
  now flags partial horizontal clipping, only exact Sources marker exemptions
  may scroll, marked containers must be fully contained, and each clipped
  control is checked after bounded target/max/initial scroll with restoration.
  The hostile canary is x=280 width=80 in a 320px viewport. Rollback uncovered
  and repaired compact Podcast Studio controls (wrapped storyboard actions and
  bounded production-review button). Default and rollback all-screen matrices
  passed 7/7 each; focused Vitest passed 3 files/16 tests, both Next builds,
  frontend lint/tsc, diff-check, and rebrand audit (0 unexpected active
  identities) passed. `.last-run.json` restored to baseline SHA
  `e22df5d0991eb28c09093b1e678b3fa8cd1fab48185d38e67cf79fb6e63ad5ea`.
- Open item: visual/test atomic commit and parent reconciliation remain;
  packaging/install/merge/push are not performed.
