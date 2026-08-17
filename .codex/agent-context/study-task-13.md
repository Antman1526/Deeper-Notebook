# Study Workbench Task 13 context

- Worktree: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook/.worktrees/study-workbench`
- Branch: `codex/study-workbench`
- Starting HEAD: `e061ead9` after independently approved Task 12.
- Global context: `/Users/Antman/.codex/context.md`
- Approved design: `docs/superpowers/specs/2026-08-11-deeper-notebook-study-workbench-design.md`
- Approved plan: `docs/superpowers/plans/2026-08-11-deeper-notebook-study-workbench.md`
- Exact brief: `.superpowers/sdd/task-13-brief.md`

## Objective

Implement optional, local-only Study voice transcription and synthesis through
the existing local model manager. Voice is an enhancement to the single text
tutor, never a replacement and never a network/provider fallback.

## Required boundaries

- Feature gate all new Study endpoints consistently with existing Study APIs.
- Preserve Task 12 approved-plan lifecycle gating and text-tutor behavior.
- Validate the plan ID and require an authorized Study plan before voice work;
  do not create an authority bypass through the voice endpoints.
- Stream uploaded audio into a task-owned temporary file with a hard 25 MiB
  cap; allow only explicit audio MIME types; delete the file in `finally` on
  success, failure, timeout, or cancellation.
- Enforce duration metadata when reliably available, but never claim decoded
  media-duration proof from MIME/header guesses alone.
- STT transcript: nonblank, at most 16 KiB UTF-8. TTS input: nonblank, at most
  8 KiB UTF-8. TTS output: bounded bytes and explicit safe audio MIME.
- Resolve only `model_manager.get_speech_to_text()` and
  `get_text_to_speech()`; absence returns safe `local_speech_unavailable` and
  must not call any cloud/network model even if the plan permits web models.
- Normalize different local model call signatures behind one adapter and avoid
  exposing paths, provider payloads, stack traces, or raw model errors.
- UI uses microphone/MediaRecorder only after an explicit user gesture,
  handles denial/cancel/unmount, revokes object URLs, and remains optional when
  either capability is absent.

## TDD and verification

1. Add strict backend and frontend RED tests before production code.
2. Implement the nine brief-owned paths only unless a discovered contract
   requires a narrowly justified adjoining test.
3. Run exact focused backend/frontend commands from the brief, adjoining speech
   model tests, Ruff, ESLint, TypeScript, compile/diff checks, and a flag-on
   frontend build.
4. Scan staged and commit range with gitleaks, preserve unrelated state, commit
   atomically as `feat(study): add optional local voice tutoring`.
5. Append milestones, final evidence, and open limits here and to the global
   context. Do not begin Task 14.

## Done criteria

- All prescribed behavior has executable tests, including absent capability,
  MIME/size/cleanup/no-cloud fallback/empty output/bounded TTS/cancel/denial.
- No Critical or Important concern remains in self-review.
- Exact file list, RED/GREEN evidence, static/build results, sensitive scan,
  commit hash, and residual runtime limits are reported.

## Task 13 execution result — 2026-08-12

- DONE at commit `891f9d11` (`feat(study): add optional local voice tutoring`),
  with exactly the nine brief-owned paths changed. The supplied task context
  remains untracked by repository convention.
- RED: backend collection failed on missing `api.routers.study_voice`; frontend
  collection failed on missing `StudyVoiceTutor`. GREEN: voice 8 passed;
  adjoining filtered command 8 passed/18 deselected; frontend voice/session
  6 passed; Ruff, scoped ESLint, TypeScript, compileall, diff checks, and the
  flag-on Next build passed. Staged and `e061ead9..HEAD` gitleaks found 0 leaks.
- Local-only authority is preflighted from persisted default Model records,
  requiring speech type plus `ollama`/`openai_compatible` provider (runtime
  Esperanto `openai-compatible` is normalized). Remote defaults never call a
  speech getter. Voice accepts only approved Study lifecycle states, streams
  uploads at 25 MiB, cleans task files on all exits, bounds transcript/TTS
  UTF-8 and audio MIME/bytes, and exposes only safe errors.
- Report: `.superpowers/sdd/task-13-report.md`. Open limits: capability
  discovery is outside the nine-file scope and UI defaults closed without a
  supplied receipt; browser/device, hosted, release, and real-model runtime
  proof remain separate. No cloud/provider/database/deployment mutation.

## Task 13 review repair milestone — 2026-08-12

- Repair starts at `891f9d11`; task context stays untracked. RED: backend 1/21
  (new credential/capability/duration contracts absent), frontend 7/2 (ready
  receipt and stale cancel/new TTS), strict API decoder 0/2. GREEN before final
  hardening: voice backend 30/30, adjoining filtered 30/30, frontend voice /
  session / TutorDock / API 19/19, Ruff/compileall/diff, ESLint/tsc, and flag-on
  build pass.
- Persisted local authority is now Model -> fixed non-secret Credential
  projection only (`provider`, base_url, endpoint_stt/tts, endpoint); exact
  `credential:` links required; env fallback and cross-table/corrupt links fail
  closed. `_is_local_speech_endpoint` accepts only exact localhost, 127/8, or
  ::1 and rejects public/LAN/link-local, userinfo, suffix spoof, malformed,
  missing, and unreadable config. Runtime Esperanto `.base_url` is checked when
  exposed; runtime `.provider` remains optional. Capability uses the same policy
  without speech getter acquisition.
- Added feature-gated approved-plan capability receipt, route-level UploadFile
  close, Learn receipt discovery, transcript->TutorDock composer (no dispatch),
  answer->explicit Play (no autoplay), operation identity/cancellation reset,
  and finite/nonnegative model-returned duration <=300s. Client capability and
  transcript decoders are exact-key strict. Repair commit `d3e228ac` uses exact
  subject `fix(study): enforce local voice capability`; pre-commit staged and
  post-commit `891f9d11..HEAD` gitleaks scans report 0 leaks.

## Task 13 third repair milestone — 2026-08-12

- Third repair starts at `d3e228ac`. RED: backend voice 30 passed/6 failed
  (Esperanto Path contract and capability runtime acquisition/timeout); frontend
  targeted 19 passed/2 failed (event envelope and strict audio bounds).
- `_invoke_transcriber` now passes `str(path)` to installed Esperanto STT.
  Capability calls bounded common `_local_model` after persisted loopback
  policy, so getter/factory errors, unsupported Ollama speech, public runtime
  endpoint, and timeout all report unavailable without leakage. Valid
  OpenAI-compatible runtime is accepted. TutorDock receives monotonic
  `{id,text}` events, preserving repeated identical dictation after edits; TTS
  client accepts only server audio MIME allowlist and <=10 MiB.
- GREEN: voice 36/36; adjoining filtered backend 36/36 with 18 deselected;
  Study component/API 13 files/64 tests; Ruff/compileall/diff, ESLint (0 errors,
  2 existing RecorderStub unused-arg warnings), tsc, and flag-on Next build pass.
  Repair commit `9905c271` uses exact subject `fix(study): verify local voice
  runtime`; staged and `d3e228ac..HEAD` gitleaks scans report 0 leaks. Supplied
  task context remains untracked.
