# Visual Artifact Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Turn structured slide-deck and infographic artifacts into professional, local, reopenable PPTX, PDF, and PNG deliverables with purpose-built previews and edit-safe export refresh.

**Architecture:** Add format-specific exporters under `open_notebook/studio/exporters/` that accept validated v1 documents and write only to caller-allocated paths. The existing artifact export orchestrator remains responsible for safe names, collision handling, persistence, and API exposure. Frontend viewers consume the same structured document stored in `output_payload.document`, while legacy or invalid payloads continue to render as Markdown.

**Tech Stack:** Python 3.11/3.12, Pydantic 2, python-pptx 1.0.2, Pillow 11.3.x, FastAPI, React 19, Next.js 16, TypeScript, Tailwind CSS, Vitest, pytest.

---

## Boundaries And Decisions

- This remains single-user and local-first. No account, sharing, or hosted rendering service is added.
- PPTX is editable and contains real title/body shapes, speaker notes, visual direction, and source markers.
- Slide PDF is deterministic and self-contained. It is rendered from the same layout model with Pillow, avoiding a LibreOffice or PowerPoint runtime requirement.
- Infographic PNG and PDF use a constrained layout system. Generated HTML is not executed.
- Files are written only beneath the existing configured artifact export directory.
- Existing Markdown/JSON/CSV/Course Pack exports remain unchanged.
- A failed optional visual export does not discard a successfully generated artifact; the failure is recorded as a bounded export warning.
- Structured edits recompute derived metadata and regenerate sidecar exports from the edited document.
- Edited artifacts allocate new export paths after snapshotting the prior revision. This keeps historical revision files immutable while the active artifact exposes only the newly generated paths.

## File Map

- Create `open_notebook/studio/exporters/__init__.py`: public visual-export API.
- Create `open_notebook/studio/exporters/theme.py`: shared color, typography, spacing, wrapping, and citation helpers.
- Create `open_notebook/studio/exporters/slides.py`: PPTX and raster-PDF rendering for `SlideDeckDocument`.
- Create `open_notebook/studio/exporters/infographic.py`: PNG and PDF rendering for `InfographicDocument`.
- Create `tests/test_studio_visual_exporters.py`: reopen and content assertions for every format.
- Modify `pyproject.toml` and `uv.lock`: make python-pptx and Pillow direct application dependencies at already-resolved compatible versions.
- Modify `open_notebook/studio/artifact_generation.py`: allocate, write, and persist visual export paths from validated documents.
- Modify `api/routers/studio.py`: refresh visual and existing exports after a valid structured PATCH.
- Modify `tests/test_evidence_studio_artifact_api.py`: generation, failure isolation, and edit-refresh coverage.
- Create `frontend/src/components/onp/VisualArtifactViewers.tsx`: slide and infographic viewers.
- Create `frontend/src/components/onp/VisualArtifactViewers.test.tsx`: interaction and fallback coverage.
- Modify `frontend/src/components/onp/ArtifactRail.tsx`: select structured visual viewers and prioritize visual exports.
- Modify `frontend/src/components/onp/ArtifactRail.test.tsx`: integrated viewer and saved-format assertions.
- Modify `README.md` and `desktop/CHANGELOG.md`: document visual deliverables and verification.

### Task 1: Direct Dependencies And Exporter Contract

- [x] **Step 1: Add failing import and dispatch tests**

Create tests that parse a `SlideDeckDocument` and `InfographicDocument`, call the public exporter functions, and initially fail because `open_notebook.studio.exporters` does not exist.

```python
from open_notebook.studio.exporters import export_infographic, export_slide_deck


def test_visual_exporters_reject_the_wrong_document(tmp_path):
    with pytest.raises(TypeError, match="SlideDeckDocument"):
        export_slide_deck(
            infographic_document(), tmp_path / "wrong.pptx", tmp_path / "wrong.pdf"
        )
```

- [x] **Step 2: Verify RED**

Run: `uv run pytest tests/test_studio_visual_exporters.py -q`

Expected: collection fails because the exporter package is absent.

- [x] **Step 3: Add direct dependencies and public API**

Add these compatible direct dependencies without upgrading the existing Pillow constraint:

```toml
"pillow>=11.3.0,<12.0",
"python-pptx>=1.0.2,<2.0",
```

Expose `export_slide_deck(document: SlideDeckDocument, pptx_path: Path,
pdf_path: Path) -> None` and `export_infographic(document:
InfographicDocument, png_path: Path, pdf_path: Path) -> None`. Each function
validates the concrete document type before creating either output file.

- [x] **Step 4: Lock and verify dependencies**

Run: `uv lock`

Run: `uv run python -c "import PIL, pptx; print(PIL.__version__, pptx.__version__)"`

Expected: Pillow 11.3.x and python-pptx 1.0.2 import successfully.

### Task 2: Editable PPTX And Slide PDF

- [x] **Step 1: Write PPTX reopen tests**

The test must reopen the output with `Presentation(path)` and assert:

- 16:9 dimensions;
- one title slide plus one slide per structured slide;
- slide titles and bullets remain editable text;
- speaker notes include notes, visual direction, and citation markers;
- all generated files are non-empty.

- [x] **Step 2: Write PDF reopen tests**

Open the PDF with Pillow or PyMuPDF and assert page count, 16:9 page bounds, and nonblank rendered pixels.

- [x] **Step 3: Implement shared visual theme**

Use a restrained multi-color palette with fixed constants, 16:9 dimensions, bounded text wrapping, safe truncation, and a citation footer. The theme must not depend on network fonts or generated images.

- [x] **Step 4: Implement PPTX rendering**

Use `python-pptx` shapes and text frames. Do not flatten slides to images. Add notes through `slide.notes_slide.notes_text_frame` and include source markers in both the footer and notes.

- [x] **Step 5: Implement raster PDF rendering**

Render each slide to an RGB Pillow image using the same hierarchy and save a multipage PDF with fixed resolution and margins.

- [x] **Step 6: Verify GREEN and lint**

Run: `uv run pytest tests/test_studio_visual_exporters.py -q`

Run: `uv run ruff check open_notebook/studio/exporters tests/test_studio_visual_exporters.py`

### Task 3: Deterministic Infographic PNG And PDF

- [x] **Step 1: Write image reopen tests**

Cover portrait, landscape, and square orientations. Assert exact dimensions, RGB/RGBA mode, nonblank pixel variance, title/panel count metadata, and a one-page PDF that reopens.

- [x] **Step 2: Implement constrained panel layouts**

Render `text`, `metric`, `timeline`, `comparison`, `process`, and `chart` panels with distinct but consistent treatments. Use stable grid tracks and bounded wrapping so long content cannot overlap adjacent panels.

- [x] **Step 3: Preserve citations**

Every panel with citations must display markers within that panel. The footer lists all unique markers in first-seen order.

- [x] **Step 4: Verify GREEN and lint**

Run the exporter tests and Ruff. Inspect generated test fixtures with Pillow pixel checks.

### Task 4: Artifact Export Integration And Edit Refresh

- [x] **Step 1: Add failing generation integration tests**

For `slide_deck`, assert `export_paths` includes `pptx` and `pdf`. For `infographic`, assert it includes `png` and `pdf`. Reopen every path and assert the JSON sidecar contains the same paths.

- [x] **Step 2: Add visual failure-isolation test**

Monkeypatch the visual exporter to raise and assert the artifact remains completed with Markdown/JSON exports plus a bounded `export_warnings.visual` entry that contains no source text.

- [x] **Step 3: Add structured PATCH refresh test**

Start with a completed slide artifact, PATCH a changed v1 document, and assert a revision snapshot is retained and newly allocated visual exports contain the edited title while owner state is preserved.

- [x] **Step 4: Integrate validated document dispatch**

Parse `artifact.output_payload.document` with `parse_payload_document`, allocate paths through `_artifact_export_path`, call only the matching visual exporter, and update `artifact.export_paths` before writing JSON metadata.

- [x] **Step 5: Keep failures bounded and local**

Catch visual-export exceptions at the visual boundary, log the exception without source content, remove incomplete files, and store only exception type plus a 240-character message.

- [x] **Step 6: Refresh exports after structured edits**

Snapshot the previous completed artifact before applying a changed document, save canonical payload state, and regenerate all sidecars in a worker thread. Legacy content-only PATCH behavior remains unchanged.

- [x] **Step 7: Verify API tests and lint**

Run focused artifact API tests and Ruff for all changed backend files.

### Task 5: Purpose-Built Visual Viewers

- [x] **Step 1: Write failing viewer tests**

Test slide navigation, stable 16:9 sizing, speaker-note visibility, infographic orientation, panel labels, citation markers, malformed-document Markdown fallback, and keyboard previous/next behavior.

- [x] **Step 2: Implement a narrow structured-document guard**

Accept only v1 `slide_deck` and `infographic` documents with the expected arrays. Never render arbitrary HTML from model output.

- [x] **Step 3: Implement SlideDeckViewer**

Provide a thumbnail rail, one stable 16:9 stage, icon previous/next controls with tooltips, slide count, speaker-notes disclosure, and citation footer. Long bullets wrap and scroll inside fixed bounds rather than resizing the stage.

- [x] **Step 4: Implement InfographicViewer**

Use constrained responsive tracks and orientation-aware bounds. Give each panel kind a recognizable visual treatment without nested cards or decorative gradients.

- [x] **Step 5: Integrate ArtifactRail exports**

Prefer visual formats in this order: PPTX, PDF, PNG, Markdown, JSON. Keep generic Open, Copy, and Folder actions for every saved file.

- [x] **Step 6: Verify frontend gates**

Run focused Vitest, TypeScript typecheck, lint, and production build.

### Task 6: Documentation, Full Verification, And Review

- [x] **Step 1: Update README and changelog**

Document actual formats, local output location, editability boundaries, deterministic rendering, and fallback behavior.

- [x] **Step 2: Run full backend and frontend suites**

Run `uv run pytest -q`, full Vitest, TypeScript typecheck, lint, and production build.

- [x] **Step 3: Inspect generated deliverables**

Reopen PPTX with python-pptx, PDF with PyMuPDF/Pillow, and PNG with Pillow. Confirm nonblank output, expected dimensions, notes, and citation markers.

- [x] **Step 4: Run fresh-context review**

Challenge path containment, malformed structured documents, text overflow, source leakage in errors, stale exports after edits, legacy compatibility, and optional-export failure isolation.

- [x] **Step 5: Address findings test-first and rerun gates**

- [x] **Step 6: Mark this plan complete, commit, merge, and push**

## Acceptance Criteria

- Slide artifacts produce editable `.pptx` and reopenable multipage `.pdf` files.
- PPTX retains speaker notes, visual direction, and citations.
- Infographic artifacts produce nonblank `.png` and `.pdf` files in every supported orientation.
- Visual files are visible through the existing saved-export controls.
- Structured edits cannot leave old visual files or derived metadata presented as current.
- Legacy Markdown artifacts remain readable and downloadable.
- Export failures do not erase a completed artifact or leak source content.
- No accounts, roles, sharing, or remote rendering are introduced.

## Completion Receipt

Completed on 2026-07-17 on branch `feature/visual-exports-v1`.

- Backend: `2522 passed, 9 skipped, 8 warnings` from `uv run pytest -q`. Warnings are dependency deprecations and are not introduced by this work.
- Frontend: `56` test files and `364` tests passed from the full Vitest run.
- Static gates: TypeScript passed, Ruff passed, and `git diff --check` passed.
- Lint: zero errors and two pre-existing warnings outside this feature (`notebooks/[id]/page.tsx` unused `cn`; `GeneratePodcastDialog.tsx` missing `episodeLength` hook dependency).
- Production build: Next.js 16.2.6 compiled successfully and generated all 19 static pages.
- Deliverable inspection: PPTX, slide PDF, infographic PNG, and infographic PDF reopened successfully. Portrait, landscape, square, and schema-maximum 20-panel infographics were visually checked for clipping and overlap.
- Browser inspection: desktop at 1440x1000 and mobile at 390x844 showed no horizontal document overflow. The mobile artifact dialog scrolls to all controls, and the final mocked notebook route produced no console errors or warnings.
- Fresh-context review: fixed dense 20-panel infographic layout overflow and added coverage for all orientations; fixed the slide preview to include the same generated cover page as PPTX/PDF exports. The suggestion to overwrite export paths in place was intentionally rejected because revision snapshots retain those paths and require immutable historical files.
