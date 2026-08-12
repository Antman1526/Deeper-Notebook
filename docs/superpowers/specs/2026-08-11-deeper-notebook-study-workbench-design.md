# Deeper Notebook Study Workbench Design

## Status

Approved product design. This document specifies an additive expansion of the
existing `/study` route. It does not authorize breaking changes to current
Study card, review, notebook, source, artifact, or public API contracts.

## Goal

Turn the existing evidence-backed Study review surface into a local-first AI
learning workbench. A user can start with a topic, existing notebook material,
PDFs, videos, notes, an Anki package, or explicitly approved web research; ask
Deeper Notebook to propose an editable syllabus; approve that syllabus; and
then learn through cited guides, tutoring, practice, projects, flashcards, and
adaptive review.

The result should feel native to Deeper Notebook: calm, evidence-led,
approval-first, private by default, reversible, and integrated with the
application's existing notebooks, sources, Evidence Studio, local model roles,
runtime receipts, and FSRS scheduling.

## Approved product decisions

- Evidence-first and research-enabled plans both exist. Local evidence is the
  default; web research is an explicit per-plan permission.
- Generation starts with a proposed syllabus. The user may edit, reorder, add,
  or remove units before approval. Downstream generation is gated on approval.
- A Study Plan is an independent workspace that can link multiple notebooks,
  sources, notes, PDFs, videos, and web findings without changing the originals.
- Deeper Notebook's native FSRS review system remains authoritative.
- Initial scope includes bounded Anki package import and export. Live two-way
  Anki synchronization is not part of the initial release.
- The workbench includes a coordinated team of specialized AI tutors and
  assistants, not only a generic chat panel.

## Existing foundation to preserve

The current application already provides:

- a Study navigation item and `/study` route;
- source-cited, versioned `StudyCard` records;
- append-only `StudyReview` receipts;
- native FSRS scheduling with Again, Hard, Good, and Easy ratings;
- additive `/api/study/cards` creation, due-card, and review endpoints;
- PDF, video, note, notebook, and local-vault ingestion;
- source fingerprints, evidence spans, and citation-aware artifacts;
- Evidence Studio artifact kinds for study guides, course packs, quizzes, and
  flashcards;
- local model routing, including the existing study-oriented model role;
- background workflow, progress, recovery, and runtime status patterns;
- optional, approval-gated web research;
- local desktop packaging and a local-first data root.

This design extends those systems. It does not introduce a second card
scheduler, source store, artifact engine, model router, or notebook database.

## Upstream inspiration and licensing boundary

The product behavior is informed by:

- DeepStudent's unified learning workflow: materials, AI tutoring, notes,
  concept maps, practice, research, and flashcards sharing one data layer.
- Anki's separation of notes and cards, deck organization, portable packages,
  card templates, tags, cloze/basic card patterns, and spaced repetition.

Both referenced projects are AGPL-licensed. Deeper Notebook will not embed,
vendor, fork, translate, or copy their implementation. The work will be a
native implementation against Deeper Notebook's existing architecture. Anki
package support is an interoperability adapter with explicit compatibility
tests and receipts, not a dependency on Anki's application code.

References:

- <https://github.com/helixnow/deep-student>
- <https://github.com/ankitects/anki>

## Product principles

1. **Evidence before fluency.** Generated explanations identify citations,
   exercises, inferences, and unresolved gaps instead of presenting all output
   as equally sourced.
2. **Approval before expansion.** The user approves the syllabus before the
   system creates a large learning pack or schedule.
3. **Local before remote.** Local models and local sources are the default.
   Cloud models and web research require visible, scoped permission.
4. **One learning graph.** Guides, concepts, activities, quizzes, projects,
   cards, tutor sessions, and progress refer to the same plan, units, and
   evidence.
5. **Assistants propose; users authorize.** An assistant may teach, coach, and
   draft. It may not silently change an approved plan or expand authority.
6. **Original material stays intact.** Plans link to sources and notebooks
   read-only. Destructive source changes are outside Study authority.
7. **Resumable over magical.** Long operations expose state, checkpoints,
   cancellation, recovery, and clear failure reasons.
8. **Portable without split authority.** Anki packages are supported, while
   Deeper Notebook remains authoritative for native scheduling and progress.

## Primary user journey

1. Open **Study** from the navigation bar.
2. Select **Create Study Plan** or **Import Anki Package**.
3. Describe the topic, desired outcome, current level, deadline, weekly time
   budget, preferred session length, and learning preferences.
4. Link existing notebooks/sources, upload PDFs or videos, import an Anki
   package, or explicitly enable web research.
5. Observe local extraction, transcription, OCR, indexing, and source-readiness
   states.
6. Optionally complete a short diagnostic.
7. Ask the Curriculum Architect to propose a cited syllabus.
8. Edit, reorder, add, or remove units and activities.
9. Approve a specific immutable syllabus version.
10. Generate the learning pack unit by unit.
11. Learn with source-aware tutors, guides, examples, concept maps, practice,
    projects, and native FSRS review.
12. Monitor mastery and accept or reject proposed adaptations.
13. Import or export Anki packages with a compatibility report.

## Information architecture

### Study Home

The current due-card experience remains immediately available and expands into
a dashboard containing:

- Today's review queue
- Continue learning
- Active Study Plans
- Weak concepts
- Weekly progress and pacing
- Recently added material
- Create Study Plan
- Import Anki Package

### Plan workspace

Each Study Plan provides:

- **Overview:** next action, progress, time remaining, source coverage, and
  degraded capabilities.
- **Syllabus:** ordered units, objectives, prerequisites, activities, effort,
  approval, and version history.
- **Learn:** cited lessons, worked examples, tutor sessions, and unit notes.
- **Guide:** concise and comprehensive study-guide projections.
- **Map:** concept, prerequisite, and dependency relationships in outline and
  visual forms.
- **Practice:** recall, cloze, short answer, multiple choice, applied problems,
  timed practice, and mock exams.
- **Flashcards:** native FSRS cards, proposals, review history, and Anki package
  import/export.
- **Sources:** local material, web evidence, processing state, citation
  coverage, and missing evidence.
- **Progress:** concept mastery, review consistency, pacing, weak areas, and
  intervention history.

### Plan creation wizard

The wizard uses six stages:

1. Goal and desired outcome
2. Starting level or diagnostic
3. Target date and time budget
4. Existing sources and new uploads
5. Learning and accessibility preferences
6. Proposed syllabus review

The wizard must be resumable. Closing it cannot discard uploaded sources or an
already-created draft unless the user explicitly deletes the draft.

## AI Study Team

The workbench presents one coordinated team through a persistent Tutor dock.
Only one foreground assistant leads an interaction, while bounded background
jobs may produce approved artifacts.

### Assistants

- **Study Director:** coordinates the plan, recommends the next action, and
  routes requests to specialists.
- **Curriculum Architect:** proposes syllabi, prerequisites, milestones,
  pacing, and revisions.
- **Socratic Tutor:** teaches through questions, hints, and progressive
  disclosure rather than immediately giving answers.
- **Concept Explainer:** provides level-adjusted explanations, examples,
  analogies, counterexamples, and visual structures.
- **Source Guide:** answers strictly from selected material and links users to
  pages, passages, notes, or video timestamps.
- **Practice Coach:** creates adaptive recall, cloze, short-answer,
  multiple-choice, and applied exercises.
- **Exam Coach:** runs timed practice, mock exams, oral examinations, grading,
  and remediation.
- **Memory Coach:** proposes flashcards, manages FSRS review guidance, identifies
  weak topics, and coordinates Anki package workflows.
- **Research Scout:** performs explicitly approved web research, compares
  sources, and proposes additions.
- **Project Mentor:** creates applied projects, milestones, rubrics, and
  iterative feedback.
- **Writing Coach:** reviews essays, explanations, proofs, or reports against
  selected material and visible rubrics.
- **Progress Coach:** identifies pacing or mastery issues and proposes schedule
  or syllabus adjustments.

### Tutor modes

- Teach me
- Ask a question
- Quiz me
- Socratic mode
- Solve it with me
- Give me a hint
- Explain my mistake
- Oral exam
- Build a practice test
- Plan today's session
- Review this writing
- Turn this into flashcards
- Create a project
- Research this gap

The user may pin a specialist or allow the Study Director to route the request.

### Shared context and handoffs

Assistants share a bounded structured context:

- approved goal and syllabus version;
- selected sources and permissions;
- current unit and objectives;
- concept mastery and recent mistakes;
- due reviews and plan schedule;
- user-confirmed learning preferences;
- unresolved questions; and
- structured assistant handoff receipts.

Assistants do not pass unrestricted transcripts or hidden reasoning between
jobs. A handoff records the observation, evidence, proposed action, origin,
time, and user decision. The UI exposes concise rationale, not private
chain-of-thought.

### Authority modes

- **Ask:** read-only answers and source navigation.
- **Coach:** questions, hints, explanations, and feedback.
- **Plan:** proposed syllabus, schedule, or activity changes.
- **Create:** approved guide, quiz, card, project, or report generation.

An assistant may not silently enable network access, use a cloud model, change
an approved syllabus, add or remove sources, publish card proposals, change the
overall schedule, or delete learning data.

### Study memory

Each plan has private, editable learning memory for confirmed goals,
preferences, understood concepts, recurring misconceptions, useful analogies,
accommodations, interventions, and unresolved questions. Memory is local and
plan-scoped by default. Users can inspect, correct, export, or clear it.
Inferred difficulties do not become durable facts without confirmation.

## Generation pipeline

```text
Source readiness
  -> Concept extraction
  -> Prerequisite mapping
  -> Syllabus proposal
  -> User edit and approval
  -> Unit generation
  -> Citation verification
  -> Practice and card generation
  -> Schedule creation
  -> Mastery-driven adaptation proposals
```

Each stage has a typed input, typed output, bounded result size, idempotency key,
checkpoint, cancellation state, and sanitized failure code. The system does not
run an unbounded autonomous assistant loop.

## Data model

All persistence changes are additive.

### `study_plan`

Stores plan identity, goal, starting level, target date, weekly budget, session
length, preferences, model/network policy, lifecycle state, and timestamps.

### `study_plan_source`

Links a plan to an existing source, notebook, note, imported package, or captured
web-evidence record. It stores plan-local selection and authority metadata, not
a second copy of the source.

### `study_syllabus_version`

An immutable syllabus snapshot containing ordered units, objectives,
prerequisites, estimated effort, source coverage, planned activities, author,
approval state, and parent version.

### `study_unit`

Projects the active syllabus units for query efficiency. It stores current
ordering, completion state, mastery summary, and active artifact references.
The immutable syllabus version remains the authority for what was approved.

### `study_activity`

Represents a reading, lesson, tutor session, quiz, recall exercise, exam,
project, review block, or user-defined task assigned to a unit.

### `study_progress`

An append-only receipt for completion, assessment, mastery, intervention, and
schedule decisions. Aggregated progress is a projection, not the only record.

### `study_plan_artifact`

Links existing Evidence Studio artifacts to a plan and unit. Artifact content
continues to use the established artifact store and evidence contracts.

### `study_plan_card`

Associates versioned native Study cards with plans, units, concepts, and card
roles without modifying the existing public `StudyCard` contract.

### `study_assistant_handoff`

Stores bounded structured handoffs: assistant role, plan/unit, evidence,
observation, proposed action, user decision, and timestamps.

### `study_plan_memory`

Stores user-confirmed, editable plan-local memory with provenance, status, and
last-confirmed time.

### `study_import_job` and `study_export_job`

Track bounded Anki package work, checkpoints, counts, warnings, compatibility
decisions, output receipt, and terminal status.

## Lifecycle

```text
draft
  -> analyzing_sources
  -> syllabus_proposed
  -> editing
  -> approved
  -> generating
  -> active
  -> completed | archived
```

Recoverable `blocked` or `failed` stage state is recorded separately from the
plan lifecycle so retrying one job does not corrupt plan authority. Approval is
bound to an exact syllabus version and source manifest. Material source changes
after approval create a visible drift state and a revision proposal; they do
not silently rewrite the active plan.

## Source and evidence behavior

- PDFs use existing parsing, OCR, chunking, indexing, fingerprints, and page
  citations.
- Videos use local metadata/transcription where available and retain timestamp
  citations.
- Notebook notes and existing sources are linked read-only.
- Web research is enabled explicitly per plan and captured locally with URL,
  provider, retrieval time, content fingerprint, and evidence metadata.
- AI-created examples and exercises are labeled as generated rather than
  represented as source claims.
- Inferences identify their supporting evidence and inference status.
- Missing coverage remains a first-class knowledge gap.
- Syllabus approval is blocked when required source processing is incomplete,
  unless the user explicitly accepts clearly marked partial coverage.

## API design

Existing `/api/study/cards` behavior remains unchanged. New endpoints are
additive under `/api/study/plans` and use strict request/response models.

Representative endpoints:

```text
POST   /api/study/plans
GET    /api/study/plans
GET    /api/study/plans/{plan_id}
PATCH  /api/study/plans/{plan_id}
POST   /api/study/plans/{plan_id}/sources
DELETE /api/study/plans/{plan_id}/sources/{source_link_id}
POST   /api/study/plans/{plan_id}/syllabus:propose
GET    /api/study/plans/{plan_id}/syllabus
PUT    /api/study/plans/{plan_id}/syllabus
POST   /api/study/plans/{plan_id}/syllabus:approve
POST   /api/study/plans/{plan_id}/generate
POST   /api/study/plans/{plan_id}/assistants/{role}:invoke
GET    /api/study/plans/{plan_id}/progress
GET    /api/study/plans/{plan_id}/jobs
POST   /api/study/plans/{plan_id}/jobs/{job_id}:cancel
POST   /api/study/plans/{plan_id}/jobs/{job_id}:retry
POST   /api/study/plans/{plan_id}/anki:import
POST   /api/study/plans/{plan_id}/anki:export
```

Mutation requests use idempotency keys or optimistic version checks where a
retry or concurrent edit could duplicate work. Error responses use bounded
reason codes and do not expose paths, prompts, credentials, raw provider
responses, or exception strings.

## Anki package interoperability

### Initial supported behavior

- Import standard `.apkg` packages into a selected new or existing Study Plan.
- Export a plan, unit, or selected card set to `.apkg`.
- Support basic, reversed, and cloze semantics; tags; deck hierarchy; safe
  media; note/card relationships; and compatible scheduling metadata.
- Preserve safe unsupported metadata for round-trip reporting when practical.
- Produce a deterministic compatibility receipt listing imported, exported,
  transformed, skipped, and rejected items.

### Authority boundary

Imported cards become native versioned Study cards and use native FSRS after
import. Export translates current native state into the supported package
shape. Deeper Notebook does not claim live Anki synchronization or exact
preservation of unsupported add-ons, executable templates, or scheduler
extensions.

### Untrusted-package handling

The importer validates before materialization:

- archive member count and names;
- compressed and expanded byte budgets;
- path containment and duplicate paths;
- supported SQLite files and bounded schema queries;
- record, field, deck, card, template, and media counts;
- text and media sizes;
- media filenames and hashes;
- template HTML/CSS sanitization; and
- rejection of scripts, executables, add-on code, unsafe links, and malformed
  scheduling data.

Package parsing runs as a resumable background job. A failed import does not
partially publish cards into the active plan.

## Reliability and recovery

Long operations expose `queued`, `running`, `paused`, `failed`, `cancelled`,
and `completed` states. Jobs preserve finished stages and can retry only the
failed stage.

The UI distinguishes source, extraction, transcription, indexing, model,
evidence, citation, timeout, web, package, database, and storage failures. It
does not reduce them to a generic error.

Generation jobs write to provisional records and publish only after schema,
evidence, and policy checks succeed. Cancellation cannot leave active syllabus
or artifact pointers referencing incomplete output.

## Security and privacy

- Local models and sources are default.
- Network and cloud-model authority is explicit, scoped, and revocable.
- Credentials are excluded from prompts, receipts, exports, and error payloads.
- Tutor tools receive plan-scoped least privilege.
- Existing outbound URL and SSRF controls apply at discovery and final
  transport boundaries.
- Uploads and packages are untrusted and bounded before materialization.
- Generated rich content uses the existing sanitized rendering boundary.
- Original source writes, deletions, publication, and external side effects are
  outside Study assistant authority.
- Assistant actions, approvals, imports, exports, and plan revisions produce
  local receipts.

## Performance and resource controls

- Parsing, transcription, indexing, research, and generation run outside API
  request handlers.
- Large inputs are summarized and retrieved in bounded chunks.
- Learning packs generate by unit with reusable checkpoints.
- Tutor retrieval is scoped to the active plan, unit, concepts, and selected
  sources.
- Source summaries, transcripts, embeddings, concept extraction, and evidence
  projections are reused when fingerprints match.
- Background job concurrency and local model residency are bounded.
- Cards, questions, research results, assistant handoffs, and prompt context
  have explicit limits.
- Queries are paginated and indexed by plan, lifecycle, due time, unit order,
  job state, and review time.
- Frontend queries use targeted invalidation and avoid refetching an entire
  plan during one card review or job progress update.

## Accessibility and visual design

- Study retains the Luminous Folio visual language and rollback-shell parity.
- The interface uses calm density, progressive disclosure, and one dominant
  next action rather than presenting every assistant simultaneously.
- Plan creation, syllabus reordering, tutor modes, dialogs, uploads, review,
  and Anki workflows are fully keyboard accessible.
- Every route has one main landmark, a visible heading, stable focus return,
  accessible names, and non-color-only status.
- Compact layouts keep primary actions visible and offer marked, bounded
  scrolling only where necessary.
- Reduced motion, touch targets, loading, empty, degraded, offline, partial,
  populated, error, and recovery states are first-class.
- Long jobs show stage, elapsed time, cancellation, and resumability rather
  than an indefinite spinner.

## Compatibility and rollback

- Current Study card/review APIs and database records remain valid.
- Migrations are additive and safe on an existing data root.
- Existing card review remains available independent of plan generation.
- The Study Workbench is developed behind a reversible feature flag.
- Until acceptance, the current due-card dashboard is the flag-off rollback
  surface.
- Existing notebooks, sources, artifacts, cards, and reviews require no
  destructive migration.
- No user-facing behavior outside Study changes unless a verified shared bug is
  found and separately documented.

## Verification strategy

### Backend

- Strict contracts and malformed-input rejection for every new record.
- Lifecycle transition and optimistic-concurrency tests.
- Idempotent retries and concurrent approval/generation tests.
- Source-manifest drift and partial-coverage behavior.
- Evidence/citation validation and assistant authority tests.
- Local-only, web-enabled, and cloud-model policy matrices.
- Interrupted, cancelled, resumed, and failed job tests.
- Existing Study card, review, FSRS, and artifact regressions.
- Anki package round-trip, compatibility, hostile archive, hostile SQLite,
  unsafe template, oversized media, and atomic-publication tests.
- Authentication and plan-scoped authorization tests.
- Real SurrealDB projection/integration proof for new persistence paths.

### Frontend

- Study Home and every Plan workspace state.
- Wizard persistence and source readiness.
- Syllabus editing, reordering, versioning, approval, and drift.
- Assistant selection, routing, handoffs, authority modes, and recovery.
- Tutor modes, evidence navigation, video timestamps, and PDF pages.
- Guide, map, practice, cards, progress, and Anki compatibility reports.
- Loading, empty, partial, offline, degraded, error, and populated states.
- Keyboard, focus, landmarks, screen-reader names, reduced motion, compact,
  tablet, desktop, and both shell modes.
- No unexpected external requests or hidden cloud/model authority changes.

### End to end

```text
Create plan
  -> upload PDF and video
  -> process locally
  -> propose syllabus
  -> edit and approve
  -> generate one complete unit
  -> tutor from cited sources
  -> complete quiz
  -> generate and review cards
  -> export Anki package
  -> import into a fresh plan
  -> restart the application
  -> verify progress, evidence, and scheduling persist
```

Acceptance includes source tests, browser tests, real database integration,
isolated native Supervisor/runtime proof, packaged-app smoke, source-fingerprint
preservation, and verification that unrelated user data and external sources
were not written.

## Delivery sequence

1. Additive Study Plan contracts, migrations, repositories, and APIs.
2. Study Home, plan list/detail, and creation wizard.
3. Source linking, PDF/video upload, readiness, and drift receipts.
4. Syllabus proposal, editing, versioning, approval, and lifecycle.
5. Unit generation and existing Evidence Studio artifact integration.
6. Tutor dock, Study Director, specialist assistants, authority modes, handoffs,
   and plan-local learning memory.
7. Mastery, progress, diagnostic, and adaptation proposals.
8. Anki package import/export and compatibility reporting.
9. Complete accessibility, security, performance, browser, real-database,
   native, packaged, and rollback acceptance.

Each delivery slice must be test-first, independently reviewable, reversible,
and leave all prior gates green.

## Non-goals for the initial release

- Live two-way Anki synchronization
- An Anki add-on runtime or executable template support
- Real-time multi-user collaboration
- Automatic web access or automatic cloud-model fallback
- Unbounded autonomous tutoring agents
- Silent syllabus or schedule replacement
- Writes to linked notebooks, external vaults, or original sources
- Exact emulation of every Anki scheduler extension or third-party add-on
- Copying or embedding DeepStudent or Anki implementation code

## Done criteria

The Study Workbench is complete only when:

- a user can create an independent plan from a topic;
- PDFs and videos can produce an editable, cited syllabus locally;
- optional web research works only after explicit permission;
- syllabus approval gates downstream generation;
- guides, maps, lessons, practice, projects, cards, and tutors share one plan
  and evidence model;
- specialized assistants collaborate through bounded, inspectable handoffs;
- assistants obey visible authority and model/network boundaries;
- native FSRS adapts reviews without breaking existing Study cards;
- Anki package import/export produces deterministic compatibility receipts;
- failures are recoverable and do not partially publish invalid data;
- all existing application gates remain green; and
- isolated native and packaged local-first flows pass without touching
  unrelated user data.
