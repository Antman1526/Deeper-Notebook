# Study Workbench Task 13 receipt

Date: 2026-08-12
Branch: `codex/study-workbench`
Base/starting HEAD: `e061ead9` (`fix(study): gate tutor by approved syllabus`)
Owned exactly the nine brief paths; `.codex/agent-context/study-task-13.md`
remains unrelated and untracked.

## TDD evidence

RED was recorded before production files existed. The exact focused command
failed at backend collection because `api.routers.study_voice` was missing and
at frontend collection because `StudyVoiceTutor` was missing.

GREEN focused evidence:

- backend voice suite: 8 passed;
- adjoining command: 8 passed, 18 deselected;
- frontend `StudyVoiceTutor` + `StudyLearningSession`: 6 passed;
- scoped ESLint and TypeScript: passed.

The tests cover feature-off 404, invalid/remote plan authority, explicit local
provider checks (including Esperanto's `openai-compatible` spelling), absent
capability/no cloud fallback, MIME and duration bounds, streamed 25 MiB upload,
temporary-file cleanup on success/cancellation, empty/oversized transcripts,
bounded TTS input/output, safe audio MIME, microphone denial/cancel, and object
URL cleanup.

## Implementation summary

- Added plan-authorized local-only STT/TTS service with strict provider-record
  preflight, normalized Esperanto signatures, 25 MiB task-owned upload files,
  bounded UTF-8 transcript/TTS text, response MIME/byte checks, timeouts, and
  safe error codes.
- Added feature-gated transcribe/synthesize routes and strict assistant-adjacent
  request/response contracts.
- Added an optional MediaRecorder UI that requests the microphone only after a
  user gesture, handles denial/cancel/unmount, revokes audio URLs, and leaves
  the existing TutorDock usable when either speech capability is unavailable.

## Verification

- `uv run pytest -q tests/test_study_voice_tutor.py tests/test_capture_routing.py tests/test_models_api.py -k 'speech or voice or study or transcri'`: 8 passed, 18 deselected.
- `uv run ruff check ...`: passed.
- `uv run python -m compileall -q` on all touched Python paths: passed.
- Frontend focused Vitest: 2 files / 6 tests passed; scoped ESLint and `tsc --noEmit`: passed.
- `NEXT_PUBLIC_DN_STUDY_WORKBENCH=enabled npm run build`: passed.
- `git diff --cached --check`: passed; staged gitleaks: 0 leaks (~47 KB).

## Open limits

The UI receives an explicit capability receipt prop and defaults closed when no
receipt is supplied; capability discovery is outside the nine-file Task 13
scope. Full browser/device, hosted, release, and real local-model runtime proof
remain separate gates. No cloud/provider, database, media, or deployment
mutation was performed.

## Task 13 review repair receipt — 2026-08-12

Repair started clean at `891f9d11`; the supplied `.codex/agent-context/` file
remains untracked. The review RED was captured before repair production edits:
backend collection reached 1 passed / 21 failed because the credential-loader,
capability, duration, and operation contracts were absent; frontend targeted
voice/session tests reached 7 passed / 2 failed on ready capability discovery
and cancel-then-new synthesis. Strict decoder RED was 2 failed before the
exact-key boundary was added.

Repair GREEN and scope:

- `StudyVoiceService` now reads only a fixed non-secret Credential projection
  (`provider`, `base_url`, endpoint fields), rejects cross-table links, requires
  a linked persisted credential (no env fallback), and accepts only exact
  localhost/127\/8/::1 endpoints. Public HTTPS, LAN/link-local, userinfo and
  suffix-spoof hosts fail closed before speech invocation; exposed Esperanto
  runtime endpoints are checked again without requiring a runtime `.provider`.
- `GET /api/study/plans/{plan_id}/voice:capability` is approved-plan and feature
  gated, performs the same persisted policy without acquiring STT/TTS, and
  returns only `{stt,tts}` readiness. UploadFile is closed in the route finally.
- Learn discovers the receipt fail-closed, feeds every dictated transcript into
  TutorDock without dispatch, and exposes the latest successful answer to an
  explicit user-gesture Play control without autoplay. Per-operation IDs and
  abort controllers suppress stale cancellation completions; returned numeric
  Esperanto duration is finite/nonnegative and capped at five minutes.
- Client decoders reject extra provider metadata. Narrow adjoining changes are
  limited to `TutorDock.tsx` plus `frontend/src/lib/api/study-voice.test.ts` and
  the approved Study session/voice tests.

Final repair evidence:

- `uv run pytest -q tests/test_study_voice_tutor.py`: 30 passed.
- Adjoining filtered backend command: 30 passed, 18 deselected.
- Frontend voice/session/TutorDock/API Vitest: 4 files / 19 passed; scoped
  ESLint (two existing unused stub-argument warnings only) and TypeScript pass.
- Ruff, compileall, `git diff --check`, and flag-on Next build pass.
- Staged gitleaks and the `891f9d11..HEAD` commit-range scan both report 0
  leaks. The atomic repair commit uses subject
  `fix(study): enforce local voice capability`; no provider, credential,
  database, media, network, or deployment mutation occurred.

Repair open limits remain browser/device accessibility/runtime proof and real
local Esperanto model execution; hosted/release gates are separate.
