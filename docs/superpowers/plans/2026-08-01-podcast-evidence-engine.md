# Podcast Evidence and Intellectual Production Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Phase 2's transient preview/current-worker bridge with a durable, source-grounded production engine that versions Research Set, Evidence, Storyboard, Script, Verification, Voice, and Episode artifacts; supports safe resumption and segment regeneration; and makes every audio claim traceable to recorded evidence.

**Architecture:** Migration 41 adds app-owned production, manifest-item, claim, evidence-link, artifact-version, stage-run, segment-version, model-receipt, and idempotency tables. The engine captures bounded, revision-pinned research context through unified knowledge APIs, partitions large sets without truncation, and advances an explicit stage state machine. Each stage consumes immutable parent artifact versions and creates a new immutable child; upstream changes mark descendants stale. Independent evidence, script, and verification roles use the Phase 1 planner, and bounded adaptive escalation retains both first-pass and final artifacts. Existing episode/audio records remain the final playback compatibility layer.

**Tech Stack:** Python 3.11/3.12, Pydantic 2 strict contracts, FastAPI, SurrealDB/SurrealQL transactions, existing command worker and podcast creator, React 19, Next.js 16, TypeScript, Zod 4, TanStack Query 5, Zustand 5, Vitest, Testing Library, Playwright, pytest, Ruff, and Phase 1 local-model planning/resource governance.

## Global Constraints

- Begin only after Phase 1 and Phase 2 completion gates pass; use a fresh `codex/` worktree.
- External inputs remain `external_read_only`. All manifests, captured contexts, claims, scripts, receipts, transcripts, and audio are app-owned artifacts.
- Manifest rows store stable IDs, relative locators, revisions, fingerprints, inclusion state, and reasons; they never store an external absolute root or write permission.
- A versioned `research_context` artifact may store the exact bounded text used for replay. It is derived app-owned data, never source authority, and is not written back externally.
- Whole-notebook and large research sets are partitioned into bounded batches and completely accounted for; no silent truncation or silent exclusion.
- Strict evidence is the default. Unsupported factual claims cannot reach Voice. Interpretation mode requires explicit inference/hypothesis/speculation language.
- Storyboard approval is required by default. Trusted-template bypass remains off unless the user explicitly enables it per template.
- Stage mutations require an operation ID and expected parent version. Retried operations are durably idempotent.
- Upstream edits mark descendants stale but never delete artifact history.
- Adaptive escalation is unit-bounded, retains first-pass output, has at most two higher-tier attempts, and cannot weaken evidence, privacy, authority, or execution policy.
- Strict Local records zero cloud endpoint requests. Local Preferred cloud use requires contextual approval for the exact stage and content class.
- Route receipts expose stable model identity, local fingerprint/revision, provider, tier, selection source, measurements, and reason; they expose no canonical model path, credential, prompt, source body, or provider response.
- Default runtime policy permits at most one heavyweight MLX language model. The orchestrator queues incompatible swaps through the Phase 1 governor.
- Voice failures preserve approved Script and Verification. Segment regeneration changes one segment lineage and final assembly only.
- Audio filesystem operations remain contained beneath the existing app-owned episode root.
- Automated tests use synthetic data. A controlled proof of live mounted brains requires separate source-hash receipts and no-write instrumentation.
- Run large suites serially. Do not push, merge, or enable external write-back in this plan.

---

## File Map

### Create

- `deeper_notebook/database/migrations/41.surrealql` — production and immutable artifact schema.
- `deeper_notebook/database/migrations/41_down.surrealql` — remove only migration-41 tables and indexes.
- `deeper_notebook/podcasts/evidence_contracts.py` — strict manifest, claim, evidence, storyboard, script, verification, artifact, stage, segment, and receipt contracts.
- `deeper_notebook/podcasts/evidence_repository.py` — transactional immutable artifacts, optimistic stage transitions, and idempotency receipts.
- `deeper_notebook/podcasts/research_sets.py` — stable selection capture, deduplication, batching, revision decisions, and context artifacts.
- `deeper_notebook/podcasts/evidence_engine.py` — claim extraction, supporting/contradicting links, diversity, gaps, and evidence states.
- `deeper_notebook/podcasts/storyboard_engine.py` — cited narrative segments, approval, keyboard-safe ordering semantics, and invalidation.
- `deeper_notebook/podcasts/script_engine.py` — versioned dialogue generation and citation binding.
- `deeper_notebook/podcasts/verification_engine.py` — independent deterministic and model-assisted policy gates.
- `deeper_notebook/podcasts/production_orchestrator.py` — resumable stage graph, cancellation, retries, voice handoff, and segment regeneration.
- `deeper_notebook/podcasts/model_execution.py` — stage route execution, bounded escalation, and redacted receipts.
- `api/schemas/podcast_productions.py` — strict redacted API models.
- `api/routers/podcast_productions.py` — production CRUD, stage actions, source decisions, approvals, and artifact reads.
- `tests/test_podcast_evidence_migration.py`, `tests/test_podcast_evidence_contracts.py`, `tests/test_podcast_evidence_repository.py`, `tests/integration/test_podcast_evidence_persistence.py`, `tests/test_podcast_research_sets.py`, `tests/test_podcast_evidence_engine.py`, `tests/test_podcast_storyboard_engine.py`, `tests/test_podcast_script_engine.py`, `tests/test_podcast_verification_engine.py`, `tests/test_podcast_model_execution.py`, `tests/test_podcast_production_orchestrator.py`, `tests/test_podcast_segment_versions.py`, and `tests/test_podcast_productions_api.py`.
- `frontend/src/lib/api/podcast-productions.ts` and test — strict Zod contracts and API client.
- `frontend/src/lib/hooks/use-podcast-production.ts` and test — query keys, polling, optimistic guards, and mutations.
- `frontend/src/components/podcasts/EvidenceBlueprint.tsx` and test.
- `frontend/src/components/podcasts/ClaimEvidenceInspector.tsx` and test.
- `frontend/src/components/podcasts/VerificationReport.tsx` and test.
- `frontend/src/components/podcasts/ArtifactHistory.tsx` and test.
- `frontend/src/components/podcasts/SourceChangeDecision.tsx` and test.
- `frontend/src/components/podcasts/EpisodeWaveform.tsx` and test.
- `frontend/src/components/podcasts/SegmentRegenerationDialog.tsx` and test.
- `frontend/e2e/podcast-evidence-engine.spec.ts`
- `scripts/verify_podcast_evidence_engine.py`
- `tests/test_verify_podcast_evidence_engine.py`
- `docs/verification/2026-08-01-podcast-evidence-engine.md`

### Modify

- `api/main.py` — inject and register the production repository, engines, and router.
- `api/routers/podcasts.py` — route Phase-3-capable Quick/Studio submissions to the orchestrator and retain legacy episode reads.
- `api/podcast_service.py` — accept verified script/voice handoff and final episode compatibility metadata.
- `commands/podcast_commands.py` and `commands/podcast_staged.py` — voice/final assembly from approved immutable script artifacts.
- `deeper_notebook/podcasts/models.py` — final episode production ID and artifact-version references.
- `deeper_notebook/local_models/contracts.py`, `planner.py`, and receipt tests — stage/unit purpose and escalation provenance.
- `deeper_notebook/knowledge_engine/repository.py` and `service.py` — revision-pinned bounded reads by stable document/block IDs.
- `frontend/src/components/podcasts/PodcastStudio.tsx` — unlock Evidence and Verification stages.
- `ResearchSetPanel.tsx`, `OutlineStoryboard.tsx`, `PodcastModelPlan.tsx`, `ProductionTimeline.tsx`, `PodcastLibrary.tsx`, and `EpisodeLab.tsx` — durable artifact and stage data.
- `GlobalAudioPlayer.tsx` and `SyncedTranscript.tsx` — exact claim/evidence navigation.
- podcast types, APIs, hooks, commands, locales, and existing tests.

## Interfaces Locked by This Plan

### Durable production graph

```python
ArtifactKind = Literal[
    "research_set",
    "research_context",
    "evidence_blueprint",
    "storyboard",
    "script",
    "verification",
    "voice_segment",
    "episode_assembly",
]
StageName = Literal[
    "research_set",
    "evidence",
    "storyboard",
    "script",
    "verification",
    "voice",
    "episode",
]
ArtifactState = Literal["current", "stale", "superseded", "failed"]
EvidenceState = Literal[
    "supported", "contested", "interpretive", "unsupported", "unavailable"
]
StageState = Literal[
    "pending",
    "queued",
    "running",
    "awaiting_review",
    "approved",
    "completed",
    "failed",
    "cancelled",
    "blocked",
]


class ResearchSetManifestItem(_Strict):
    item_id: str
    selection_kind: str
    document_id: str
    block_id: str | None
    space_id: str
    authority_kind: Literal["app_owned", "external_read_only"]
    relative_locator: str
    source_revision_id: str
    content_fingerprint: str
    inclusion_mode: Literal["full", "selected_blocks", "summary"]
    inclusion_state: Literal[
        "included", "duplicate", "excluded", "unavailable", "changed"
    ]
    inclusion_reason: str


class ArtifactVersion(_Strict):
    artifact_id: str
    production_id: str
    kind: ArtifactKind
    version: int = Field(ge=1)
    state: ArtifactState
    parent_artifact_ids: list[str] = Field(max_length=64)
    content_fingerprint: str
    created_at: datetime


class EvidenceClaim(_Strict):
    claim_id: str
    evidence_artifact_id: str
    statement: str
    state: EvidenceState
    confidence: float = Field(ge=0, le=1)
    interpretation_label: str | None
    supporting_link_ids: list[str] = Field(max_length=128)
    contradicting_link_ids: list[str] = Field(max_length=128)
    unresolved_question_ids: list[str] = Field(max_length=64)


class ClaimEvidenceLink(_Strict):
    link_id: str
    claim_id: str
    document_id: str
    block_id: str | None
    source_revision_id: str
    source_start: int | None
    source_end: int | None
    relation: Literal["supports", "contradicts", "contextualizes"]
    excerpt_fingerprint: str


class ModelExecutionReceipt(_Strict):
    receipt_id: str
    production_id: str
    stage: StageName
    unit_id: str
    attempt: int = Field(ge=1, le=3)
    model_id: str
    model_fingerprint: str
    provider: str
    resource_tier: Literal["light", "standard", "heavyweight"]
    selection_source: Literal["automatic", "role_override", "production_override"]
    route_reason: str
    measurements: dict[str, float | bool | str]
    input_artifact_ids: list[str]
    output_artifact_id: str
```

### Stage transitions

Allowed forward transitions are:

```text
research_set.completed -> evidence.queued
evidence.completed -> storyboard.awaiting_review
storyboard.approved -> script.queued
script.completed -> verification.queued
verification.completed -> voice.queued
voice.completed -> episode.queued
episode.completed -> terminal
```

`failed` may retry the same stage; `cancelled` may resume the same stage; `blocked` requires its recorded decision; no transition skips unapproved Storyboard or failed Verification. An upstream new artifact marks every reachable descendant `stale` in one transaction.

### Verification result

```python
class VerificationFinding(_Strict):
    finding_id: str
    severity: Literal["info", "warning", "blocking"]
    code: Literal[
        "missing_evidence",
        "stale_revision",
        "contested_without_counterpoint",
        "unlabeled_interpretation",
        "speaker_role_drift",
        "duration_mismatch",
        "audience_mismatch",
        "unresolved_citation",
    ]
    script_segment_id: str
    claim_id: str | None
    message: str


class VerificationReport(_Strict):
    artifact_id: str
    policy: Literal["strict", "interpretation"]
    outcome: Literal["passed", "blocked"]
    findings: list[VerificationFinding]
    verified_script_artifact_id: str
```

Strict mode passes only when no blocking finding exists and every factual script claim resolves to a current or explicitly recorded revision evidence link.

---

### Task 1: Migration 41 and Strict Evidence Contracts

**Files:** migration pair, `evidence_contracts.py`, migration/contract tests, migration discovery test

- [ ] Write failing tests asserting migration 41 defines exactly `podcast_production`, `podcast_research_item`, `podcast_artifact_version`, `podcast_claim`, `podcast_claim_evidence`, `podcast_stage_run`, `podcast_segment_version`, `podcast_model_receipt`, and `podcast_operation_receipt` with unique production/version and operation indexes.
- [ ] Define every interface above with `ConfigDict(extra="forbid", strict=True)`, lowercase SHA-256 validation, stable record-ID patterns, bounded arrays/text, UTC datetimes, and no path field.
- [ ] Implement the up migration as additive schemafull tables. The down migration removes only these nine tables/indexes and leaves episodes, knowledge engine, workspace, navigation, and Phase-2 metadata intact.
- [ ] Test malformed evidence states, spans, lineage cycles, revision IDs, unsupported transitions, receipt attempts above three, and extra fields fail closed.
- [ ] Run `pytest -q tests/test_podcast_evidence_migration.py tests/test_podcast_evidence_contracts.py tests/test_migration_discovery.py`.
- [ ] Commit with `git commit -m "feat: define podcast evidence schema"`.

### Task 2: Transactional Repository, Idempotency, and Invalidation

**Files:** `evidence_repository.py`, repository tests, integration persistence test

- [ ] Use a fake connection to write failing tests for create production, append immutable artifact, duplicate operation replay, optimistic parent conflict, legal/illegal stage transition, descendant invalidation, cancellation, and segment-version lineage.
- [ ] Implement parameterized SurrealQL transactions. Every mutation first checks `podcast_operation_receipt`; replay returns the recorded result without another row or stage transition.
- [ ] Enforce `(production_id, kind, version)` uniqueness, immutable artifact content, `expected_parent_artifact_id`, and stage revision compare-and-swap.
- [ ] Implement graph traversal from changed artifact to descendants and mark them stale without deleting bodies, receipts, approvals, or failure history.
- [ ] Assert database errors return stable scrubbed repository codes and never leak statements or variables.
- [ ] Run `pytest -q tests/test_podcast_evidence_repository.py tests/integration/test_podcast_evidence_persistence.py` with the integration fixture's persistent temporary SurrealDB process and expect both files to pass.
- [ ] Commit with `git commit -m "feat: persist immutable podcast artifacts"`.

### Task 3: Durable Research Set Capture and Complete Batching

**Files:** `research_sets.py`, knowledge repository/service bounded reads, tests

- [ ] Test mixed authority, notebook expansion, selected blocks, exact duplicate, near duplicate, changed revision, missing/failed parse, 10,001-item rejection, and multi-batch accounting.
- [ ] Resolve all Phase-2 selection variants to stable document/block/revision records. Create one manifest row per accounted item and a versioned `research_context` artifact containing exact bounded input text plus a source-span map.
- [ ] Batch by both character and item limits. Assert `sum(batch item IDs) == all included item IDs`, IDs appear once, and synthesized output references every completed batch artifact.
- [ ] For changed content require one decision: `refresh_evidence` captures the current revision and creates a new Research Set version; `continue_recorded_revision` uses an existing captured context; `remove_item` records explicit exclusion.
- [ ] Never read a canonical external path; use unified knowledge service bounded reads only.
- [ ] Run `pytest -q tests/test_podcast_research_sets.py tests/test_knowledge_engine_repository.py tests/test_knowledge_engine_service.py`.
- [ ] Commit with `git commit -m "feat: capture durable research sets"`.

### Task 4: Claim-Level Evidence Blueprint

**Files:** `evidence_engine.py`, `model_execution.py`, planner extensions, tests

- [ ] Define deterministic fixtures with supported, contested, interpretive, unsupported, unavailable, duplicate, low-diversity, and unresolved claims.
- [ ] Route bounded extraction units through `evidence_extraction`; normalize claim text and citations; link only to captured document/block/revision spans; compute evidence state from supporting/contradicting links and availability.
- [ ] Calculate source diversity, contradictions, unresolved questions, knowledge gaps, and proposed segment coverage as deterministic post-processing independent of model prose.
- [ ] If a unit fails schema/confidence/coverage/contradiction thresholds, escalate that unit only. Persist first-pass and final artifacts plus one receipt per attempt.
- [ ] Stop with reviewable `blocked` when no accepted higher local tier exists; never invoke cloud in Strict Local.
- [ ] Run `pytest -q tests/test_podcast_evidence_engine.py tests/test_podcast_model_execution.py tests/test_local_model_planner.py tests/test_research_core_local_models_api.py`.
- [ ] Commit with `git commit -m "feat: build claim evidence blueprints"`.

### Task 5: Cited Storyboard, Approval, and Stale Descendants

**Files:** `storyboard_engine.py`, API schemas/router, `OutlineStoryboard.tsx`, `EvidenceBlueprint.tsx`, tests

- [ ] Test storyboard segments require purpose, lead question, host roles, duration, claim IDs, evidence link IDs, learning outcome, transition intent, and explicit uncertainty for contested claims.
- [ ] Generate through `podcast_outline`, then deterministically reject missing claim/link references or a duration total outside the editorial brief tolerance.
- [ ] Implement reorder, edit, add, remove, resize, and approval as new storyboard versions. Every edit marks Script and later descendants stale; approval records operation ID, version, timestamp, and actor `local_user`.
- [ ] Build Evidence Blueprint and cited Storyboard UI with keyboard reorder, focus retention, state labels, source diversity, contradictions, gaps, and exact evidence navigation.
- [ ] Require approval before Script unless the selected saved template has an explicit trusted-direct-generation flag and the current user confirms it for this production.
- [ ] Run `pytest -q tests/test_podcast_storyboard_engine.py tests/test_podcast_productions_api.py && (cd frontend && npx vitest run src/components/podcasts/EvidenceBlueprint.test.tsx src/components/podcasts/ClaimEvidenceInspector.test.tsx src/components/podcasts/OutlineStoryboard.test.tsx --pool=forks --maxWorkers=1)`.
- [ ] Commit with `git commit -m "feat: approve cited podcast storyboards"`.

### Task 6: Script Generation and Independent Verification Gate

**Files:** `script_engine.py`, `verification_engine.py`, `VerificationReport.tsx`, tests

- [ ] Create fixtures for each verification code and both evidence policies. Assert strict mode blocks every unlabeled unsupported factual claim.
- [ ] Generate versioned segments through `podcast_script` from the approved storyboard and evidence artifact only. Bind each factual sentence to claim/evidence IDs and each speaker to an approved host role.
- [ ] Run deterministic checks first, then an independently routed `claim_verification` pass when deterministic checks clear. The verifier cannot use the exact same model receipt as Script when another accepted local route fits within memory policy; otherwise record why separation was impossible.
- [ ] In interpretation mode permit unsupported analysis only when labeled as analysis, inference, hypothesis, or speculation and never present it as source fact.
- [ ] Return blocked findings to Script review. Only `VerificationReport(outcome="passed")` may queue Voice.
- [ ] Build the report UI with finding-to-script-to-claim-to-evidence navigation and no raw provider errors.
- [ ] Run `pytest -q tests/test_podcast_script_engine.py tests/test_podcast_verification_engine.py && (cd frontend && npx vitest run src/components/podcasts/VerificationReport.test.tsx --pool=forks --maxWorkers=1)`.
- [ ] Commit with `git commit -m "feat: verify podcast scripts before voice"`.

### Task 7: Resumable Orchestration, Cancellation, and Model Receipts

**Files:** `production_orchestrator.py`, `model_execution.py`, router, command worker, tests

- [ ] Test every legal stage transition, failure at every stage, restart recovery, duplicate delivery, cancellation, source decision, route block, model swap queue, and one-heavyweight enforcement.
- [ ] Implement one orchestrator command that claims a stage with compare-and-swap, loads immutable parent artifacts, plans/reserves a route, runs one bounded stage/unit, commits artifact plus receipt, and advances atomically.
- [ ] Requeue only failed/incomplete units. Do not regenerate approved Research Set, Evidence, Storyboard, Script, or Verification after a Voice failure.
- [ ] On cancellation finish the current atomic write, mark the active stage cancelled, release memory, stop partial child processes, and preserve completed artifacts.
- [ ] On restart scan nonterminal claimed stages whose lease expired and return them to queued with a recovery receipt.
- [ ] Run `pytest -q tests/test_podcast_production_orchestrator.py tests/test_podcast_model_execution.py tests/test_podcast_command_defenses.py tests/test_v0_8_68_podcast_staged.py tests/test_v0_8_68_podcast_offline_gate.py desktop/tests/test_launcher.py`.
- [ ] Commit with `git commit -m "feat: resume podcast production stages"`.

### Task 8: Voice, Segment Versions, and Final Assembly

**Files:** orchestrator, podcast service/commands/models, segment APIs, `SegmentRegenerationDialog.tsx`, tests

- [ ] Test voice consumes only passed Verification, emits timing/speaker/chapter metadata, and maps every segment to the approved script version.
- [ ] Store each voice segment under the contained app-owned episode directory and create a `podcast_segment_version` row with script segment ID, voice route receipt, audio fingerprint, transcript timing, and parent segment version.
- [ ] Implement segment regeneration as a new segment version plus new episode assembly version. Unaffected segment IDs, audio fingerprints, and receipts must remain byte-for-byte identical.
- [ ] Verify final assembly has monotonically increasing timings, complete script-segment coverage, matching transcript text fingerprints, and no citation absent from the verified script.
- [ ] Preserve current Episode records/audio endpoints by linking the current completed assembly and production ID.
- [ ] Run `pytest -q tests/test_podcast_segment_versions.py tests/test_podcast_audio_containment.py tests/test_v0_8_68_podcast_improvements.py tests/test_podcast_command_defenses.py && (cd frontend && npx vitest run src/components/podcasts/SegmentRegenerationDialog.test.tsx src/components/podcasts/GlobalAudioPlayer.test.tsx src/components/podcasts/SyncedTranscript.test.tsx --pool=forks --maxWorkers=1)`.
- [ ] Commit with `git commit -m "feat: version podcast voice segments"`.

### Task 9: Production APIs and Phase-3 Studio Integration

**Files:** production API/router/hooks/types, Studio/Lab/library components and tests

- [ ] Add bounded endpoints to create/list/get productions; fetch artifacts/history; run/retry/cancel stages; approve storyboard; resolve findings; choose source-change decisions; regenerate a segment; and navigate a citation.
- [ ] Require operation IDs on mutations and expected revision/version on update-like actions. Return HTTP 409 for stale operations and replay successful idempotent operations.
- [ ] Unlock Evidence and Verification in the Studio timeline, replace transient preview with durable Research Set, and show stage versions, stale descendants, approvals, failures, model receipts, and recovery actions.
- [ ] Upgrade Episode Lab with waveform text alternative, speaker lanes, chapters, synchronized transcript, claim/evidence states, source revision, artifact history, and segment regeneration.
- [ ] Filter the Podcast library by format, knowledge space, profile, evidence state, date, and stage while retaining global playback.
- [ ] Run `pytest -q tests/test_podcast_productions_api.py && (cd frontend && npx vitest run src/lib/api/podcast-productions.test.ts src/lib/hooks/use-podcast-production.test.tsx src/components/podcasts/PodcastStudio.test.tsx src/components/podcasts/PodcastLibrary.test.tsx src/components/podcasts/EpisodeLab.test.tsx src/components/podcasts/ArtifactHistory.test.tsx src/components/podcasts/SourceChangeDecision.test.tsx src/components/podcasts/EpisodeWaveform.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit && npm run build)`.
- [ ] Commit with `git commit -m "feat: connect Studio to evidence productions"`.

### Task 10: End-to-End, Protected-Source, and Native Runtime Proof

**Files:** Playwright spec, verifier, verifier tests, verification record

- [ ] Browser-test a mixed app-owned/external production through Research Set, Evidence, storyboard edit/approval, Script, blocked then repaired Verification, Voice, Episode Lab, citation navigation, and one-segment regeneration.
- [ ] Test a whole notebook large enough for multiple batches and prove every included ID appears in batch accounting and final blueprint coverage.
- [ ] Inject Voice failure and prove approved upstream artifact fingerprints remain unchanged after resume; replay the same operation and prove one episode only.
- [ ] Exercise Strict Local with a network recorder and require zero non-loopback model requests; inspect small-to-large escalation receipts and confirm first-pass artifacts remain accessible.
- [ ] Hash synthetic Obsidian/Logseq fixtures before and after all flows and require equality plus zero external write attempts. Then run the separately approved controlled live-mount proof with the same hash/no-write gates.
- [ ] Run final serial gates: `pytest -q tests/test_podcast_evidence_migration.py tests/test_podcast_evidence_contracts.py tests/test_podcast_evidence_repository.py tests/integration/test_podcast_evidence_persistence.py tests/test_podcast_research_sets.py tests/test_podcast_evidence_engine.py tests/test_podcast_storyboard_engine.py tests/test_podcast_script_engine.py tests/test_podcast_verification_engine.py tests/test_podcast_model_execution.py tests/test_podcast_production_orchestrator.py tests/test_podcast_segment_versions.py tests/test_podcast_productions_api.py tests/test_verify_podcast_evidence_engine.py`; `ruff check deeper_notebook/podcasts api/routers/podcast_productions.py api/schemas/podcast_productions.py commands/podcast_commands.py commands/podcast_staged.py`; `(cd frontend && npx vitest run src/components/podcasts src/lib/api/podcast-productions.test.ts src/lib/hooks/use-podcast-production.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit && npm run build && npx playwright test e2e/podcast-evidence-engine.spec.ts --project=native-runtime)`; then `python scripts/verify_podcast_evidence_engine.py --native-url http://localhost:65060 --require-surrealdb`.
- [ ] Record exact commands, versions, timestamps, artifact IDs/fingerprints, source hashes, zero-write receipts, zero-cloud receipt, pass/fail counts, and native-runtime outcome in `docs/verification/2026-08-01-podcast-evidence-engine.md`.
- [ ] Commit with `git commit -m "test: verify podcast evidence engine"`.

## Phase 3 Completion Gate

Phase 3 is complete only when durable immutable versions cover every production stage; whole notebooks batch without truncation; claims expose evidence states and exact recorded revisions; strict policy blocks unsupported factual audio; storyboard approval and independent verification gate Voice; stage retry is idempotent; downstream failure preserves approved upstream artifacts; segment regeneration changes only its lineage and assembly; route and escalation receipts retain first-pass provenance without paths or secrets; Strict Local records zero cloud requests; one-heavyweight policy holds; live controlled Obsidian/Logseq hashes remain identical with zero write receipts; browser/build/database/native evidence is recorded; and all eighteen acceptance criteria in the approved design are satisfied.
