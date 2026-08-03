# Podcast Intelligence Studio verification record

Status: **controlled verification passed; packaged-device, real-worker, and
external-mount proof remain open.**

This record keeps three boundaries distinct: owned synthetic service execution,
deterministic browser fixtures, and the task-owned loopback runtime. None is a
claim about a packaged desktop build, a real model worker, audio decoding, or a
user vault.

## Scope and environment

- Source base: `46e26347`; Task 8 verification changes were uncommitted when
  the receipts below were captured.
- Python: pytest 9.0.3; frontend: Vitest 4.1.8; browser receipt:
  @playwright/test 1.61.1; Node v24.17.0; npm 11.13.0.
- Persistent runtime: task-owned API `127.0.0.1:65060` backed by task-owned
  SurrealDB `127.0.0.1:65059`. It used disposable data and credentials outside
  the repository and user data directories.
- No external Obsidian or Logseq vault was mounted, scanned, hashed, or
  modified. Browser and service fixtures contain only owned synthetic content.

## Executed results

| Check | Result | Evidence boundary |
| --- | --- | --- |
| Backend serial slice | passed: 109 tests | Selection/service/API/migration/command/audio/staged/offline/verifier suites |
| Scoped Python lint | passed | Required podcast paths and selection/API tests |
| Focused frontend slice | passed: 19 files, 74 tests | Podcast components, library utilities, and Studio store |
| Frontend production build | passed | Next.js production build |
| Native-runtime browser receipt | passed: 5 cases | Isolated loopback app with deterministic podcast/selection fixtures |
| Synthetic verifier | passed | [Aggregate JSON receipt](2026-08-01-podcast-intelligence-studio-synthetic-proof.json) |
| Standalone TypeScript | inherited failure: 13 diagnostics | Existing unrelated test typing in ThemeProvider, theme-store, and use-knowledge-workspace |

The browser receipt covers safe empty Studio entry on a 390px viewport;
outline approval and keyboard reorder; active cancellation; Episode Lab player
handoff through a protected audio response fixture; retry-to-Studio;
whole-notebook oversize fail-closed behavior; strict-local request receipts;
reduced motion; 200-percent page-scale visibility; keyboard-only note/source
entry; and no Studio submission after cancellation. It also proves notebook,
app-note, and app-source entry payloads against a task-owned notebook/note.

Saved search, graph selection, external knowledge document, and selected block
have no equivalent standalone production-entry UI in this task environment.
The browser test therefore validates their retry selection wire values at the
Studio boundary; it does not label that coverage as a direct browser entry.

## Synthetic execution receipt

The verifier calls application/service code with injected fixture-only seams:

1. It creates an owned temporary Obsidian/Logseq pair and prepares a read-only
   saved-search selection through `PodcastSelectionService`.
2. It executes fake-worker submission and the real retry handler, including its
   durable retry fence and removal of an owned 21-byte old audio file.
3. It records zero fixture-boundary write attempts and compares fixture hashes
   before/after. The aggregate inventory hash is
   `8e8deca5d1b377a688baa6375844203b4af0d4a3b39c9c8cb975655f1b383490`.
4. It accepts the browser gate only from a JSON report for exactly five passing,
   unskipped `native-runtime` cases targeting
   `e2e/podcast-intelligence-studio.spec.ts`.

Semantic unified-index selection intentionally remains blocked with
`verified_unified_embedding_index_required`; it is reported separately and is
not treated as evidence of a live external source search.

## Commands exercised

```text
uv run pytest -q tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_podcast_studio_api.py tests/test_podcast_studio_migration.py tests/test_podcast_command_defenses.py tests/test_podcast_audio_containment.py tests/test_v0_8_68_podcast_staged.py tests/test_v0_8_68_podcast_offline_gate.py tests/test_verify_podcast_studio.py
uv run ruff check deeper_notebook/podcasts api/routers/podcasts.py api/podcast_service.py commands/podcast_commands.py tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_podcast_studio_api.py
(cd frontend && npx vitest run src/components/podcasts src/lib/podcasts src/lib/stores/podcast-studio-store.test.ts --pool=forks --maxWorkers=1)
(cd frontend && npx tsc --noEmit) # inherited unrelated test typing failures
(cd frontend && npm run build)
(cd frontend && PLAYWRIGHT_JSON_OUTPUT_FILE=<owned-temp>/playwright.json API_URL=http://127.0.0.1:65060 INTERNAL_API_URL=http://127.0.0.1:65060 npx playwright test e2e/podcast-intelligence-studio.spec.ts --project=native-runtime --reporter=json)
DEEPER_NOTEBOOK_LOG_DIR=<owned-temp>/logs uv run python scripts/verify_podcast_studio.py --native-url http://127.0.0.1:65060 --playwright-report <owned-temp>/playwright.json --output <owned-temp>/proof.json
```

## Open gates

1. Packaged-device launch, accessibility, and Gatekeeper checks were not run.
2. No real local model route/worker or real audio decode/playback was invoked;
   browser audio uses a protected synthetic response and asserts player handoff.
3. No live external read-only mount scan or projection was attempted.
4. Semantic unified-index selection remains intentionally blocked until a
   verified index is available.
5. `npx tsc --noEmit` remains blocked by the 13 pre-existing diagnostics in
   unrelated frontend test files noted above; production build still passed.
