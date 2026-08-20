# Structured Artifact Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace markdown-only Evidence Studio generation with versioned, validated artifact documents while preserving every existing markdown artifact, viewer, revision, and export path.

**Architecture:** Add Pydantic document schemas and a registry keyed by the existing artifact type. Generate against the selected schema with LangChain structured output when supported, fall back to schema-prompted JSON for local models, allow one bounded repair attempt, and render validated documents back to markdown for current viewers and exports. Store the new envelope inside the existing flexible `StudioArtifact.output_payload`, so no SurrealDB migration or destructive backfill is required.

**Tech Stack:** Python 3.11-3.12, Pydantic v2, LangChain 1.x, FastAPI, SurrealDB flexible object fields, TypeScript 5, React 19, Vitest, pytest.

**Official references:**

- Pydantic recommends discriminated unions for predictable union validation: https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions
- LangChain models expose `with_structured_output` with Pydantic validation and `include_raw=True`: https://docs.langchain.com/oss/python/langchain/models#structured-output

---

## File Map

**Create**

- `open_notebook/studio/schemas/__init__.py`: public schema and registry exports.
- `open_notebook/studio/schemas/documents.py`: Pydantic models for artifact documents.
- `open_notebook/studio/schemas/registry.py`: artifact-type-to-schema resolution and payload validation.
- `open_notebook/studio/payloads.py`: versioned envelope and legacy compatibility helpers.
- `open_notebook/studio/structured_generation.py`: structured model invocation, JSON fallback, and one repair attempt.
- `open_notebook/studio/renderers/__init__.py`: renderer export.
- `open_notebook/studio/renderers/markdown.py`: deterministic document-to-markdown rendering.
- `tests/test_studio_artifact_schemas.py`: schema and registry contract tests.
- `tests/test_studio_artifact_payloads.py`: compatibility envelope tests.
- `tests/test_studio_structured_generation.py`: structured/fallback/repair tests.
- `tests/test_studio_markdown_renderer.py`: renderer golden tests.
- `frontend/src/lib/studio-artifacts.ts`: typed envelope guards and markdown compatibility accessor.
- `frontend/src/lib/studio-artifacts.test.ts`: frontend compatibility tests.

**Modify**

- `open_notebook/studio/artifact_generation.py`: generate, validate, render, persist, and retain failure receipts.
- `tests/test_evidence_studio_artifact_api.py`: API generation assertions for new and legacy payloads.
- `api/routers/studio.py`: validate structured payloads on artifact PATCH without changing the response shape.
- `frontend/src/lib/api/studio.ts`: add typed structured-envelope interfaces while retaining `Record<string, unknown>` compatibility.
- `frontend/src/components/onp/ArtifactRail.tsx`: use the compatibility accessor without changing the existing viewer layout.
- `frontend/src/components/onp/ArtifactRail.test.tsx`: prove legacy and structured artifacts render identically.
- `README.md`: describe typed Studio artifacts and legacy compatibility.

No database migration is required because migration 23 defines `output_payload` as a flexible object.

---

### Task 1: Define Versioned Artifact Document Schemas

**Files:**

- Create: `open_notebook/studio/schemas/__init__.py`
- Create: `open_notebook/studio/schemas/documents.py`
- Create: `open_notebook/studio/schemas/registry.py`
- Test: `tests/test_studio_artifact_schemas.py`

- [x] **Step 1: Write failing schema registry tests**

```python
import pytest
from pydantic import ValidationError

from open_notebook.studio.schemas import (
    FlashcardsDocument,
    SlideDeckDocument,
    parse_artifact_document,
    schema_for_artifact_type,
)


def test_registry_resolves_slide_deck_schema():
    assert schema_for_artifact_type("slide_deck") is SlideDeckDocument


def test_parse_flashcards_document_rejects_missing_back():
    payload = {
        "schema_version": 1,
        "artifact_type": "flashcards",
        "title": "RAG review",
        "cards": [{"front": "What is retrieval?", "citations": ["[S1]"]}],
    }
    with pytest.raises(ValidationError):
        parse_artifact_document("flashcards", payload)


def test_parse_artifact_document_rejects_type_mismatch():
    payload = {
        "schema_version": 1,
        "artifact_type": "quiz",
        "title": "Wrong discriminator",
        "cards": [],
    }
    with pytest.raises(ValidationError):
        parse_artifact_document("flashcards", payload)
```

- [x] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest tests/test_studio_artifact_schemas.py -q`

Expected: collection fails because `open_notebook.studio.schemas` does not exist.

- [x] **Step 3: Implement strict Pydantic document models**

Use `ConfigDict(extra="forbid")` on generated document models. Define reusable `CitedText`, `ArtifactSection`, and the following typed documents:

```python
class ArtifactDocumentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=240)


class GenericDocument(ArtifactDocumentBase):
    artifact_type: Literal["report", "study_guide", "briefing", "faq", "timeline"]
    summary: str = ""
    sections: list[ArtifactSection] = Field(min_length=1)


class FlashcardsDocument(ArtifactDocumentBase):
    artifact_type: Literal["flashcards"] = "flashcards"
    cards: list[Flashcard] = Field(min_length=1)


class QuizDocument(ArtifactDocumentBase):
    artifact_type: Literal["quiz"] = "quiz"
    questions: list[QuizQuestion] = Field(min_length=1)


class DataTableDocument(ArtifactDocumentBase):
    artifact_type: Literal["data_table"] = "data_table"
    columns: list[str] = Field(min_length=1)
    rows: list[DataTableRow] = Field(min_length=1)


class MindMapDocument(ArtifactDocumentBase):
    artifact_type: Literal["mind_map"] = "mind_map"
    root: MindMapNode


class SlideDeckDocument(ArtifactDocumentBase):
    artifact_type: Literal["slide_deck"] = "slide_deck"
    audience: str = ""
    slides: list[Slide] = Field(min_length=1, max_length=40)


class InfographicDocument(ArtifactDocumentBase):
    artifact_type: Literal["infographic"] = "infographic"
    orientation: Literal["portrait", "landscape", "square"] = "portrait"
    panels: list[InfographicPanel] = Field(min_length=1, max_length=20)


class CoursePackDocument(ArtifactDocumentBase):
    artifact_type: Literal["course_pack", "training_guide"]
    audience: str
    learning_outcomes: list[str] = Field(min_length=1)
    modules: list[CourseModule] = Field(min_length=1)
    final_assessment: list[QuizQuestion] = Field(default_factory=list)


class PodcastOutlineDocument(ArtifactDocumentBase):
    artifact_type: Literal["podcast_outline"] = "podcast_outline"
    cold_open: str
    segments: list[PodcastSegment] = Field(min_length=1)
    takeaways: list[CitedText] = Field(default_factory=list)


class ResearchRunDocument(ArtifactDocumentBase):
    artifact_type: Literal["research_run"] = "research_run"
    objective: str
    hypotheses: list[str] = Field(default_factory=list)
    stages: list[ResearchStage] = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
```

Define the public document union after the concrete models so annotations and
registry helpers use one consistent type:

```python
ArtifactDocument = Annotated[
    GenericDocument
    | FlashcardsDocument
    | QuizDocument
    | DataTableDocument
    | MindMapDocument
    | SlideDeckDocument
    | InfographicDocument
    | CoursePackDocument
    | PodcastOutlineDocument
    | ResearchRunDocument,
    Field(discriminator="artifact_type"),
]
```

Citation markers use `Field(pattern=r"^\[S[1-9]\d*\]$")`. Quiz options carry stable IDs; a model validator ensures `correct_option_id` exists in the options. Data-table rows validate that every key is present in `columns` at the document level. Mind-map nodes use `children: list[MindMapNode]` with a bounded validator rejecting depth above 8.

Create a registry mapping existing `StudioArtifactType` strings to these schemas. Map `training_guide` and `course_pack` to `CoursePackDocument`; exclude `podcast_audio` because audio records are produced by the podcast pipeline rather than this text artifact generator.

- [x] **Step 4: Run the schema tests and confirm GREEN**

Run: `uv run pytest tests/test_studio_artifact_schemas.py -q`

Expected: all tests pass.

- [x] **Step 5: Run lint for the new package**

Run: `uv run ruff check open_notebook/studio/schemas tests/test_studio_artifact_schemas.py`

Expected: no errors.

- [x] **Step 6: Commit the schema contract**

```bash
git add open_notebook/studio/schemas tests/test_studio_artifact_schemas.py
git commit -m "feat(studio): define versioned artifact schemas"
```

---

### Task 2: Add the Backward-Compatible Payload Envelope

**Files:**

- Create: `open_notebook/studio/payloads.py`
- Test: `tests/test_studio_artifact_payloads.py`

- [x] **Step 1: Write failing payload compatibility tests**

```python
from open_notebook.studio.payloads import (
    artifact_markdown,
    build_structured_payload,
    parse_payload_document,
)


def test_legacy_content_remains_readable():
    assert artifact_markdown({"content": "# Legacy"}) == "# Legacy"


def test_new_payload_keeps_legacy_content_alias():
    document = parse_artifact_document("flashcards", FLASHCARD_FIXTURE)
    payload = build_structured_payload(document, "# Cards")
    assert payload["schema_version"] == 1
    assert payload["content"] == "# Cards"
    assert payload["markdown"] == "# Cards"
    assert payload["document"]["artifact_type"] == "flashcards"


def test_parse_payload_document_returns_none_for_legacy_payload():
    assert parse_payload_document("report", {"content": "# Legacy"}) is None
```

- [x] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest tests/test_studio_artifact_payloads.py -q`

Expected: import failure for `open_notebook.studio.payloads`.

- [x] **Step 3: Implement the envelope helpers**

```python
def build_structured_payload(
    document: ArtifactDocument,
    markdown: str,
    *,
    validation: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(extras or {})
    payload.update(
        {
            "schema_version": document.schema_version,
            "document": document.model_dump(mode="json"),
            "markdown": markdown,
            "content": markdown,
            "validation": validation or {"status": "valid", "errors": []},
        }
    )
    return payload


def artifact_markdown(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    value = payload.get("markdown") or payload.get("content") or ""
    return value if isinstance(value, str) else ""


def parse_payload_document(
    artifact_type: str,
    payload: Mapping[str, Any] | None,
) -> ArtifactDocument | None:
    if not payload or payload.get("schema_version") != 1:
        return None
    document = payload.get("document")
    if not isinstance(document, dict):
        raise InvalidInputError("Structured artifact payload is missing document")
    return parse_artifact_document(artifact_type, document)
```

`study_progress` and artifact-specific metadata remain sibling keys and are never discarded when the artifact is patched.

- [x] **Step 4: Run tests and lint**

Run: `uv run pytest tests/test_studio_artifact_payloads.py -q`

Run: `uv run ruff check open_notebook/studio/payloads.py tests/test_studio_artifact_payloads.py`

Expected: both pass.

- [x] **Step 5: Commit the compatibility layer**

```bash
git add open_notebook/studio/payloads.py tests/test_studio_artifact_payloads.py
git commit -m "feat(studio): add structured payload envelope"
```

---

### Task 3: Render Typed Documents to Deterministic Markdown

**Files:**

- Create: `open_notebook/studio/renderers/__init__.py`
- Create: `open_notebook/studio/renderers/markdown.py`
- Test: `tests/test_studio_markdown_renderer.py`

- [x] **Step 1: Write failing golden renderer tests**

Cover generic sections, flashcards, quizzes, data tables, mind maps, slides with speaker notes, infographics, Course Packs, podcast outlines, and Research Runs.

```python
def test_slide_deck_renderer_keeps_notes_and_citations():
    document = SlideDeckDocument.model_validate(SLIDE_DECK_FIXTURE)
    markdown = render_artifact_markdown(document)
    assert "## Slide 1: Retrieval-Augmented Generation" in markdown
    assert "Speaker notes:" in markdown
    assert "[S1]" in markdown


def test_quiz_renderer_matches_existing_viewer_labels():
    document = QuizDocument.model_validate(QUIZ_FIXTURE)
    markdown = render_artifact_markdown(document)
    assert "## Question 1" in markdown
    assert "A. Retrieve relevant passages" in markdown
    assert "Answer: A" in markdown
    assert "Explanation:" in markdown
```

- [x] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest tests/test_studio_markdown_renderer.py -q`

Expected: import failure for the renderer package.

- [x] **Step 3: Implement a `singledispatch` renderer**

Use `functools.singledispatch` so each document type has one focused renderer and future exporters can reuse the same schemas. Preserve the existing markdown labels consumed by `StudyArtifactViewers.tsx`:

```python
@singledispatch
def render_artifact_markdown(document: ArtifactDocumentBase) -> str:
    raise TypeError(f"Unsupported artifact document: {type(document).__name__}")


@render_artifact_markdown.register
def _(document: FlashcardsDocument) -> str:
    parts = [f"# {document.title}"]
    for index, card in enumerate(document.cards, start=1):
        parts.extend(
            [
                f"## Flashcard {index}",
                f"Front: {card.front}",
                f"Back: {card.back}",
                f"Source: {' '.join(card.citations)}",
            ]
        )
    return "\n\n".join(parts).rstrip() + "\n"
```

Escape pipe characters and line breaks in data-table cells. Render recursive mind-map nodes with indentation and a depth guard. Do not insert unsupported citation markers.

- [x] **Step 4: Run renderer and existing viewer parser tests**

Run: `uv run pytest tests/test_studio_markdown_renderer.py -q`

Run: `cd frontend && npm test -- --run src/components/onp/ArtifactRail.test.tsx`

Expected: renderer tests pass and existing frontend parser tests remain green.

- [x] **Step 5: Commit the renderer**

```bash
git add open_notebook/studio/renderers tests/test_studio_markdown_renderer.py
git commit -m "feat(studio): render typed artifacts to markdown"
```

---

### Task 4: Add Structured Model Invocation with One Repair Attempt

**Files:**

- Create: `open_notebook/studio/structured_generation.py`
- Test: `tests/test_studio_structured_generation.py`

- [x] **Step 1: Write failing model adapter tests**

Use small fake async models, not provider mocks. Cover native structured success, unsupported structured output with JSON fallback, fenced JSON extraction, one repair success, and repair exhaustion.

```python
@pytest.mark.asyncio
async def test_native_structured_output_is_preferred():
    model = NativeStructuredModel(FLASHCARD_DOCUMENT)
    result = await generate_structured_document(
        model=model,
        schema=FlashcardsDocument,
        messages=[HumanMessage(content="Build cards")],
        timeout_seconds=5,
    )
    assert result.document.artifact_type == "flashcards"
    assert result.attempts == 1
    assert model.plain_invocations == 0


@pytest.mark.asyncio
async def test_invalid_json_gets_exactly_one_repair_attempt():
    model = PlainJsonModel(["not json", json.dumps(FLASHCARD_FIXTURE)])
    result = await generate_structured_document(...)
    assert result.attempts == 2
    assert len(model.calls) == 2
```

- [x] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest tests/test_studio_structured_generation.py -q`

Expected: import failure for `structured_generation`.

- [x] **Step 3: Implement native and fallback paths**

```python
@dataclass(frozen=True)
class StructuredGenerationResult:
    document: ArtifactDocumentBase
    raw_output: str
    attempts: int
    strategy: Literal["native", "json", "json_repair"]


async def generate_structured_document(*, model, schema, messages, timeout_seconds):
    native = getattr(model, "with_structured_output", None)
    if callable(native):
        try:
            structured = native(schema, include_raw=True)
            response = await asyncio.wait_for(
                structured.ainvoke(messages), timeout=timeout_seconds
            )
            parsed = response.get("parsed") if isinstance(response, dict) else response
            if parsed is not None:
                document = (
                    parsed
                    if isinstance(parsed, schema)
                    else schema.model_validate(parsed)
                )
                return StructuredGenerationResult(
                    document, _raw_text(response), 1, "native"
                )
        except (NotImplementedError, TypeError, ValueError, ValidationError):
            pass

    return await _generate_json_with_repair(
        model=model,
        schema=schema,
        messages=messages,
        timeout_seconds=timeout_seconds,
    )
```

The fallback appends the exact `schema.model_json_schema()` and asks for one JSON object. Parse plain JSON or a fenced `json` block. On JSON or Pydantic validation failure, call the model once more with the bounded original output, compact `ValidationError.errors(include_url=False)`, and schema. A second failure raises `StructuredArtifactGenerationError` containing a redacted, size-limited receipt; it does not loop.

- [x] **Step 4: Run tests and lint**

Run: `uv run pytest tests/test_studio_structured_generation.py -q`

Run: `uv run ruff check open_notebook/studio/structured_generation.py tests/test_studio_structured_generation.py`

Expected: both pass.

- [x] **Step 5: Commit the model adapter**

```bash
git add open_notebook/studio/structured_generation.py tests/test_studio_structured_generation.py
git commit -m "feat(studio): validate structured model output"
```

---

### Task 5: Integrate Structured Generation into Evidence Studio

**Files:**

- Modify: `open_notebook/studio/artifact_generation.py`
- Modify: `tests/test_evidence_studio_artifact_api.py`

- [x] **Step 1: Add failing artifact-generation tests**

Add tests proving:

1. a generated report stores `schema_version`, `document`, `markdown`, `content`, and validation metadata;
2. markdown export still exists and contains the rendered document;
3. revision snapshots retain the entire structured envelope;
4. unsupported `podcast_audio` returns a typed 422 rather than a generic artifact;
5. exhausted repair stores a concise failure receipt without source text.

```python
assert artifact.output_payload["schema_version"] == 1
assert artifact.output_payload["document"]["artifact_type"] == "report"
assert artifact.output_payload["markdown"] == artifact.output_payload["content"]
assert artifact.output_payload["validation"]["status"] == "valid"
```

- [x] **Step 2: Run focused tests and confirm RED**

Run: `uv run pytest tests/test_evidence_studio_artifact_api.py -q`

Expected: new envelope assertions fail against `{content: markdown}`.

- [x] **Step 3: Replace the markdown-only generation call**

Resolve the schema before model provisioning, revise the system prompt to require source markers in typed citation fields, call `generate_structured_document`, render the document, and build the envelope:

```python
schema = schema_for_artifact_type(artifact.artifact_type)
result = await generate_structured_document(
    model=chain,
    schema=schema,
    messages=[
        SystemMessage(content=system_prompt),
        HumanMessage(content=combined_context),
    ],
    timeout_seconds=_PAGE_TIMEOUT_SEC,
)
content = render_artifact_markdown(result.document)
legacy_extras = _artifact_output_payload(artifact, content, citations)
legacy_extras.pop("content", None)
artifact.output_payload = build_structured_payload(
    result.document,
    content,
    validation={
        "status": "valid",
        "errors": [],
        "strategy": result.strategy,
        "attempts": result.attempts,
    },
    extras=legacy_extras,
)
```

Keep `output_format="markdown"` during this foundation slice because markdown remains the viewer/export format. Later visual-export plans will add PPTX, PNG, and PDF paths.

On `StructuredArtifactGenerationError`, set `status="failed"` and store only:

```python
{
    "schema_version": 1,
    "validation": {
        "status": "invalid",
        "errors": exc.errors,
        "attempts": exc.attempts,
    },
    "error": "Artifact output did not match the required structure",
}
```

Do not retain source context or unbounded raw model output.

- [x] **Step 4: Run backend Studio tests**

Run: `uv run pytest tests/test_evidence_studio_foundation.py tests/test_evidence_studio_artifact_api.py tests/test_studio_router.py tests/test_studio_e2e_multipage.py -q`

Expected: all pass.

- [x] **Step 5: Commit the generation integration**

```bash
git add open_notebook/studio/artifact_generation.py tests/test_evidence_studio_artifact_api.py
git commit -m "feat(studio): persist validated artifact documents"
```

---

### Task 6: Validate Structured Artifact Updates at the API Boundary

**Files:**

- Modify: `api/routers/studio.py`
- Modify: `tests/test_evidence_studio_artifact_api.py`

- [x] **Step 1: Write failing PATCH validation tests**

```python
def test_patch_rejects_invalid_structured_document(client, artifact):
    response = client.patch(
        f"/api/studio/artifacts/{artifact.id}",
        json={
            "output_payload": {
                "schema_version": 1,
                "document": {"artifact_type": "quiz", "title": "Broken"},
                "markdown": "# Broken",
                "content": "# Broken",
            }
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_artifact_document"


def test_patch_accepts_legacy_markdown_payload(client, artifact):
    response = client.patch(
        f"/api/studio/artifacts/{artifact.id}",
        json={"output_payload": {"content": "# Owner edited legacy artifact"}},
    )
    assert response.status_code == 200


def test_patch_rejects_unknown_schema_version(client, artifact):
    response = client.patch(
        f"/api/studio/artifacts/{artifact.id}",
        json={
            "output_payload": {
                "schema_version": 2,
                "document": {"artifact_type": "report", "title": "Future"},
                "content": "# Compatibility fallback",
            }
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_artifact_schema"
```

- [x] **Step 2: Run the tests and confirm RED**

Run: `uv run pytest tests/test_evidence_studio_artifact_api.py -q`

Expected: invalid structured payload is currently accepted.

- [x] **Step 3: Validate only versioned payloads before save**

In the existing artifact PATCH handler, fetch the artifact first and call
`parse_payload_document(artifact.artifact_type, update.output_payload)` when
`schema_version` is present. Reject unknown versions rather than persisting an
envelope this app cannot validate. Convert `ValidationError` and
`InvalidInputError` into HTTP 422 with a bounded error list. Do not validate or
rewrite legacy payloads.

For a valid v1 document, render canonical markdown on the server and rebuild
the envelope before saving. Preserve owner state such as `study_progress` and
future exporter metadata, recompute derived viewer metadata such as
`data_table_rows`, `research_stages`, and `citation_warnings`, and replace
client-provided `markdown` and `content` with the deterministic renderer output.
This keeps the structured document authoritative and ensures the existing
markdown content fingerprint invalidates stale study progress whenever the
document changes.

- [x] **Step 4: Run API tests and lint**

Run: `uv run pytest tests/test_evidence_studio_artifact_api.py -q`

Run: `uv run ruff check api/routers/studio.py tests/test_evidence_studio_artifact_api.py`

Expected: both pass.

- [x] **Step 5: Commit API validation**

```bash
git add api/routers/studio.py tests/test_evidence_studio_artifact_api.py
git commit -m "fix(studio): reject invalid artifact document edits"
```

---

### Task 7: Add Frontend Envelope Types and Legacy Compatibility

**Files:**

- Create: `frontend/src/lib/studio-artifacts.ts`
- Create: `frontend/src/lib/studio-artifacts.test.ts`
- Modify: `frontend/src/lib/api/studio.ts`
- Modify: `frontend/src/components/onp/ArtifactRail.tsx`
- Modify: `frontend/src/components/onp/ArtifactRail.test.tsx`

- [x] **Step 1: Write failing frontend helper tests**

```typescript
import { artifactMarkdown, structuredArtifactMeta } from './studio-artifacts'

it('reads existing legacy markdown content', () => {
  expect(artifactMarkdown({ content: '# Legacy' })).toBe('# Legacy')
})

it('prefers structured markdown and exposes validation state', () => {
  const payload = {
    schema_version: 1,
    document: { schema_version: 1, artifact_type: 'report', title: 'Report' },
    markdown: '# Structured',
    content: '# Compatibility alias',
    validation: { status: 'valid', errors: [], strategy: 'native', attempts: 1 },
  }
  expect(artifactMarkdown(payload)).toBe('# Structured')
  expect(structuredArtifactMeta(payload)?.validation.status).toBe('valid')
})
```

- [x] **Step 2: Run tests and confirm RED**

Run: `cd frontend && npm test -- --run src/lib/studio-artifacts.test.ts`

Expected: module import failure.

- [x] **Step 3: Implement narrow TypeScript types and guards**

```typescript
export interface StructuredArtifactValidation {
  status: 'valid' | 'invalid'
  errors: Array<Record<string, unknown>>
  strategy?: 'native' | 'json' | 'json_repair'
  attempts?: number
}

export interface StructuredArtifactEnvelope {
  schema_version: 1
  document: Record<string, unknown> & {
    schema_version: 1
    artifact_type: StudioArtifactType
    title: string
  }
  markdown: string
  content: string
  validation: StructuredArtifactValidation
}

export function artifactMarkdown(payload?: Record<string, unknown>): string {
  const markdown = payload?.markdown ?? payload?.content
  return typeof markdown === 'string' ? markdown : ''
}
```

Import `StudioArtifactType` with a type-only import from `./api/studio` so the
helper introduces no runtime dependency cycle.

Keep `StudioArtifact.output_payload` as `Record<string, unknown>` intersected with optional known fields so older plugins and artifact metadata remain valid.

- [x] **Step 4: Update ArtifactRail and tests**

Replace direct `output_payload.content` access with `artifactMarkdown`. Add
tests proving a recognized v1 envelope renders its `markdown`, unknown or
malformed envelopes fall back to `content`, revision selection renders that
revision's envelope, and study-progress updates preserve `document`,
`markdown`, `content`, and existing metadata. Do not add visible labels in this
foundation slice; validation display and its localization belong to the next
evidence-quality plan.

- [x] **Step 5: Run frontend verification**

Run: `cd frontend && npm test -- --run src/lib/studio-artifacts.test.ts src/components/onp/ArtifactRail.test.tsx`

Run: `cd frontend && npx tsc --noEmit`

Run: `cd frontend && npm run lint`

Expected: all pass with zero errors.

- [x] **Step 6: Commit the frontend compatibility layer**

```bash
git add frontend/src/lib/studio-artifacts.ts frontend/src/lib/studio-artifacts.test.ts frontend/src/lib/api/studio.ts frontend/src/components/onp/ArtifactRail.tsx frontend/src/components/onp/ArtifactRail.test.tsx
git commit -m "feat(studio): display structured artifact status"
```

---

### Task 8: Document, Verify, and Package the Foundation Slice

**Files:**

- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-17-structured-artifact-foundation.md`

- [x] **Step 1: Update README architecture and Evidence Studio sections**

Document that new artifacts use validated typed documents, retain deterministic markdown, support one bounded repair attempt, and preserve legacy markdown artifacts without migration.

- [x] **Step 2: Run all focused backend tests**

Run:

```bash
uv run pytest \
  tests/test_studio_artifact_schemas.py \
  tests/test_studio_artifact_payloads.py \
  tests/test_studio_structured_generation.py \
  tests/test_studio_markdown_renderer.py \
  tests/test_evidence_studio_foundation.py \
  tests/test_evidence_studio_artifact_api.py \
  tests/test_studio_router.py \
  tests/test_studio_e2e_multipage.py -q
```

Expected: all pass.

- [x] **Step 3: Run full frontend gates**

Run: `cd frontend && npm test`

Run: `cd frontend && npx tsc --noEmit`

Run: `cd frontend && npm run lint`

Run: `cd frontend && npm run build`

Expected: all pass.

- [x] **Step 4: Run the full backend suite**

Run: `uv run pytest -q`

Expected: all tests pass, with only documented skips.

- [x] **Step 5: Inspect the final diff and repository state**

Run: `git diff --check`

Run: `git status --short`

Expected: only intended foundation files and the pre-existing unrelated `desktop/build/__pycache__/` and `docker-compose.yml.bak` entries are present.

- [x] **Step 6: Commit documentation and plan completion**

```bash
git add README.md docs/superpowers/plans/2026-07-17-structured-artifact-foundation.md
git commit -m "docs: explain structured Evidence Studio artifacts"
```

- [x] **Step 7: Fresh-context verification**

Ask a verifier to inspect the full diff, rerun the focused tests, and specifically challenge:

- legacy artifact compatibility;
- local-model fallback and repair bounds;
- source-content leakage in failures;
- revision preservation;
- fragile markdown viewer compatibility;
- unintended SurrealDB migration requirements.

Address any verified findings with test-first follow-up commits.

---

## Foundation Completion Criteria

- Existing `{content: markdown}` artifacts open, revise, export, and retain study progress.
- Newly generated supported artifacts persist a valid v1 document and deterministic markdown compatibility alias.
- Unsupported or invalid model output gets at most one repair attempt.
- Invalid structured edits receive a typed HTTP 422 response.
- Revision snapshots preserve complete structured envelopes.
- No source text or secrets appear in structured-generation failure receipts.
- No database migration or destructive backfill is introduced.
- Focused backend tests, full backend tests, frontend tests, typecheck, lint, and production build pass.
- The repository remains single-user; no account, role, sharing, or collaboration code is added.

## Completion Receipt

Completed on 2026-07-17 on `feature/structured-artifacts-v1` and reviewed
against `desktop-app` before integration.

- Focused Studio backend verification: 116 tests passed before review; the
  reviewer independently reran 77 focused tests successfully.
- Final backend verification after review fixes: 2,510 passed, 9 skipped, with
  8 pre-existing dependency deprecation warnings.
- Frontend verification: 122 suites and 359 tests passed; TypeScript typecheck
  and the Next.js production build passed. ESLint reported zero errors and two
  pre-existing warnings outside this change.
- Ruff and `git diff --check` passed.
- Fresh-context review found two correctness issues: citations could disappear
  when a Data Table already had a `Source` column, and structured PATCH edits
  could preserve stale derived viewer metadata. Both were fixed test-first in
  commit `a3dcf9f` and the complete backend suite was rerun afterward.
- No SurrealDB migration, account system, sharing model, or collaboration code
  was introduced.
