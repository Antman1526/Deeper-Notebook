# Podcast Intelligence Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make podcast generation an optional, explicit action for every readable notebook and note, add Quick Podcast and a full Podcast Intelligence Studio, and upgrade the Podcasts route into a production workspace while reusing the current staged podcast engine honestly.

**Architecture:** A strict `PodcastSelection` union carries stable app-owned or unified-knowledge references from menus, commands, Search, Graph, and the Knowledge workspace. A read-only preview service resolves those references through existing notebook and unified knowledge APIs, reports inclusion and readiness without retaining a durable manifest, and submits only confirmed selections to the current podcast service. One responsive `PodcastStudio` component powers both a Knowledge pane and the Podcasts route. Current mode/profile, outline review, generation stages, cancellation, retry, transcript citations, and global player remain the execution foundation; Phase-3-only evidence artifacts are displayed as future locked stages, not fabricated data.

**Tech Stack:** Python 3.11/3.12, Pydantic 2, FastAPI, existing PodcastService and command worker, SurrealDB episode records, React 19, Next.js 16, TypeScript, Zod 4, Zustand 5, TanStack Query 5, Vitest, Testing Library, Playwright, pytest, and the Phase 1 local route planner.

## Global Constraints

- Begin only after the Phase 1 completion gate passes and use a fresh `codex/` worktree.
- External Obsidian and Logseq inputs remain `external_read_only`; selection reads unified projections and never opens or writes canonical external paths.
- Podcast generation is always optional, user-initiated, reviewable, cancelable before submission, and absent from create/save/scan/watcher/indexing effects.
- Every readable notebook or note exposes `Turn into podcast`; unavailable or empty items keep the action visible but disabled with the exact stable reason.
- Dismissing Quick Podcast or Studio performs no model request, worker submission, audio write, episode insert, source mutation, or workspace mutation beyond closing the UI.
- Whole-notebook preview reports included, excluded, duplicate, unavailable, changed, and oversize content. It never silently truncates.
- Phase 2 does not claim a durable Research Set Manifest, claim-level evidence blueprint, script verification, artifact graph, or segment regeneration. Those are Phase 3.
- Existing episode/profile/speaker tables and generated-audio containment remain authoritative for current production.
- Storyboard approval maps to the existing outline-review gate; the UI must label it `Outline storyboard` until Phase 3 supplies cited storyboard artifacts.
- Local route plans are inspectable and overrideable, but submission must use only planner-approved routes and the selected execution policy.
- No raw provider error, credential, absolute model path, absolute vault path, or copied external source root may appear in API responses.
- Run large suites serially. Do not push, merge, or enable live external watchers in this plan.

---

## File Map

### Create

- `deeper_notebook/podcasts/selection_contracts.py` — strict selection descriptors, preview entries, readiness, and normalized submission input.
- `deeper_notebook/podcasts/selection_service.py` — bounded read-only resolution, deduplication, revision checks, and current-worker content assembly.
- `api/schemas/podcast_studio.py` — strict request/response wire contracts.
- `deeper_notebook/database/migrations/40.surrealql` — optional Phase-2 episode selection, brief, and redacted model-plan fields.
- `deeper_notebook/database/migrations/40_down.surrealql` — remove only the Phase-2 episode fields.
- `tests/test_podcast_selection_contracts.py`
- `tests/test_podcast_selection_service.py`
- `tests/test_podcast_studio_api.py`
- `tests/test_podcast_studio_migration.py`
- `frontend/src/lib/podcasts/selection.ts` — strict Zod contracts and selection helpers.
- `frontend/src/lib/podcasts/selection.test.ts`
- `frontend/src/lib/stores/podcast-studio-store.ts` — transient confirmed draft state with no automatic submission.
- `frontend/src/lib/stores/podcast-studio-store.test.ts`
- `frontend/src/components/podcasts/TurnIntoPodcastAction.tsx`
- `frontend/src/components/podcasts/TurnIntoPodcastAction.test.tsx`
- `frontend/src/components/podcasts/QuickPodcastDialog.tsx`
- `frontend/src/components/podcasts/QuickPodcastDialog.test.tsx`
- `frontend/src/components/podcasts/PodcastStudio.tsx`
- `frontend/src/components/podcasts/PodcastStudio.test.tsx`
- `frontend/src/components/podcasts/ResearchSetPanel.tsx`
- `frontend/src/components/podcasts/ResearchSetPanel.test.tsx`
- `frontend/src/components/podcasts/EditorialBriefPanel.tsx`
- `frontend/src/components/podcasts/EditorialBriefPanel.test.tsx`
- `frontend/src/components/podcasts/OutlineStoryboard.tsx`
- `frontend/src/components/podcasts/OutlineStoryboard.test.tsx`
- `frontend/src/components/podcasts/PodcastModelPlan.tsx`
- `frontend/src/components/podcasts/PodcastModelPlan.test.tsx`
- `frontend/src/components/podcasts/ProductionTimeline.tsx`
- `frontend/src/components/podcasts/ProductionTimeline.test.tsx`
- `frontend/src/components/podcasts/PodcastLibrary.tsx`
- `frontend/src/components/podcasts/PodcastLibrary.test.tsx`
- `frontend/src/components/podcasts/EpisodeLab.tsx`
- `frontend/src/components/podcasts/EpisodeLab.test.tsx`
- `frontend/src/components/podcasts/EpisodeCard.test.tsx`
- `frontend/src/app/(dashboard)/podcasts/studio/page.tsx`
- `frontend/e2e/podcast-intelligence-studio.spec.ts`
- `scripts/verify_podcast_studio.py`
- `tests/test_verify_podcast_studio.py`
- `docs/verification/2026-08-01-podcast-intelligence-studio.md`

### Modify

- `api/routers/podcasts.py` — preview, readiness, quick-submit, and normalized Studio submission routes.
- `api/podcast_service.py` — accept normalized server-resolved content and planner-approved stage routes.
- `commands/podcast_commands.py` — persist redacted model plan and selection summary on current episode records.
- `deeper_notebook/podcasts/models.py` — Phase-2 selection summary, model plan, and editorial brief fields with legacy defaults.
- podcast API, model, migration, mode, staged, path-containment, retry, and offline-gate tests.
- `frontend/src/lib/types/podcasts.ts`, `frontend/src/lib/api/podcasts.ts`, and `frontend/src/lib/hooks/use-podcasts.ts` — Studio contracts and hooks.
- `frontend/src/components/podcasts/GeneratePodcastDialog.tsx` — reduce to a compatibility launcher that delegates to Quick Podcast or Studio.
- `frontend/src/components/podcasts/EpisodesTab.tsx` and `EpisodeCard.tsx` — delegate to production library/Lab surfaces while preserving actions.
- `frontend/src/components/podcasts/GlobalAudioPlayer.tsx` and `SyncedTranscript.tsx` — Episode Lab integration without breaking route-persistent playback.
- `frontend/src/app/(dashboard)/podcasts/page.tsx` — production-oriented library and Studio entry.
- `frontend/src/components/vault/KnowledgePodcastPane.tsx` — embed the same Studio component.
- `frontend/src/app/(dashboard)/notebooks/components/NotebookCard.tsx`, `NotebookRow.tsx`, `NotebookHeader.tsx`, `NotesColumn.tsx`, and `SourcesColumn.tsx` — optional notebook, note, and notebook-source actions.
- `frontend/src/components/sources/SourceCard.tsx` and `frontend/src/components/source/SourceDetailContent.tsx` — optional source actions.
- `frontend/src/components/vault/KnowledgePaneContent.tsx`, `KnowledgeSearchPane.tsx`, `VaultGraph.tsx`, `KnowledgeBookmarksPanel.tsx`, `KnowledgeWorkspacesPanel.tsx`, and `KnowledgeTabStrip.tsx` — optional active tab, block, Search, Graph, bookmark, and workspace actions.
- `frontend/src/lib/commands/knowledge-command-catalog.ts` and command tests — Quick Podcast and Studio commands.
- locale bundles and parity tests.

## Interfaces Locked by This Plan

### Selection and preview

```python
class NotebookSelection(_Strict):
    kind: Literal["notebook"]
    notebook_id: str


class AppNoteSelection(_Strict):
    kind: Literal["app_note"]
    note_id: str


class AppSourceSelection(_Strict):
    kind: Literal["app_source"]
    source_id: str
    inclusion_mode: Literal["insights", "full"] = "full"


class KnowledgeDocumentSelection(_Strict):
    kind: Literal["knowledge_document"]
    document_id: str
    expected_revision_id: str | None = None


class KnowledgeBlockSelection(_Strict):
    kind: Literal["knowledge_block"]
    document_id: str
    block_id: str
    expected_revision_id: str | None = None
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)


class KnowledgeCollectionSelection(_Strict):
    kind: Literal["knowledge_collection"]
    collection_kind: Literal["folder", "bookmark", "workspace"]
    collection_id: str


class SearchSelection(_Strict):
    kind: Literal["saved_search"]
    query: str
    search_mode: Literal["exact", "text", "semantic"]
    space_ids: list[str] = Field(max_length=32)
    authority_kinds: list[Literal["app_owned", "external_read_only"]] = Field(
        max_length=2
    )


class GraphSelection(_Strict):
    kind: Literal["graph_selection"]
    document_ids: list[str] = Field(min_length=1, max_length=128)


PodcastSelection = Annotated[
    NotebookSelection
    | AppNoteSelection
    | AppSourceSelection
    | KnowledgeDocumentSelection
    | KnowledgeBlockSelection
    | KnowledgeCollectionSelection
    | SearchSelection
    | GraphSelection,
    Field(discriminator="kind"),
]


class SelectionPreviewEntry(_Strict):
    stable_id: str
    title: str
    authority_kind: Literal["app_owned", "external_read_only"]
    relative_locator: str | None
    revision_id: str | None
    fingerprint: str | None
    state: Literal[
        "included",
        "duplicate",
        "unavailable",
        "changed",
        "empty",
        "failed_parse",
        "oversize",
    ]
    reason: str
    estimated_characters: int = Field(ge=0)


class PodcastSelectionPreview(_Strict):
    selection_fingerprint: str
    entries: list[SelectionPreviewEntry] = Field(max_length=10_000)
    included_characters: int = Field(ge=0)
    requires_batch_engine: bool
    current_worker_eligible: bool
    blocked_reasons: list[str]
```

The preview fingerprint hashes normalized stable references, revisions, inclusion modes, and editorial inputs. It contains no source body. Submission repeats resolution and rejects a stale fingerprint with `podcast_selection_changed`.

### Editorial and model plan

```typescript
export type PodcastEditorialBrief = {
  centralQuestion: string
  audience: 'foundation' | 'practitioner' | 'expert'
  purpose: 'explain' | 'analyze' | 'challenge' | 'compare' | 'teach'
  format: 'brief' | 'deep_dive' | 'critique' | 'debate'
  targetMinutes: number
  requiredTakeaway: string
  includeUnansweredQuestions: boolean
  evidencePolicy: 'strict' | 'interpretation'
  episodeProfileName: string
  speakerProfileName: string
}

export type PodcastStageModelPlan = {
  stage: 'outline' | 'script' | 'voice' | 'transcription'
  role: 'podcast_outline' | 'podcast_script' | 'text_to_speech' | 'speech_to_text'
  outcome: 'ready' | 'blocked' | 'approval_required'
  modelId: string | null
  provider: string | null
  resourceTier: 'light' | 'standard' | 'heavyweight' | null
  selectionSource: 'automatic' | 'role_override' | 'production_override' | null
  reason: string
}
```

The Phase-2 timeline is `Research Set Preview → Editorial Brief → Outline Storyboard → Script/Voice Job → Episode`. Evidence and Verification appear as locked Phase-3 stages and are never marked complete.

---

### Task 1: Strict Podcast Selection Contracts

**Files:** selection contract/service modules and tests, knowledge repository/service tests

- [ ] Write strict model tests for every selection variant, paired selected-text offsets, duplicate IDs, 128-item graph bounds, 32-space search bounds, canonical ID patterns, forbidden extra fields, and absence of absolute paths.
- [ ] Add read-only repository/service methods that resolve an app source, document, block/text span, folder, bookmark, workspace, search, or graph selection; return recorded revisions and fingerprints; and list bounded members without accepting a filesystem path.
- [ ] Implement normalization that sorts unordered IDs, preserves explicit block order, deduplicates exact stable IDs, marks near-duplicate fingerprints for review, and computes the selection fingerprint.
- [ ] Prove a mixed app-owned/external selection is valid and that no selected external target gains a write capability.
- [ ] Run `pytest -q tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_knowledge_engine_repository.py tests/test_knowledge_engine_service.py`.
- [ ] Commit with `git commit -m "feat: define podcast research selections"`.

### Task 2: Read-Only Preview, Readiness, and Confirmed Submission APIs

**Files:** `api/schemas/podcast_studio.py`, `api/routers/podcasts.py`, `api/podcast_service.py`, `tests/test_podcast_studio_api.py`, existing podcast defense tests

- [ ] Write failing API tests for preview, stale revision, duplicate, empty, unavailable, failed parse, oversize, missing model role, missing voice, storage failure, worker failure, and a successful confirmed submission.
- [ ] Add `POST /podcasts/selection/preview`, `POST /podcasts/readiness`, and `POST /podcasts/studio/submit`. Each body is bounded before nested validation and accepts selection descriptors, not copied canonical paths.
- [ ] On submit, require `selection_fingerprint`, rerun resolution, reject changes with HTTP 409 and stable code, assemble current-worker content server-side, and reject `requires_batch_engine=true` with `podcast_batch_engine_required` rather than truncating.
- [ ] Call Phase 1 route planning for outline, script, voice, and optional transcription. A blocked plan prevents submission; Local Preferred approval is stage-specific.
- [ ] Reuse `PodcastService.submit_generation_job`, existing offline gate, output containment, one-attempt command policy, and per-episode retry lock.
- [ ] Scrub raw exceptions and assert the response contains no root, credential, source body, or model path.
- [ ] Run `pytest -q tests/test_podcast_studio_api.py tests/test_podcast_command_defenses.py tests/test_podcast_audio_containment.py tests/test_v0_8_68_podcast_offline_gate.py`.
- [ ] Commit with `git commit -m "feat: preview and submit podcast selections"`.

### Task 3: Optional Action Registry and Command Integration

**Files:** `TurnIntoPodcastAction.tsx`, selection helpers/store, command catalog/bridge, notebook/note/source/Knowledge/Search/Graph/bookmark/workspace menu tests

- [ ] Create a shared action adapter that accepts one `PodcastSelection[]`, a visible label, a disabled reason, and destinations `quick` or `studio`; opening it only populates transient Studio state.
- [ ] Register `podcast.quick_from_selection` and `podcast.open_studio_from_selection` as app-owned mutations that may read external evidence but declare no external mutation capability.
- [ ] Add the action to the exact notebook, note, source, Knowledge tab/block, Search, Graph, bookmark, named-workspace, and command files in the Modify map. Use stable document/block/search/graph descriptors; never pass a vault root or direct file path.
- [ ] Test every eligible notebook and note shows the action, every unavailable item shows the exact reason, and no React mount/open/dismiss path calls generation.
- [ ] Test keyboard invocation and focus restoration for menus and the command palette.
- [ ] Run `(cd frontend && npx vitest run src/components/podcasts/TurnIntoPodcastAction.test.tsx src/lib/podcasts/selection.test.ts src/lib/stores/podcast-studio-store.test.ts src/lib/commands/knowledge-command-catalog.test.ts --pool=forks --maxWorkers=1 && npx tsc --noEmit)`.
- [ ] Commit with `git commit -m "feat: offer optional podcast actions"`.

### Task 4: Quick Podcast Confirmation

**Files:** `QuickPodcastDialog.tsx`, test, Studio store, podcast hooks/API

- [ ] Write tests for title/profile/mode/duration recommendations, included/excluded counts, route plan, evidence-policy label, stale preview recovery, cancel, and confirmed submit.
- [ ] Implement a two-step dialog: `Review selection` then `Confirm production`. Disable confirmation until preview and all required stage routes are ready.
- [ ] Default to saved user settings and source-grounded deterministic suggestions; show one editable reason per suggestion.
- [ ] Default `review_outline=true` and evidence policy `strict`; label the current Phase-2 gate `Outline storyboard review`.
- [ ] Ensure cancel clears transient selections and sends no mutation. Confirm sends exactly one submission with an idempotency key and closes only after accepted response.
- [ ] Run `(cd frontend && npx vitest run src/components/podcasts/QuickPodcastDialog.test.tsx src/lib/stores/podcast-studio-store.test.ts --pool=forks --maxWorkers=1)`.
- [ ] Commit with `git commit -m "feat: add Quick Podcast confirmation"`.

### Task 5: Full Podcast Studio and Responsive Production Timeline

**Files:** Studio, ResearchSet, EditorialBrief, OutlineStoryboard, ModelPlan, Timeline components and tests; `GeneratePodcastDialog.tsx`; Podcast Studio route; Knowledge Podcast pane

- [ ] Write component tests for the four-region desktop layout, sequential narrow layout, keyboard stage navigation, Research Set states, all editorial fields, outline reorder buttons, model overrides, and explicit locked Evidence/Verification stages.
- [ ] Build one `PodcastStudio` controller shared by route and pane. Its state machine is `selecting → preview_ready → briefing_ready → submitted → awaiting_outline → generating → completed|failed|cancelled`.
- [ ] Split the oversized legacy dialog by delegating content selection to `ResearchSetPanel`, settings to `EditorialBriefPanel`, outline review to `OutlineStoryboard`, and route details to `PodcastModelPlan`.
- [ ] Provide drag reorder plus Move Earlier/Move Later buttons; keep focus on the moved segment and announce the new position.
- [ ] Map current backend stages to the production timeline and keep `Evidence` and `Verification` visibly locked with `Available after intellectual engine upgrade`.
- [ ] Lazy-load the Studio from the Knowledge Podcast pane and preserve current workspace resizing and autosave responsiveness.
- [ ] Run `(cd frontend && npx vitest run src/components/podcasts/PodcastStudio.test.tsx src/components/podcasts/ResearchSetPanel.test.tsx src/components/podcasts/EditorialBriefPanel.test.tsx src/components/podcasts/OutlineStoryboard.test.tsx src/components/podcasts/PodcastModelPlan.test.tsx src/components/podcasts/ProductionTimeline.test.tsx src/components/podcasts/GeneratePodcastDialog.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)`.
- [ ] Commit with `git commit -m "feat: build Podcast Intelligence Studio"`.

### Task 6: Production-Oriented Podcast Library and Episode Lab

**Files:** `PodcastLibrary.tsx`, `EpisodeLab.tsx`, existing page/cards/player/transcript, tests

- [ ] Write tests that group episodes into Continue Production, Ready to Review, Completed, and Needs Attention based on current job status and generation stage.
- [ ] Add filters for current format, profile, date, production stage, and selection authority summary; evidence-state filters remain disabled and labeled as Phase 3.
- [ ] Build Episode Lab around the existing global player, outline, synchronized transcript, citation IDs, stage history, retry, cancel, and download actions. Preserve player state across route changes.
- [ ] Citation clicks resolve through current source citation behavior. Where no exact evidence block exists, label `Source citation — claim evidence mapping arrives in Phase 3`; do not manufacture a block link.
- [ ] Preserve audio containment, MIME detection, pagination, retry serialization, outline approval, and delete confirmation.
- [ ] Run `(cd frontend && npx vitest run src/components/podcasts/PodcastLibrary.test.tsx src/components/podcasts/EpisodeLab.test.tsx src/components/podcasts/EpisodeCard.test.tsx src/components/podcasts/GlobalAudioPlayer.test.tsx src/components/podcasts/SyncedTranscript.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)`.
- [ ] Commit with `git commit -m "feat: organize podcast production workspace"`.

### Task 7: Episode Metadata Compatibility and Model-Plan Receipts

**Files:** `deeper_notebook/database/migrations/40.surrealql`, `deeper_notebook/database/migrations/40_down.surrealql`, `deeper_notebook/podcasts/models.py`, `commands/podcast_commands.py`, `api/podcast_service.py`, `api/routers/podcasts.py`, `frontend/src/lib/types/podcasts.ts`, `tests/integration/test_podcast_mode_migration.py`, `tests/test_v0_8_68_episode_schema_parity.py`, `tests/test_v0_8_68_podcast_staged.py`, and `tests/test_podcast_command_defenses.py`

- [ ] Add optional episode fields `selection_summary`, `selection_fingerprint`, `editorial_brief`, and `model_plan_receipts` with safe defaults for legacy rows. The down migration removes only these fields.
- [ ] Persist counts, authority kinds, stable IDs, revision IDs, profile settings, and redacted planner receipts; persist no selected source body, absolute root, model path, or credential.
- [ ] Keep retry on the same normalized settings and selection fingerprint. If selection has changed, return to preview rather than deleting the old episode first.
- [ ] Prove legacy episodes load, new episodes retry once without duplication, cancellation retains current metadata, and provider failure does not erase the selected brief.
- [ ] Run `pytest -q tests/test_podcast_studio_migration.py tests/test_v0_8_68_episode_schema_parity.py tests/integration/test_podcast_mode_migration.py tests/test_v0_8_68_podcast_staged.py tests/test_v0_8_68_podcast_improvements.py tests/test_podcast_studio_api.py`.
- [ ] Commit with `git commit -m "feat: retain podcast Studio metadata"`.

### Task 8: Browser, Protected-Source, Build, and Native Proof

**Files:** Playwright spec, verifier, verifier tests, verification record

- [ ] Browser-test Quick Podcast and Studio from an app notebook, app note, external note, selected block, Search set, and Graph cluster; dismiss one of each and prove zero submission.
- [ ] Review a whole-notebook preview, observe an oversize fail-closed state, edit/reorder/approve an outline, cancel a job, retry a failed job, and play a completed episode through Episode Lab.
- [ ] Verify model-plan inspection/override rejection, Strict Local zero-cloud behavior, keyboard-only operation, 200% zoom, reduced motion, and responsive sequential Studio.
- [ ] Run the protected-source verifier on synthetic Obsidian/Logseq fixtures: hash before, preview, submit through an injected fake worker, retry, play metadata, hash after, and require equality plus zero external write receipts.
- [ ] Run final serial gates: `pytest -q tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_podcast_studio_api.py tests/test_podcast_studio_migration.py tests/test_podcast_command_defenses.py tests/test_podcast_audio_containment.py tests/test_v0_8_68_podcast_staged.py tests/test_v0_8_68_podcast_offline_gate.py tests/test_verify_podcast_studio.py`; `ruff check deeper_notebook/podcasts api/routers/podcasts.py api/podcast_service.py commands/podcast_commands.py tests/test_podcast_selection_contracts.py tests/test_podcast_selection_service.py tests/test_podcast_studio_api.py`; `(cd frontend && npx vitest run src/components/podcasts src/lib/podcasts src/lib/stores/podcast-studio-store.test.ts --pool=forks --maxWorkers=1 && npx tsc --noEmit && npm run build && npx playwright test e2e/podcast-intelligence-studio.spec.ts --project=native-runtime)`; then `python scripts/verify_podcast_studio.py --native-url http://localhost:65060`.
- [ ] Record exact commands, versions, hashes, results, current-worker limitations, and native proof in `docs/verification/2026-08-01-podcast-intelligence-studio.md`.
- [ ] Commit with `git commit -m "test: verify Podcast Intelligence Studio"`.

## Phase 2 Completion Gate

Phase 2 is complete only when every readable notebook/note offers an optional action; cancel/dismiss is side-effect free; preview never silently truncates; Quick and Studio require confirmation; current outline/retry/cancel/player behavior remains functional; route plans are inspectable and privacy-safe; the Podcasts route and Knowledge pane share the responsive Studio; Phase-3-only capabilities are labeled honestly; external source hashes are unchanged; and the app remains usable without the intellectual evidence engine.
