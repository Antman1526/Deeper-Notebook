# Gemini-Forward Phase 2A Source Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first, source-derived visual gallery and compact source covers across Deeper Notebook without changing source authority, introducing image generation, or weakening the Phase 1 visual and rollback contracts.

**Architecture:** `source` stays authoritative. A separate bounded extraction command computes a versioned source fingerprint, acquires a durable owner-fenced lease, extracts one safe derivative, atomically publishes it under the controlled data root, and records rebuildable cache metadata. Read projections batch-match cache rows by canonical source ID plus persisted `source.updated`; strict frontend decoders and shared container-responsive components fail soft to typographic covers.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SurrealDB/SurrealQL, `surreal-commands`, PyMuPDF, Pillow, `imageio-ffmpeg`, Next.js 16, React 19, TypeScript, Zod, TanStack Query, Vitest, Testing Library, Playwright, Ruff, ESLint, Gitleaks.

## Global Constraints

- Treat `docs/superpowers/specs/2026-08-14-gemini-forward-phase-2a-source-gallery-design.md` at commit `35a6026b` as the approved authority.
- Preserve `source` as the sole content/evidence authority; all visual rows and files are derived and disposable.
- Backend flag `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED` and frontend flag `NEXT_PUBLIC_DN_SOURCE_VISUALS` both default off; explicit `0` disables them.
- Frontend Source Gallery also requires `NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2`; either flag off preserves the current UI and request ledger.
- Never generate images, call a cloud image provider, capture webpage screenshots, accept custom image uploads, or send source text to a visual provider.
- Accept only embedded PDF images, bounded video frames, and embedded audio artwork; otherwise render a deterministic typographic cover.
- Output only static `image/webp`, maximum `1280 x 720`, maximum `1.5 MiB`; reject animated media, SVG, decoded images over `40,000,000` pixels, malformed data, and decoder warnings.
- Inspect at most 24 PDF pages / 64 embedded candidates, three video timestamps, 15 seconds per frame attempt, and 60 seconds per extraction job.
- Enforce at most two extraction jobs process-wide and one durable active lease per source fingerprint; lease duration is exactly 90 seconds.
- Keep the default cache ceiling at `2 GiB`; eviction is derived-only, oldest-ready-first, bounded, and must never delete source files.
- Source list/detail projection adds one batch query and does not hash source bodies or files; exact asset serving revalidates the full fingerprint.
- Preserve Phase 1 target-size, clipping, overflow, scroll-reachability, theme, high-contrast, reduced-motion, same-origin ledger, and feature-off contracts.
- Phase 2A budget: no more than `40 KiB` JavaScript gzip and `24 KiB` CSS gzip above the Phase 1 V2-on baseline; CLS remains `<= 0.05`.
- Do not add runtime dependencies: PyMuPDF, Pillow, and `imageio-ffmpeg` are already present.
- Preserve unrelated tracked/untracked state; do not stage `.codex/agent-context/*`.

---

### Task 1: Freeze flags, migration 46, and strict contracts

**Files:**
- Modify: `deeper_notebook/feature_flags.py`
- Modify: `frontend/src/lib/features.ts`
- Modify: `frontend/src/lib/features.test.ts`
- Modify: `frontend/src/lib/features-build-contract.test.ts`
- Create: `deeper_notebook/database/migrations/46.surrealql`
- Create: `deeper_notebook/database/migrations/46_down.surrealql`
- Create: `deeper_notebook/source_visuals/__init__.py`
- Create: `deeper_notebook/source_visuals/contracts.py`
- Create: `api/schemas/source_visuals.py`
- Modify: `tests/test_evidence_studio_foundation.py`
- Modify: `tests/test_migration_discovery.py`
- Create: `tests/test_source_visual_contracts.py`

**Interfaces:**
- Produces: `source_visuals_enabled() -> bool`.
- Produces: `SourceVisualAuthority`, `SourceVisualRecord`, `SourceVisualClaim`, `SourceVisualOperationReceipt`, `SourceVisualLocator`, `PreparedVisualAsset`.
- Produces: `SourceVisualRefreshRequest`, `SourceVisualDeleteRequest`, `SourceVisualReceiptResponse`, `SourceVisualStatusResponse`, `SourceVisualJobResponse`.
- Migration 46 owns only `source_visual_cache`, `source_visual_claim`, and `source_visual_operation` plus their indexes.

- [ ] **Step 1: Write strict RED tests for both flags, contracts, and migration discovery**

```python
def test_source_visual_flag_defaults_off_and_accepts_explicit_enable(monkeypatch):
    import deeper_notebook.feature_flags as flags
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", raising=False)
    assert flags.source_visuals_enabled() is False
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", "1")
    assert flags.source_visuals_enabled() is True

def test_migration_46_is_symmetric_and_schema_full():
    ups, downs = AsyncMigrationManager._discover_migrations()
    assert ups[45].version == 46
    assert "DEFINE TABLE IF NOT EXISTS source_visual_cache SCHEMAFULL" in ups[45].sql
    assert "DEFINE TABLE IF NOT EXISTS source_visual_claim SCHEMAFULL" in ups[45].sql
    assert "DEFINE TABLE IF NOT EXISTS source_visual_operation SCHEMAFULL" in ups[45].sql
    assert downs[45] is not None
    assert "REMOVE TABLE IF EXISTS source_visual_operation" in downs[45].sql
    assert "REMOVE TABLE IF EXISTS source_visual_claim" in downs[45].sql
    assert "REMOVE TABLE IF EXISTS source_visual_cache" in downs[45].sql
```

```ts
it('keeps source visuals off unless explicitly enabled', () => {
  delete process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS
  expect(isSourceVisualsEnabled()).toBe(false)
  process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '1'
  expect(isSourceVisualsEnabled()).toBe(true)
  process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS = '0'
  expect(isSourceVisualsEnabled()).toBe(false)
})
```

- [ ] **Step 2: Run RED and confirm only missing Phase 2A symbols/files fail**

Run:

```bash
uv run pytest -q tests/test_evidence_studio_foundation.py tests/test_migration_discovery.py tests/test_source_visual_contracts.py
cd frontend && npx vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts
```

Expected: backend collection fails on `deeper_notebook.source_visuals.contracts` / migration 46 / flag; frontend fails on `isSourceVisualsEnabled`.

- [ ] **Step 3: Implement strict Pydantic contracts and default-off flags**

Use these exact public shapes in `deeper_notebook/source_visuals/contracts.py`:

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256 = r"^[0-9a-f]{64}$"
SourceVisualOrigin = Literal["embedded", "video_frame", "audio_artwork"]

class SourceVisualLocator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    page: int | None = Field(default=None, ge=1, le=24)
    timestamp_ms: int | None = Field(default=None, ge=0)
    resource_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def exactly_one_locator(self):
        if sum(value is not None for value in (self.page, self.timestamp_ms, self.resource_id)) != 1:
            raise ValueError("source visual locator must contain exactly one value")
        return self

class SourceVisualAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str = Field(pattern=r"^source:[A-Za-z0-9_-]+$", max_length=512)
    source_updated_at: datetime
    normalized_source_type: str = Field(min_length=1, max_length=64)
    asset_url: str | None = Field(default=None, max_length=4096)
    controlled_file_path: str | None = Field(default=None, max_length=4096)
    source_file_sha256: str | None = Field(default=None, pattern=SHA256)
    full_text_sha256: str | None = Field(default=None, pattern=SHA256)
    content_sha256: str = Field(pattern=SHA256)
    extractor_version: str = Field(min_length=1, max_length=64)

class SourceVisualRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    source_id: str
    source_updated_at: datetime
    source_file_sha256: str | None = Field(default=None, pattern=SHA256)
    content_sha256: str = Field(pattern=SHA256)
    asset_sha256: str = Field(pattern=SHA256)
    asset_relpath: str = Field(min_length=1, max_length=512)
    origin: SourceVisualOrigin
    source_locator: SourceVisualLocator
    extractor_version: str = Field(min_length=1, max_length=64)
    alt_text: str = Field(min_length=1, max_length=300)
    width: int = Field(ge=1, le=1280)
    height: int = Field(ge=1, le=720)
    mime_type: Literal["image/webp"] = "image/webp"
    created_at: datetime
    updated_at: datetime
```

Define the claim, operation, prepared-asset, API request, response, status, and job models with `extra="forbid"`; use lowercase 64-character hashes, request IDs `1..256`, operation `refresh | delete`, outcomes `queued | replayed | deleted | failed`, status state `queued | processing | unavailable | failed`, and no raw path/source-text response fields. `SourceVisualStatusResponse` contains only state, optional opaque command ID, optional bounded error code, and updated timestamp.

- [ ] **Step 4: Add migration 46 with exact bounds and indexes**

The up migration must define:

```surql
DEFINE TABLE IF NOT EXISTS source_visual_cache SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS schema_version ON TABLE source_visual_cache TYPE int DEFAULT 1 ASSERT $value = 1;
DEFINE FIELD IF NOT EXISTS source_id ON TABLE source_visual_cache TYPE record<source>;
DEFINE FIELD IF NOT EXISTS source_updated_at ON TABLE source_visual_cache TYPE datetime;
DEFINE FIELD IF NOT EXISTS source_file_sha256 ON TABLE source_visual_cache TYPE option<string> ASSERT $value = NONE OR string::matches($value, "^[0-9a-f]{64}$");
DEFINE FIELD IF NOT EXISTS content_sha256 ON TABLE source_visual_cache TYPE string ASSERT string::matches($value, "^[0-9a-f]{64}$");
DEFINE FIELD IF NOT EXISTS asset_sha256 ON TABLE source_visual_cache TYPE string ASSERT string::matches($value, "^[0-9a-f]{64}$");
DEFINE FIELD IF NOT EXISTS asset_relpath ON TABLE source_visual_cache TYPE string ASSERT string::len($value) >= 1 AND string::len($value) <= 512;
DEFINE FIELD IF NOT EXISTS origin ON TABLE source_visual_cache TYPE string ASSERT $value IN ["embedded", "video_frame", "audio_artwork"];
DEFINE FIELD IF NOT EXISTS source_locator ON TABLE source_visual_cache FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS extractor_version ON TABLE source_visual_cache TYPE string ASSERT string::len($value) >= 1 AND string::len($value) <= 64;
DEFINE FIELD IF NOT EXISTS alt_text ON TABLE source_visual_cache TYPE string ASSERT string::len($value) >= 1 AND string::len($value) <= 300;
DEFINE FIELD IF NOT EXISTS width ON TABLE source_visual_cache TYPE int ASSERT $value >= 1 AND $value <= 1280;
DEFINE FIELD IF NOT EXISTS height ON TABLE source_visual_cache TYPE int ASSERT $value >= 1 AND $value <= 720;
DEFINE FIELD IF NOT EXISTS mime_type ON TABLE source_visual_cache TYPE string ASSERT $value = "image/webp";
DEFINE FIELD IF NOT EXISTS created_at ON TABLE source_visual_cache TYPE datetime;
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE source_visual_cache TYPE datetime;
DEFINE INDEX IF NOT EXISTS idx_source_visual_identity ON TABLE source_visual_cache COLUMNS source_id, content_sha256 UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_source_visual_updated ON TABLE source_visual_cache COLUMNS updated_at;
```

Also define claim identity, owner token, 90-second lease deadline, optional `record<command>`, and operation receipt fields/indexes matching the contracts. The down migration removes operation, claim, then cache and nothing else.

- [ ] **Step 5: Run GREEN and commit**

Run the Step 2 commands plus:

```bash
uv run ruff check deeper_notebook/source_visuals api/schemas/source_visuals.py tests/test_source_visual_contracts.py
git diff --check
```

Expected: all selected tests pass and Ruff/diff-check exit 0.

Commit:

```bash
git add -f deeper_notebook/database/migrations/46.surrealql deeper_notebook/database/migrations/46_down.surrealql
git add deeper_notebook/feature_flags.py deeper_notebook/source_visuals api/schemas/source_visuals.py tests/test_evidence_studio_foundation.py tests/test_migration_discovery.py tests/test_source_visual_contracts.py frontend/src/lib/features.ts frontend/src/lib/features.test.ts frontend/src/lib/features-build-contract.test.ts
git commit -m "feat(sources): define visual cache contracts"
```

---

### Task 2: Canonical source authority, claims, and operation receipts

**Files:**
- Create: `deeper_notebook/source_visuals/authority.py`
- Create: `deeper_notebook/source_visuals/repository.py`
- Create: `tests/test_source_visual_authority.py`
- Create: `tests/test_source_visual_repository.py`

**Interfaces:**
- Consumes: Task 1 contracts and migration.
- Produces: `async compute_source_visual_authority(source: Source) -> SourceVisualAuthority`.
- Produces: `SourceVisualAuthorityError` and `SourceVisualConflictError` with bounded public error codes and no source text/path payload.
- Produces: `SourceVisualRepository.acquire_claim`, `bind_command`, `renew_claim`, `complete_claim`, `release_claim`, `record_operation`, `get_operation`, `list_current`, `publish_ready`, `delete_ready`.
- `list_current(revisions: Mapping[str, datetime])` performs one query and never hashes content.

- [ ] **Step 1: Write RED authority tests**

Cover canonical JSON stability, explicit `null` fields, full-text change, source revision change, file-byte change, file changing during hash, symlink, non-regular file, sibling-prefix path, and outside-upload-root rejection.

```python
def test_canonical_fingerprint_is_stable_and_versioned():
    left = canonical_fingerprint_payload(
        source_id="source:one", normalized_source_type="upload",
        asset_url=None, source_file_sha256="a" * 64,
        full_text_sha256="b" * 64, extractor_version="source-visual-v1",
    )
    right = canonical_fingerprint_payload(
        full_text_sha256="b" * 64, source_file_sha256="a" * 64,
        asset_url=None, normalized_source_type="upload",
        source_id="source:one", extractor_version="source-visual-v1",
    )
    assert left == right
    assert fingerprint_payload(left) == fingerprint_payload(right)
```

- [ ] **Step 2: Write RED repository tests for one-query projection and fenced leases**

Test exact cases: first acquire, same-owner renewal, live-owner contention, expired takeover, old-owner renew/complete rejection, command CAS, exact operation replay, request conflict, malformed row omission, and stale `source_updated_at` omission.

```python
@pytest.mark.asyncio
async def test_list_current_uses_source_revision_without_hashing(monkeypatch):
    repository = SourceVisualRepository()
    query = AsyncMock(return_value=[READY_ROW])
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    result = await repository.list_current({"source:one": SOURCE_UPDATED})
    assert result["source:one"].source_updated_at == SOURCE_UPDATED
    assert query.await_count == 1
```

- [ ] **Step 3: Run RED**

```bash
uv run pytest -q tests/test_source_visual_authority.py tests/test_source_visual_repository.py
```

Expected: collection fails on missing modules and interfaces.

- [ ] **Step 4: Implement streamed authority hashing and exact-root validation**

Use 1 MiB reads, `os.open(..., O_RDONLY | O_NOFOLLOW)` where available, `fstat` before/after, regular-file mode checks, exact `Path.is_relative_to(upload_root)`, and canonical compact JSON:

```python
def fingerprint_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def canonical_fingerprint_payload(*, source_id: str, normalized_source_type: str,
                                  asset_url: str | None, source_file_sha256: str | None,
                                  full_text_sha256: str | None,
                                  extractor_version: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_id": source_id,
        "source_type": normalized_source_type,
        "asset_url": asset_url,
        "source_file_sha256": source_file_sha256,
        "full_text_sha256": full_text_sha256,
        "extractor_version": extractor_version,
    }
```

- [ ] **Step 5: Implement owner-fenced Surreal transactions**

Use parameter-bound record IDs and one transaction per state change. `acquire_claim` must create or take over only when `lease_until <= now`; `bind_command`, renewal, completion, and release require exact `owner_token`. `record_operation` creates deterministic `source_visual_operation:<sha256>` and validates an existing row against the complete bound payload before returning replay.

```python
def claim_identity(source_id: str, content_sha256: str, extractor_version: str) -> str:
    return hashlib.sha256(f"{source_id}\0{content_sha256}\0{extractor_version}".encode()).hexdigest()

def operation_identity(source_id: str, request_id: str, operation: str) -> str:
    return hashlib.sha256(f"{source_id}\0{request_id}\0{operation}".encode()).hexdigest()
```

The query must compare `source.updated` in the same transaction before publishing a ready row. `list_current` accepts at most 200 revisions, binds them as variables, and validates each row independently.

- [ ] **Step 6: Run GREEN and commit**

```bash
uv run pytest -q tests/test_source_visual_contracts.py tests/test_source_visual_authority.py tests/test_source_visual_repository.py
uv run ruff check deeper_notebook/source_visuals tests/test_source_visual_authority.py tests/test_source_visual_repository.py
git diff --check
git add deeper_notebook/source_visuals tests/test_source_visual_authority.py tests/test_source_visual_repository.py
git commit -m "feat(sources): bind visual extraction authority"
```

---

### Task 3: Controlled derivative storage, deletion, and eviction

**Files:**
- Create: `deeper_notebook/source_visuals/storage.py`
- Create: `deeper_notebook/source_visuals/cleanup.py`
- Create: `tests/test_source_visual_storage.py`

**Interfaces:**
- Produces: `SourceVisualStore.stage`, `publish`, `read_exact`, `tombstone`, `restore_tombstone`, `remove_tombstone`.
- Produces: `SourceVisualCleanup.reconcile_tombstones(limit=100)` and `evict_to_budget(max_bytes=2 * 1024**3, page_size=100)`.
- All methods consume validated hashes/records, never caller paths.

- [ ] **Step 1: Write RED storage tests**

Cover canonical relative path, exclusive temp creation, fsync-before-rename, asset-byte hash mismatch, symlinked root/segment/file, sibling-prefix paths, non-regular files, replacement crash windows, DB delete failure restore, unlink failure tombstone retry, malformed tombstones, active-read race, bounded cleanup, oldest-first eviction, and proof that source files are unchanged.

```python
def test_asset_relpath_contains_only_derived_hash_segments():
    relpath = asset_relpath("source:one", "a" * 64, "b" * 64)
    assert relpath == f"{sha256(b'source:one').hexdigest()[:2]}/{'a' * 64}/{'b' * 64}.webp"
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest -q tests/test_source_visual_storage.py
```

Expected: missing storage/cleanup modules.

- [ ] **Step 3: Implement exact-root atomic storage**

Resolve the root from `DATA_FOLDER/source-visual-cache/v1`, reject a symlink root, create a marked task temp directory inside the root, write with `O_CREAT | O_EXCL`, flush and `os.fsync`, reopen and hash, atomically `os.replace` to the validated canonical path, fsync the parent directory, and return only `asset_relpath` plus verified metadata.

Use tombstone names matching exactly:

```python
TOMBSTONE = re.compile(r"^\.expired-([0-9a-f]{16})-([0-9a-f]{64})\.webp$")
```

Deletion order is rename exact asset -> conditionally delete exact DB row -> unlink tombstone; DB failure restores the original name. Cleanup never follows symlinks and processes at most 100 task-owned tombstones per sweep.

- [ ] **Step 4: Implement bounded eviction**

Fetch at most 100 ready records ordered `updated_at ASC`; validate file/hash and skip active claim identities. Delete one exact derived record/file at a time until under `2 GiB`; stop if a page makes no progress. Never traverse source uploads or accept arbitrary roots.

- [ ] **Step 5: Run GREEN and commit**

```bash
uv run pytest -q tests/test_source_visual_storage.py tests/test_source_visual_repository.py
uv run ruff check deeper_notebook/source_visuals tests/test_source_visual_storage.py
git diff --check
git add deeper_notebook/source_visuals/storage.py deeper_notebook/source_visuals/cleanup.py tests/test_source_visual_storage.py
git commit -m "feat(sources): contain visual cache files"
```

---

### Task 4: Bounded PDF, video, and audio extraction

**Files:**
- Create: `deeper_notebook/source_visuals/media.py`
- Create: `deeper_notebook/source_visuals/extractors.py`
- Create: `scripts/create_source_visual_fixtures.py`
- Create: `tests/test_source_visual_media.py`
- Create: `tests/test_source_visual_extractors.py`
- Create: `tests/fixtures/source_visuals/fixture.pdf`
- Create: `tests/fixtures/source_visuals/fixture.mp4`
- Create: `tests/fixtures/source_visuals/fixture-artwork.m4a`

**Interfaces:**
- Produces: `VisualCandidate(origin, locator, encoded_bytes, score, stable_key)`.
- Produces: `extract_pdf_candidates`, `extract_video_candidates`, `extract_audio_artwork`, `select_candidate`, `prepare_webp`.
- Produces: `SourceVisualMediaError` with a bounded non-path error code.
- Uses PyMuPDF, Pillow, and `imageio_ffmpeg.get_ffmpeg_exe()` only.

- [ ] **Step 1: Create tiny deterministic media fixtures and RED tests**

Generate fixtures once with `uv run python scripts/create_source_visual_fixtures.py`, commit the script and bounded fixture bytes, and assert their SHA-256 values in tests. The script writes only the three exact fixture paths listed above, refuses existing unexpected files, uses fixed colors/metadata/timestamps, and verifies output size before exit. Tests cover first-24-page/64-candidate bounds, duplicate hashes, tiny/extreme/alpha-only rejection, deterministic PDF ranking, exactly three deterministic video timestamps, 15-second attempt timeout, 60-second total timeout, embedded artwork only, and no full audio decode.

Security tests must include PNG/JPEG/WebP success plus SVG, animated GIF/WebP, decompression-bomb warning, >40MP header, polyglot, truncated input, unsupported codec, non-image stream, and >1.5 MiB output failure.

- [ ] **Step 2: Run RED**

```bash
uv run pytest -q tests/test_source_visual_media.py tests/test_source_visual_extractors.py
```

Expected: missing media/extractor modules.

- [ ] **Step 3: Implement the decoder boundary**

Set `Image.MAX_IMAGE_PIXELS = 40_000_000`; convert `Image.DecompressionBombWarning` to error inside a scoped warnings context; reject `is_animated`/`n_frames != 1`, SVG signatures, unsupported Pillow formats, invalid dimensions, and alpha-only images. Apply EXIF orientation, convert to sRGB RGB, contain within 1280x720 with a neutral letterbox, and encode WebP through a deterministic quality ladder until bytes are <=1.5 MiB.

```python
WEBP_QUALITIES = (86, 80, 74, 68, 60, 52)
MAX_OUTPUT_BYTES = 1_572_864
MAX_PIXELS = 40_000_000
```

- [ ] **Step 4: Implement bounded subprocess extraction**

Invoke ffmpeg with `asyncio.create_subprocess_exec`, never `shell=True`; pass `-nostdin`; cap stdout/stderr; terminate then kill on timeout; and validate returned bytes through the same decoder. Video duration parsing accepts only the bounded `Duration: HH:MM:SS.xx` form. Candidate timestamps are 25%, 50%, and 75% of positive duration, deduplicated and capped at three. Audio uses only `-map 0:v:0 -frames:v 1` and fails to typographic fallback when no attached picture exists.

- [ ] **Step 5: Implement deterministic scoring and selection**

Score resolution, edge variance, exposure distance, and non-uniformity with fixed weights. Sort descending score, then locator, resource ID, and SHA-256; never use randomness or model inference. Neutral alt text is derived only from bounded title, source kind, origin label, and locator.

- [ ] **Step 6: Run GREEN and commit**

```bash
uv run pytest -q tests/test_source_visual_media.py tests/test_source_visual_extractors.py
uv run ruff check deeper_notebook/source_visuals tests/test_source_visual_media.py tests/test_source_visual_extractors.py
uv run bandit -q -r deeper_notebook/source_visuals
git diff --check
git add deeper_notebook/source_visuals scripts/create_source_visual_fixtures.py tests/test_source_visual_media.py tests/test_source_visual_extractors.py tests/fixtures/source_visuals
git commit -m "feat(sources): extract bounded local visuals"
```

---

### Task 5: Durable queue handoff and extraction command

**Files:**
- Create: `deeper_notebook/source_visuals/queue.py`
- Create: `deeper_notebook/source_visuals/service.py`
- Create: `commands/source_visual_commands.py`
- Modify: `commands/__init__.py`
- Modify: `commands/source_commands.py`
- Create: `tests/test_source_visual_command.py`
- Create: `tests/test_source_visual_ingest_handoff.py`

**Interfaces:**
- Produces: `async submit_source_visual(source_id, request_id, *, explicit: bool) -> SourceVisualJobResponse`.
- Produces command `extract_source_visual` under the existing compatibility
  app identity from `deeper_notebook.identity.LEGACY_COMMAND_APP`.
- Command input strictly includes source ID, request ID, expected content hash, extractor version, and 64-character claim-owner token.
- Command output contains only source/command IDs, hashes, origin, dimensions, duration, outcome, and bounded error code.

- [ ] **Step 1: Write RED tests for contention, replay, lease takeover, and ingest isolation**

Test two independent submitters, same request replay, different request/live-claim convergence, conflicting operation payload 409 domain error, failure before queue insertion, failure after queue insertion before claim bind, worker restart takeover, owner fencing, global semaphore of two, per-fingerprint serialization, cancellation cleanup, and success/failure never changing source content.

Assert `process_source_command` remains successful when visual queue submission raises and does not submit when the backend flag is off.

- [ ] **Step 2: Run RED**

```bash
uv run pytest -q tests/test_source_visual_command.py tests/test_source_visual_ingest_handoff.py
```

Expected: missing queue/service/command registration.

- [ ] **Step 3: Implement claim-before-submit queueing**

Compute authority, record/replay the refresh operation, acquire the deterministic claim with a fresh cryptographic owner token, submit through `surreal_commands.submit_command` inside `asyncio.to_thread` with a 10-second timeout, then CAS-bind the returned `record<command>`. If submission fails, release only the exact owned claim and mark the exact operation failed. A live claim returns its already-bound command or a bounded queued receipt; it never starts a second job.

After an explicit delete, replay of the deterministic `ingest:<content_sha256>` operation returns its prior receipt and does not recreate the asset. A new explicit refresh request ID may acquire the expired completed claim, clear/bind a new command under owner fencing, and recreate the derivative. Test both paths across a worker restart.

- [ ] **Step 4: Implement the command service flow**

Inside a process-wide `asyncio.Semaphore(2)`, recompute authority, reject stale expected fingerprint, renew the 90-second lease before/after candidate enumeration and before publication, prepare and publish the exact derivative, complete the owner-fenced claim, and run bounded eviction. On cancellation or typed extraction failure, remove only task temp data, release/complete only the exact owner, and return a bounded failure code.

```python
from deeper_notebook.identity import LEGACY_COMMAND_APP

@command("extract_source_visual", app=LEGACY_COMMAND_APP, retry={
    "max_attempts": 3,
    "wait_strategy": "exponential_jitter",
    "wait_min": 1,
    "wait_max": 10,
    "stop_on": [SourceVisualAuthorityError, SourceVisualMediaError],
})
async def extract_source_visual_command(input_data: ExtractSourceVisualInput) -> ExtractSourceVisualOutput:
    return await SourceVisualService().execute(input_data)
```

- [ ] **Step 5: Add best-effort post-ingest handoff**

After authoritative `process_source_command` success and before returning its existing output, call `submit_source_visual` only when the backend flag is on. Use deterministic auto request ID `ingest:<content_sha256>`. Catch/log a bounded visual error code without source text or path and never alter source-processing success.

- [ ] **Step 6: Run GREEN and commit**

```bash
uv run pytest -q tests/test_source_visual_command.py tests/test_source_visual_ingest_handoff.py tests/test_source_processing_progress.py tests/test_live_source_ingestion_smoke.py
uv run ruff check deeper_notebook/source_visuals commands/source_visual_commands.py commands/source_commands.py tests/test_source_visual_command.py tests/test_source_visual_ingest_handoff.py
git diff --check
git add deeper_notebook/source_visuals commands/__init__.py commands/source_commands.py commands/source_visual_commands.py tests/test_source_visual_command.py tests/test_source_visual_ingest_handoff.py
git commit -m "feat(sources): queue visual extraction safely"
```

---

### Task 6: Source projection and strict visual API

**Files:**
- Create: `api/source_visual_projection.py`
- Create: `api/routers/source_visuals.py`
- Modify: `api/main.py`
- Modify: `api/models.py`
- Modify: `api/routers/sources.py`
- Modify: `api/routers/search.py`
- Modify: `api/schemas/capture.py`
- Modify: `api/routers/capture.py`
- Create: `tests/test_source_visual_api.py`
- Create: `tests/test_source_visual_projection.py`

**Interfaces:**
- Produces optional `visual: SourceVisualReceiptResponse | None` and `visual_status: SourceVisualStatusResponse | None` on source list/detail and source-bearing search results.
- Produces `GET /sources/{source_id}/visual`, `POST /sources/{source_id}/visual:refresh`, `DELETE /sources/{source_id}/visual`.
- Capture list may include `linked_source` only when an item's existing full-file SHA-256 exactly matches a current cache row's `source_file_sha256`; it does not create or mutate a source.

- [ ] **Step 1: Write RED projection/API tests**

Cover one batch query for 30 sources, no body/file hash on list/detail, stale revision omission, malformed row omission, detail/list parity, safe queued/processing/unavailable/failed status projection, raw worker-error suppression, ready visual clearing status, exact source-bearing search projection, bounded capture SHA-to-source batch matching, asset 200/ETag/immutable headers, matching `If-None-Match` 304, missing file/hash/MIME/fingerprint failures, refresh replay/conflict, delete replay/conflict, delete-then-auto-ingest no-recreation, delete-then-new-explicit-refresh recreation, DB/file crash windows, feature-off uniform 404 before payload validation, missing source 404, and no cache mutation on GET.

- [ ] **Step 2: Run RED**

```bash
uv run pytest -q tests/test_source_visual_projection.py tests/test_source_visual_api.py
```

Expected: missing projection/router and response fields.

- [ ] **Step 3: Implement one-query projections**

`project_source_visuals(rows)` builds `{source_id: updated}` from at most 200 returned rows, calls `SourceVisualRepository.list_current` once, validates cache plus current claim/command status from that one query, and returns immutable opaque URLs plus bounded status only:

```python
def visual_asset_url(source_id: str, asset_sha256: str) -> str:
    token = hashlib.sha256(f"{source_id}\0{asset_sha256}".encode()).hexdigest()
    return f"/api/sources/{quote(source_id, safe='')}/visual?v={token}"
```

Do not expose `asset_relpath` or `source_file_sha256`. Integrate the projection after each existing source list/detail row is authoritative. Search projects only source-bearing parent IDs. Capture binds at most 200 existing item SHA values into one query, matches them only to current cache/source revisions, and attaches an already-projected linked source; unmatched items stay unchanged.

- [ ] **Step 4: Implement strict endpoints**

Register a separate router under `/sources`. Run the feature guard before request-body or record parsing. GET loads source + current row, recomputes full authority, validates controlled cache path/hash/size/MIME, supports exact ETag, and streams bytes with:

```python
headers = {
    "ETag": f'"{record.asset_sha256}"',
    "Cache-Control": "private, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
}
```

Refresh delegates to Task 5 queue and returns `202` for new work or `200` for replay. Delete uses Task 3 tombstone flow plus Task 2 operation receipt. Map typed stale/conflict/corrupt authority to `409`; never return raw paths or decoder details.

- [ ] **Step 5: Run GREEN and commit**

```bash
uv run pytest -q tests/test_source_visual_projection.py tests/test_source_visual_api.py tests/test_sources_api.py tests/test_capture_inbox.py tests/test_capture_routing.py tests/test_search_api.py
uv run ruff check api deeper_notebook/source_visuals tests/test_source_visual_api.py tests/test_source_visual_projection.py
uv run python -m compileall -q api deeper_notebook/source_visuals commands/source_visual_commands.py
git diff --check
git add api deeper_notebook/source_visuals tests/test_source_visual_api.py tests/test_source_visual_projection.py
git commit -m "feat(sources): expose derived visual receipts"
```

---

### Task 7: Strict frontend decoder, API methods, and query hooks

**Files:**
- Create: `frontend/src/lib/types/source-visuals.ts`
- Create: `frontend/src/lib/api/source-visuals.ts`
- Create: `frontend/src/lib/api/source-visuals.test.ts`
- Modify: `frontend/src/lib/types/api.ts`
- Modify: `frontend/src/lib/types/search.ts`
- Modify: `frontend/src/lib/api/sources.ts`
- Modify: `frontend/src/lib/api/query-client.ts`
- Modify: `frontend/src/lib/hooks/use-sources.ts`
- Create: `frontend/src/lib/hooks/use-source-visuals.ts`

**Interfaces:**
- Produces `SourceVisualReceipt`, `SourceVisualStatus`, `decodeSourceVisual`, `decodeSourceVisualStatus`, `decodeSourceWithVisual`.
- Produces `sourceVisualsApi.refresh(sourceId, requestId)` and `.remove(sourceId, requestId)`.
- Produces `useRefreshSourceVisual`, `useRemoveSourceVisual`, and `useRecentVisualSources(limit)`.

- [ ] **Step 1: Write RED decoder and mutation tests**

Test every valid origin/locator/status, unknown origin/status, unknown keys, malformed/non-lowercase hashes, zero/oversized dimensions, wrong MIME, empty/oversized alt, external/absolute/path-bearing asset URL, invalid timestamp/page/resource ID, raw error text rejection, and fail-soft source decoding. Test encoded source IDs, request ID stability across mutation retry, exact invalidation of list/detail/visual keys, and 4xx no-auto-retry.

```ts
it('drops an invalid visual without dropping its source', () => {
  const source = decodeSourceWithVisual({ ...SOURCE, visual: { ...VISUAL, mime_type: 'image/svg+xml' } })
  expect(source.id).toBe('source:one')
  expect(source.visual).toBeNull()
})
```

- [ ] **Step 2: Run RED**

```bash
cd frontend && npx vitest run src/lib/api/source-visuals.test.ts src/lib/api/sources.test.ts src/lib/hooks/use-sources.test.tsx
```

Expected: missing decoder/API/hooks.

- [ ] **Step 3: Implement Zod strict decoding**

Use `.strict()` schemas, lowercase hash regex, `z.literal('image/webp')`, dimensions bounded to 1280x720, and a relative opaque URL regex restricted to `/api/sources/<encoded-id>/visual?v=<64hex>`. Model the locator as a discriminated union by origin and reject extra/multiple locator keys. Strictly decode status from the four known states with a bounded error-code regex; wrap only `visual` and `visual_status` parsing in `safeParse`; preserve the strict source response.

- [ ] **Step 4: Implement API and query ownership**

Decode list/get/search/capture source-bearing responses at the API boundary. Generate one request ID when a user action begins and reuse it for React Query retries. On success invalidate all source-list families, exact detail, visual key, and source-bearing search/capture queries. `useRecentVisualSources` calls the existing source list with `limit <= 4` only when both frontend flags are enabled.

- [ ] **Step 5: Run GREEN and commit**

```bash
cd frontend && npx vitest run src/lib/api/source-visuals.test.ts src/lib/api/sources.test.ts src/lib/hooks/use-sources.test.tsx
cd frontend && npx tsc --noEmit
cd frontend && npx eslint src/lib/types/source-visuals.ts src/lib/api/source-visuals.ts src/lib/hooks/use-source-visuals.ts src/lib/api/sources.ts src/lib/hooks/use-sources.ts
git diff --check
git add frontend/src/lib
git commit -m "feat(ui): decode source visual receipts"
```

---

### Task 8: Shared covers, provenance, adaptive gallery, and Evidence Peek

**Files:**
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceVisualProvenance.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceCover.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/EvidencePeek.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceGallery.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/source-gallery.css`
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceCover.test.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/EvidencePeek.test.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/SourceGallery.test.tsx`
- Modify: `frontend/src/app/globals.css`

**Interfaces:**
- `SourceCover({ source, variant, priority, onOpen, onRefresh, onRemove })` owns image/fallback state.
- `SourceGallery({ sources, selectedId, onSelect, onOpen, onRefresh, onRemove, filters })` owns layout only and never fetches.
- `EvidencePeek({ sourceId, title, evidenceQuery, onClose })` calls the existing passage locator, retains scroll, and restores invoker focus.

- [ ] **Step 1: Write RED component tests**

Cover each origin label, useful accessible image name, typographic fallback for null/invalid/broken image, fixed aspect ratio before load, lazy non-priority images, queued/processing/failed/unavailable status copy after reload, raw error-code-to-safe-copy mapping, dispatch-once refresh/remove, disabled same-identity refresh, visible provenance, feature-card selection, compact reflow class contract, high contrast, reduced motion, no decorative motion, Evidence Peek exact query/snippet, unavailable state, Escape close, and invoker focus return.

- [ ] **Step 2: Run RED**

```bash
cd frontend && npx vitest run src/components/deeper-notebook/source-gallery/*.test.tsx
```

Expected: missing components.

- [ ] **Step 3: Implement SourceCover and provenance**

Render `<img>` only for a valid receipt. Set width/height, `loading={priority ? 'eager' : 'lazy'}`, `decoding="async"`, useful alt containing title + origin, and a one-way `onError` fallback. Typographic fallback uses real DOM title/type/status and `aria-hidden` decorative shapes. Origin text is exactly `Embedded image`, `Video frame`, or `Embedded artwork`.

- [ ] **Step 4: Implement adaptive hybrid CSS**

Use a named inline-size container and bounded auto-fit tracks:

```css
.dn-source-gallery { container: source-gallery / inline-size; }
.dn-source-gallery__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr));
  gap: clamp(.75rem, 2cqi, 1.25rem);
}
@container source-gallery (min-width: 64rem) {
  .dn-source-gallery__card[data-featured='true'] { grid-column: span 2; grid-row: span 2; }
}
@container source-gallery (max-width: 34rem) {
  .dn-source-gallery__card { grid-template-columns: 6rem minmax(0, 1fr); }
}
```

Retain minimum 44px action targets, `min-width: 0`, wrapping before truncation, no horizontal overflow, no carousel/parallax/auto-advance, and scoped short-height spacing only.

- [ ] **Step 5: Implement Evidence Peek without imagery inference**

Call `sourcesApi.locatePassage(sourceId, evidenceQuery)` only when an existing source summary/match provides a query. Display the returned exact snippet and score label; never derive a claim from the cover. Preserve document/gallery scroll and restore focus on close.

- [ ] **Step 6: Run GREEN and commit**

```bash
cd frontend && npx vitest run src/components/deeper-notebook/source-gallery/*.test.tsx
cd frontend && npx tsc --noEmit
cd frontend && npx eslint src/components/deeper-notebook/source-gallery
git diff --check
git add frontend/src/components/deeper-notebook/source-gallery frontend/src/app/globals.css
git commit -m "feat(ui): add adaptive source gallery"
```

---

### Task 9: Sources and Notebook route adoption with exact rollback

**Files:**
- Modify: `frontend/src/app/(dashboard)/sources/page.tsx`
- Modify: `frontend/src/app/(dashboard)/sources/page.test.tsx`
- Modify: `frontend/src/components/sources/SourceCard.tsx`
- Modify: `frontend/src/components/sources/SourceCard.test.tsx`
- Modify: `frontend/src/app/(dashboard)/notebooks/components/SourcesColumn.tsx`
- Create: `frontend/src/app/(dashboard)/notebooks/components/SourcesColumn.visuals.test.tsx`

**Interfaces:**
- Sources route renders `SourceGallery` only when V2 and source-visual flags are true; the exact current table remains the else branch.
- Notebook `SourceCard` uses `SourceCover variant="compact"` under the same flag gate and preserves existing selection/context/menu behavior.

- [ ] **Step 1: Write RED route tests**

Assert V2+visuals renders the adaptive gallery, feature card, provenance, fallback states, and dispatch-once actions. Assert either flag off renders the existing source grid/table, makes no visual mutation call, retains keyboard navigation and exact existing source actions. Notebook tests must prove selection, context toggles, delete/remove/retry, virtualization threshold, infinite scroll, and drag/drop are unchanged.

- [ ] **Step 2: Run RED**

```bash
cd frontend && npx vitest run 'src/app/(dashboard)/sources/page.test.tsx' src/components/sources/SourceCard.test.tsx 'src/app/(dashboard)/notebooks/components/SourcesColumn.visuals.test.tsx'
```

Expected: gallery/compact cover assertions fail.

- [ ] **Step 3: Integrate through one explicit flag branch**

Keep current data loading, pagination, sort state, delete confirmation, source-create callback, and keyboard behavior. Under the enabled branch, pass existing sources/actions into `SourceGallery`; do not add an independent fetch. In `SourceCard`, insert compact `SourceCover` without changing the outer interactive element or adding nested buttons.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd frontend && npx vitest run 'src/app/(dashboard)/sources/page.test.tsx' src/components/sources/SourceCard.test.tsx 'src/app/(dashboard)/notebooks/[id]/page.test.tsx' 'src/app/(dashboard)/notebooks/components/SourcesColumn.visuals.test.tsx'
cd frontend && npx tsc --noEmit
cd frontend && npx eslint 'src/app/(dashboard)/sources/page.tsx' src/components/sources/SourceCard.tsx 'src/app/(dashboard)/notebooks/components/SourcesColumn.tsx'
git diff --check
git add frontend/src/app/'(dashboard)'/sources frontend/src/app/'(dashboard)'/notebooks/components frontend/src/components/sources
git commit -m "feat(ui): surface visuals in source workspaces"
```

---

### Task 10: Knowledge, Search, and Capture compact treatments

**Files:**
- Modify: `frontend/src/app/(dashboard)/knowledge/page.tsx`
- Create: `frontend/src/app/(dashboard)/knowledge/page.test.tsx`
- Modify: `frontend/src/app/(dashboard)/search/page.tsx`
- Modify: `frontend/src/app/(dashboard)/search/page.test.tsx`
- Modify: `frontend/src/components/capture/CaptureInbox.tsx`
- Modify: `frontend/src/components/capture/CaptureItemRow.tsx`
- Modify: `frontend/src/components/capture/CaptureItemRow.test.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/RecentSourceStrip.tsx`
- Create: `frontend/src/components/deeper-notebook/source-gallery/RecentSourceStrip.test.tsx`

**Interfaces:**
- Knowledge page owns the optional recent-source query and passes typed sources to `RecentSourceStrip`; the component never fetches.
- Search uses the already-decoded optional visual on source-bearing results only.
- Capture renders a compact cover only when the backend returns an exact `linked_source`; unlinked items retain current UI.

- [ ] **Step 1: Write RED integration tests**

Knowledge: enabled flags produce one bounded recent-source list call, compact covers, and no change to KnowledgeExplorer authority; either flag off produces no added call. Search: source results get covers/Evidence Peek, note/insight results do not, existing modal IDs remain exact. Capture: linked imported item gets a cover, unlinked/ready/duplicate items retain review routing, and no component guesses by filename/path.

- [ ] **Step 2: Run RED**

```bash
cd frontend && npx vitest run 'src/app/(dashboard)/knowledge/page.test.tsx' 'src/app/(dashboard)/search/page.test.tsx' src/components/capture/CaptureItemRow.test.tsx src/components/deeper-notebook/source-gallery/RecentSourceStrip.test.tsx
```

Expected: missing recent strip and compact integrations.

- [ ] **Step 3: Implement the route-owned data flow**

Knowledge calls `useRecentVisualSources(4)` only when both flags are enabled and renders the strip outside the canonical Vault editor. Search reads `result.visual` from its existing mutation response and uses `result.matches?.[0]` as the Evidence Peek query. Capture reads only `item.linked_source`; it never fetches by path, hashes a local file, or infers a source association in the browser.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd frontend && npx vitest run 'src/app/(dashboard)/knowledge/page.test.tsx' 'src/app/(dashboard)/search/page.test.tsx' src/components/capture/CaptureItemRow.test.tsx src/components/deeper-notebook/source-gallery/RecentSourceStrip.test.tsx
cd frontend && npx tsc --noEmit
cd frontend && npx eslint 'src/app/(dashboard)/knowledge/page.tsx' 'src/app/(dashboard)/search/page.tsx' src/components/capture src/components/deeper-notebook/source-gallery/RecentSourceStrip.tsx
git diff --check
git add frontend/src/app/'(dashboard)'/knowledge frontend/src/app/'(dashboard)'/search frontend/src/components/capture frontend/src/components/deeper-notebook/source-gallery
git commit -m "feat(ui): connect source visuals across research routes"
```

---

### Task 11: Exact browser state matrix, rollback ledger, and measured budgets

**Files:**
- Modify: `frontend/src/lib/visual-system/route-manifest.ts`
- Modify: `frontend/src/lib/visual-system/route-manifest.test.ts`
- Create: `frontend/e2e/fixtures/source-gallery.ts`
- Modify: `frontend/e2e/fixtures/visual-system.ts`
- Create: `frontend/e2e/source-gallery.spec.ts`
- Create: `frontend/scripts/measure-source-gallery-budgets.mjs`
- Create: `scripts/measure_source_visuals.py`
- Modify: `frontend/package.json`

**Interfaces:**
- Keeps the existing 22-route/264-cell Phase 1 matrix unchanged.
- Adds an explicit `SOURCE_GALLERY_CELLS` manifest covering enabled, ready, processing, failed, missing/corrupt, compact, and feature-off states for Sources, Notebook detail, Knowledge, Search, and Capture.
- Produces JSON budget receipts for JS/CSS gzip, CLS, extraction duration, cache bytes, and query counts.

- [ ] **Step 1: Write RED manifest/fixture/browser contracts**

The source-gallery fixture must reject wrong methods, unknown same-origin APIs, and all external requests. It must use exact per-cell method/path/frequency maps and serve actual bounded WebP fixtures with useful alt text/origin labels. RED browser assertions cover 320x844, 768x1024, 1020x631, and 1440x900; three Phase 1 themes; text/card/action four-edge containment; >=44px interactive targets; unique IDs; no broken images; no horizontal document overflow; strict scroll owner/advance/lower-content reachability; focus return; and dispatch exactly once.

Feature-off cells assert zero `/api/sources/*/visual` and zero visual mutation calls while the legacy route remains usable.

- [ ] **Step 2: Run RED**

```bash
cd frontend && npx vitest run src/lib/visual-system/route-manifest.test.ts
cd frontend && NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser --workers=1
```

Expected: manifest/fixture cases fail until routes expose Phase 2A UI.

- [ ] **Step 3: Implement exact fixture and cells**

Use only exact route handlers and canonical encoded source IDs. Record `{viewport, method, canonicalPath, status}` at the handler boundary. A wrong method returns 405 and records unexpected. Unknown APIs abort. External origins abort before path matching. Restore `test-results/.last-run.json` byte-for-byte after each run and remove only task-generated result directories.

- [ ] **Step 4: Add measured budget scripts**

`measure-source-gallery-budgets.mjs` compares explicit Phase 1 and Phase 2A Next build manifests, gzips only changed browser JS/CSS assets, and fails above +40 KiB JS or +24 KiB CSS. The Playwright spec records maximum CLS and fails above 0.05. `measure_source_visuals.py` runs deterministic fixtures, records per-kind duration/output bytes, verifies <=60s, and queries cache total <=2 GiB without mutating source rows.

- [ ] **Step 5: Run GREEN browser and rollback gates**

```bash
cd frontend && NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser --workers=1
cd frontend && NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 npx playwright test e2e/visual-system-matrix.spec.ts --project=mocked-browser --workers=1
cd frontend && NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 NEXT_PUBLIC_DN_SOURCE_VISUALS=0 npx playwright test e2e/source-gallery.spec.ts --project=mocked-browser --grep 'feature-off rollback' --workers=1
```

Expected: Source Gallery cells pass, Phase 1 stays 264/264, and explicit rollback passes with zero visual ledger entries.

- [ ] **Step 6: Run builds and budgets, then commit**

```bash
cd frontend && NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 NEXT_PUBLIC_DN_SOURCE_VISUALS=1 npm run build
cd frontend && NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=0 NEXT_PUBLIC_DN_SOURCE_VISUALS=0 npm run build
cd frontend && npm run test:feature-build-contract
cd frontend && node scripts/measure-source-gallery-budgets.mjs
uv run python scripts/measure_source_visuals.py
git diff --check
git add frontend/e2e frontend/src/lib/visual-system frontend/scripts/measure-source-gallery-budgets.mjs frontend/package.json scripts/measure_source_visuals.py
git commit -m "test(ui): prove source gallery visual contracts"
```

---

### Task 12: Real SurrealDB, security, full regression, and acceptance receipt

**Files:**
- Create: `tests/integration/test_source_visual_repository.py`
- Create: `docs/verification/2026-08-14-gemini-forward-phase-2a-source-gallery.md`
- Modify only if evidence requires: `scripts/rebrand-allowlist.json`
- Modify only if selector inventory requires: `scripts/rebrand_audit.py`

**Interfaces:**
- Produces a disposable real-database proof for migration, contention, crash windows, restart hydration, deletion, and downgrade.
- Produces the final acceptance receipt; no deployment/public-release claim.

- [ ] **Step 1: Write RED real-Surreal tests**

Use a fresh namespace/database. Test migration 46 up/down, schema-full extra-field rejection, unique cache identity, two-client claim contention, live-owner fencing, expired takeover, operation replay/conflict, command binding, concurrent ready publication, source update stale omission, file-before-DB and DB-before-cleanup crash recovery, deletion restore, restart hydration, bounded eviction, and downgrade/cache deletion leaving every source row byte-for-byte equivalent.

- [ ] **Step 2: Run RED then GREEN real-database proof**

```bash
SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_source_visual_repository.py -m integration_surreal
```

Expected after implementation: all tests pass against a disposable real SurrealDB instance and cleanup removes the namespace/container/listeners it owns.

- [ ] **Step 3: Run affected backend and frontend suites**

```bash
uv run pytest -q tests/test_source_visual_*.py tests/test_sources_api.py tests/test_capture_inbox.py tests/test_capture_routing.py tests/test_search_api.py tests/test_source_processing_progress.py tests/test_live_source_ingestion_smoke.py
uv run pytest -q tests/ --ignore=tests/integration
cd frontend && npm test -- --run
cd frontend && npm run lint
cd frontend && npx tsc --noEmit
```

Expected: all affected suites pass; full suites either pass or every unrelated pre-existing failure is reproduced at the pre-Phase-2A base and documented with exact selectors/logs.

- [ ] **Step 4: Run security, dependency, migration, identity, and secret gates**

```bash
uv lock --check
uv run ruff check api commands deeper_notebook/source_visuals tests/test_source_visual_*.py tests/integration/test_source_visual_repository.py
uv run python -m compileall -q api commands deeper_notebook/source_visuals
uv run bandit -q -r api/routers/source_visuals.py deeper_notebook/source_visuals commands/source_visual_commands.py
uv run python scripts/rebrand_audit.py --check
uv run pytest -q tests/test_product_identity.py tests/test_migration_discovery.py
git diff --check
gitleaks git --staged --redact --no-banner
```

Also export a frozen advisory input and run `pip-audit` without changing the lock. If the local `uvx`/ensurepip environment fails before audit, record the exact host failure and run a no-dependency audit that proves no new Phase 2A dependency was introduced.

- [ ] **Step 5: Perform fresh review and fix every Critical/Important finding**

Review the actual implementation diff against the approved spec and this plan. Use the project code-review framework when available; if Code Review Graph or Open Code Review is unavailable, record that and complete a native fresh-context review. Re-run the smallest RED/GREEN regressions for every accepted finding. Do not accept unresolved Critical or Important findings.

- [ ] **Step 6: Write the acceptance receipt**

Record commits, exact files, RED evidence, focused/full/backend/frontend/real-Surreal/browser/build/security/performance results, source-row preservation, feature-off zero-ledger proof, known warnings, unavailable third-party review evidence, and explicit non-goals. State clearly that native signed/notarized packaging, hosted CI, deployment, and public release remain outside Phase 2A unless separately authorized and proven.

- [ ] **Step 7: Stage exact scope, scan, and commit**

```bash
git status --short
git diff --cached --check
gitleaks git --staged --redact --no-banner
git commit -m "feat(ui): deliver local source visual gallery"
git diff --check HEAD^..HEAD
gitleaks git --log-opts='HEAD^..HEAD' --redact --no-banner
```

Expected: tracked worktree clean after commit; supplied `.codex/agent-context/*` remains untracked; no generated browser/build/cache artifacts are staged.

---

## Final Done Criteria

- [ ] Source visuals are source-derived, local, bounded, static WebP, visibly labeled, and never treated as evidence.
- [ ] Source list/detail reads are side-effect free, one-query projected, and revision-matched without source rehashing.
- [ ] Exact asset reads revalidate full authority and never accept a caller path.
- [ ] Cross-process claims, 90-second lease takeover, owner fencing, operation replay, command binding, and publication/deletion crash windows pass real SurrealDB tests.
- [ ] Typographic fallback preserves disabled, missing, queued, failed, stale, corrupt, and unsupported states without failing any route.
- [ ] Sources, Notebook, Knowledge, Search, and Capture integrations preserve their existing data/actions and add no independent component authority fetch.
- [ ] Existing Phase 1 264-cell matrix remains green; the Source Gallery matrix and explicit feature-off zero-request rollback are green.
- [ ] 44px targets, containment, scroll reachability, useful alt text, visible provenance, focus return, high contrast, reduced motion, and no horizontal overflow are proven.
- [ ] JS/CSS/CLS/extraction/cache budgets are measured and within the approved limits.
- [ ] Focused/full/static/build/identity/rebrand/security/secret gates are green or have exact reproduced pre-existing-only receipts.
- [ ] Fresh review reports no unresolved Critical or Important findings.
- [ ] Final commit and verification receipt are present; no deployment/public-release claim is made.
