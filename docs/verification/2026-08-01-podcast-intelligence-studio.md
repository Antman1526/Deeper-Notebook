# Podcast Intelligence Studio verification record

Status: **controlled verification passed at final repair revision
`d0962f4d0dac8b74df84503f991722fe90b5c15c`; packaged-device, live-worker,
audio-decode, semantic-index, and current external-vault proof remain open.**

This record separates the owned synthetic source boundary, deterministic
browser fixture, and task-owned loopback runtime. It does not claim a packaged
desktop run, an installed model worker, decoded or played live audio, or a user
vault mount or scan.

## Current controlled run

- Runtime revision: `d0962f4d0dac8b74df84503f991722fe90b5c15c`. The task-owned
  API health response at `127.0.0.1:65060` returned that exact opt-in,
  checkout-verified `proof_revision`.
- Runtime data: disposable API data and SurrealDB on task-owned loopback ports
  `65060` and `65059`; no user data or credentials were used.
- Browser receipt: [sanitized five-case native-runtime receipt](2026-08-03-podcast-intelligence-studio-playwright.json).
  The verifier launched Playwright itself, kept the raw path-bearing report in
  an ephemeral directory, required the exact five spec titles and matching
  runtime-revision annotations, then wrote this deterministic aggregate. It
  records five expected, five passed, zero skipped, and zero unexpected.
- Independent result: [synthetic verifier proof](2026-08-03-podcast-intelligence-studio-proof.json)
  passed. It records zero fixture-write attempts, zero external-write receipts,
  unchanged source hashes, and successful old-audio deletion before temporary
  cleanup.
- No current run mounted, scanned, hashed, projected, or modified an Obsidian
  or Logseq user vault. The verifier used a newly created sentinel-owned
  temporary Obsidian/Logseq pair only.

## Executed checks

| Check | Result |
| --- | --- |
| Backend Task 8 serial slice | 120 passed; 7 dependency deprecation warnings |
| Scoped Ruff, including every touched Python path | passed |
| Focused frontend Task 8 slice | 20 files, 79 tests passed; includes selection-preserving Studio handoff and modal pointer-lock regressions |
| `npm exec -- tsc --noEmit` comparison | 13 inherited diagnostics only: ThemeProvider, use-knowledge-workspace, and theme-store tests |
| `npm run build` | passed |
| Native Playwright enumeration | exactly 5 Task 8 cases |
| Revision-bound native Playwright receipt | 5/5 passed against `d0962f4d...c15c` |
| `scripts/verify_podcast_studio.py --expected-revision d0962f4d...c15c` | passed; owns Playwright execution and validates health, exact spec identities, and every report annotation |

The serial matrix used these commands, in order:

```text
uv run pytest -q tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_podcast_studio_api.py tests/test_podcast_studio_migration.py tests/test_podcast_command_defenses.py tests/test_podcast_audio_containment.py tests/test_v0_8_68_podcast_staged.py tests/test_v0_8_68_podcast_offline_gate.py tests/test_verify_podcast_studio.py
uv run ruff check deeper_notebook/podcasts api/main.py api/routers/podcasts.py api/podcast_service.py commands/podcast_commands.py scripts/verify_podcast_studio.py tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_podcast_studio_api.py tests/test_verify_podcast_studio.py
(cd frontend && npm exec -- vitest run src/components/podcasts src/lib/podcasts src/lib/stores/podcast-studio-store.test.ts src/components/vault/VaultGraph.test.tsx --pool=forks --maxWorkers=1)
(cd frontend && npm exec -- tsc --noEmit) # inherited comparison only; 13 unrelated diagnostics
(cd frontend && npm run build)
```

## Browser coverage and containment

The native receipt invokes production UI controls, not a retry-selection
shortcut: notebook, app note, app source, exact and text Search, graph
conversion, the external knowledge document action, and a real reader
double-click selection for the identified block. Each Quick review carries its
exact selection into Studio, performs a second readiness review, and closes
without a submission. The handoff waits for the modal to release its pointer
lock, so the Studio remains mouse-operable after navigation. The receipt
also covers non-loopback request aborting, an override rejected by readiness
with confirmation disabled and zero submit, Episode Lab's `Play in global
player` handoff, and selected-block identity receipt.

Every HTTP(S) browser request is recorded and must target a task-owned loopback
host. The strict fixture rejects unregistered requests and records no external
mutation. Its allowed local-model settings and route-plan calls are read-only
synthetic responses; they do not invoke a model or worker.

The verifier's synthetic selection flow deliberately keeps semantic selection
blocked with `verified_unified_embedding_index_required`. This is not evidence
of a live semantic index.

## Historical external-vault containment evidence — not this run

The following is retained as historical, controlled evidence of the original
external-vault boundary. It is not a claim that the current Task 8 run mounted
or scanned those paths.

The rebuilt native application was started locally with both designated external
mounts still read-only and watcher-disabled. A controlled Obsidian scan returned
`409 vault_unavailable` after 15.016 seconds, and a follow-up vault-list request
returned `200`; this proves a macOS filesystem stall is contained rather than
freezing the API. The Markdown inventory fingerprints before and after remained:

- Obsidian: `7e471f9e0b1694f5bb7b454178f0e66842f877f542031af36a6caffeb341a8e2`
- Logseq: `4bd3b904ead8cf13a7d62b6945a76e3dd9f5c5d08444fec502a102175ddcd02c`

The historical scan did not reach projection because the packaged process lacked
the required macOS filesystem permission. No external source write occurred.

## Open gates

1. Packaged-device launch, accessibility, and Gatekeeper checks were not run.
2. No real local model route/worker or live audio decode/playback was invoked.
3. No current live external read-only mount scan or projection was attempted.
4. Semantic unified-index selection remains blocked until a verified index is
   available.
