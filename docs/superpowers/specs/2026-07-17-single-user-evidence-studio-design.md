# Open Notebook Plus: Single-User Evidence Studio Design

**Date:** 2026-07-17
**Status:** Proposed for implementation
**Product boundary:** Personal, single-user, local-first. No accounts, teams, roles, public notebooks, or collaboration features.

## Purpose

Open Notebook Plus will become a private evidence-to-action studio that turns local and connected sources into verifiable answers, editable deliverables, adaptive learning material, and replayable research workflows. It will retain its existing local-model, privacy, podcast, Evidence Studio, and Course Pack strengths while closing the most important quality and workflow gaps with NotebookLM.

The product will not reproduce Google's identity, sharing, or cloud collaboration model. All new features must work for one owner and preserve local-first behavior. Cloud services remain optional and explicit.

## Product Principles

1. **Evidence before presentation.** Every generated claim must remain traceable to a source passage or be marked as unsupported.
2. **Structured before rendered.** Studio artifacts are generated into typed JSON schemas, validated, and then rendered or exported.
3. **Local by default.** Local files, models, speech, and exports remain first-class. Network access is visible and opt-in.
4. **Editable deliverables.** Generated decks, graphics, courses, and reports are working documents, not terminal chat responses.
5. **Replayable automation.** Research and synchronization runs retain their inputs, steps, approvals, outputs, and errors.
6. **One owner, many devices.** Mobile support is a personal companion and capture surface, not a multi-user service.

## Scope

### Included

- Typed Evidence Studio artifact schemas and schema-version migration.
- Claim-level citation validation, evidence coverage, and contradiction reporting.
- Finished slide deck exports in PPTX and PDF.
- Finished infographic exports in PNG and PDF.
- Agentic Research Runs with planning, web discovery, fetch, review, import, synthesis, pause, resume, cancel, and replay.
- Local watched folders and a connector framework for Google Drive, OneDrive, Dropbox, Notion, Git, RSS, and email ingestion.
- Source freshness, change detection, reprocessing, and artifact-staleness indicators.
- Adaptive flashcards, quizzes, mastery tracking, spaced repetition, Course Pack assignments, certificates, and local learning analytics.
- Installable PWA behavior, mobile share/capture flows, voice notes, camera/document capture, offline study data, and downloaded audio.
- Image/OCR/vision ingestion, spreadsheet ingestion, ePub ingestion, and video keyframe/scene enrichment.
- Interactive podcast questions and narrated video lesson generation.
- Local-model capability profiles, task benchmarks, vision routing, resource estimates, and optional private LAN inference nodes.
- Signed/notarized release pipeline hooks, update verification, and opt-in local crash reports.
- Refactoring required to split Studio orchestration from the oversized API router and remove duplicate artifact-generation logic.

### Explicitly Excluded

- User registration or login identities.
- Multi-user notebook permissions.
- Viewer/editor roles.
- Public notebook links.
- Shared comments, presence, or collaborative editing.
- Hosted SaaS billing, plans, quotas, or organization administration.

The existing optional single-password API gate remains for protecting a locally exposed instance. It is not expanded into an identity system.

## Architecture

### 1. Structured Artifact Core

Create a versioned artifact document contract under `open_notebook/studio/schemas/`. Each artifact type has a Pydantic schema and a stable discriminator. Initial schemas cover reports, flashcards, quizzes, data tables, mind maps, slide decks, infographics, Course Packs, podcast outlines, and Research Runs.

The generation flow becomes:

```text
selected sources
  -> normalized evidence bundle
  -> model structured output
  -> schema validation and bounded repair
  -> claim/citation validation
  -> persisted artifact document
  -> viewer and format-specific exporters
```

`StudioArtifact.output_payload` remains the persistence envelope for backward compatibility. New payloads include `schema_version`, `document`, `validation`, and `study_progress`. Existing markdown artifacts remain readable and can be lazily converted when edited or regenerated.

Generation and export logic move out of `api/routers/studio.py`. The router will validate HTTP input and call focused services. `open_notebook/studio/artifact_generation.py` will orchestrate generation; separate validators and exporters will own their formats.

### 2. Evidence and Trust Layer

The evidence bundle assigns stable passage identifiers to retrieved source spans. Generated claims reference one or more passage identifiers rather than only source-level markers. Validation computes:

- citation resolution rate;
- claim evidence coverage;
- unsupported claims;
- conflicting source passages;
- stale-source dependencies;
- extraction-quality warnings.

The UI shows an evidence summary and allows jumping from a claim to the exact source passage. Validation never silently deletes content. Unsupported claims are visibly flagged and can be regenerated, accepted, or removed by the owner.

### 3. Visual Deliverables

Slide decks use a structured slide model containing layout, title, body blocks, speaker notes, citations, and optional visual directions. PPTX generation uses `python-pptx`; PDF export uses the existing document conversion/runtime strategy where available and otherwise presents a clear dependency message. A browser slideshow viewer provides editing and per-slide revision.

Infographics use a constrained scene model rather than arbitrary HTML. The renderer supports headings, metric callouts, timelines, comparisons, process flows, charts, icons, images, and citations. A deterministic browser renderer exports PNG and PDF. The first release favors professional templates and editability over unrestricted image generation.

Narrated video lessons combine approved slides, generated narration, local or selected TTS, captions, and FFmpeg composition into MP4. Video generation is background work and may be cancelled or resumed.

### 4. Agentic Research Runs

A Research Run is a durable workflow, not a one-shot artifact prompt. Its state machine contains:

1. research question and constraints;
2. proposed plan;
3. optional owner approval;
4. search queries;
5. candidate-source review;
6. safe URL fetch and extraction;
7. deduplication and source-quality scoring;
8. evidence matrix and contradiction scan;
9. cited synthesis;
10. follow-up questions and export.

All external tool calls are logged. Network access is explicit. The run can pause, resume after restart, cancel, and replay from the retained plan. Imported sources become ordinary notebook sources, so later chat and artifact generation use the same evidence.

### 5. Source Connectors and Freshness

Introduce a connector protocol with `discover`, `snapshot`, `fingerprint`, `fetch`, and `describe_auth` operations. The first production connector is a native watched-folder connector because it provides maximum value without cloud credentials. Subsequent connectors are optional adapters.

Each synchronized source stores connector identity, external identity, content fingerprint, last checked time, last changed time, and sync status. A changed source is re-extracted and re-embedded through the existing job queue. Artifacts depending on changed sources are marked stale but are not automatically overwritten.

Cloud connectors store tokens using the existing encrypted credential system. Sync is owner-configured, rate-limited, and disabled in forced-offline mode.

### 6. Adaptive Learning and Course Packs

Study progress becomes a first-class versioned record rather than incidental viewer state. Flashcards use a deterministic spaced-repetition scheduler. Quizzes store attempts, correctness, explanations, cited evidence, topic tags, difficulty, and confidence. A mastery profile aggregates performance by notebook topic.

Course Packs gain:

- editable modules and lesson ordering;
- learner and instructor views;
- assignment and completion states;
- adaptive remediation suggestions;
- certificates generated locally;
- xAPI statement export and optional local LRS delivery;
- source-change warnings and guided course regeneration.

No student accounts are introduced. The single owner can use learner mode personally or export SCORM/xAPI packages to an external LMS.

### 7. Personal Mobile Companion

The existing responsive frontend becomes an installable PWA. The manifest, service worker, icons, offline shell, and update lifecycle are owned by the frontend. Mobile navigation uses dedicated Source, Chat, Studio, and Learn views rather than compressed desktop columns.

Mobile capture supports:

- OS share-target ingestion for URLs and supported files where the platform permits;
- text and voice notes;
- camera/document images;
- queueing captures while the local desktop API is unavailable;
- replaying the queue after reconnecting;
- offline flashcards, quizzes, and downloaded podcast/video playback.

The companion connects to the owner's desktop over a configured local/private URL and existing API password. It does not establish a hosted synchronization service.

### 8. Multimodal Ingestion

Image ingestion performs metadata extraction, OCR, and optional vision-model description. Spreadsheets preserve sheet names, tables, formulas-as-text, and row/column references. ePub ingestion preserves chapter structure. Video enrichment samples bounded keyframes and scenes in addition to transcription.

Every extractor returns normalized text, structured metadata, extraction quality, and provenance. Vision calls respect offline and privacy routing. If no vision model is available, OCR and metadata still complete and the UI explains the reduced result.

### 9. Local Model Intelligence

Local model records gain capability profiles for structured output, tool use, vision, context size, grounded QA, artifact generation, and resource requirements. Benchmarks are opt-in and store measured latency, memory use, schema success, citation quality, and task scores.

Routing uses measured profiles when available and conservative static capabilities otherwise. The UI explains the selected route and warns before loading a model likely to exceed available memory. Optional LAN inference nodes use explicit owner configuration, health checks, and the same privacy classification as local endpoints.

### 10. Interactive Audio and Video

Interactive podcast mode pauses playback, records or accepts a typed question, retrieves supporting passages, generates a cited answer, synthesizes it with the selected voice, and resumes the original timeline. Interactions are stored only in the local notebook unless the owner deletes them.

Video lessons are generated only from an approved slide document. Regeneration can target narration, one slide, or the full video without rebuilding unaffected assets.

### 11. Release Hardening

Packaging gains explicit signing and notarization configuration without embedding credentials in the repository. Unsigned developer builds remain possible and clearly labeled. Update manifests include version, platform, architecture, URL, size, and SHA-256 signature metadata. The updater verifies artifacts before installation.

Crash reports default to local files and can be exported manually. Any remote reporting is opt-in, redacts source content and secrets, and shows the destination before enabling.

## User Experience

Evidence Studio remains the main output surface. Artifact creation opens a compact configuration dialog with artifact type, selected sources, purpose, length, language, model route, and output formats. Long-running work appears as durable progress in the artifact rail and continues when the owner navigates elsewhere.

Artifact viewers use a consistent toolbar: edit, validate, revise, compare revisions, export, regenerate, and delete. Trust information is visible but does not overwhelm the document. Mobile uses the same document models with narrower, task-focused viewers.

The interface will not add promotional feature descriptions. Empty, loading, permission, offline, dependency-missing, and failure states provide direct recovery actions.

## Error Handling

- Schema-invalid model output gets one bounded repair attempt and then fails with retained raw output for diagnosis.
- Export failures do not discard the validated artifact document.
- Research steps are idempotent and checkpointed so retries do not duplicate imported sources.
- Connector failures use bounded exponential backoff and show the last successful snapshot.
- Source changes mark dependent artifacts stale; they never overwrite owner edits.
- PWA capture queues are size-limited and visibly report items that cannot sync.
- Vision, TTS, video, and document converters report missing local dependencies with actionable setup guidance.
- All background jobs support cancellation and retain a concise failure receipt.

## Security and Privacy

- No source content is sent to a network service without the existing model/provider or connector configuration permitting it.
- URL ingestion continues to use SSRF protection and content-size limits.
- Connector credentials use encrypted storage and least-scope OAuth permissions.
- PWA caches never store provider credentials and avoid caching raw source bodies by default.
- Generated HTML, slide previews, and infographic content are sanitized before rendering.
- Local/LAN inference endpoints are never inferred to be trusted solely from their hostname; the owner explicitly classifies them.

## Testing and Verification

Each vertical slice follows test-first development and leaves the existing app functional.

Required automated coverage:

- Pydantic schema validation and migration fixtures for every artifact type.
- Golden evidence fixtures measuring claim-to-passage resolution.
- Export smoke tests that reopen generated PPTX, PNG, PDF, SCORM, xAPI, and MP4 artifacts.
- Durable Research Run restart, cancel, replay, deduplication, and SSRF tests.
- Connector fingerprint and change-detection contract tests.
- Deterministic spaced-repetition and mastery tests.
- PWA manifest, offline shell, capture queue, and update tests.
- Multimodal extraction fixtures without network dependencies.
- Local-model route selection and resource-guard tests.
- Backend full suite, frontend Vitest, lint, typecheck, and production build.
- Playwright desktop and mobile screenshots at 320, 768, 1024, and 1440 pixel widths.
- Native macOS package smoke and Windows workflow package smoke before release claims.

## Implementation Order

1. Structured artifact contracts and Studio service boundary.
2. Evidence validation and quality benchmark harness.
3. Editable slide decks and PPTX/PDF export.
4. Editable infographics and PNG/PDF export.
5. Durable agentic Research Runs.
6. Watched-folder connector and source freshness.
7. Adaptive learning and Course Pack upgrades.
8. PWA shell, mobile capture, and offline learning.
9. Image, spreadsheet, ePub, and video-scene ingestion.
10. Local-model capability benchmarking and vision routing.
11. Interactive podcast mode and narrated video lessons.
12. Additional cloud connectors.
13. Signing, notarization, update verification, and final release validation.

Every numbered item is a separate implementation plan and may use a feature flag until its end-to-end acceptance criteria pass.

## Success Measures

- At least 95 percent of generated citation references resolve to an exact retained passage in the evaluation corpus.
- At least 90 percent of generated artifacts pass their schema without manual repair on supported benchmark models.
- A slide deck opens successfully in PowerPoint/LibreOffice and retains citations and speaker notes.
- A Research Run can restart mid-run without duplicate source imports.
- A watched source update appears in the notebook and marks dependent artifacts stale without overwriting them.
- Flashcard scheduling and mastery state survive application restart and artifact revision.
- The installed PWA can capture while disconnected and synchronize after reconnecting.
- All new network activity is attributable in the UI and blocked by forced-offline mode.
- Release artifacts are reproducible, checksum-verified, and clearly signed or labeled as developer builds.

## Trade-offs

- The design favors structured, editable outputs over unconstrained generative visuals.
- It favors personal local/private connectivity over hosted cross-device synchronization.
- It delays broad cloud connectors until the connector contract and watched-folder implementation are proven.
- It retains backward compatibility for markdown artifacts instead of forcing a destructive migration.
- It does not attempt NotebookLM's public notebook ecosystem or Gemini-wide product integration.

## Areas for Review

- Confirm the single-user boundary remains permanent for this roadmap.
- Confirm a PWA connected to the owner's desktop is preferable to introducing a hosted sync service.
- Confirm deterministic professional infographic templates are acceptable before optional image-generation enhancements.
- Confirm Research Runs may access configured web-search/fetch providers only after visible owner approval when the approval setting is enabled.
- Confirm signing and notarization may remain configuration-ready until platform certificates are supplied by the owner.
