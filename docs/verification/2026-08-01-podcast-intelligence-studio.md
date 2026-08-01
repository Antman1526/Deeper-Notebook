# Podcast Intelligence Studio verification record

Status: **partially verified; native-runtime proof blocked**

This record distinguishes the implemented Studio and Episode Lab behavior from
the still-unavailable persistent local runtime. It contains no external vault
paths, source bodies, credentials, or model paths.

## Revision and tools

- Revision under test: `5e4f3a17` (before this verification-record commit)
- Python test runner: pytest 9.0.3
- Frontend test runner: Vitest 4.1.8
- Browser runner: Playwright 1.61.1
- Node: v24.17.0; npm: 11.13.0

## Completed checks

| Check | Result | Scope |
| --- | --- | --- |
| Podcast backend serial slice | passed: 82 tests | Selection contracts/service, Studio API/migration, command safeguards, audio containment, staged/offline behavior, verifier tests |
| Studio frontend focused slice | passed: 27 tests | Studio, Quick Podcast, selection store, Episode Lab, library, player, transcript, and podcast components |
| Episode Lab/library slice | passed: 8 tests | Library groups and filters; route-persistent player handoff; transcript/citation status; retry/cancel eligibility; global player and synced transcript |
| TypeScript | passed | `npx tsc --noEmit` after Episode Lab and library changes |
| Production frontend build | passed | Next.js production build after Episode Lab and library changes |
| Browser safe-entry check | blocked by native API | The native-runtime spec is collected and requires the app shell's persistent local API; it refuses a partial stubbed proof |
| Synthetic protected-source proof | passed with blocked native gates | [JSON record](2026-08-01-podcast-intelligence-studio-synthetic-proof.json) |

The synthetic proof created two owned temporary fixture notes. Its inventory
hash was `8e8deca5d1b377a688baa6375844203b4af0d4a3b39c9c8cb975655f1b383490`;
hashes remained equal before and after the preview, fake-worker submit, retry,
and metadata review. It recorded zero external writes. Semantic selection stays
blocked until a verified unified embedding index exists.

## Commands exercised

```text
uv run pytest -q tests/test_verify_podcast_studio.py
uv run ruff check scripts/verify_podcast_studio.py tests/test_verify_podcast_studio.py
(cd frontend && npx playwright test e2e/podcast-intelligence-studio.spec.ts --project=native-runtime --reporter=line)
(cd frontend && npx vitest run src/components/podcasts/PodcastLibrary.test.tsx src/components/podcasts/EpisodeLab.test.tsx src/components/podcasts/GlobalAudioPlayer.test.tsx src/components/podcasts/SyncedTranscript.test.tsx --pool=forks --maxWorkers=1 --reporter=verbose)
(cd frontend && npx tsc --noEmit)
uv run python scripts/verify_podcast_studio.py --output docs/verification/2026-08-01-podcast-intelligence-studio-synthetic-proof.json
```

## Open gates

1. Start a persistent native API plus SurrealDB runtime and verify its loopback
   `/health` route. At this record time, `http://localhost:65060/health`
   returned HTTP 000.
2. Repeat the protected-source proof through that native runtime and browser
   environment, including whole-notebook preview, oversize fail-closed state,
   outline approval/reorder, cancellation, retry, and Episode Lab playback.
3. Run the final browser suite after the persistent runtime is available. The
   current browser spec is intentionally blocked without that API rather than
   substituting partial route stubs for a live desktop/database proof.

## Safety boundary

The canonical Obsidian and Logseq folders remain external read-only inputs.
This verification run did not mount, scan, alter, or hash either user folder.
