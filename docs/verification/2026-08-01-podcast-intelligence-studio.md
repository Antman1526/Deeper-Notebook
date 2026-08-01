# Podcast Intelligence Studio verification record

Status: **partially verified; controlled native-runtime safe-entry proof passed**

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
| Production frontend build | passed | Next.js production build completed as the native browser test's web-server precondition after Episode Lab and library changes |
| Browser safe-entry check | passed: 1 test | A live isolated API + SurrealDB runtime on loopback; completed-onboarding state; mobile Studio route; no selection and zero Studio submission |
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

1. The prior application port `http://localhost:65060/health` remains
   unavailable. A separate isolated development runtime did pass
   `http://127.0.0.1:5055/health` after applying all 40 migrations, but it is
   not a packaged desktop-app proof.
2. Repeat the protected-source proof through a supported native application
   runtime against the designated external read-only mounts, including
   whole-notebook preview, oversize fail-closed state, outline
   approval/reorder, cancellation, retry, and Episode Lab playback.
3. The controlled database has no local model routes or worker. Production
   submission, audio generation, and model-plan readiness are therefore not
   proven and were not attempted.

## Safety boundary

The canonical Obsidian and Logseq folders remain external read-only inputs.
This verification run did not mount, scan, alter, or hash either user folder.
