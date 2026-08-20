# Research Core Lab and Local Model Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Research Core Lab Knowledge workspace with equal, restorable Read, Write, Ask, Search, Graph, and Podcast modes plus verified smallest-capable local-model routing, without changing external-source authority or breaking current workspace, command, graph, bookmark, and editing behavior.

**Architecture:** A version-2 workspace document separates a tab's research mode from its target and migrates version-1 sessions in memory before persistence. Focused pane components reuse the current reader/editor, indexed search, graph, chat, and podcast foundations. A pure local-model planner classifies verified models into measured resource tiers, applies execution and compute policy, and returns redacted plans; the API remains read-only until the user explicitly saves local settings. The desktop config remains the device-local source of the model-library folder.

**Tech Stack:** Python 3.11/3.12, Pydantic 2, FastAPI, SurrealDB, React 19, Next.js 16, TypeScript, Zod 4, Zustand 5, TanStack Query 5, Vitest, Testing Library, Playwright, pytest, Ruff, native MLX, llama.cpp-compatible GGUF, Ollama, and loopback OpenAI-compatible runtimes.

## Global Constraints

- Execute in a dedicated `codex/` worktree created from local `main` at or after approved design commit `7ad69489`.
- Preserve the user's unrelated changes in `api/routers/vault.py`, `deeper_notebook/vault/repository.py`, `deeper_notebook/vault/service.py`, `desktop/launcher.py`, `desktop/tests/test_launcher.py`, `tests/test_vault_api.py`, and `commands/memory_commands.py`.
- Do not mount, scan, benchmark against, or write to the live Obsidian or Logseq brains during automated tests.
- External content remains `external_read_only`; this phase adds no external write, rename, move, delete, property update, task toggle, or backlink mutation.
- `/Users/Antman/Desktop/MacBook AI models` is selected through device-local configuration and `DEEPER_NOTEBOOK_MODEL_DIR`; it is never a portable source constant.
- Inventory, classification, health, and planning are read-only. Automatic routing excludes planned, removed, incomplete, unsupported, unavailable, unaccepted, or identity-mismatched models.
- Strict Local never contacts a cloud endpoint. Local Preferred requires a contextual user approval before cloud use. No provider failure changes policy.
- Default compute profile is `balanced`; selection is deterministic and uses the smallest accepted model that clears capability, quality, context, health, and memory gates.
- Only one heavyweight MLX language model may be active by default. Speech and embedding sidecars require a successful memory reservation.
- Workspace version 1 remains readable. Version 2 is written only after successful migration and full validation.
- Current Session remains file-backed crash recovery. Named-workspace revisions remain database-backed and immutable by autosave.
- No continuous decorative animation, no new animation dependency, and no unbounded polling.
- Run large backend and frontend suites serially on this Mac.
- Do not push, merge, enable live watchers, or promote cloud fallback in this plan.

---

## File Map

### Create

- `deeper_notebook/local_models/contracts.py` — strict execution policy, compute profile, role, readiness, resource tier, route-plan, and redacted receipt contracts.
- `deeper_notebook/local_models/planner.py` — eligibility, smallest-capable selection, override precedence, memory gating, and deterministic escalation planning.
- `deeper_notebook/local_models/settings.py` — owner-only atomic persistence for non-secret local routing preferences.
- `tests/test_local_model_planner.py`
- `tests/test_local_model_settings.py`
- `tests/test_research_core_local_models_api.py`
- `frontend/src/lib/knowledge/research-modes.ts` — mode descriptors and availability rules.
- `frontend/src/lib/knowledge/research-modes.test.ts`
- `frontend/src/components/vault/ResearchCoreHeader.tsx`
- `frontend/src/components/vault/ResearchCoreHeader.test.tsx`
- `frontend/src/components/vault/KnowledgeModeLauncher.tsx`
- `frontend/src/components/vault/KnowledgeModeLauncher.test.tsx`
- `frontend/src/components/vault/KnowledgeIntelligenceRail.tsx`
- `frontend/src/components/vault/KnowledgeIntelligenceRail.test.tsx`
- `frontend/src/components/vault/KnowledgeAskPane.tsx`
- `frontend/src/components/vault/KnowledgeAskPane.test.tsx`
- `frontend/src/components/vault/KnowledgeSearchPane.tsx`
- `frontend/src/components/vault/KnowledgeSearchPane.test.tsx`
- `frontend/src/components/vault/KnowledgePodcastPane.tsx`
- `frontend/src/components/vault/KnowledgePodcastPane.test.tsx`
- `frontend/src/components/local-models/LocalExecutionPolicyPanel.tsx`
- `frontend/src/components/local-models/LocalExecutionPolicyPanel.test.tsx`
- `frontend/src/components/local-models/ModelRoutePlanPanel.tsx`
- `frontend/src/components/local-models/ModelRoutePlanPanel.test.tsx`
- `frontend/e2e/research-core-lab.spec.ts`
- `scripts/verify_research_core_lab.py`
- `tests/test_verify_research_core_lab.py`
- `docs/verification/2026-08-01-research-core-lab.md`

### Modify

- `deeper_notebook/workspace/contracts.py` — version-2 discriminated tab targets and version-1 migration.
- `deeper_notebook/workspace/persistence.py` — parse either version, migrate, and atomically persist version 2.
- `deeper_notebook/knowledge_engine/navigation_contracts.py` — named-workspace surface target compatibility.
- `api/routers/knowledge_workspace.py` — version-2 response and bounded migration errors.
- `api/routers/local_models.py` — redacted readiness, planning, and settings endpoints.
- `api/main.py` — inject routing settings and planner dependencies.
- `deeper_notebook/local_models/__init__.py` — public contracts only.
- `deeper_notebook/local_models/inventory.py` — readiness facts and safe symlink boundary reporting.
- `deeper_notebook/local_models/role_routing.py` — approved role set and planner adapter.
- `deeper_notebook/local_models/quality_tasks.py` — probes for all executable research roles.
- `deeper_notebook/local_models/benchmarks.py` — resource measurements and accepted benchmark fingerprint.
- `desktop/config.py` — persist library folder, execution policy, compute profile, and memory limit without secrets in API responses.
- `desktop/launcher.py` — export selected folder and governor facts; enforce one-heavyweight-MLX default.
- `tests/test_knowledge_workspace_persistence.py`, `tests/test_knowledge_workspace_api.py`, `tests/test_local_model_role_routing.py`, `tests/test_local_model_quality_tasks.py`, `tests/test_local_model_benchmarks.py`, `tests/test_v0_8_39_local_models_inventory.py`, `desktop/tests/test_config.py`, `desktop/tests/test_launcher.py`, and `desktop/tests/test_launcher_adaptive_nctx.py` — contract, migration, routing, and resource-governor regressions.
- `frontend/src/lib/api/knowledge-workspace.ts` — version-2 Zod wire contracts and migration.
- `frontend/src/lib/stores/knowledge-workspace-store.ts` — typed surface tabs and migration-safe actions.
- `frontend/src/lib/api/local-models.ts` — strict readiness, route-plan, settings, and receipt types.
- `frontend/src/lib/hooks/use-local-models.ts` — query keys and mutations.
- `frontend/src/app/(dashboard)/settings/local-models/page.tsx` — policy, compute, role overrides, and grouped readiness.
- `frontend/src/components/local-models/ModelInventory.tsx` — group by readiness, modality, role, and resource fit.
- `frontend/src/components/local-models/RoleBenchmarkPanel.tsx` — expanded roles and tier measurements.
- `frontend/src/components/vault/KnowledgeExplorer.tsx` — Research Core shell composition.
- `frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx` — semantic adaptive canvas and responsive rails.
- `frontend/src/components/vault/KnowledgePaneContent.tsx` — mode dispatcher while preserving document render modes.
- `frontend/src/components/vault/KnowledgeUtilityRail.tsx` — collapsible Knowledge rail behavior.
- `frontend/src/components/vault/KnowledgeLinksInspector.tsx` — Intelligence rail content adapter.
- `frontend/src/components/vault/KnowledgeTabStrip.tsx` — mode identity and accessible labels.
- `frontend/src/components/vault/vault.css` and `frontend/src/app/globals.css` — Research Core tokens, focus, reduced motion, and responsive states.
- `frontend/src/lib/commands/knowledge-command-catalog.ts` and command tests — six mode commands.
- every `frontend/src/lib/locales/*/index.ts` bundle and locale parity tests.

## Interfaces Locked by This Plan

### Workspace contracts

```python
ResearchMode = Literal["read", "write", "ask", "search", "graph", "podcast"]
DocumentRenderMode = Literal["reading", "source", "live-preview", "canvas"]


class DocumentTabTarget(_Strict):
    kind: Literal["document"]
    container_id: str
    note_id: str
    title: str
    relative_locator: str
    authority: Literal["external-vault", "overlay"]
    knowledge_document_id: str | None = None
    render_mode: DocumentRenderMode = "reading"


class AskTabTarget(_Strict):
    kind: Literal["ask"]
    thread_id: str | None = None
    selected_document_ids: list[str] = Field(default_factory=list, max_length=128)


class SearchTabTarget(_Strict):
    kind: Literal["search"]
    query: str = Field(default="", max_length=512)
    search_mode: Literal["exact", "text", "semantic"] = "text"
    space_ids: list[str] = Field(default_factory=list, max_length=32)
    authority_kinds: list[Literal["app_owned", "external_read_only"]] = Field(
        default_factory=list, max_length=2
    )


class GraphTabTarget(_Strict):
    kind: Literal["graph"]
    root_document_id: str | None = None
    space_ids: list[str] = Field(default_factory=list, max_length=32)
    relation_kinds: list[str] = Field(default_factory=list, max_length=32)
    viewport: GraphViewport = Field(default_factory=GraphViewport)


class PodcastTabTarget(_Strict):
    kind: Literal["podcast"]
    production_id: str | None = None
    seed_document_ids: list[str] = Field(default_factory=list, max_length=128)


KnowledgeTabTarget = Annotated[
    DocumentTabTarget
    | AskTabTarget
    | SearchTabTarget
    | GraphTabTarget
    | PodcastTabTarget,
    Field(discriminator="kind"),
]


class KnowledgeTabStateV2(_Strict):
    id: str
    mode: ResearchMode
    title: str
    target: KnowledgeTabTarget


class KnowledgeWorkspaceDocumentV2(_Strict):
    version: Literal[2] = 2
    active_pane_id: str
    next_id: int
    panes: dict[str, KnowledgePaneStateV2]
    layout: KnowledgeLayoutNode
    navigation: KnowledgeWorkspaceNavigation
```

`migrate_workspace_v1(document)` maps reading/source/live-preview to `mode="read"`, editable Overlay tabs to `mode="write"`, graph to `mode="graph"`, canvas to `mode="read"`, and preserves every stable ID, relative locator, pane, split size, active tab, and navigation preference.

### Local routing contracts

```python
ModelRole = Literal[
    "research_chat",
    "evidence_extraction",
    "claim_verification",
    "editorial_writing",
    "embedding_retrieval",
    "vision_analysis",
    "code_data_analysis",
    "podcast_outline",
    "podcast_script",
    "speech_to_text",
    "text_to_speech",
]
Readiness = Literal[
    "ready_verified",
    "ready_unverified",
    "requires_runtime",
    "runtime_unavailable",
    "installed_unsupported",
    "incomplete",
    "planned",
    "removed",
]
ResourceTier = Literal["light", "standard", "heavyweight"]
ExecutionPolicy = Literal["strict_local", "local_preferred", "custom"]
ComputeProfile = Literal["efficient", "balanced", "maximum_quality"]
SelectionSource = Literal["automatic", "role_override", "production_override"]


class RouteRequest(_Strict):
    role: ModelRole
    required_context_tokens: int = Field(ge=0, le=2_000_000)
    modalities: list[Literal["text", "image", "audio"]] = Field(max_length=3)
    requires_structured_output: bool = False
    execution_policy: ExecutionPolicy
    compute_profile: ComputeProfile
    role_override_model_id: str | None = None
    production_override_model_id: str | None = None


class ModelRoutePlan(_Strict):
    role: ModelRole
    outcome: Literal["ready", "blocked", "approval_required"]
    selected_model_id: str | None
    selected_provider: str | None
    resource_tier: ResourceTier | None
    selection_source: SelectionSource | None
    route_reason: str
    escalation_model_ids: list[str] = Field(max_length=2)
    blocked_reason: str | None = None
```

No route-plan or receipt contains `path`, `model_dir`, a credential, prompt text, source text, or provider response.

---

### Task 1: Version-2 Workspace Contracts and Lossless Migration

**Files:** `deeper_notebook/workspace/contracts.py`, `deeper_notebook/workspace/persistence.py`, `deeper_notebook/knowledge_engine/navigation_contracts.py`, `tests/test_knowledge_workspace_persistence.py`, `tests/test_knowledge_workspace_api.py`, `tests/test_knowledge_navigation_contracts.py`, `tests/integration/test_knowledge_navigation_persistence.py`, `frontend/src/lib/api/knowledge-workspace.ts`, `frontend/src/lib/api/knowledge-workspace.test.ts`, `frontend/src/lib/api/knowledge-navigation.ts`, `frontend/src/lib/api/knowledge-navigation.test.ts`, `frontend/src/lib/stores/knowledge-workspace-store.ts`, `frontend/src/lib/stores/knowledge-workspace-store.test.ts`

- [ ] Write backend fixtures for each version-1 render mode and assert `migrate_workspace_v1` produces the exact version-2 target, layout, active IDs, and navigation state defined above.
- [ ] Run `pytest -q tests/test_knowledge_workspace_persistence.py tests/test_knowledge_workspace_api.py` and confirm the new version-2 assertions fail before implementation.
- [ ] Implement the discriminated contracts, a bounded before-validator for 32 panes/128 tabs/depth 64, version dispatch, and a pure version-1 migration. Reject a mismatched mode/target pair with `workspace_mode_target_mismatch`.
- [ ] Add equivalent strict Zod schemas and `migrateKnowledgeWorkspaceV1`; parse unknown wire data as V1 or V2, migrate once, then store only V2.
- [ ] Version named-workspace snapshots with the same discriminated targets. Restore version-1 named snapshots through the same pure migration and retain immutable named-workspace revision history.
- [ ] Add tests proving malformed targets fail closed, canonical paths never appear, V1 is accepted, V2 round-trips, and one migration increments neither `revision` nor `nextId`.
- [ ] Run `pytest -q tests/test_knowledge_workspace_persistence.py tests/test_knowledge_workspace_api.py tests/test_knowledge_navigation_contracts.py tests/integration/test_knowledge_navigation_persistence.py && (cd frontend && npx vitest run src/lib/api/knowledge-workspace.test.ts src/lib/api/knowledge-navigation.test.ts src/lib/stores/knowledge-workspace-store.test.ts --pool=forks --maxWorkers=1)` and expect all selected tests to pass.
- [ ] Commit with `git commit -m "feat: version research workspace modes"`.

### Task 2: Research Mode Descriptors and Pane Dispatcher

**Files:** `frontend/src/lib/knowledge/research-modes.ts`, its test, `KnowledgePaneContent.tsx`, `KnowledgeAskPane.tsx`, `KnowledgeSearchPane.tsx`, `KnowledgePodcastPane.tsx`, and component tests

- [ ] Write a table-driven test over all six modes asserting label, icon key, keyboard shortcut, required target kind, and availability reason.
- [ ] Implement this exact descriptor shape:

```typescript
export type ResearchModeDescriptor = {
  id: ResearchMode
  label: 'Read' | 'Write' | 'Ask' | 'Search' | 'Graph' | 'Podcast'
  shortcut: '1' | '2' | '3' | '4' | '5' | '6'
  targetKind: KnowledgeTabTarget['kind']
  requiresDocument: boolean
}
```

- [ ] Extract the existing document/graph behavior into the `document` and `graph` dispatcher branches without changing queries, editor authority, Canvas behavior, graph viewport persistence, selection tracking, or document metrics.
- [ ] Build Ask as a scoped shell over current local chat primitives, Search over `useKnowledgeIndexedSearch`, and Podcast as a Phase-1 landing pane that displays the current selection and explicitly states that generation opens in Phase 2; none may auto-submit work on mount.
- [ ] Test that external documents disable Write with `External source — read only`, unavailable models disable Ask with the returned readiness reason, empty selection still permits Search, and Podcast never calls `/podcasts/generate` merely by opening.
- [ ] Run `(cd frontend && npx vitest run src/lib/knowledge/research-modes.test.ts src/components/vault/KnowledgePaneContent.test.tsx src/components/vault/KnowledgeAskPane.test.tsx src/components/vault/KnowledgeSearchPane.test.tsx src/components/vault/KnowledgePodcastPane.test.tsx --pool=forks --maxWorkers=1)`.
- [ ] Commit with `git commit -m "feat: add typed research pane modes"`.

### Task 3: Research Core Header, Mode Launcher, and Intelligence Rail

**Files:** the three new Research Core components and tests, `KnowledgeUtilityRail.tsx`, `KnowledgeLinksInspector.tsx`, `KnowledgeTabStrip.tsx`, `KnowledgeWorkspaceLayout.tsx`

- [ ] Write component tests asserting semantic `header`, `nav`, `main`, and `aside`; six keyboard-reachable modes; model readiness disclosure; non-color authority labels; rail collapse focus restoration; and tab names containing mode plus title.
- [ ] Implement `ResearchCoreHeader` with workspace title, authority summary, save state, local readiness state, memory-pressure state, and queued-work count. Expanded readiness details may show model IDs and providers but never model paths.
- [ ] Implement `KnowledgeModeLauncher` as a roving-tabindex toolbar. `Alt+1` through `Alt+6` opens or activates a compatible tab in the active pane; activation never replaces an unsaved Overlay draft.
- [ ] Implement `KnowledgeIntelligenceRail` with contextual `evidence`, `connections`, `properties`, and `production` panels. Reuse `KnowledgeLinksInspector` for connections and keep collapsed content unmounted.
- [ ] Preserve split resize, close behavior, `aria-controls`, active tab fallback, and named-workspace restore in `KnowledgeWorkspaceLayout` and `KnowledgeTabStrip`.
- [ ] Run `(cd frontend && npx vitest run src/components/vault/ResearchCoreHeader.test.tsx src/components/vault/KnowledgeModeLauncher.test.tsx src/components/vault/KnowledgeIntelligenceRail.test.tsx src/components/vault/KnowledgeWorkspaceLayout.test.tsx src/components/vault/KnowledgeTabStrip.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit)`; expect zero failures and zero TypeScript errors.
- [ ] Commit with `git commit -m "feat: compose Research Core workspace shell"`.

### Task 4: Research Core Visual System, Responsive Rails, and Motion Safety

**Files:** `frontend/src/components/vault/vault.css`, `frontend/src/app/globals.css`, Research Core component tests, locale files

- [ ] Add tests for CSS hook classes, `prefers-reduced-motion`, accessible names, focus restoration, and narrow-width drawer labels.
- [ ] Add semantic tokens `--research-canvas`, `--research-panel`, `--research-line`, `--research-accent`, `--research-accent-strong`, `--research-warning`, and `--research-glow` using the approved deep-teal/cyan Research Core palette.
- [ ] Use one restrained entry transition no longer than 180ms. Under reduced motion set transition and animation duration to `0.01ms`; define no infinite animation.
- [ ] At widths below 1024px, convert both rails to labeled drawers; below 720px, make mode surfaces sequential and keep the active mode toolbar sticky without obscuring focus.
- [ ] Add translations for every new label and run the locale parity test so every supported locale has identical keys.
- [ ] Run `(cd frontend && npx vitest run src/components/vault --pool=forks --maxWorkers=1 && npx tsc --noEmit)`.
- [ ] Commit with `git commit -m "style: apply Research Core Lab system"`.

### Task 5: Verified Inventory and Readiness Classification

**Files:** `deeper_notebook/local_models/contracts.py`, `inventory.py`, `manifest.py`, `tests/test_v0_8_39_local_models_inventory.py`, `tests/test_local_model_manifest.py`, `tests/test_research_core_local_models_api.py`

- [ ] Create synthetic roots covering complete MLX, GGUF, Transformers, planned manifest rows, removed rows, partial files, runtime mismatch, and an external STT/TTS symlink. Snapshot every fixture hash before discovery.
- [ ] Implement readiness as a pure function of file completeness, supported runtime, manifest state, current runtime identity, bounded health, benchmark acceptance, and trusted symlink target. Manifest text alone can never yield `ready_verified`.
- [ ] Return `path` only from the dedicated inventory endpoint; return `model_id`, format, modality, readiness, readiness reason, measured tier, and accepted roles everywhere else.
- [ ] Add an explicit trust record keyed by selected-root fingerprint and resolved-target fingerprint; never follow an untrusted external symlink recursively.
- [ ] Assert planned, removed, incomplete, unsupported, unverified, and identity-mismatched models are visible but not route-eligible; assert fixture hashes are unchanged.
- [ ] Run `pytest -q tests/test_v0_8_39_local_models_inventory.py tests/test_local_model_manifest.py tests/test_research_core_local_models_api.py`.
- [ ] Commit with `git commit -m "feat: classify local model readiness"`.

### Task 6: Smallest-Capable Planner, Overrides, and Adaptive Escalation

**Files:** `deeper_notebook/local_models/planner.py`, `contracts.py`, `role_routing.py`, `quality_tasks.py`, `benchmarks.py`, `tests/test_local_model_planner.py`, `tests/test_local_model_quality_tasks.py`, `tests/test_local_model_benchmarks.py`

- [ ] Write table-driven tests for the eleven roles, light/standard/heavyweight classification from measured peak memory and latency, deterministic tie-breaking, three compute profiles, override precedence, stale benchmark exclusion, and no eligible route.
- [ ] Implement eligibility in this order: readiness → modality → role acceptance → context → structured output → health → memory reservation → execution policy. Sort eligible automatic candidates by profile tier preference, accepted quality descending, peak memory ascending, latency ascending, stable model ID ascending.
- [ ] Apply precedence `production_override > role_override > automatic`; an override that fails a gate returns `blocked` and is never silently replaced.
- [ ] Implement escalation plans with at most two higher-tier model IDs. Escalation is permitted only for schema invalidity, confidence below the role threshold, insufficient evidence coverage, contradiction failure, or declared task complexity.
- [ ] Retain first-pass model ID, fingerprint, measurements, reason, and bounded unit ID in the escalation receipt; never persist raw source or output in the receipt.
- [ ] Add quality tasks for all roles; speech roles use bounded capability/identity probes rather than language prompts.
- [ ] Run `pytest -q tests/test_local_model_planner.py tests/test_local_model_quality_tasks.py tests/test_local_model_benchmarks.py tests/test_local_model_role_routing.py`.
- [ ] Commit with `git commit -m "feat: plan smallest capable local routes"`.

### Task 7: Device-Local Settings and Resource Governor

**Files:** `deeper_notebook/local_models/settings.py`, `desktop/config.py`, `desktop/launcher.py`, their tests, `api/routers/local_models.py`

- [ ] Write tests for atomic owner-only persistence, a path containing spaces, invalid/unreadable roots, Balanced default, restart restoration, one-heavyweight-MLX exclusion, sidecar reservations, and provider cleanup after failed load.
- [ ] Extend launcher config with `execution_policy`, `compute_profile`, `local_model_memory_limit_bytes`, `role_overrides`, and `trusted_external_model_roots`; preserve old config files through defaults.
- [ ] Add `GET /api/local-models/settings`, `PUT /api/local-models/settings`, and `POST /api/local-models/route-plan`. PUT validates the selected root and writes atomically; it never returns SurrealDB credentials or the encryption key.
- [ ] Export the selected root through `DEEPER_NOTEBOOK_MODEL_DIR`, record memory pressure and reservations, queue incompatible heavyweight swaps, and stop partial child processes after a failed health check.
- [ ] Prove Strict Local route planning performs zero requests to non-loopback model endpoints using an injected transport recorder.
- [ ] Run `pytest -q tests/test_local_model_settings.py tests/test_research_core_local_models_api.py desktop/tests/test_config.py desktop/tests/test_launcher.py desktop/tests/test_launcher_adaptive_nctx.py`.
- [ ] Commit with `git commit -m "feat: govern local model execution"`.

### Task 8: Local Models and Research Header Product Surfaces

**Files:** `frontend/src/lib/api/local-models.ts`, `frontend/src/lib/hooks/use-local-models.ts`, `frontend/src/app/(dashboard)/settings/local-models/page.tsx`, `frontend/src/app/(dashboard)/settings/local-models/page.test.tsx`, `frontend/src/components/local-models/LocalExecutionPolicyPanel.tsx`, `frontend/src/components/local-models/LocalExecutionPolicyPanel.test.tsx`, `frontend/src/components/local-models/ModelRoutePlanPanel.tsx`, `frontend/src/components/local-models/ModelRoutePlanPanel.test.tsx`, `frontend/src/components/local-models/ModelInventory.tsx`, `frontend/src/components/local-models/ModelInventory.test.tsx`, `frontend/src/components/vault/ResearchCoreHeader.tsx`, and `frontend/src/components/vault/ResearchCoreHeader.test.tsx`

- [ ] Add strict frontend schemas for settings, readiness groups, model route plans, blocked reasons, memory state, and redacted receipts; reject any response containing `path` outside inventory.
- [ ] Build Settings panels for library selection/rescan, readiness groups, runtime compatibility, role routes and overrides, measured tiers, compute profile, execution policy, memory limit, and benchmark/acceptance history.
- [ ] Show the active Research Chat and Embedding routes in Ask/Search and Evidence/Storyboard/Script/Verification/Voice route plans in the Podcast landing surface.
- [ ] Require a confirmation dialog that identifies stage and content class before Local Preferred can proceed to any cloud model; cancel leaves policy and task unchanged.
- [ ] Test unavailable and degraded states, explicit override rejection, Strict Local fail-closed, and that canonical paths appear only on Settings inventory.
- [ ] Run `(cd frontend && npx vitest run src/app/'(dashboard)'/settings/local-models/page.test.tsx src/components/local-models/LocalExecutionPolicyPanel.test.tsx src/components/local-models/ModelRoutePlanPanel.test.tsx src/components/local-models/ModelInventory.test.tsx src/components/vault/ResearchCoreHeader.test.tsx --pool=forks --maxWorkers=1 && npx tsc --noEmit && npm run build)`.
- [ ] Commit with `git commit -m "feat: expose explainable local model plans"`.

### Task 9: Commands, Persistence, and Browser Acceptance

**Files:** command catalog/bridge/tests, `frontend/e2e/research-core-lab.spec.ts`, `scripts/verify_research_core_lab.py`, verification tests and record

- [ ] Register `knowledge.mode.read`, `.write`, `.ask`, `.search`, `.graph`, and `.podcast` with stable IDs, availability predicates, and no external mutation capability.
- [ ] Add Playwright coverage to open every mode from launcher and command palette, split mixed modes, restore Current Session and a named workspace, preserve an Overlay draft, verify external Write is disabled, inspect route reasons, and operate both responsive drawers by keyboard.
- [ ] Implement the verifier against synthetic temporary data. It records workspace migration, local-library before/after fingerprints, zero cloud requests in Strict Local, one-heavyweight enforcement, and focused test/build results.
- [ ] Run `pytest -q tests/test_verify_research_core_lab.py` and the verifier; then run the Playwright spec against the persistent native runtime.
- [ ] Record commands, versions, timestamps, hashes, pass/fail counts, and any native-only remaining gate in `docs/verification/2026-08-01-research-core-lab.md`.
- [ ] Run final serial gates: `pytest -q tests/test_knowledge_workspace_persistence.py tests/test_knowledge_workspace_api.py tests/test_local_model_planner.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py tests/test_verify_research_core_lab.py desktop/tests/test_config.py desktop/tests/test_launcher.py`; `ruff check deeper_notebook/local_models deeper_notebook/workspace api/routers/local_models.py desktop/config.py desktop/launcher.py tests/test_local_model_planner.py tests/test_local_model_settings.py tests/test_research_core_local_models_api.py`; `(cd frontend && npx vitest run src/components/vault src/components/local-models src/lib/api/knowledge-workspace.test.ts src/lib/stores/knowledge-workspace-store.test.ts --pool=forks --maxWorkers=1 && npx tsc --noEmit && npm run build && npx playwright test e2e/research-core-lab.spec.ts --project=native-runtime)`; then `python scripts/verify_research_core_lab.py --native-url http://localhost:65060`.
- [ ] Commit with `git commit -m "test: verify Research Core Lab"`.

## Phase 1 Completion Gate

Phase 1 is complete only when all six modes restore across tabs and splits; current Knowledge functions still pass; external write capabilities remain absent; the selected model library is unchanged by inventory and routing; automatic routes use only verified models; Balanced chooses the smallest capable accepted model; Strict Local records zero cloud requests; one-heavyweight-MLX enforcement is proven; accessibility, responsive, production-build, and native-runtime evidence is recorded; and the app remains usable without Phase 2 or Phase 3.
