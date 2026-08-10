# Luminous Research Folio verification receipt

## Task 1 baseline receipt

- Date: 2026-08-09
- Repository: `Deeper-Notebook`
- Branch: `agent/documentation-reconstruction`
- Baseline revision: `46e13127a26fa7cb87789e8d495ec7e8926f29b8`
- Scope: feature-flag and sidebar navigation parity contracts only.
- Rollback: omit `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` or set it to `0`; the flag
  remains disabled by default until the approved Task 15 gate.

### Preserved dirty-file inventory

The baseline had no modified tracked files. The following user-owned untracked
paths were present before Task 1 and are intentionally preserved outside the
Task 1 commit:

```text
.codex/agent-context/deeper-notebook-research-evidence-adoption.md
.codex/agent-context/deeper-notebook-web-intelligence.md
.codex/agent-context/luminous-research-folio.md
.codex/agent-context/research-evidence-ui.md
desktop/build/__pycache__/
```

### Current route-entry inventory

The baseline contains these route entry points:

```text
/ (frontend/src/app/page.tsx)
/login
/advanced
/capture
/knowledge
/notebooks/[id]
/notebooks
/ (dashboard root)
/podcasts
/podcasts/studio
/search
/settings/api-keys
/settings/launcher-prefs
/settings/local-models
/settings/mcp
/settings
/setup-wizard
/sources/[id]
/sources
/studio
/study
/transformations
```

The existing sidebar navigation contract retains this exact href order:

```text
/sources
/capture
/notebooks
/knowledge
/search
/studio
/podcasts
/study
/settings/api-keys
/transformations
/settings
/settings/mcp
/settings/launcher-prefs
/advanced
```

The create targets remain `source`, `notebook`, and `podcast`.

### Current theme IDs

```text
research-core-dark
research-core-light
deep-ocean
graphite-lab
arctic-research
archive-paper
high-contrast-dark
high-contrast-light
light-blue
system
solarized-light
github-light
paper
catppuccin-latte
rose-pine-dawn
dark
midnight-aurora
tokyo-night
catppuccin-mocha
rose-pine
one-dark
gruvbox-dark
solarized-dark
dracula
nord
```

### Evidence rule

Baseline failures and pre-existing diagnostics are recorded with their exact
command and output; they are not repaired opportunistically as part of this
visual migration.

## Task 1 implementation evidence

The static `NEXT_PUBLIC_DN_LUMINOUS_FOLIO` flag defaults to `false` and reads
only its canonical static `process.env` property. Existing sidebar hrefs and
create targets are exported for downstream shell contracts without changing
their values.

Focused contract command:

```bash
cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx
```

Result: 3 files passed, 9 tests passed.

Required gates:

| Gate | Exact command | Result |
| --- | --- | --- |
| RED | `cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx` | Expected 3 failures: missing flag export, missing static flag reference, and missing navigation exports. |
| Focused GREEN | `cd frontend && npm exec vitest run src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/deeper-notebook/shell/navigation-contract.test.tsx` | 3 files passed; 9 tests passed. |
| Feature build contract | `cd frontend && npm run test:feature-build-contract` | Exit 0; Next.js 16.2.12 production contract build and generated-value verification passed. |
| Scoped ESLint | `cd frontend && npm exec eslint src/lib/features.ts src/lib/features.test.ts src/lib/features-build-contract.test.ts src/components/layout/AppSidebar.tsx src/components/deeper-notebook/shell/navigation-contract.test.tsx` | Exit 0. |
| Diff check | `git diff --check` | Exit 0. |

Self-review confirmed that the sidebar href strings, section ordering, labels,
icons, create dialog handlers, and existing feature-flag aliases are unchanged;
only the requested static flag and downstream exports were added. The new flag
has no legacy alias and remains false by default. This receipt does not claim
later redesign, native-runtime, package, or release proof.
