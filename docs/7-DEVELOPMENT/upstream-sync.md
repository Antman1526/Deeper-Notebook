# Safe Upstream Sync

Open Notebook Plus tracks the original project as `upstream`, but Plus has
desktop, local-model, Evidence Studio, and BrainPulseKnowledge changes that
must not be overwritten by a blind pull.

Use this process when `lfnovo/open-notebook` has new updates.

## One-Time Safety Rule

Disable accidental pushes to the original repository:

```bash
git remote set-url --push upstream DISABLED
```

The fetch URL stays active, so updates can still be pulled read-only.

## Standard Flow

1. Finish or checkpoint current Plus work.
2. Run the guard:

```bash
scripts/upstream_sync_guard.sh prepare
```

3. If the current worktree is dirty, the guard writes a recovery snapshot and
   stops before any merge happens.
4. When the worktree is clean, the guard creates an integration worktree and
   starts the upstream merge there.
5. Resolve conflicts in the integration worktree only.
6. Run the verification ladder.
7. Merge the integration branch back into `desktop-app` only after the checks
   pass.

## Why A Separate Worktree

The main `desktop-app` checkout often contains active Plus development. A
separate worktree lets maintainers inspect upstream changes, resolve conflicts,
and run tests without risking local work.

## Preserve These Plus Areas

During conflict resolution, protect these areas unless there is a deliberate
replacement plan:

- Desktop launcher and native app startup files under `desktop/`.
- Local model inventory, manifest, benchmark, launch-default, and health APIs.
- `AI_Models` integration rooted at `/Users/Antman/Desktop/AI_Models`.
- Evidence Studio artifact API, schemas, domain model, exports, and frontend rail.
- ONP shadow components under `frontend/src/components/onp/`.
- Source ingestion safety: async defaults, upload caps, retry preflight,
  processing progress, extraction-quality signals, and source-readiness gates.
- BrainPulseKnowledge export/import paths.

## Verification Ladder

At minimum, run focused checks that cover Plus behavior and upstream-touching
surfaces:

```bash
uv run pytest tests/test_evidence_studio_artifact_api.py \
  tests/test_sources_api.py \
  tests/test_v0_8_39_local_models_inventory.py \
  tests/test_local_model_role_routing.py

cd frontend
npm test -- --run src/components/onp/ArtifactRail.test.tsx \
  src/app/'(dashboard)'/settings/local-models/page.test.tsx
npx tsc --noEmit
npm run lint
```

For browser proof, start the local preview with the fixture API URL, then run
the smoke harness:

```bash
cd frontend
PORT=3100 NEXT_PUBLIC_API_URL=http://127.0.0.1:5055 npm run start

cd ..
ONP_BASE_URL=http://127.0.0.1:3100 \
ONP_FIXTURE_API_PORT=5055 \
node output/playwright/onp-visual-smoke.mjs
```

## Useful Read-Only Commands

Compare branch divergence:

```bash
git rev-list --left-right --count desktop-app...upstream/main
```

Preview upstream file churn:

```bash
git diff --stat desktop-app..upstream/main
```

List upstream commits:

```bash
git log --oneline --decorate desktop-app..upstream/main
```

## Do Not

- Do not run `git pull upstream main` directly on `desktop-app`.
- Do not merge upstream with a dirty worktree.
- Do not accept upstream deletions of Plus-only files without review.
- Do not skip the browser smoke when upstream touches frontend routing,
  source ingestion, settings, model selection, or notebooks.
