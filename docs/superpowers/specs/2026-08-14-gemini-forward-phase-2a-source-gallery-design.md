# Gemini-Forward Phase 2A Source Gallery Design

**Date:** 2026-08-14

**Status:** Approved design; implementation requires a separate approved plan

**Product:** Deeper Notebook

**Phase:** 2A — source-derived imagery, provenance, and rebuildable cache

## 1. Decision Summary

Phase 2A adds the Visual Source Gallery and source-derived covers without
changing source authority or introducing image generation. The approved UI is
an adaptive hybrid: one selected or recent source may receive a larger,
evidence-rich treatment, while supporting sources use a responsive grid that
collapses toward compact rows as inline space narrows.

The extraction system runs as a separate bounded command after authoritative
source processing. Gallery reads remain side-effect free. A missing, stale,
disabled, or failed visual always renders a deterministic typographic cover;
image failure never fails a source route.

This phase includes:

- `source_visual_cache` as additive, rebuildable presentation metadata;
- embedded PDF imagery, bounded video frames, and embedded audio artwork;
- visible and accessible imagery-origin labels;
- `SourceCover`, `SourceGallery`, and Evidence Peek integration;
- Sources, Notebook, Knowledge, Search, and Capture route integration;
- exact rollback, security, performance, migration, and real-database proof.

This phase excludes local image generation, webpage screenshots, cloud image
providers, arbitrary SVG rendering, custom image uploads, Unified Artifact
Studio, and all Phase 3 work.

## 2. Authority and Privacy Boundary

`source` remains the sole source authority. Notebook references, source text,
assets, provenance, citations, artifacts, Study records, Podcast records, and
model routing retain their existing contracts.

Visual metadata is derived and disposable:

- visual creation never edits a source record;
- stale visual records are ignored when the source fingerprint changes;
- deleting a visual never deletes or rewrites the source;
- downgrade and feature-off paths ignore visual records safely;
- images are never interpreted as evidence;
- private source text is not written to prompts, logs, receipts, or filenames;
- no network image or generation provider is selected implicitly.

## 3. Feature and Rollback Contract

Phase 2A uses two explicit flags:

- backend: `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED`;
- frontend: `NEXT_PUBLIC_DN_SOURCE_VISUALS`.

Both flags default off until Phase 2A acceptance is complete. The frontend
gallery presentation requires the canonical Phase 1
`NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2` flag and the source-visuals flag. Explicit
`0` disables each flag.

Rules:

- V2 off preserves the current source cards and request ledger;
- source visuals off preserves current source cards even when V2 is on;
- backend feature-off mutation and asset endpoints return the uniform typed
  feature-unavailable response and perform no extraction or cache mutation;
- list/detail source responses keep the additive optional visual field absent
  or `null` when no valid record exists;
- no read request enqueues extraction;
- the cache table may remain after rollback and is ignored safely.

## 4. Source Fingerprint

Every extraction is bound to a canonical versioned fingerprint. The fingerprint
is SHA-256 over a canonical JSON payload containing:

- fingerprint schema version `1`;
- canonical source record ID;
- normalized source type;
- source asset URL when present;
- SHA-256 of the controlled source file when present;
- SHA-256 of `full_text` when present;
- extractor policy version.

The canonical JSON uses sorted keys, UTF-8, and compact separators. Missing
values are represented explicitly as `null`. A file hash is computed only after
the path has passed the existing upload-root containment checks. Symlinks,
non-regular files, disappearing files, and files outside the controlled uploads
root fail closed.

The record field remains named `content_sha256` to match the approved entire-app
design; it stores this versioned source-visual fingerprint rather than a hash of
one arbitrary source field.

## 5. Persistence Model

Migration `46` adds `source_visual_cache` as a schema-full table. Migration
`46_down` removes only that table and its indexes.

Each ready record contains:

- `schema_version: int` fixed to `1`;
- `source_id: record<source>`;
- `content_sha256: string` matching lowercase SHA-256;
- `asset_sha256: string` matching lowercase SHA-256;
- `asset_relpath: string` containing a bounded relative cache path only;
- `origin: embedded | video_frame | audio_artwork`;
- `source_locator: option<object>` with exactly one bounded page, timestamp, or
  embedded-resource identifier appropriate to the origin;
- `extractor_version: string` bounded to 64 characters;
- `alt_text: string` bounded to 300 characters;
- `width: int` in `1..1280`;
- `height: int` in `1..720`;
- `mime_type: string` fixed to `image/webp` for derived assets;
- `created_at: datetime`;
- `updated_at: datetime`.

The unique key is `(source_id, content_sha256)`. An index on `updated_at`
supports derived-only cache eviction. No pending or failed row is stored in the
cache table; job state remains in the existing command infrastructure.

Old records for stale fingerprints may be removed by bounded cleanup. Their
absence never affects source readability.

## 6. Controlled Asset Storage

Derived assets live under:

```text
DATA_FOLDER/source-visual-cache/v1/<source-id-sha256-prefix>/<content_sha256>/<asset_sha256>.webp
```

`asset_relpath` is always relative to `DATA_FOLDER/source-visual-cache/v1` and
contains only validated lowercase hash segments and the `.webp` suffix. The
service resolves both root and candidate, rejects symlink traversal and
non-regular files, and proves the candidate is beneath the exact root before
read, replacement, or deletion.

Writers use a task-owned temporary directory under the same controlled root,
write with exclusive creation, flush and fsync, verify the final bytes, then
rename atomically. Database publication occurs only after the final file is
valid. A replacement keeps the prior valid record and file until the new record
is committed.

Deletion uses a two-phase tombstone within the cache root: rename the exact
validated asset, conditionally delete its matching record, then unlink the
tombstone. A database failure restores the file. Bounded cleanup reconciles
only exact task-owned tombstones and never scans or deletes outside the cache
root.

## 7. Extraction Command

The existing command system gains `extract_source_visual`. Its input is strict
and bounded:

- canonical `source_id`;
- caller `request_id` no longer than 256 characters;
- expected `content_sha256`;
- extractor policy version.

The durable idempotency identity is SHA-256 over source ID, content fingerprint,
and extractor version. One logical job may run per identity. Concurrent or
replayed submissions converge on the same ready cache record.

The command sequence is:

1. load the source by exact record ID;
2. recompute the fingerprint and reject stale authority;
3. resolve and validate the controlled source asset;
4. enumerate bounded candidates for the normalized source kind;
5. select the best candidate through deterministic quality rules;
6. decode, orient, crop or letterbox, and encode the bounded WebP;
7. verify dimensions, encoded size, MIME, hash, and containment;
8. atomically publish the asset and cache record;
9. remove task-owned temporary data;
10. return a bounded receipt containing IDs, hashes, origin, dimensions,
    duration, and outcome without source text or raw paths.

Source processing remains successful when visual submission or extraction
fails. At the end of successful source processing, the backend may submit the
visual command only when the backend flag is on. An explicit refresh uses the
same idempotent path.

## 8. Candidate Selection

Candidate priority in Phase 2A is:

1. eligible embedded PDF image;
2. bounded representative video frame;
3. eligible embedded audio artwork;
4. deterministic typographic fallback in the frontend.

PDF selection examines only the first 24 pages and at most 64 embedded-image
candidates. It rejects tiny icons, extreme aspect ratios, alpha-only images,
duplicate hashes, unsupported formats, and candidates that exceed decoder
limits. Selection is deterministic by quality score, page, embedded-resource
identifier, and hash.

Video selection examines at most three timestamps derived deterministically
from duration. Each extraction attempt has a 15-second deadline and the full
job has a 60-second deadline. The selected frame follows deterministic
sharpness, exposure, and non-uniformity rules with stable timestamp tie-breaks.

Audio selection reads embedded artwork only. Phase 2A does not generate a
waveform, contact external metadata services, or decode the complete audio
stream merely to obtain artwork.

## 9. Media Security Limits

The fixed limits are:

- static WebP output only;
- maximum output dimensions `1280 x 720`;
- maximum encoded output `1.5 MiB`;
- maximum decoded candidate `40,000,000` pixels;
- animated inputs rejected;
- SVG inputs rejected;
- maximum 64 PDF image candidates across the first 24 pages;
- maximum three video timestamps;
- 15 seconds per video-frame attempt;
- 60 seconds per extraction job;
- at most two extraction jobs globally;
- at most one active job per source fingerprint;
- default total cache ceiling `2 GiB`.

Decoder warnings for decompression bombs become failures. MIME is determined
from validated bytes, not filename or caller headers. Polyglots, malformed
containers, truncated media, unsupported codecs, and over-budget media fail
closed to typographic presentation. Media tooling never enters the browser
bundle.

Cache eviction is derived-only and oldest-ready-first. It operates on a bounded
record page, validates each exact path and hash, and never removes source files.
An eviction race with an active read or replacement fails soft and retries on a
later bounded sweep.

## 10. API Contract

Source list and detail projections gain:

```text
visual: SourceVisualReceipt | null
```

`SourceVisualReceipt` contains only:

- source ID;
- content and asset hashes;
- origin;
- bounded source locator;
- alt text;
- width and height;
- MIME type;
- immutable opaque asset URL;
- created and updated timestamps.

The list endpoint loads visual receipts in one bounded batch for the returned
source IDs. It returns only records whose fingerprint matches current source
authority. A malformed or unreadable cache row is omitted rather than widening
the response contract or failing the source list.

Endpoints are:

- `GET /sources/{source_id}/visual` — serve the exact current derived bytes;
- `POST /sources/{source_id}/visual:refresh` — submit or replay the bounded job;
- `DELETE /sources/{source_id}/visual` — remove the current derived cache only.

The GET endpoint resolves the current DB receipt, validates source ownership,
fingerprint, path, asset hash, MIME, and size, then returns immutable content
with the asset hash as ETag. It never accepts a filesystem path from the caller.

Refresh and delete accept strict request bodies with a caller request ID. Replay
must match source, fingerprint, and operation exactly. Stale, conflicting, or
corrupt receipts return typed `409`; missing source returns `404`; feature-off
returns the uniform feature-unavailable response; decoder/extractor failure is
reported through command status and does not alter the source.

## 11. Frontend Architecture

Shared components live under
`frontend/src/components/deeper-notebook/source-gallery/`:

- `SourceCover` owns the stable aspect-ratio image box, typographic fallback,
  alt text, origin label, loading state, and broken-asset fallback;
- `SourceGallery` owns selection, filters, adaptive hybrid layout, and compact
  reflow but receives typed sources and callbacks;
- `SourceVisualProvenance` renders visible and accessible origin text;
- `EvidencePeek` adapts the existing citation/passages behavior and preserves
  reading position and focus return;
- `source-gallery.css` owns named containers, auto-fit tracks, image geometry,
  and short-height behavior.

The frontend API decoder rejects unknown origin values, malformed hashes,
non-positive dimensions, oversized dimensions, unsupported MIME, missing alt
text, and non-opaque asset routes. Invalid visual data becomes `null` and the
source remains usable.

Route usage is:

- `/sources`: full adaptive-hybrid gallery;
- notebook source column: compact cover rows preserving current selection and
  context actions;
- `/knowledge`: compact cover treatment for selected source context;
- `/search`: cover thumbnails only for source-bearing results;
- `/capture`: bounded source preview after a source has been created or linked.

Routes keep their existing hooks and mutations. No component fetches source
authority independently. Existing actions dispatch exactly once.

## 12. Adaptive Hybrid Layout

On comfortable and large containers, the selected or most recent eligible
source may occupy a larger feature card with provenance and evidence metadata.
Supporting sources use bounded auto-fit tracks. On compact containers the
feature card loses special span and all cards reflow into readable compact rows.

Rules:

- layout responds to named container inline size, not viewport alone;
- source title and critical status remain real DOM text;
- title, actions, and provenance labels wrap before truncation;
- repeated secondary metadata may truncate only with an accessible full value;
- image boxes preserve aspect ratio and prevent layout shift;
- cards and actions retain the Phase 1 target, clipping, overflow, and scroll
  reachability contracts;
- no carousel, auto-advance, parallax, decorative motion, or competitor asset;
- Research Core dark and high contrast use the same information hierarchy;
- typographic fallback is intentional presentation, never a broken-image icon.

## 13. Imagery Provenance and Alt Text

Every rendered image has a visible origin label:

- `Embedded image`;
- `Video frame`;
- `Embedded artwork`.

The accessible name includes source title and origin. Alt text is concise and
describes what the image represents without claiming facts that extraction did
not establish. Automated alt text uses bounded source title, source kind,
locator, and neutral origin wording; raw source passages are not inserted.

Typographic covers render their text as normal DOM content and hide decorative
shapes from assistive technology. No state is communicated by image or color
alone.

## 14. Evidence Peek

Evidence Peek reuses the existing citation source and passage-location
contracts. It does not infer claims from imagery and does not create a new
evidence record. When evidence metadata exists, a source card may open the exact
source passage in a drawer or popover while retaining the gallery scroll and
returning focus to the invoking control on close.

Missing, stale, or unavailable evidence shows the existing bounded unavailable
state. Opening a cover image never substitutes for opening evidence.

## 15. Failure and Recovery

Visual state is one of:

- ready source-derived image;
- typographic fallback with extraction unavailable;
- typographic fallback with extraction queued or processing;
- typographic fallback after typed extraction failure;
- feature-off legacy presentation.

Routes never block on image work. A failed image request replaces only the
image region with the typographic cover. A refresh action is explicit,
idempotent, and disabled while the same identity is active. Error copy states
that the source remains available and offers one safe retry action.

Deleting the current visual removes its cache receipt and derived file. The
completed command identity prevents immediate automatic recreation for the same
fingerprint; explicit refresh or a future source fingerprint may produce a new
cover. Custom replacement is deferred.

## 16. Performance Budgets

- Source-list projection adds one bounded batch query, never one query per card.
- Route shell and source text render without waiting for visual records.
- Initial browser images are bounded derivatives, never original media.
- Browser image loading is lazy outside the initial visible region.
- Browser bundles import no PDF, video, audio, or image-decoder tooling.
- Cumulative layout shift remains at or below the Phase 1 flagship budget of
  `0.05`.
- Phase 2A JavaScript gzip growth is capped at `40 KiB` and CSS gzip growth at
  `24 KiB` relative to the Phase 1 V2-on baseline.
- Backend extraction has two-job global concurrency and a 60-second job limit.
- Default cache storage is capped at `2 GiB` with derived-only eviction.

Any budget increase requires a measured receipt and explicit review before
acceptance.

## 17. Test and Verification Contract

### 17.1 Backend unit and API tests

RED-first tests cover:

- strict schema and response decoding;
- canonical fingerprint stability and authority change;
- controlled-root and symlink rejection;
- MIME sniffing, polyglots, SVG, animation, decompression bombs, pixel and byte
  limits;
- deterministic PDF, video, and audio candidate selection;
- timeouts, cancellation, global and per-source concurrency;
- idempotent replay, competing requests, stale replacement, and failure before
  and after file publication;
- opaque asset serving, ETag, hash mismatch, and missing-file fallback;
- two-phase deletion and tombstone recovery;
- bounded eviction and source preservation;
- uniform feature-off behavior.

### 17.2 Real SurrealDB tests

Disposable real-database tests cover:

- migration `46` and symmetric `46_down`;
- schema-full rejection and unique source/fingerprint identity;
- concurrent idempotent publication;
- source fingerprint change and stale-cache omission;
- publication and deletion crash windows;
- restart hydration;
- proof that cache deletion and downgrade leave every source row unchanged.

### 17.3 Frontend tests

Component tests cover strict receipt decoding, each origin label, typographic
fallback, loading and broken image behavior, refresh/remove dispatch once,
focus return, Evidence Peek, container reflow, high contrast, reduced motion,
feature-off, and invalid receipt fail-soft behavior.

The checked route/state manifest expands Sources, Notebook detail, Knowledge,
Search, and Capture with relevant populated, processing, failure, missing-image,
and feature-off cases. Browser tests retain exact same-origin method/path
ledgers, reject external requests, and verify text/action/card containment,
44-pixel targets, scroll ownership, lower-content reachability, unique IDs,
image integrity, useful alt text, and no horizontal document overflow.

### 17.4 Final gates

Acceptance requires:

- focused and affected full backend suites;
- full frontend unit suite, ESLint, and TypeScript;
- V2/source-visuals on and explicit off production builds;
- feature-build contract;
- affected browser matrix plus explicit rollback ledger;
- real SurrealDB migration and concurrency proof;
- media-security review, dependency/advisory review, rebrand audit, diff checks,
  and staged/range secret scans;
- measured JavaScript, CSS, CLS, extraction, and cache receipts;
- fresh final review with no Critical or Important findings.

## 18. Completion Boundary

Phase 2A is complete only when:

1. the adaptive-hybrid gallery is usable on Sources and its shared compact
   treatments preserve Notebook, Knowledge, Search, and Capture behavior;
2. source-derived images are bounded, locally extracted, and visibly labeled;
3. typographic fallback handles disabled, missing, stale, queued, failed, and
   corrupt visual states without failing a route;
4. cache records and files are rebuildable, contained, idempotent, and safely
   removable;
5. real Surreal migration, concurrency, restart, deletion, and downgrade proofs
   are green;
6. V2 or source-visuals off preserves the Phase 1 legacy presentation and
   request behavior;
7. security, accessibility, responsive, performance, build, browser, rebrand,
   secret, and final-review gates pass;
8. no raw source text, uncontrolled path, cloud image request, or source
   mutation enters the visual pipeline;
9. no local generation, webpage preview, custom cover upload, Artifact Studio,
   Insight Canvas, or Phase 3 work is present.

The next separately approved slice may add bounded local abstract generation.
Webpage screenshots require their own outbound-policy and browser-security
design. Unified Artifact Studio remains a later phase.
