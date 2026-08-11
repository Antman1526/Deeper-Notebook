# Deeper Notebook Reliability Experience Design

## Goal

Make Deeper Notebook feel faster, safer, and easier to understand without
changing its local-first authority model. The work delivers six connected
improvements: measured startup acceleration, a Recovery Center, a trustworthy
system dashboard, verified update notices, Focus mode, and visible local
backup/provenance receipts.

## Product principles

- The notebook opens before optional local AI is fully available. A delayed
  model must never block notes, sources, search, or the database.
- A problem is stated as a capability and a next safe action, never as a
  generic technical error or an opaque stack trace.
- Every status is local, bounded, and explainable. No telemetry, cloud model,
  remote write, vault scan, mount, import, or repair is triggered implicitly.
- Obsidian and Logseq mounts remain external-read-only. Source hashes and
  mount authority are displayed as evidence, not treated as permission to
  write.
- Existing routes, settings, update opt-out, and the one-release Luminous
  rollback flag remain valid.

## Architecture

`desktop` owns launch measurements and a bounded model-selection cache under
the existing active data root. A new read-only runtime snapshot endpoint
combines the established readiness contract, optional-service availability,
last startup receipt, update compatibility, and local export/knowledge
provenance summaries. It redacts paths, credentials, and raw logs.

The frontend consumes that one snapshot through TanStack Query. It supplies a
compact Horizon summary, a Settings detail page, and the Recovery Center.
Recovery actions are only existing explicit actions: retry a read, reload the
page, open the local diagnostics view, or invoke the already guarded desktop
repair-and-relaunch bridge. No action automatically repairs data, downloads an
update, changes models, or modifies an external vault.

Focus mode is a local display preference. It adds a root attribute and command
that collapses nonessential visual chrome while leaving semantic landmarks,
keyboard access, route behavior, and all content mounted.

## The six slices

### 1. Startup acceleration

Record named startup milestones and persist only a sanitized last-startup
receipt. Cache a previously selected chat GGUF only when its path is inside the
configured model root and its metadata still matches. A stale or absent cache
falls back to the existing bounded scan; it never selects an arbitrary file.
The initial window and core API remain available while optional model discovery
continues or is unavailable. The UI reports the optional capability as pending
or unavailable rather than delaying the application.

Success is measured as a before/after receipt for core-ready time, plus tests
that prove a matching cache avoids directory enumeration and stale cache data
cannot escape its model-root boundary.

### 2. Recovery Center

Replace the generic render-error fallback with an accessible Recovery Center.
It distinguishes a local UI rendering failure from API/database/migration or
optional-model availability. It includes Retry, Reload, a copyable sanitized
diagnostic code, and the existing guarded desktop repair/relaunch action only
when the runtime explicitly says it is available. It never exposes exception
text, local paths, tokens, or raw logs in production.

### 3. Trust dashboard

Expose a read-only `RuntimeSnapshot` showing API, database, migrations,
optional AI capabilities, update status, and local knowledge/backup evidence.
The Horizon shows the smallest useful summary. Settings shows fuller,
keyboard-accessible detail with exact plain-language meanings and a manual
refresh. A failing optional AI capability remains yellow/degraded, not a red
claim that the user's notes are unusable.

### 4. Verified update notices

Keep the existing privacy-gated, notify-only GitHub check. Treat a release as
actionable only when it is from the canonical repository, parses as a valid
version, and exposes the named Deeper Notebook macOS artifact plus a checksum
asset. Otherwise show an informational "release needs verification" state and
do not label it as an available app update. The app never downloads, installs,
or replaces itself.

### 5. Focus mode

Add a persisted `focusMode` preference alongside the existing display
preferences. The command palette and an accessible shell control toggle it.
The main document surface grows, decorative motion respects the existing
reduced-motion preference, and utilities stay reachable through the command
bar. Escape exits focus mode. The setting is local only and defaults off.

### 6. Backup and provenance visibility

Surface only existing local receipts: the newest auto-export metadata, its
age/size/integrity status, and per-mounted-space authority/source-fingerprint
summary. The UI does not enumerate arbitrary filesystem locations or read
source contents. Manual export and restore remain their separate,
approval-gated workflows.

## Data contracts

`RuntimeSnapshot` is a read-only API shape with:

- `core`: readiness status and database/migration checks;
- `optional`: named capability states (`ready`, `pending`, `unavailable`),
  reason codes, and no raw exception/path values;
- `startup`: last core-ready duration and cache status, when a receipt exists;
- `update`: current version, verified candidate state, and release URL only;
- `recovery`: whether the existing native relaunch bridge is available;
- `backup`: newest local auto-export timestamp, byte count, and integrity
  state, if known;
- `provenance`: mount count, read-only/external count, and source-fingerprint
  summary without content or absolute paths.

Unknown is a first-class state. Clients must render unknown safely and must not
infer a healthy state from missing fields.

## Safety and privacy boundaries

- Runtime responses use allowlisted reason codes and relative labels. They do
  not return environment values, credentials, model paths, absolute vault
  paths, exception strings, source text, or checksums of user content.
- Model-cache writes are atomic, mode 0600 where supported, bounded in size,
  and are ignored on malformed JSON or root/metadata mismatch.
- Update validation only reads public GitHub release metadata after the
  existing user-controlled opt-in. It cannot modify an app bundle.
- Backup/provenance display is read-only. Existing vault root approval and
  source-hash/no-write checks are not weakened.

## Verification

- TDD unit tests for each new desktop/API/frontend boundary, including malformed
  snapshots, stale model caches, unverified releases, and absent local receipts.
- Keyboard and reduced-motion tests for Recovery Center and Focus mode.
- Browser proof at desktop and mobile widths for dashboard, Settings, error,
  degraded, and focus states.
- Backend/frontend/desktop/lint/type/build gates, then an installed-app smoke
  using a disposable data root. The update card must remain notify-only and
  external mounts must remain unchanged.
