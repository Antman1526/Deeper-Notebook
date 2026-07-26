# Deeper Notebook Rebrand Design

**Date:** 2026-07-26

**Author:** Anthony Henry with Codex

**Repository:** https://github.com/Antman1526/Deeper-Notebook

**Upstream:** https://github.com/lfnovo/open-notebook

**Status:** Approved by the user on 2026-07-26

## Purpose

Rename Open Notebook Plus to **Deeper Notebook** as a complete product identity,
not merely a display-label change. The rebrand covers the native desktop app,
frontend, backend metadata, release artifacts, documentation, repository links,
configuration contracts, persistent data paths, and internal downstream
namespaces.

The migration must preserve existing notebooks, sources, notes, credentials,
models, settings, and desktop upgrade behavior.

## Product Position

Deeper Notebook is a local-first research and knowledge workspace that combines
source-grounded AI research with a portable personal knowledge graph.

The rebrand keeps the product's existing differentiators:

- Local and cloud model choice.
- Grounded chat with citations.
- Research and Evidence Studio.
- Podcasts and transformations.
- Memory and privacy controls.
- MCP tools and local web search.
- Native macOS and Windows applications.
- Self-hosted server support.

## Canonical Identity

| Surface | Canonical value |
|---|---|
| Product name | `Deeper Notebook` |
| GitHub repository | `Antman1526/Deeper-Notebook` |
| Repository URL | `https://github.com/Antman1526/Deeper-Notebook` |
| Repository slug | `Deeper-Notebook` |
| Lowercase product slug | `deeper-notebook` |
| Python distribution | `deeper-notebook` |
| Python import package | `deeper_notebook` |
| Primary environment prefix | `DEEPER_NOTEBOOK_` |
| Short environment prefix | `DN_` |
| User data directory | `.deeper-notebook` |
| Frontend/internal short namespace | `dn` |
| Downstream API namespace | `/api/deeper-notebook` |
| macOS app | `Deeper Notebook.app` |
| Windows executable | `Deeper Notebook.exe` |
| macOS artifact | `Deeper-Notebook-mac-<arch>.dmg` |
| Windows portable artifact | `Deeper-Notebook-windows-x64.zip` |
| Windows installer | `Deeper-Notebook-Setup-x64.exe` |

## Compatibility Identities

The following names remain accepted as deprecated aliases during the migration:

| Legacy identity | Compatibility behavior |
|---|---|
| `open_notebook` | Import shim forwarding to `deeper_notebook` |
| `open-notebook` | Accepted distribution/config reference where upstream compatibility requires it |
| `OPEN_NOTEBOOK_*` | Read after canonical `DEEPER_NOTEBOOK_*`; emits one deprecation receipt |
| `ONP_*` | Read after canonical `DN_*`; emits one deprecation receipt |
| `.open-notebook-plus` | Migrated or used as a fallback data root under the rules below |
| `/api/onp/*` | Route alias forwarding to `/api/deeper-notebook/*` |
| Frontend `onp` imports/classes | Mechanical alias during component migration; removed only after consumers move |
| Old GitHub repository URL | Replaced in active product links; retained only in historical records |

Canonical variables always win when canonical and legacy variables are both set.
The application must never silently combine two conflicting values.

## Visual Identity

### Direction

The approved direction combines:

- **Notebook Spark** shape: a clear notebook outline with an intelligence spark.
- **Research Core** colorway: focused teal-to-cyan colors on a deep blue-green
  background.

### Palette

| Role | Color |
|---|---|
| Deep background | `#071B1D` |
| Dark teal | `#0F766E` |
| Primary teal | `#2DD4BF` |
| Cyan accent | `#38BDF8` |
| Light foreground accent | `#CCFBF1` |

### Wordmark

- Product name: `Deeper Notebook`.
- Tagline: `Think further with every source`.
- The wordmark uses the full product name; it does not abbreviate the visible
  brand to `DN`.
- The symbol must remain legible at app-icon, tray-icon, favicon, and sidebar
  sizes.

### Surfaces

The new identity appears in:

- App icon, favicon, splash, launch reveal, first-run wizard, and tray.
- Sidebar, dashboard masthead, login, connection errors, model manager, memory
  dashboard, and setup pages.
- Window titles, permission prompts, already-running dialogs, and native menus.
- Exported PDF, DOCX, PPTX, spreadsheet, and research-artifact metadata.
- Installer screens, mounted DMG name, Start Menu shortcuts, and uninstall
  entries.
- README, documentation, issue templates, workflows, update checks, and
  release manifests.
- All supported frontend locales.

## Naming Boundaries

### Rename

Active product-owned identifiers and user-visible text are renamed.

This includes:

- UI strings and accessibility labels.
- Desktop packaging and release artifacts.
- Product-owned documentation and active downstream links.
- Downstream package metadata and service descriptions.
- Product-owned environment names and data-path defaults.
- Downstream-only code namespaces such as `onp` components and routers.
- Test names, fixtures, and assertions that encode the active product identity.

### Preserve

The rebrand does not rewrite:

- Historical changelog entries describing an old released artifact.
- Historical design documents and implementation plans, except for an appended
  note identifying the successor product.
- Upstream `lfnovo/open-notebook` attribution, sync instructions, package
  compatibility, and issue references where they truly refer to upstream.
- Third-party dependency names.
- Database record values that require a separate data migration before they can
  change safely.
- Stable opaque installer identifiers such as the Windows installer GUID.

## Data-Root Migration

### Desired state

Fresh installs use:

- macOS/Linux: `~/.deeper-notebook/`
- Windows: `%USERPROFILE%\.deeper-notebook\`

### Upgrade detection

At launch:

1. Resolve the canonical data root.
2. Resolve the legacy `.open-notebook-plus` root.
3. Acquire a single-instance migration lock.
4. Classify the state:
   - neither root exists;
   - canonical only;
   - legacy only;
   - both roots exist and are equivalent;
   - both roots exist and conflict.
5. Never merge conflicting roots automatically.

### Legacy-only migration

When only the legacy root exists:

1. Create a migration receipt outside the directory being moved.
2. Validate available disk and filesystem capabilities.
3. Snapshot small configuration files and record hashes for all critical
   databases and manifests.
4. Prefer a same-volume atomic rename.
5. Create a legacy compatibility link or redirect when the platform supports a
   safe implementation.
6. Revalidate the critical hashes at the canonical location.
7. Start services only after validation passes.

If a safe atomic move is unavailable, the application continues using the
legacy root and reports `migration-deferred`; it does not perform a silent large
copy.

### Both-roots conflict

When both roots contain non-equivalent state:

- Start in recovery mode.
- Do not launch write-capable backend services.
- Show root paths, sizes, timestamps, and hash summaries without exposing
  secrets.
- Require an explicit operator choice and create a backup before any merge or
  replacement.

### Rollback

The migration receipt contains:

- Migration ID and timestamp.
- Source and destination roots.
- Strategy used.
- Critical before/after hashes.
- Compatibility-link result.
- Validation result.
- Rollback instructions.

Rollback never deletes the destination automatically.

## Environment Migration

Configuration resolution follows this order:

1. Canonical `DEEPER_NOTEBOOK_*`.
2. Canonical short `DN_*`, only for settings intentionally assigned a short
   alias.
3. Legacy `OPEN_NOTEBOOK_*`.
4. Legacy downstream `ONP_*`.
5. Built-in default.

Each setting has one normalization function and one resolved value. Runtime code
does not independently read multiple aliases.

Secrets are never copied into logs or migration receipts. Receipts identify the
winning variable name, not its value.

## Python Package Migration

`deeper_notebook` becomes the canonical package. Migration is staged:

1. Introduce `deeper_notebook` and move product-owned imports.
2. Keep `open_notebook` as a forwarding compatibility package.
3. Add contract tests showing public imports resolve to the same objects.
4. Update packaged runtime paths and worker command registrations.
5. Remove the shim only in a future breaking release with a separate decision.

Upstream synchronization may still use an explicit upstream subtree or adapter.
The compatibility package must not duplicate implementation.

## Desktop Packaging Migration

### macOS

- Display name, executable, app bundle name, DMG volume, and artifact use
  `Deeper Notebook`.
- The bundle identifier migration is staged because changing it affects macOS
  permissions and application identity.
- A bundle-ID change requires a packaged upgrade test and explicit permission
  migration notes.

### Windows

- Product, executable, installation folder, shortcut, artifact, and uninstall
  display name use `Deeper Notebook`.
- The existing Inno Setup `AppId` GUID remains stable so the new installer
  upgrades the old installation instead of creating an unrelated product.

### Releases

- Active release workflows upload only Deeper Notebook artifact names.
- Update checks use `Antman1526/Deeper-Notebook`.
- Release manifests and `latest.yml` references must match the final artifact
  bytes and sizes.

## Repository Migration

The local `origin` becomes:

`https://github.com/Antman1526/Deeper-Notebook.git`

Active documentation, badges, update checks, release workflows, and issue links
use the new repository. Historical changelog links remain unchanged when they
identify an old release or commit accurately.

The local checkout directory may be renamed after the branch is clean and no
process is using it. Directory renaming is not required for code correctness.

## Localization

`Deeper Notebook` remains a proper product name in every locale.

Translations must update:

- Application name.
- Login and connection descriptions.
- Restart and update notices.
- Documentation labels.
- Provider and model descriptions that name the product.

Tests assert no active locale retains `Open Notebook`, `Open notebook+`, or
`Open Notebook Plus` as the product name.

## Error Handling

The rebrand migration uses explicit states:

- `not-needed`
- `ready`
- `migration-pending`
- `migration-deferred`
- `migration-conflict`
- `migration-failed`
- `rollback-available`

A migration failure:

- Never deletes old state.
- Never starts against a partially moved database.
- Preserves the receipt and failure reason.
- Presents a recovery action.

## Verification

### Static inventory

Automated checks classify every legacy-name match as:

- required compatibility alias;
- accurate upstream reference;
- accurate historical reference;
- migration documentation;
- unexpected active legacy identity.

The final unexpected count must be zero.

### Tests

- Canonical/legacy configuration precedence.
- Data-root state classification.
- Atomic migration and failure rollback.
- Python import compatibility.
- API route aliases.
- Frontend locale and metadata branding.
- Desktop titles, dialogs, tray, and first-run pages.
- macOS and Windows artifact-name contracts.
- Update-service repository targeting.
- Exported artifact metadata.

### Build gates

- Backend focused tests.
- Frontend Vitest and production build.
- Desktop test suite.
- macOS application and DMG build.
- Windows build on a Windows host.
- Native launch smoke on both platforms.
- Manifest, checksum, and artifact-size validation.

## Rollout

1. **Identity contract:** introduce centralized brand constants and tests.
2. **Visible rebrand:** frontend, desktop, exporters, locales, and documentation.
3. **Repository and packaging:** links, update service, workflows, and artifact
   names.
4. **Compatibility aliases:** configuration, routes, imports, and data-root
   detection.
5. **Migration:** guarded data-root migration and receipts.
6. **Proof:** full tests, packaged launch checks, and legacy-name inventory.

Each rollout step is independently reviewable and reversible.

## Acceptance Criteria

- Every active user-facing product label says `Deeper Notebook`.
- The approved Notebook Spark/Research Core identity is used on all primary
  surfaces.
- Active downstream links target `Antman1526/Deeper-Notebook`.
- New installations use canonical identifiers.
- Existing installations retain all data and settings.
- Legacy configuration remains accepted with deterministic precedence.
- Active artifacts use Deeper Notebook names.
- Historical and upstream references remain accurate.
- No destructive migration runs without a receipt and rollback path.
- macOS and Windows packaged launch checks pass before release.
