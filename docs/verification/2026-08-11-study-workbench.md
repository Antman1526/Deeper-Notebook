# Study Workbench release-proof receipt

## Scope and boundary

- Date: 2026-08-13
- Repository: `Deeper-Notebook`
- Worktree: `codex/study-workbench`
- Scope: Task 18 isolated source-to-study proof, restart parity, authoritative
  regression gates, and the default-on Study Workbench boundary.
- Rollback: set `DEEPER_NOTEBOOK_STUDY_WORKBENCH=0` for the backend or
  `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0` for the frontend. Unset values are now
  enabled by default.
- The proof used only deterministic local PDF/video fixtures, a loopback model
  fixture, a disposable Surreal namespace/database, and exact task-owned
  processes. No user vault, credential, document, external source, or hosted
  provider was used.

## Two-phase real proof

The prepare and verify phases were separate process invocations over the same
task-owned database. The verifier-local supervisor launched the production API,
worker, frontend, Surreal, and model commands and recorded bounded PID/start
identity and argv digests. The desktop Supervisor was not used because it binds
canonical user state.

| Receipt | Result |
| --- | --- |
| Prepare phase | Exit `5` by design (`external_restart_required`); source-to-study workflow and restart receipt persisted. |
| Verify phase | Separate invocation, exit `0`; replacement process identities were new and durable parity passed. |
| API/frontend/Surreal/model ports | `47121` / `47122` / `47123` / `47124`; all free after cleanup. |
| Namespace/database | `study_ns_task18final` / `study_db_task18final`; disposable and removed with the owned stack. |
| PDF fixture SHA-256 | `c53cdfea5754c74335e25ce635dd34653a569fc79aabe17f2305cb6e863d1fe0` before and after. |
| Video fixture SHA-256 | `b9ed66ed0da82b86c39ef04173cfaae8c573b3ab3cfea0d63a273923816f5c47` before and after. |
| External sentinel SHA-256 | `72b6720b0bdcc14c91357f26dabb26b28bfaad91d587fe08d4fa6f5667db0e79` before and after. |
| External writes | `0`. |
| Final report | Sanitized report outcome `PASSED`, blocker `none`; no credentials, prompts, payloads, document contents, or raw home paths. |
| Cleanup | Task root removed; all four listeners free; no proof-labeled Docker containers; external sentinel retained. |

The workflow crossed the real HTTP/API boundaries for both sources, source
processing/readiness, plan and source links, syllabus proposal/edit/approval,
unit generation, Source Guide and Practice Coach, progress/review cards, Anki
export/preview/publish/import, and post-restart durable queries. The verifier
also checks receipt IDs, source/artifact/syllabus/Anki metadata, fixture hashes,
external write count, frontend Study marker, and exact-owned cleanup.

## Authoritative gates

| Gate | Exact command/result |
| --- | --- |
| Backend non-integration | `PYTHONPATH=. uv run pytest tests/ -q --ignore=tests/integration` — **4386 passed, 1 skipped, 14 warnings**. |
| Ruff | `uv run ruff check .` — exit `0`. |
| Rebrand audit | `uv run python scripts/rebrand_audit.py --check` — RC0; compatibility `825`, historical `1749`, migration `584`, unexpected `0`, upstream `99`, stale `0`. |
| Desktop | `./.build-venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q` — **823 passed, 2 skipped, 3 warnings**. |
| Real Surreal | `SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_plan_repository.py tests/integration/test_study_progress_repository.py -m integration_surreal` — **20 passed, 1 warning**. |
| Verifier unit | `uv run pytest -q tests/test_verify_study_workbench.py` — **17 passed, 6 warnings**. |
| Frontend unit | `npm test -- --run` — **229 files, 1624 tests passed**. |
| Frontend lint | `npm run lint` — exit `0`; two existing `_stream`/`_options` warnings in `StudyVoiceTutor.test.tsx`. |
| TypeScript | `npx tsc --noEmit` — exit `0`. |
| Frontend default-on build | `npm run build` — exit `0`; Study routes generated. |
| Frontend explicit-off build | `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build` — exit `0`. |
| Browser default-on | Study + all-screen mocked matrix with Study env unset — **22 passed, 1 skipped**, exit `0`. |
| Browser rollback | `NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0` same matrix — **8 passed, 15 skipped**, exit `0`; rollback test passed and Study matrix skipped. |
| Full mocked browser gate | `env -u NEXT_PUBLIC_DN_STUDY_WORKBENCH npm run test:e2e:mocked -- --workers=1` — **71 passed, 5 skipped**, exit `0`; six stale Luminous desktop baselines were refreshed against the current committed UI and the focused nine-test visual subset passed. |
| Feature flag contracts | Backend/frontend focused flag tests passed for default-on and explicit `0`. |

The canonical `npm run test:feature-build-contract` remains a known worktree
boundary: Next/Turbopack rejects the repository's `frontend/node_modules`
symlink as outside the filesystem root. The repository-equivalent Webpack
contract build and `node scripts/verify-feature-env-build.mjs` both passed RC0;
the canonical symlink diagnostic is retained honestly rather than relabeled.

The desktop exact gate required local-only build-environment remediation:
`httpx2`/`httpcore2` were removed from `.build-venv` after the regenerated lock
installed them, restoring the repository's expected `httpx` exception behavior.
No source or lockfile bypass was used; `.build-venv` is ignored local state.

## Review and limits

The implementation preserves the flag-off Study dashboard/review surface and
keeps all cleanup fail-closed. Source and artifact IDs are bounded to the
disposable proof namespace, and owner-link conflicts roll back newly-created
cards without exposing orphan due cards. Code Review Graph evidence was
unavailable because no graph artifact exists; direct source tracing and the
listed tests are the review evidence. This receipt does not claim native-device
browser, signed/notarized packaging, hosted CI, deployment, or public release.
