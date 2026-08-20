# Deeper Notebook Study Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the existing `/study` route into a local-first, evidence-grounded AI learning workbench with approved syllabi, specialized tutors, adaptive practice, and secure Anki package interoperability.

**Architecture:** Preserve the existing `StudyCard`, `StudyReview`, FSRS scheduler, source ingestion, and Evidence Studio APIs. Add focused Study Plan domain modules, additive SurrealDB tables and `/api/study/plans` routers, then compose them through typed frontend clients and plan-scoped UI. Treat AI generation and Anki work as bounded, resumable jobs; keep current due-card review as the feature-flag rollback surface.

**Tech Stack:** Python 3.11/3.12, FastAPI, Pydantic v2, SurrealDB, LangChain model adapters, existing Evidence Studio structured generation, FSRS 6, Next.js 16, React 19, TypeScript, TanStack Query, Zustand, Tailwind/shadcn, Vitest, Playwright, `genanki==0.13.1` for MIT-licensed export only, Python stdlib `zipfile`/`sqlite3` for bounded import.

## Global Constraints

- Do not change existing `/api/study/cards`, `StudyCard`, `StudyReview`, or FSRS serialized contracts.
- All database changes are additive and have matching down migrations for task-owned tables.
- Linked notebooks, notes, sources, and external vaults remain read-only.
- Local sources and local models are default; web research and cloud models require explicit per-plan authority.
- A syllabus proposal must be edited or approved before downstream generation.
- Assistants may propose changes but may not silently expand network/model/data authority.
- Anki packages are untrusted archives; import must validate before materialization and publish atomically.
- The feature flag must preserve the current Study dashboard and review session byte-for-byte in flag-off mode.
- Each task follows RED -> GREEN, scoped review, `git diff --check`, and an atomic commit.
- Preserve unrelated dirty/untracked paths and never stage `.codex/agent-context`, `graphify-out`, `node_modules`, `.playwright-cli`, or generated Playwright results.
- Code Review Graph evidence is unavailable because `graphify-out/graph.json` is absent; use direct source tracing and record that limitation in review receipts.

---

## File ownership map

### Existing files retained as compatibility boundaries

- `deeper_notebook/study/contracts.py` — current card/review wire-independent contracts; only import from it.
- `deeper_notebook/study/scheduler.py` — current FSRS adapter; no scheduler replacement.
- `deeper_notebook/study/repository.py` — current card/review persistence; only additive helper methods if a plan-card link needs them.
- `api/routers/study.py` and `api/schemas/study.py` — current public card/review API; no response-shape changes.
- `frontend/src/components/study/StudySession.tsx` — current review interaction; compose it, do not rewrite it.
- `api/routers/sources.py` and `frontend/src/components/sources/AddSourceDialog.tsx` — only source upload/processing path.
- `deeper_notebook/studio/generation/*` — only artifact generation/evidence path.

### New backend modules

- `deeper_notebook/study/plans.py` — plan, source-link, syllabus, unit, and lifecycle contracts.
- `deeper_notebook/study/plan_repository.py` — plan/syllabus/source-link persistence.
- `deeper_notebook/study/syllabus_service.py` — source readiness, typed proposal generation, approval manifest, and drift checks.
- `deeper_notebook/study/assistants.py` — roles, authority, invocations, handoffs, and plan-memory contracts.
- `deeper_notebook/study/assistant_repository.py` — bounded handoff/session/memory persistence.
- `deeper_notebook/study/assistant_service.py` — assistant routing, retrieval, structured response, and proposal enforcement.
- `deeper_notebook/study/progress.py` — progress receipts, mastery projection, and adaptation proposals.
- `deeper_notebook/study/progress_repository.py` — append-only progress and aggregate queries.
- `deeper_notebook/study/anki_package.py` — untrusted package inspection/import translation and safe export adapter.
- `deeper_notebook/study/anki_repository.py` — import/export job checkpoints and atomic publication.
- `api/schemas/study_plans.py`, `study_assistants.py`, `study_anki.py` — strict HTTP contracts.
- `api/routers/study_plans.py`, `study_assistants.py`, `study_anki.py` — additive endpoints.
- `deeper_notebook/database/migrations/41*.surrealql`, `42*.surrealql`, `43*.surrealql` — plan, assistant/progress, and Anki job tables.

### New frontend modules

- `frontend/src/lib/types/study-plans.ts` — exact plan/syllabus/source/progress types.
- `frontend/src/lib/types/study-assistants.ts` — exact tutor invocation/handoff types.
- `frontend/src/lib/types/study-anki.ts` — package job and compatibility types.
- `frontend/src/lib/api/study-plans.ts`, `study-assistants.ts`, `study-anki.ts` — HTTP clients.
- `frontend/src/lib/hooks/use-study-plans.ts`, `use-study-assistants.ts`, `use-study-anki.ts` — query/mutation ownership.
- `frontend/src/components/study/StudyWorkbench.tsx` — flag-on Study home composition.
- `frontend/src/components/study/StudyPlanWizard.tsx` — resumable plan intake.
- `frontend/src/components/study/StudyPlanWorkspace.tsx` — plan route and tab composition.
- `frontend/src/components/study/SyllabusEditor.tsx` — edit/version/approve interaction.
- `frontend/src/components/study/TutorDock.tsx` — one foreground tutor and specialist routing.
- `frontend/src/components/study/StudyProgressPanel.tsx` — mastery/pacing/adaptation proposals.
- `frontend/src/components/study/AnkiPackagePanel.tsx` — import/export and compatibility receipts.
- `frontend/src/app/(dashboard)/study/plans/[planId]/page.tsx` — plan workspace route.

---

## Phase A — Plans, sources, and syllabus approval

### Task 1: Reversible Study Workbench feature boundary

**Files:**
- Modify: `deeper_notebook/feature_flags.py`
- Modify: `tests/test_evidence_studio_foundation.py`
- Modify: `frontend/src/lib/features.ts`
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/lib/features-build-contract.test.ts`
- Modify: `frontend/src/app/(dashboard)/study/page.tsx`
- Modify: `frontend/src/app/(dashboard)/study/page.test.tsx`

**Interfaces:**
- Produces: `study_workbench_enabled() -> bool`
- Produces: `isStudyWorkbenchEnabled(): boolean`
- Preserves: flag-off render of `StudyDashboard` plus `StudySession`

- [ ] **Step 1: Add failing backend and frontend flag tests**

```python
def test_study_workbench_flag_defaults_off_and_accepts_canonical_name(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_STUDY_WORKBENCH", raising=False)
    assert feature_flags.study_workbench_enabled() is False
    monkeypatch.setenv("DEEPER_NOTEBOOK_STUDY_WORKBENCH", "enabled")
    assert feature_flags.study_workbench_enabled() is True
```

```tsx
it('keeps the current Study review surface when the workbench flag is off', () => {
  process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '0'
  render(<StudyPage />)
  expect(screen.getByText('Study dashboard')).toBeInTheDocument()
  expect(screen.getByText('Study session')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run RED tests**

Run: `uv run pytest -q tests/test_evidence_studio_foundation.py -k study_workbench && cd frontend && npx vitest run src/lib/features.test.ts 'src/app/(dashboard)/study/page.test.tsx'`

Expected: backend fails because `study_workbench_enabled` is absent; frontend fails because `isStudyWorkbenchEnabled` and the flag branch are absent.

- [ ] **Step 3: Add explicit canonical flags and the rollback branch**

```python
def study_workbench_enabled() -> bool:
    return _env_flag("DEEPER_NOTEBOOK_STUDY_WORKBENCH")
```

```ts
export function isStudyWorkbenchEnabled(): boolean {
  return envFlag(process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH, undefined)
}
```

Render `<StudyWorkbench />` only when enabled; keep the existing page body in the false branch without changing its props or copy.

- [ ] **Step 4: Run GREEN and static checks**

Run: `uv run pytest -q tests/test_evidence_studio_foundation.py -k 'feature_flags or study_workbench' && cd frontend && npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts 'src/app/(dashboard)/study/page.test.tsx' && npx eslint src/lib/features.ts 'src/app/(dashboard)/study/page.tsx' && npx tsc --noEmit`

Expected: all selected tests pass; ESLint and TypeScript exit 0.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/feature_flags.py tests/test_evidence_studio_foundation.py frontend/src/lib/features.ts frontend/src/lib/features.test.ts frontend/src/lib/features-build-contract.test.ts 'frontend/src/app/(dashboard)/study/page.tsx' 'frontend/src/app/(dashboard)/study/page.test.tsx'
git commit -m "feat(study): add reversible workbench boundary"
```

### Task 2: Study Plan and syllabus domain contracts

**Files:**
- Create: `deeper_notebook/study/plans.py`
- Create: `tests/test_study_plan_contracts.py`

**Interfaces:**
- Produces: `StudyPlan`, `StudyPlanPreferences`, `StudyPlanSourceLink`, `StudySyllabus`, `StudySyllabusUnit`, `StudyActivity`, `StudyPlanState`
- Consumes later: repository, API schemas, syllabus service, progress service

- [ ] **Step 1: Write failing strict-contract and lifecycle tests**

```python
def test_syllabus_is_bounded_versioned_and_requires_unique_units():
    syllabus = StudySyllabus(
        plan_id="study_plan:one",
        version=1,
        source_manifest_sha256="a" * 64,
        units=[
            StudySyllabusUnit(
                unit_id="foundations",
                title="Foundations",
                objectives=["Explain the core idea"],
                estimated_minutes=60,
            )
        ],
    )
    assert syllabus.units[0].unit_id == "foundations"
    with pytest.raises(ValidationError):
        StudySyllabus(
            plan_id="study_plan:one",
            version=1,
            source_manifest_sha256="a" * 64,
            units=[syllabus.units[0], syllabus.units[0]],
        )
```

Also test blank text, more than 64 units, more than 20 objectives per unit, naive datetimes, unknown extra fields, illegal lifecycle transitions, duplicate source links, and approval without a source manifest.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_plan_contracts.py`

Expected: collection error because `deeper_notebook.study.plans` is absent.

- [ ] **Step 3: Implement frozen bounded contracts**

```python
StudyPlanState = Literal[
    "draft",
    "analyzing_sources",
    "syllabus_proposed",
    "editing",
    "approved",
    "generating",
    "active",
    "completed",
    "archived",
]


class StudySyllabusUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    unit_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    objectives: list[str] = Field(min_length=1, max_length=20)
    prerequisite_unit_ids: list[str] = Field(default_factory=list, max_length=20)
    estimated_minutes: int = Field(ge=5, le=10_080)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    activities: list[StudyActivity] = Field(default_factory=list, max_length=50)


class StudySyllabus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=512)
    version: int = Field(ge=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    units: list[StudySyllabusUnit] = Field(min_length=1, max_length=64)
    approved_at: datetime | None = None
```

Implement explicit `StudyPlan.transition(next_state, expected_version)` with an allowlisted transition map; no arbitrary state assignment.

- [ ] **Step 4: Run GREEN and Ruff**

Run: `uv run pytest -q tests/test_study_plan_contracts.py && uv run ruff check deeper_notebook/study/plans.py tests/test_study_plan_contracts.py`

Expected: all contract tests pass and Ruff exits 0.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/plans.py tests/test_study_plan_contracts.py
git commit -m "feat(study): define plan and syllabus contracts"
```

### Task 3: Additive plan persistence and migrations

**Files:**
- Create: `deeper_notebook/database/migrations/41.surrealql`
- Create: `deeper_notebook/database/migrations/41_down.surrealql`
- Create: `deeper_notebook/study/plan_repository.py`
- Create: `tests/test_study_plan_repository.py`
- Create: `tests/integration/test_study_plan_repository.py`

**Interfaces:**
- Produces: `StudyPlanRepository.create/get/list/update/add_source/remove_source/save_syllabus/approve_syllabus`
- Consumes: Task 2 contracts

- [ ] **Step 1: Write repository RED tests with a fake query boundary**

```python
@pytest.mark.asyncio
async def test_approval_uses_expected_plan_and_syllabus_versions(monkeypatch):
    calls = []

    async def query(sql, params):
        calls.append((sql, params))
        return [
            {
                **PLAN_RECORD,
                "state": "approved",
                "active_syllabus_version": 1,
                "revision": 3,
            }
        ]

    monkeypatch.setattr(plan_repository, "repo_query", query)
    result = await StudyPlanRepository().approve_syllabus(
        "study_plan:one", syllabus_version=1, expected_revision=2
    )
    assert "revision = $expected_revision" in calls[0][0]
    assert result.state == "approved"
```

Test list pagination caps, record projection, ownership-safe missing records, unique source links, immutable syllabus versions, and no source deletion.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_plan_repository.py`

Expected: import failure because the repository is absent.

- [ ] **Step 3: Add schemafull tables and repository**

Migration 41 defines `study_plan`, `study_plan_source`, `study_syllabus`, `study_unit`, `study_plan_artifact`, and `study_plan_card`, with indexes on plan state, updated time, plan/source uniqueness, plan/syllabus version uniqueness, plan/unit order, and plan/card uniqueness. Store linked source IDs as bounded strings so source authority stays with the established source store.

```python
class StudyPlanRepositoryError(RuntimeError):
    pass


class StudyPlanRepository:
    async def approve_syllabus(
        self, plan_id: str, *, syllabus_version: int, expected_revision: int
    ) -> StudyPlan:
        rows = await repo_query(
            "BEGIN TRANSACTION; UPDATE $syllabus SET approved_at = time::now() WHERE plan_id = $plan_id AND version = $version; UPDATE $plan MERGE $plan_patch WHERE revision = $expected_revision RETURN AFTER; COMMIT TRANSACTION;",
            {
                "syllabus": ...,
                "plan": ensure_record_id(plan_id),
                "plan_id": ensure_record_id(plan_id),
                "version": syllabus_version,
                "expected_revision": expected_revision,
                "plan_patch": {
                    "state": "approved",
                    "active_syllabus_version": syllabus_version,
                    "revision": expected_revision + 1,
                },
            },
        )
        return _plan_from_record(_one_record(rows))
```

- [ ] **Step 4: Run unit and real-Surreal tests**

Run: `uv run pytest -q tests/test_study_plan_repository.py`

Then, with the repository's disposable Surreal test fixture: `SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_plan_repository.py -m integration_surreal`

Expected: unit tests and real-database create/list/version/approve/link tests pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/database/migrations/41.surrealql deeper_notebook/database/migrations/41_down.surrealql deeper_notebook/study/plan_repository.py tests/test_study_plan_repository.py tests/integration/test_study_plan_repository.py
git commit -m "feat(study): persist plans and syllabus versions"
```

### Task 4: Add strict Study Plan API contracts and CRUD

**Files:**
- Create: `api/schemas/study_plans.py`
- Create: `api/routers/study_plans.py`
- Modify: `api/main.py`
- Create: `tests/test_study_plans_api.py`
- Modify: `tests/test_product_identity.py` only if the router insertion shifts an allowlisted identity anchor; update only exact affected anchors/digests.

**Interfaces:**
- Produces: `POST/GET/PATCH /api/study/plans`, source-link, syllabus read/update/approve endpoints
- Consumes: `StudyPlanRepository`

- [ ] **Step 1: Write API RED tests**

```python
def test_create_plan_forbids_unknown_fields(client, repository):
    response = client.post(
        "/api/study/plans",
        json={"title": "Physics", "goal": "Learn mechanics", "unexpected": True},
    )
    assert response.status_code == 422


def test_approve_syllabus_requires_exact_revision(client, repository):
    response = client.post(
        "/api/study/plans/study_plan%3Aone/syllabus:approve",
        json={"syllabus_version": 1, "expected_revision": 7},
    )
    assert response.status_code == 409
```

Cover create/list/get/patch, pagination, 404 non-disclosure, 409 stale revision, 409 illegal lifecycle, feature-off 404, and safe 503 repository failures.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_plans_api.py`

Expected: 404 or import failure for absent routes.

- [ ] **Step 3: Implement schemas and router**

```python
router = APIRouter(prefix="/study/plans", tags=["study-plans"])


@router.post("", response_model=StudyPlanResponse, status_code=201)
async def create_study_plan(payload: CreateStudyPlanRequest) -> StudyPlanResponse:
    _require_study_workbench()
    try:
        return StudyPlanResponse.from_plan(
            await _repository().create(payload.to_plan())
        )
    except StudyPlanRepositoryError:
        raise HTTPException(
            status_code=503, detail="Study plans are unavailable"
        ) from None
```

Register `study_plans.router` under `/api` without moving the existing `study.router` registration.

- [ ] **Step 4: Run GREEN, OpenAPI, Ruff, and identity gates**

Run: `uv run pytest -q tests/test_study_plans_api.py tests/test_study_scheduler.py && uv run ruff check api/schemas/study_plans.py api/routers/study_plans.py api/main.py tests/test_study_plans_api.py && uv run python scripts/rebrand_audit.py --check`

Expected: new API and existing card API tests pass; audit has zero unexpected/stale entries.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/study_plans.py api/routers/study_plans.py api/main.py tests/test_study_plans_api.py scripts/rebrand-allowlist.json scripts/rebrand_audit.py tests/test_product_identity.py
git commit -m "feat(study): expose additive plan APIs"
```

### Task 5: Link sources and report readiness without duplicating ingestion

**Files:**
- Create: `deeper_notebook/study/source_service.py`
- Modify: `api/routers/study_plans.py`
- Modify: `api/schemas/study_plans.py`
- Create: `tests/test_study_plan_sources.py`
- Create: `frontend/src/components/study/StudySourcePicker.tsx`
- Create: `frontend/src/components/study/StudySourcePicker.test.tsx`

**Interfaces:**
- Produces: `StudySourceService.readiness(plan) -> StudySourceReadiness`
- Reuses: `Source.get`, existing `AddSourceDialog`, current source status fields

- [ ] **Step 1: Write failing readiness and UI composition tests**

```python
@pytest.mark.asyncio
async def test_readiness_marks_missing_text_without_reading_or_copying_source(
    monkeypatch,
):
    monkeypatch.setattr(
        source_service.Source,
        "get",
        AsyncMock(
            return_value=SimpleNamespace(
                id="source:one", title="Lecture", full_text="", command="command:one"
            )
        ),
    )
    receipt = await StudySourceService().readiness([LINK])
    assert receipt.ready is False
    assert receipt.items[0].reason == "processing"
```

```tsx
it('opens the existing source dialog instead of implementing a second uploader', () => {
  render(<StudySourcePicker links={[]} onOpenUpload={openUpload} />)
  fireEvent.click(screen.getByRole('button', { name: 'Upload PDF or video' }))
  expect(openUpload).toHaveBeenCalledOnce()
})
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_plan_sources.py && cd frontend && npx vitest run src/components/study/StudySourcePicker.test.tsx`

Expected: missing service/component failures.

- [ ] **Step 3: Implement source-link verification and readiness projection**

Validate source existence before linking; de-duplicate links; expose only source ID, title, kind, readiness, command ID, fingerprint status, and bounded reason code. Never return file paths or source bodies. The picker queries existing sources and calls the existing upload dialog; after source creation it links the returned source ID to the draft plan.

- [ ] **Step 4: Run GREEN and adjoining source tests**

Run: `uv run pytest -q tests/test_study_plan_sources.py tests/test_source_processing_progress.py tests/test_source_upload_cap.py && cd frontend && npx vitest run src/components/study/StudySourcePicker.test.tsx src/lib/hooks/use-sources.test.tsx && npx eslint src/components/study/StudySourcePicker.tsx && npx tsc --noEmit`

Expected: all selected tests and static checks pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/source_service.py api/routers/study_plans.py api/schemas/study_plans.py tests/test_study_plan_sources.py frontend/src/components/study/StudySourcePicker.tsx frontend/src/components/study/StudySourcePicker.test.tsx
git commit -m "feat(study): link existing learning sources"
```

### Task 6: Generate, edit, version, and approve syllabi

**Files:**
- Create: `deeper_notebook/study/syllabus_service.py`
- Modify: `api/routers/study_plans.py`
- Modify: `api/schemas/study_plans.py`
- Create: `tests/test_study_syllabus_service.py`
- Modify: `tests/test_study_plans_api.py`

**Interfaces:**
- Produces: `StudySyllabusService.propose(plan_id, expected_revision)`, `source_manifest`, `detect_drift`
- Reuses: `generate_structured_document`, `artifact_context`, local role routing

- [ ] **Step 1: Write RED tests for structured generation and approval gates**

```python
@pytest.mark.asyncio
async def test_proposal_is_typed_and_does_not_approve_or_generate_artifacts(fake_model):
    service = StudySyllabusService(repository=repo, model_resolver=lambda _: fake_model)
    syllabus = await service.propose("study_plan:one", expected_revision=2)
    assert syllabus.version == 1
    assert syllabus.approved_at is None
    assert repo.saved_artifacts == []


@pytest.mark.asyncio
async def test_approval_rejects_source_manifest_drift():
    with pytest.raises(StudySyllabusConflict, match="sources_changed"):
        await service.approve("study_plan:one", syllabus_version=1, expected_revision=3)
```

Cover source-not-ready, no evidence, bounded prompt context, one repair maximum, duplicate prerequisites, cyclic prerequisites, model timeout, and source drift.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_syllabus_service.py`

Expected: missing service failure.

- [ ] **Step 3: Implement a Study-specific structured schema and service**

```python
class StudySyllabusDocument(ArtifactDocumentBase):
    artifact_type: Literal["study_syllabus"] = "study_syllabus"
    title: str = Field(min_length=1, max_length=200)
    units: list[StudySyllabusUnitDocument] = Field(min_length=1, max_length=64)
    knowledge_gaps: list[str] = Field(default_factory=list, max_length=32)


async def propose(self, plan_id: str, *, expected_revision: int) -> StudySyllabus:
    plan, links, sources = await self._load_ready_plan_sources(
        plan_id, expected_revision
    )
    context_text, citations = artifact_context(sources)
    result = await generate_structured_document(
        model=await self._resolve_model(plan),
        schema=StudySyllabusDocument,
        messages=self._messages(plan, context_text),
        timeout_seconds=120,
    )
    syllabus = self._to_syllabus(plan, result.document, citations)
    return await self.repository.save_syllabus(
        syllabus, expected_revision=expected_revision
    )
```

Use a deterministic SHA-256 over sorted source IDs plus content fingerprints as the approval manifest. Validate the prerequisite graph is acyclic before persistence.

- [ ] **Step 4: Run GREEN and adjoining structured-generation tests**

Run: `uv run pytest -q tests/test_study_syllabus_service.py tests/test_studio_structured_generation.py tests/test_study_plans_api.py && uv run ruff check deeper_notebook/study/syllabus_service.py api/routers/study_plans.py api/schemas/study_plans.py`

Expected: syllabus and existing structured-generation tests pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/syllabus_service.py api/routers/study_plans.py api/schemas/study_plans.py tests/test_study_syllabus_service.py tests/test_study_plans_api.py
git commit -m "feat(study): gate generation on approved syllabi"
```

### Task 7: Frontend plan client, Study Home, and draft wizard

**Files:**
- Create: `frontend/src/lib/types/study-plans.ts`
- Create: `frontend/src/lib/api/study-plans.ts`
- Create: `frontend/src/lib/api/study-plans.test.ts`
- Create: `frontend/src/lib/hooks/use-study-plans.ts`
- Modify: `frontend/src/lib/api/query-client.ts`
- Create: `frontend/src/components/study/StudyWorkbench.tsx`
- Create: `frontend/src/components/study/StudyWorkbench.test.tsx`
- Create: `frontend/src/components/study/StudyPlanWizard.tsx`
- Create: `frontend/src/components/study/StudyPlanWizard.test.tsx`
- Modify: `frontend/src/app/(dashboard)/study/page.tsx`

**Interfaces:**
- Produces: `studyPlansApi`, `useStudyPlans`, `useCreateStudyPlan`, `useUpdateStudyPlan`
- Consumes: Tasks 4-6 API shapes

- [ ] **Step 1: Write decoder, home, and wizard RED tests**

```ts
it('fails closed on a plan response with extra secret fields', async () => {
  mockGet.mockResolvedValue({ data: { ...PLAN, absolute_path: '/private/source.pdf' } })
  await expect(studyPlansApi.get('study_plan:one')).rejects.toThrow('Invalid Study Plan response')
})
```

```tsx
it('saves a resumable draft before source selection', async () => {
  render(<StudyPlanWizard open onOpenChange={vi.fn()} />)
  await user.type(screen.getByLabelText('Learning goal'), 'Understand mechanics')
  await user.click(screen.getByRole('button', { name: 'Save and continue' }))
  expect(createPlan).toHaveBeenCalledWith(expect.objectContaining({ goal: 'Understand mechanics' }))
})
```

- [ ] **Step 2: Run RED**

Run: `cd frontend && npx vitest run src/lib/api/study-plans.test.ts src/components/study/StudyWorkbench.test.tsx src/components/study/StudyPlanWizard.test.tsx`

Expected: missing modules/components.

- [ ] **Step 3: Implement exact decoders, query ownership, Home, and wizard**

Define `QUERY_KEYS.studyPlans`, `studyPlan(id)`, `studyPlanSources(id)`, and `studySyllabus(id)`. The Home composes existing `StudyDashboard`/`StudySession` with active plans and a create/import action. The wizard stores only a created draft ID in component state; server persistence is authoritative.

- [ ] **Step 4: Run GREEN, lint, and TypeScript**

Run: `cd frontend && npx vitest run src/lib/api/study-plans.test.ts src/components/study/StudyWorkbench.test.tsx src/components/study/StudyPlanWizard.test.tsx 'src/app/(dashboard)/study/page.test.tsx' && npx eslint src/lib/types/study-plans.ts src/lib/api/study-plans.ts src/lib/hooks/use-study-plans.ts src/components/study/StudyWorkbench.tsx src/components/study/StudyPlanWizard.tsx && npx tsc --noEmit`

Expected: tests, ESLint, and TypeScript pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types/study-plans.ts frontend/src/lib/api/study-plans.ts frontend/src/lib/api/study-plans.test.ts frontend/src/lib/hooks/use-study-plans.ts frontend/src/lib/api/query-client.ts frontend/src/components/study/StudyWorkbench.tsx frontend/src/components/study/StudyWorkbench.test.tsx frontend/src/components/study/StudyPlanWizard.tsx frontend/src/components/study/StudyPlanWizard.test.tsx 'frontend/src/app/(dashboard)/study/page.tsx'
git commit -m "feat(study): add plan home and creation wizard"
```

### Task 8: Plan workspace and syllabus approval UI

**Files:**
- Create: `frontend/src/app/(dashboard)/study/plans/[planId]/page.tsx`
- Create: `frontend/src/app/(dashboard)/study/plans/[planId]/page.test.tsx`
- Create: `frontend/src/components/study/StudyPlanWorkspace.tsx`
- Create: `frontend/src/components/study/StudyPlanWorkspace.test.tsx`
- Create: `frontend/src/components/study/SyllabusEditor.tsx`
- Create: `frontend/src/components/study/SyllabusEditor.test.tsx`
- Modify: `frontend/src/lib/hooks/use-study-plans.ts`

**Interfaces:**
- Produces: tabs `overview|syllabus|learn|guide|map|practice|flashcards|sources|progress`
- Produces: version-aware edit/propose/approve mutations

- [ ] **Step 1: Write RED tests for approval, reordering, drift, and keyboard behavior**

```tsx
it('publishes only the displayed syllabus version after explicit approval', async () => {
  render(<SyllabusEditor plan={PLAN} syllabus={SYLLABUS} />)
  await user.click(screen.getByRole('button', { name: 'Approve syllabus version 2' }))
  expect(approve).toHaveBeenCalledWith({ planId: PLAN.id, syllabusVersion: 2, expectedRevision: PLAN.revision })
})
```

Test keyboard move-up/move-down controls, visible source gaps, no approve while processing, 409 refresh/recovery, and focus return after dialogs.

- [ ] **Step 2: Run RED**

Run: `cd frontend && npx vitest run 'src/app/(dashboard)/study/plans/[planId]/page.test.tsx' src/components/study/StudyPlanWorkspace.test.tsx src/components/study/SyllabusEditor.test.tsx`

Expected: missing route/components.

- [ ] **Step 3: Implement route, tabs, and versioned editor**

Use one semantic `main` through the existing route frame, URL-addressable tab state, explicit buttons for keyboard reordering, an approval confirmation containing version and source coverage, and safe recovery on stale revisions.

- [ ] **Step 4: Run GREEN and static checks**

Run: `cd frontend && npx vitest run 'src/app/(dashboard)/study/plans/[planId]/page.test.tsx' src/components/study/StudyPlanWorkspace.test.tsx src/components/study/SyllabusEditor.test.tsx && npx eslint 'src/app/(dashboard)/study/plans/[planId]/page.tsx' src/components/study/StudyPlanWorkspace.tsx src/components/study/SyllabusEditor.tsx && npx tsc --noEmit`

Expected: tests and static checks pass.

- [ ] **Step 5: Commit**

```bash
git add 'frontend/src/app/(dashboard)/study/plans/[planId]/page.tsx' 'frontend/src/app/(dashboard)/study/plans/[planId]/page.test.tsx' frontend/src/components/study/StudyPlanWorkspace.tsx frontend/src/components/study/StudyPlanWorkspace.test.tsx frontend/src/components/study/SyllabusEditor.tsx frontend/src/components/study/SyllabusEditor.test.tsx frontend/src/lib/hooks/use-study-plans.ts
git commit -m "feat(study): add approved syllabus workspace"
```

---

## Phase B — Learning artifacts and AI Study Team

### Task 9: Generate unit-scoped learning artifacts through Evidence Studio

**Files:**
- Create: `deeper_notebook/study/artifact_service.py`
- Modify: `deeper_notebook/studio/generation/prompts.py`
- Modify: `api/routers/study_plans.py`
- Modify: `api/schemas/study_plans.py`
- Create: `tests/test_study_artifact_service.py`
- Modify: `tests/test_studio_generation_contract.py`

**Interfaces:**
- Produces: `StudyArtifactService.generate_unit(plan_id, unit_id, artifact_types, expected_revision)`
- Reuses: `StudioArtifact`, `ArtifactGenerationRequest`, existing evidence evaluation

- [ ] **Step 1: Write RED tests for approval and unit/source binding**

```python
@pytest.mark.asyncio
async def test_unit_generation_requires_approved_matching_manifest():
    with pytest.raises(StudyArtifactConflict, match="syllabus_not_approved"):
        await service.generate_unit(
            "study_plan:one", "foundations", ["study_guide"], expected_revision=2
        )
```

Test supported type allowlist (`study_guide`, `course_pack`, `flashcards`, `quiz`, `mind_map`), idempotent links, evidence failures, cancellation, and no duplicate artifacts on retry.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_artifact_service.py`

Expected: missing service failure.

- [ ] **Step 3: Implement the adapter, not a second generator**

Create provisional `StudioArtifact` records bound to the plan's source IDs and unit prompt; invoke the existing generation service; link only completed artifacts through `study_plan_artifact`; reuse existing structured payloads and evaluation sidecars.

- [ ] **Step 4: Run GREEN and Studio regressions**

Run: `uv run pytest -q tests/test_study_artifact_service.py tests/test_studio_generation_contract.py tests/test_evidence_studio_artifact_api.py && uv run ruff check deeper_notebook/study/artifact_service.py deeper_notebook/studio/generation/prompts.py`

Expected: Study and existing Studio tests pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/artifact_service.py deeper_notebook/studio/generation/prompts.py api/routers/study_plans.py api/schemas/study_plans.py tests/test_study_artifact_service.py tests/test_studio_generation_contract.py
git commit -m "feat(study): generate unit learning artifacts"
```

### Task 10: Assistant, handoff, and plan-memory contracts

**Files:**
- Create: `deeper_notebook/study/assistants.py`
- Create: `deeper_notebook/study/assistant_repository.py`
- Create: `deeper_notebook/database/migrations/42.surrealql`
- Create: `deeper_notebook/database/migrations/42_down.surrealql`
- Create: `tests/test_study_assistant_contracts.py`
- Create: `tests/test_study_assistant_repository.py`

**Interfaces:**
- Produces: `StudyAssistantRole`, `StudyAuthority`, `StudyAssistantInvocation`, `StudyAssistantResponse`, `StudyAssistantHandoff`, `StudyPlanMemory`
- Produces: repository session/handoff/memory methods

- [ ] **Step 1: Write strict bounded RED tests**

```python
def test_create_authority_cannot_enable_network_or_mutate_syllabus():
    with pytest.raises(ValidationError):
        StudyAssistantInvocation(
            role="research_scout",
            authority="create",
            prompt="Research",
            network_allowed=True,
            approved_network_scope=None,
        )
```

Cover all twelve roles, four authority modes, 16 KiB prompt cap, 32 citations, 20 proposed actions, 50 handoffs per query page, plan-local memory provenance, and confirmation required for inferred memory.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_assistant_contracts.py tests/test_study_assistant_repository.py`

Expected: missing modules.

- [ ] **Step 3: Implement contracts, additive tables, and projection-safe repository**

Migration 42 defines `study_assistant_session`, `study_assistant_handoff`, `study_plan_memory`, and `study_progress` with plan/time indexes and bounded schema fields. Repository deserialization projects only model fields and never exposes prompt-provider raw payloads.

- [ ] **Step 4: Run GREEN and real-Surreal persistence proof**

Run: `uv run pytest -q tests/test_study_assistant_contracts.py tests/test_study_assistant_repository.py && SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_plan_repository.py -m integration_surreal && uv run ruff check deeper_notebook/study/assistants.py deeper_notebook/study/assistant_repository.py`

Expected: contract/repository and integration tests pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/assistants.py deeper_notebook/study/assistant_repository.py deeper_notebook/database/migrations/42.surrealql deeper_notebook/database/migrations/42_down.surrealql tests/test_study_assistant_contracts.py tests/test_study_assistant_repository.py tests/integration/test_study_plan_repository.py
git commit -m "feat(study): persist tutor handoffs and memory"
```

### Task 11: Bounded assistant orchestration and APIs

**Files:**
- Create: `deeper_notebook/study/assistant_service.py`
- Create: `api/schemas/study_assistants.py`
- Create: `api/routers/study_assistants.py`
- Modify: `api/main.py`
- Create: `tests/test_study_assistant_service.py`
- Create: `tests/test_study_assistants_api.py`

**Interfaces:**
- Produces: `invoke(plan_id, role, invocation) -> StudyAssistantResponse`
- Produces: `POST /api/study/plans/{plan_id}/assistants/{role}:invoke`

- [ ] **Step 1: Write RED tests for routing and authority**

```python
@pytest.mark.asyncio
async def test_source_guide_retrieves_only_selected_plan_sources():
    response = await service.invoke("study_plan:one", "source_guide", INVOCATION)
    assert set(response.retrieval_receipt.source_ids) == {"source:allowed"}
    assert "source:other" not in model.last_prompt


@pytest.mark.asyncio
async def test_research_scout_fails_closed_without_explicit_web_scope():
    with pytest.raises(StudyAssistantPolicyError, match="network_not_approved"):
        await service.invoke("study_plan:one", "research_scout", INVOCATION)
```

Cover one foreground invocation, bounded handoffs, timeout, cancellation, local-model route, explicit cloud route, web policy, proposal-only plan changes, citation enforcement, and safe errors.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_assistant_service.py tests/test_study_assistants_api.py`

Expected: missing service/router.

- [ ] **Step 3: Implement role registry and assistant service**

```python
ROLE_POLICIES: dict[StudyAssistantRole, AssistantPolicy] = {
    "study_director": AssistantPolicy(
        model_role="chat", tools=("read_plan", "read_progress")
    ),
    "source_guide": AssistantPolicy(
        model_role="source_synthesis", tools=("retrieve_plan_sources",)
    ),
    "practice_coach": AssistantPolicy(
        model_role="study_fast", tools=("read_plan", "read_progress")
    ),
    "research_scout": AssistantPolicy(
        model_role="research_synthesis", tools=("approved_web_research",)
    ),
}
```

Define all twelve roles explicitly. Build compact context from the approved syllabus, current unit, selected sources, progress, due reviews, confirmed memory, and at most 20 recent handoffs. Persist structured response/handoff receipts, not model chain-of-thought.

- [ ] **Step 4: Run GREEN, chat/MCP regressions, Ruff**

Run: `uv run pytest -q tests/test_study_assistant_service.py tests/test_study_assistants_api.py tests/test_source_chat_context_caps.py tests/test_mcp_security_bounds.py && uv run ruff check deeper_notebook/study/assistant_service.py api/schemas/study_assistants.py api/routers/study_assistants.py api/main.py`

Expected: assistant and adjoining security tests pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/assistant_service.py api/schemas/study_assistants.py api/routers/study_assistants.py api/main.py tests/test_study_assistant_service.py tests/test_study_assistants_api.py
git commit -m "feat(study): add bounded AI tutor team"
```

### Task 12: Tutor dock and learning-session UI

**Files:**
- Create: `frontend/src/lib/types/study-assistants.ts`
- Create: `frontend/src/lib/api/study-assistants.ts`
- Create: `frontend/src/lib/api/study-assistants.test.ts`
- Create: `frontend/src/lib/hooks/use-study-assistants.ts`
- Create: `frontend/src/components/study/TutorDock.tsx`
- Create: `frontend/src/components/study/TutorDock.test.tsx`
- Create: `frontend/src/components/study/StudyLearningSession.tsx`
- Create: `frontend/src/components/study/StudyLearningSession.test.tsx`
- Modify: `frontend/src/components/study/StudyPlanWorkspace.tsx`

**Interfaces:**
- Produces: one foreground tutor, role/mode selector, citations, proposed actions, cancel/retry
- Consumes: Task 11 API

- [ ] **Step 1: Write decoder and interaction RED tests**

```tsx
it('requires approval before a tutor proposal changes the syllabus', async () => {
  render(<TutorDock planId="study_plan:one" />)
  await user.click(screen.getByRole('button', { name: 'Apply proposed prerequisite unit' }))
  expect(screen.getByRole('dialog', { name: 'Review tutor proposal' })).toBeVisible()
  expect(updateSyllabus).not.toHaveBeenCalled()
})
```

Test role/mode keyboard selection, source-only badge, web permission request, citation navigation, timeout/retry, one active invocation, cancellation, compact drawer, and focus return.

- [ ] **Step 2: Run RED**

Run: `cd frontend && npx vitest run src/lib/api/study-assistants.test.ts src/components/study/TutorDock.test.tsx src/components/study/StudyLearningSession.test.tsx`

Expected: missing modules/components.

- [ ] **Step 3: Implement exact client/hook and one-tutor UI**

Render specialist assistants through one dock, not twelve simultaneous chats. Modes map to explicit request fields. Proposed actions render as inert cards until the user opens a review dialog and invokes the appropriate plan mutation.

- [ ] **Step 4: Run GREEN, lint, and TypeScript**

Run: `cd frontend && npx vitest run src/lib/api/study-assistants.test.ts src/components/study/TutorDock.test.tsx src/components/study/StudyLearningSession.test.tsx src/components/study/StudyPlanWorkspace.test.tsx && npx eslint src/lib/types/study-assistants.ts src/lib/api/study-assistants.ts src/lib/hooks/use-study-assistants.ts src/components/study/TutorDock.tsx src/components/study/StudyLearningSession.tsx && npx tsc --noEmit`

Expected: tests and static checks pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types/study-assistants.ts frontend/src/lib/api/study-assistants.ts frontend/src/lib/api/study-assistants.test.ts frontend/src/lib/hooks/use-study-assistants.ts frontend/src/components/study/TutorDock.tsx frontend/src/components/study/TutorDock.test.tsx frontend/src/components/study/StudyLearningSession.tsx frontend/src/components/study/StudyLearningSession.test.tsx frontend/src/components/study/StudyPlanWorkspace.tsx
git commit -m "feat(study): add source-aware tutor dock"
```

### Task 13: Optional local voice tutor

**Files:**
- Create: `deeper_notebook/study/voice_service.py`
- Create: `api/routers/study_voice.py`
- Modify: `api/schemas/study_assistants.py`
- Modify: `api/main.py`
- Create: `tests/test_study_voice_tutor.py`
- Create: `frontend/src/lib/api/study-voice.ts`
- Create: `frontend/src/components/study/StudyVoiceTutor.tsx`
- Create: `frontend/src/components/study/StudyVoiceTutor.test.tsx`
- Modify: `frontend/src/components/study/StudyLearningSession.tsx`

**Interfaces:**
- Produces: `POST /api/study/plans/{plan_id}/voice:transcribe`
- Produces: `POST /api/study/plans/{plan_id}/voice:synthesize`
- Reuses: `model_manager.get_speech_to_text()` and `get_text_to_speech()`

- [ ] **Step 1: Write RED capability, upload-bound, and UI tests**

```python
@pytest.mark.asyncio
async def test_voice_tutor_fails_closed_when_local_speech_model_is_absent(
    client, monkeypatch
):
    monkeypatch.setattr(
        model_manager, "get_speech_to_text", AsyncMock(return_value=None)
    )
    response = client.post(
        "/api/study/plans/study_plan%3Aone/voice:transcribe",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "local_speech_unavailable"
```

```tsx
it('shows spoken tutoring only when the local capability receipt is ready', () => {
  render(<StudyVoiceTutor planId="study_plan:one" capability={{ stt: 'unavailable', tts: 'ready' }} />)
  expect(screen.getByRole('button', { name: 'Record question' })).toBeDisabled()
  expect(screen.getByText('Local speech recognition is unavailable.')).toBeVisible()
})
```

Cover MIME allowlist, upload byte cap, duration cap where metadata is available,
task-owned temporary cleanup, no cloud fallback, empty transcription, bounded
TTS text, audio response content type, cancellation, and microphone denial.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_voice_tutor.py && cd frontend && npx vitest run src/components/study/StudyVoiceTutor.test.tsx`

Expected: missing service/router/component failures.

- [ ] **Step 3: Implement the local-only speech adapter and optional UI**

Write uploaded audio into a task-owned temporary file with a 25 MiB streaming
cap, call the configured local STT model, delete the temporary file in `finally`,
and return at most 16 KiB of transcript. Synthesis accepts at most 8 KiB of
assistant text, calls the configured local TTS model, and streams the bounded
audio result. Do not fall back to a network provider even when the plan permits
cloud language models. The UI uses `MediaRecorder` only after an explicit user
gesture and keeps the text tutor fully usable when speech is unavailable.

- [ ] **Step 4: Run GREEN and speech-model regressions**

Run: `uv run pytest -q tests/test_study_voice_tutor.py tests/test_capture_routing.py tests/test_models_api.py -k 'speech or voice or study or transcri' && uv run ruff check deeper_notebook/study/voice_service.py api/routers/study_voice.py api/schemas/study_assistants.py`

Run: `cd frontend && npx vitest run src/components/study/StudyVoiceTutor.test.tsx src/components/study/StudyLearningSession.test.tsx && npx eslint src/lib/api/study-voice.ts src/components/study/StudyVoiceTutor.tsx && npx tsc --noEmit`

Expected: voice, adjoining speech, and frontend gates pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/voice_service.py api/routers/study_voice.py api/schemas/study_assistants.py api/main.py tests/test_study_voice_tutor.py frontend/src/lib/api/study-voice.ts frontend/src/components/study/StudyVoiceTutor.tsx frontend/src/components/study/StudyVoiceTutor.test.tsx frontend/src/components/study/StudyLearningSession.tsx
git commit -m "feat(study): add optional local voice tutoring"
```

---

## Phase C — Mastery, adaptation, and Anki packages

### Task 14: Append-only progress and mastery projections

**Files:**
- Create: `deeper_notebook/study/progress.py`
- Create: `deeper_notebook/study/progress_repository.py`
- Create: `tests/test_study_progress.py`
- Create: `tests/test_study_progress_repository.py`
- Modify: `api/routers/study_plans.py`
- Modify: `api/schemas/study_plans.py`
- Create: `frontend/src/components/study/StudyProgressPanel.tsx`
- Create: `frontend/src/components/study/StudyProgressPanel.test.tsx`

**Interfaces:**
- Produces: `StudyProgressReceipt`, `StudyMasteryProjection`, `StudyAdaptationProposal`
- Consumes: quiz outcomes and existing Study review receipts

- [ ] **Step 1: Write RED tests for deterministic projection and proposal-only adaptation**

```python
def test_mastery_projection_is_deterministic_and_does_not_rewrite_plan():
    projection = project_mastery(RECEIPTS, REVIEW_RECEIPTS, now=NOW)
    assert projection.concepts[0].status == "needs_review"
    assert projection.proposals[0].action == "prerequisite_detour"
    assert plan_repository.calls == []
```

Test de-duplication by request ID, bounded receipt pages, lapse effects, quiz weighting, no permanent inferred memory, and schedule proposal visibility.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_progress.py tests/test_study_progress_repository.py && cd frontend && npx vitest run src/components/study/StudyProgressPanel.test.tsx`

Expected: missing modules/component.

- [ ] **Step 3: Implement append-only receipts, aggregate query, and panel**

Use pure projection functions with explicit `now`; append progress with unique request IDs; query current Study cards/reviews through repository methods rather than copying FSRS state. Render proposals with Accept/Dismiss actions; acceptance calls an existing plan/syllabus mutation and creates a decision receipt.

- [ ] **Step 4: Run GREEN and existing FSRS regressions**

Run: `uv run pytest -q tests/test_study_progress.py tests/test_study_progress_repository.py tests/test_study_scheduler.py && cd frontend && npx vitest run src/components/study/StudyProgressPanel.test.tsx src/components/study/StudySession.test.tsx && npx tsc --noEmit`

Expected: mastery and existing review tests pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/progress.py deeper_notebook/study/progress_repository.py tests/test_study_progress.py tests/test_study_progress_repository.py api/routers/study_plans.py api/schemas/study_plans.py frontend/src/components/study/StudyProgressPanel.tsx frontend/src/components/study/StudyProgressPanel.test.tsx
git commit -m "feat(study): project mastery and adaptations"
```

### Task 15: Safe native Anki package inspection and import

**Files:**
- Create: `deeper_notebook/study/anki_package.py`
- Create: `deeper_notebook/study/anki_repository.py`
- Create: `deeper_notebook/database/migrations/43.surrealql`
- Create: `deeper_notebook/database/migrations/43_down.surrealql`
- Create: `tests/test_study_anki_import.py`
- Create: `tests/fixtures/anki/build_fixtures.py`

**Interfaces:**
- Produces: `inspect_anki_package(path) -> AnkiPackageInspection`
- Produces: `import_anki_package(plan_id, path, options, request_id) -> AnkiCompatibilityReceipt`
- Supports: `collection.anki2` and `collection.anki21`; rejects unknown collection variants with a receipt

- [ ] **Step 1: Generate test-owned packages and write RED security tests**

```python
def test_import_rejects_path_traversal_before_sqlite_open(tmp_path):
    package = malicious_zip(
        tmp_path, {"../outside": b"x", "collection.anki2": b"not sqlite"}
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_member_path"):
        inspect_anki_package(package)


def test_import_is_atomic_when_one_note_is_invalid(valid_package, repository):
    with pytest.raises(AnkiPackageRejected):
        import_anki_package(
            "study_plan:one", valid_package, options=OPTIONS, request_id="request-1"
        )
    assert repository.published_cards == []
```

Cover member count, 4 KiB names, compressed/expanded budgets, duplicate members, symlinks, missing/invalid media JSON, SQLite header, query-only URI mode, table/column allowlist, record/text/media caps, unsafe filenames, hostile HTML/script, invalid scheduling, basic/reverse/cloze translation, tags/decks/media, and replay idempotency. Include a regression for Anki's published untrusted-package local-file class by proving external paths cannot be read.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_anki_import.py`

Expected: missing adapter failure.

- [ ] **Step 3: Implement validation before materialization and staged publication**

Use `zipfile.ZipFile` metadata checks before reading members. Copy only the validated collection member into a task-owned temporary directory, open with SQLite URI `mode=ro&immutable=1`, set a progress handler, query only required columns from allowlisted tables, sanitize fields/templates/media references, translate into provisional native card versions, then publish links/cards and the compatibility receipt in one repository transaction. Never execute templates or use imported add-on code.

- [ ] **Step 4: Run GREEN, security scan, and repository tests**

Run: `uv run pytest -q tests/test_study_anki_import.py tests/test_study_scheduler.py tests/test_study_plan_repository.py && uv run ruff check deeper_notebook/study/anki_package.py deeper_notebook/study/anki_repository.py tests/test_study_anki_import.py && uvx bandit -q -ll deeper_notebook/study/anki_package.py`

Expected: tests, Ruff, and medium/high Bandit scan pass.

- [ ] **Step 5: Commit**

```bash
git add deeper_notebook/study/anki_package.py deeper_notebook/study/anki_repository.py deeper_notebook/database/migrations/43.surrealql deeper_notebook/database/migrations/43_down.surrealql tests/test_study_anki_import.py tests/fixtures/anki/build_fixtures.py
git commit -m "feat(study): safely import Anki packages"
```

### Task 16: Deterministic Anki export and HTTP/UI workflows

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `api/schemas/study_anki.py`
- Create: `api/routers/study_anki.py`
- Modify: `api/main.py`
- Create: `tests/test_study_anki_export.py`
- Create: `tests/test_study_anki_api.py`
- Create: `frontend/src/lib/types/study-anki.ts`
- Create: `frontend/src/lib/api/study-anki.ts`
- Create: `frontend/src/lib/hooks/use-study-anki.ts`
- Create: `frontend/src/components/study/AnkiPackagePanel.tsx`
- Create: `frontend/src/components/study/AnkiPackagePanel.test.tsx`

**Interfaces:**
- Adds dependency: `genanki==0.13.1`
- Produces: import upload, job status, and export download endpoints
- Produces: deterministic `AnkiCompatibilityReceipt`

- [ ] **Step 1: Write RED export/API/UI tests**

```python
def test_export_uses_stable_ids_and_round_trips_basic_reverse_and_cloze(tmp_path):
    first = export_anki_package(PLAN_EXPORT, tmp_path / "first.apkg")
    second = export_anki_package(PLAN_EXPORT, tmp_path / "second.apkg")
    assert first.receipt.card_count == second.receipt.card_count == 3
    assert (
        inspect_export(first.path).stable_note_guids
        == inspect_export(second.path).stable_note_guids
    )
```

```tsx
it('shows transformed and skipped items before publishing an import', async () => {
  render(<AnkiPackagePanel planId="study_plan:one" />)
  await uploadPackage('deck.apkg')
  expect(await screen.findByText('2 cards ready, 1 transformed, 1 rejected')).toBeVisible()
  expect(importCards).not.toHaveBeenCalled()
})
```

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_study_anki_export.py tests/test_study_anki_api.py && cd frontend && npx vitest run src/components/study/AnkiPackagePanel.test.tsx`

Expected: missing export/router/component.

- [ ] **Step 3: Add audited export dependency, adapter, routes, and panel**

Pin `genanki==0.13.1`, regenerate `uv.lock`, and record its MIT license in the dependency review. Escape all fields before handing them to `genanki`; use stable IDs derived from Deeper Notebook plan/card IDs; write to a task-owned temporary file; validate the produced archive with the native inspector; atomically move it into the exports root; return only an opaque download ID and compatibility receipt. Import is preview -> explicit publish, not upload -> automatic mutation.

- [ ] **Step 4: Run GREEN, dependency audits, and static checks**

Run the package tests and export the frozen production lock for audit:

```bash
uv lock --check
uv run pytest -q tests/test_study_anki_import.py tests/test_study_anki_export.py tests/test_study_anki_api.py
audit_requirements=$(mktemp /tmp/dn-study-audit.XXXXXX.txt)
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file "$audit_requirements"
uvx pip-audit --strict -r "$audit_requirements"
audit_status=$?
rm -f "$audit_requirements"
test "$audit_status" -eq 1
```

Expected audit result: the only findings are the already documented 25 Pillow
11.3.0 advisories blocked by `podcast-creator -> moviepy -> Pillow<12`;
`genanki` and its dependency closure add zero advisories. Any different package
or finding blocks this task.

Run: `cd frontend && npx vitest run src/components/study/AnkiPackagePanel.test.tsx && npx eslint src/lib/types/study-anki.ts src/lib/api/study-anki.ts src/lib/hooks/use-study-anki.ts src/components/study/AnkiPackagePanel.tsx && npx tsc --noEmit`

Expected: Anki tests and frontend static checks pass; dependency audit introduces no new vulnerability.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock api/schemas/study_anki.py api/routers/study_anki.py api/main.py tests/test_study_anki_export.py tests/test_study_anki_api.py frontend/src/lib/types/study-anki.ts frontend/src/lib/api/study-anki.ts frontend/src/lib/hooks/use-study-anki.ts frontend/src/components/study/AnkiPackagePanel.tsx frontend/src/components/study/AnkiPackagePanel.test.tsx
git commit -m "feat(study): add Anki package portability"
```

---

## Phase D — Product completeness and release acceptance

### Task 17: Navigation, localization, accessibility, and complete browser states

**Files:**
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Modify: `frontend/src/components/common/CommandPalette.tsx`
- Modify: `frontend/src/lib/locales/en-US/index.ts`
- Modify: all 13 non-English `frontend/src/lib/locales/*/index.ts` catalogs with human-reviewed translations
- Modify: `frontend/src/lib/locales/index.test.ts`
- Create: `frontend/e2e/study-workbench.spec.ts`
- Create: `frontend/e2e/fixtures/study-workbench.ts`
- Modify: `frontend/e2e/all-screen-visual-audit.spec.ts`

**Interfaces:**
- Preserves: existing sidebar Study destination
- Adds: translated `navigation.study`, command-palette Study destination, Study browser fixture

- [ ] **Step 1: Write RED locale, navigation, and browser tests**

```tsx
it('offers Study in both sidebar and command navigation', () => {
  expect(getNavigation(t).flatMap(section => section.items).some(item => item.href === '/study')).toBe(true)
  expect(getNavigationItems(t).some(item => item.href === '/study')).toBe(true)
})
```

The Playwright spec covers empty, loading, source-processing, syllabus-proposed, approved, generating, active, degraded-model, offline, error/retry, tutor, progress, Anki preview, import receipt, and flag-off rollback at 320, 768, 1024, and 1440 widths. It asserts one main, visible h1, keyboard flow, focus return, reduced motion, bounded controls, no page/console errors, and zero unexpected external requests.

- [ ] **Step 2: Run RED**

Run: `cd frontend && npx vitest run src/lib/locales/index.test.ts src/components/layout/AppSidebar.test.tsx src/components/common/CommandPalette.test.tsx`

Expected: missing Study locale/command item failures.

- [ ] **Step 3: Localize and implement the hermetic browser fixture/spec**

Replace the hard-coded sidebar name with `t('navigation.study')`; add Study to command navigation with `GraduationCap`; add approved translations for every new Study key; implement exact mocked API response shapes and a request ledger; never use catch-all `{}` responses.

- [ ] **Step 4: Run GREEN browser matrices and static gates**

Run: `cd frontend && npm test -- --run && npm run lint && npx tsc --noEmit && npm run build && npm run test:feature-build-contract`

Run default Study and all-screen specs, then rebuild and run exact rollback:

```bash
cd frontend
npx playwright test e2e/study-workbench.spec.ts e2e/all-screen-visual-audit.spec.ts --project=mocked-browser --workers=1
NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npm run build
NEXT_PUBLIC_DN_STUDY_WORKBENCH=0 NEXT_PUBLIC_DN_LUMINOUS_FOLIO=0 npx playwright test e2e/study-workbench.spec.ts e2e/all-screen-visual-audit.spec.ts --project=mocked-browser --workers=1
```

Expected: unit/static/build gates and both browser modes pass. Restore `frontend/test-results/.last-run.json` byte-for-byte to its HEAD baseline after Playwright.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/AppSidebar.tsx frontend/src/components/common/CommandPalette.tsx frontend/src/lib/locales frontend/e2e/study-workbench.spec.ts frontend/e2e/fixtures/study-workbench.ts frontend/e2e/all-screen-visual-audit.spec.ts
git commit -m "feat(study): complete accessible learning workspace"
```

### Task 18: Integrated source-to-study proof and full regression

**Files:**
- Create: `scripts/verify_study_workbench.py`
- Create: `tests/test_verify_study_workbench.py`
- Create: `docs/verification/2026-08-11-study-workbench.md`
- Modify: `frontend/src/lib/features.ts`
- Modify: `deeper_notebook/feature_flags.py`
- Modify: flag tests from Task 1

**Interfaces:**
- Produces: two-phase isolated verifier receipt
- Changes default: Study Workbench flag from off to on only after all gates pass

- [ ] **Step 1: Write RED verifier tests**

```python
def test_verifier_requires_restart_and_preserves_external_fixture(tmp_path):
    result = run_verifier_fixture(tmp_path)
    assert result.prepare_exit == 5
    assert result.verify_exit == 0
    assert result.source_hash_before == result.source_hash_after
    assert result.external_writes == 0
```

The verifier must create disposable PDF/video fixtures, upload through the real API, wait for processing, create a plan, propose/edit/approve a syllabus, generate one unit, invoke Source Guide and Practice Coach, record progress, create/review cards, export/import an Anki package, restart the real Supervisor/API/Surreal/frontend stack, and verify durable parity.

- [ ] **Step 2: Run RED**

Run: `uv run pytest -q tests/test_verify_study_workbench.py`

Expected: missing verifier failure.

- [ ] **Step 3: Implement the bounded verifier and flip defaults only after proof**

Follow existing verifier safety patterns: unique no-symlink root, task-only ports/database/namespace, synthetic credentials, no user vaults, source hashes before/after, explicit restart PID/nonce, cleanup of exact owned processes/roots, sanitized report. Once the verifier and all matrices pass, change `study_workbench_enabled` and `isStudyWorkbenchEnabled` defaults to true while retaining explicit `0` rollback.

- [ ] **Step 4: Run authoritative release gates**

Backend:

```bash
PYTHONPATH=. uv run pytest tests/ -q --ignore=tests/integration
uv run ruff check .
uv run python scripts/rebrand_audit.py --check
```

Desktop:

```bash
./.build-venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q
```

Frontend:

```bash
cd frontend
npm test -- --run
npm run lint
npx tsc --noEmit
npm run build
npm run test:feature-build-contract
npm run test:e2e:mocked -- --workers=1
```

Real runtime:

```bash
SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_plan_repository.py -m integration_surreal
uv run python scripts/verify_study_workbench.py --proof-phase prepare [task-owned arguments]
uv run python scripts/verify_study_workbench.py --proof-phase verify [same task-owned arguments]
```

Expected: all suites pass; prepare exits 5 by design for restart; verify exits 0; source hashes unchanged; no external writes; task-owned listeners and roots are removed.

- [ ] **Step 5: Commit evidence and default-on boundary**

```bash
git add scripts/verify_study_workbench.py tests/test_verify_study_workbench.py docs/verification/2026-08-11-study-workbench.md frontend/src/lib/features.ts deeper_notebook/feature_flags.py frontend/src/lib/features.test.ts tests/test_evidence_studio_foundation.py
git commit -m "docs(study): close workbench release proof"
```

### Task 19: Native package acceptance and final independent review

**Files:**
- Modify: `docs/verification/2026-08-11-study-workbench.md` with exact receipts only
- No product source changes unless a fresh defect is reproduced RED first and repaired in a separate commit.

**Interfaces:**
- Produces: installed-app evidence and final reviewer verdict

- [ ] **Step 1: Establish exact checkout and package preconditions**

Record HEAD, tracked tree hash, source inventory hash, existing installed app identity/hash, unrelated listeners/processes, and preserved untracked inventory. Stop if tracked files are dirty or the build would overwrite unrelated user work.

- [ ] **Step 2: Build and validate the macOS artifact**

Run the repository's exact `make build-mac` target with explicit PATH and `DEEPER_NOTEBOOK_CODESIGN_IDENTITY=-`. Require backend/desktop/frontend preconditions, package-content verification, arm64 identity, `codesign --verify --deep --strict`, `hdiutil verify`, and deterministic DMG/app hashes. Report ad-hoc `spctl` rejection honestly; do not claim notarization.

- [ ] **Step 3: Perform recoverable install and isolated smoke**

Preserve the existing app under a timestamped `/Applications/Deeper Notebook.app.backup-study-...` sibling, stage and verify the fresh app, atomically swap, then launch with task-owned `HOME` and `DEEPER_NOTEBOOK_DATA_DIR`. Prove authenticated readiness, Study route rendering, PDF/video plan flow, tutor response, Anki export/import, restart persistence, redaction, and no writes to an external fixture. Stop exact owned children and verify ports are free.

- [ ] **Step 4: Request fresh-context whole-diff review**

Supply the approved design, this plan, full diff from `e61e5d82`, global/task context, test receipts, dependency audit, native/package receipts, and known limitations to `sol_reviewer` with no inherited conversation. Any high/important finding requires RED reproduction and a separate repair commit followed by re-review.

- [ ] **Step 5: Final report commit**

Update `docs/verification/2026-08-11-study-workbench.md` with every touched file and justification, exact test totals, package hashes, rollback command, feature inventory, and residual limitations. Run `git diff --check`, rebrand audit, sensitive scan, and commit only the final receipt.

```bash
git add docs/verification/2026-08-11-study-workbench.md
git commit -m "docs(study): publish workbench acceptance"
```

---

## Self-review receipt

- **Spec coverage:** Tasks 1-8 cover reversible plans, sources, and syllabus approval; Tasks 9-13 cover shared artifacts, the twelve-assistant Study Team, and optional local voice; Tasks 14-16 cover mastery, native FSRS continuity, and Anki packages; Tasks 17-19 cover localization, accessibility, security, performance, browser, real database, native, package, and independent review.
- **Compatibility:** Existing card/review schemas and endpoints are never modified. New plan-card relationships use a join table. Source uploads and Studio generation are reused.
- **Type consistency:** `StudyPlan`, `StudySyllabus`, `StudyAssistantInvocation`, `StudyProgressReceipt`, and `AnkiCompatibilityReceipt` are each defined once in backend contracts and mirrored by exact frontend decoders.
- **Security:** Network/model authority, source read-only behavior, assistant proposals, Anki archive/SQLite/media bounds, and atomic publication all have named RED tests.
- **No placeholder work:** Every task names exact files, interfaces, RED/GREEN commands, expected outcomes, and atomic commit scope.
- **Known evidence limitation:** Code Review Graph was unavailable during planning because `graphify-out/graph.json` was absent; direct source tracing established the ownership map.
