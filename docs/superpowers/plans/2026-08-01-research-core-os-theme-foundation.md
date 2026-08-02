# Research Core OS Theme Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the complete 25-theme Research Core OS foundation, make Research Core Dark the safe fresh-install default, add a categorized visual theme gallery and local contextual Guided Tips, and establish deterministic visual-proof infrastructure without redesigning unrelated application screens.

**Architecture:** Keep `desktop/window.py` as the runtime palette authority, add a typed frontend catalog for labels/groups/previews, and enforce cross-layer ID lockstep with tests. Theme components consume semantic CSS variables instead of theme IDs; generated static assets keep first-run and auxiliary desktop surfaces synchronized. Playwright captures stable theme-gallery and shell renders now, while later Research Core OS plans extend the same fixture and matrix to Dashboard, Knowledge, grounded chat, and Podcast Studio.

**Tech Stack:** Python 3.11+, Pytest, FastAPI, PyWebView desktop wrapper, Next.js 16, React 19, TypeScript, Tailwind CSS 4, Radix UI, Vitest, Testing Library, Playwright 1.61.

## Global Constraints

- Existing theme IDs and persisted selections remain valid.
- Research Core Dark is the default only for fresh installations; an existing stored selection is never silently replaced.
- The desktop palette, frontend catalog, API allowlist, first-run wizard, model manager, and memory dashboard remain lockstep-tested.
- External Obsidian and Logseq vaults remain read-only.
- Opening a research or Podcast Studio surface does not start generation.
- Fonts and theme assets must work without a network request during native launch.
- Normal text meets WCAG AA; body foreground targets WCAG AAA where the existing test contract requires it.
- Focus, selection, hover, disabled, status, and destructive states must remain distinguishable without color alone.
- Operating-system reduced motion remains authoritative.
- Guided Tips remain local-only, non-modal, independently disableable, and never start a mutation, scan, model run, or podcast.
- Do not stage or modify `desktop/requirements.lock`, `history.txt`, `desktop/build/__pycache__/`, or the root `node_modules/` directory; they are pre-existing unrelated or generated worktree state.
- Do not change protected-vault paths, watcher state, mount authority, source hashes, provider secrets, or local-model files.

## File Structure

### New files

- `frontend/src/lib/themes/catalog.ts` — typed frontend theme metadata and grouping.
- `frontend/src/lib/themes/catalog.test.ts` — 25-theme catalog, grouping, ID, and accessibility metadata contracts.
- `frontend/src/components/deeper-notebook/ThemePreviewCard.tsx` — miniature semantic shell preview for one theme.
- `frontend/src/components/deeper-notebook/ThemeGallery.tsx` — categorized, searchable, keyboard-accessible theme gallery with preview/apply/restore behavior.
- `frontend/src/components/deeper-notebook/ThemeGallery.test.tsx` — selection, preview, cancel, persistence, and accessibility tests.
- `scripts/render_theme_static_assets.py` — deterministic generator for auxiliary desktop theme CSS and first-run catalog JavaScript.
- `desktop/tests/test_theme_static_assets.py` — generated-asset freshness and 25-ID lockstep proof.
- `frontend/e2e/fixtures/theme-visuals.ts` — strict mocked auth/settings/theme fixture for visual captures.
- `frontend/e2e/theme-gallery-visual.spec.ts` — deterministic gallery and shell screenshots.
- `frontend/src/lib/guided-tips/catalog.ts` — stable route, anchor, copy, and version definitions for major-section tips.
- `frontend/src/lib/guided-tips/catalog.test.ts` — exact section coverage and stable-ID contracts.
- `frontend/src/lib/stores/guided-tips-store.ts` — local enablement and versioned completion state.
- `frontend/src/lib/stores/guided-tips-store.test.ts` — disable, completion, version, and replay persistence tests.
- `frontend/src/components/guided-tips/GuidedTipsProvider.tsx` — non-modal anchored callout controller.
- `frontend/src/components/guided-tips/GuidedTipsProvider.test.tsx` — routing, anchoring, suspension, keyboard, and Settings-control tests.
- `frontend/src/components/guided-tips/index.ts` — public Guided Tips exports.

### Modified files

- `desktop/window.py` — eight new palettes, Research Core fallback, and expanded semantic token derivation.
- `desktop/config.py` — Research Core Dark fresh-install default while preserving stored values.
- `desktop/tests/test_window.py` — exact catalog, semantic token, contrast, focus, and fallback tests.
- `desktop/tests/test_config.py` — fresh default and existing-selection preservation tests.
- `api/routers/deeper_notebook.py` — 25-ID allowlist and Research Core fallback response.
- `tests/test_deeper_notebook_router.py` — fallback and accepted-theme API tests.
- `frontend/src/lib/theme-script.ts` — canonical stored-theme precedence, Research Core fallback, and dark-class synchronization before hydration.
- `frontend/src/lib/theme-script.test.ts` — pre-hydration precedence and fallback contract.
- `frontend/src/app/globals.css` — semantic theme surface/status/focus defaults.
- `frontend/src/components/deeper-notebook/tokens.css` — semantic Research Core OS depth, evidence, authority, model-route, selection, and graph variables.
- `frontend/src/components/vault/ResearchCoreVisualSystem.test.tsx` — semantic token and reduced-motion contract.
- `frontend/src/components/deeper-notebook/ThemeSwitcher.tsx` — typed catalog, grouped compact picker, miniature previews, and restore-safe selection.
- `frontend/src/components/deeper-notebook/ThemeSwitcher.test.tsx` — groups, canonical persistence, and new-theme behavior.
- `frontend/src/components/deeper-notebook/index.ts` — gallery export.
- `frontend/src/app/(dashboard)/settings/page.tsx` — Appearance section containing the gallery.
- `desktop/first_run/static/themes.css` — generated 25-theme auxiliary variables.
- `desktop/model_manager/static/themes.css` — generated 25-theme auxiliary variables.
- `desktop/memory_dashboard/static/themes.css` — generated 25-theme auxiliary variables.
- `desktop/first_run/static/theme-catalog.generated.js` — generated first-run metadata.
- `desktop/first_run/static/index.html` — load the generated catalog before `wizard.js`.
- `desktop/first_run/static/wizard.js` — consume `window.DN_THEME_CATALOG`, group Featured themes first, and default fresh setup to Research Core Dark.
- `desktop/first_run/server.py` — use the Research Core Dark missing-body fallback.
- `desktop/model_manager/static/index.html` — use the Research Core Dark prepaint fallback.
- `desktop/model_manager/server.py` — use the Research Core Dark missing-config fallback.
- `desktop/memory_dashboard/static/index.html` — load generated theme CSS and use the Research Core Dark prepaint fallback.
- `desktop/memory_dashboard/static/dashboard.js` — use the Research Core Dark request-failure fallback.
- `desktop/memory_dashboard/server.py` — use the Research Core Dark missing-config fallback.
- `frontend/package.json` — add the focused visual-proof script.
- `frontend/playwright.config.ts` — add deterministic visual project settings without changing native/device proof boundaries.
- `frontend/src/components/layout/AppShell.tsx` — mount one Guided Tips provider for authenticated application routes.
- `frontend/src/components/layout/AppSidebar.tsx` — expose stable section anchors without changing navigation behavior.

---

### Task 1: Typed Frontend Theme Catalog

**Files:**
- Create: `frontend/src/lib/themes/catalog.ts`
- Create: `frontend/src/lib/themes/catalog.test.ts`

**Interfaces:**
- Produces: `ThemeId`, `ThemeGroup`, `ThemeDefinition`, `THEME_CATALOG`, `THEME_BY_ID`, `DARK_THEME_IDS`, `DEFAULT_THEME_ID`, and `isThemeId(value: string): value is ThemeId`.
- Consumes: no runtime API; this catalog is safe during SSR and before desktop bridge initialization.

- [ ] **Step 1: Write the failing catalog test**

```ts
import { describe, expect, it } from 'vitest'

import {
  DARK_THEME_IDS,
  DEFAULT_THEME_ID,
  THEME_BY_ID,
  THEME_CATALOG,
  isThemeId,
} from './catalog'

const expectedIds = [
  'research-core-dark', 'research-core-light',
  'deep-ocean', 'graphite-lab', 'arctic-research', 'archive-paper',
  'high-contrast-dark', 'high-contrast-light',
  'light-blue', 'system', 'solarized-light', 'github-light', 'paper',
  'catppuccin-latte', 'rose-pine-dawn',
  'dark', 'midnight-aurora', 'tokyo-night', 'catppuccin-mocha',
  'rose-pine', 'one-dark', 'gruvbox-dark', 'solarized-dark', 'dracula', 'nord',
] as const

describe('Research Core OS theme catalog', () => {
  it('contains the exact 25 unique IDs and the approved fresh default', () => {
    expect(THEME_CATALOG.map(theme => theme.id)).toEqual(expectedIds)
    expect(new Set(THEME_CATALOG.map(theme => theme.id)).size).toBe(25)
    expect(DEFAULT_THEME_ID).toBe('research-core-dark')
  })

  it('marks the flagship and accessibility themes explicitly', () => {
    expect(THEME_BY_ID['research-core-dark'].group).toBe('featured')
    expect(THEME_BY_ID['research-core-light'].group).toBe('featured')
    expect(THEME_BY_ID['high-contrast-dark'].group).toBe('accessibility')
    expect(THEME_BY_ID['high-contrast-light'].group).toBe('accessibility')
  })

  it('exposes dark-mode and runtime guards', () => {
    expect(DARK_THEME_IDS).toContain('research-core-dark')
    expect(DARK_THEME_IDS).not.toContain('research-core-light')
    expect(isThemeId('archive-paper')).toBe(true)
    expect(isThemeId('unknown-neon')).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test and verify the missing module failure**

Run:

```bash
cd frontend && npm test -- src/lib/themes/catalog.test.ts
```

Expected: FAIL because `src/lib/themes/catalog.ts` does not exist.

- [ ] **Step 3: Implement the typed catalog**

Create `frontend/src/lib/themes/catalog.ts` with these exact public types and
the 25 entries in the order asserted above:

```ts
export type ThemeGroup = 'featured' | 'light' | 'dark' | 'accessibility' | 'classics'

export interface ThemeDefinition {
  id: string
  label: string
  group: ThemeGroup
  dark: boolean
  description: string
  preview: {
    canvas: string
    panel: string
    text: string
    primary: string
    accent: string
    border: string
  }
}

export const DEFAULT_THEME_ID = 'research-core-dark' as const

export const THEME_CATALOG = [
  { id: 'research-core-dark', label: 'Research Core Dark', group: 'featured', dark: true, description: 'Signature deep-teal research instrument.', preview: { canvas: '#071B1D', panel: '#0B292B', text: '#D8FFF8', primary: '#2DD4BF', accent: '#38BDF8', border: '#225053' } },
  { id: 'research-core-light', label: 'Research Core Light', group: 'featured', dark: false, description: 'Warm mineral paper with precise teal structure.', preview: { canvas: '#F5FBF9', panel: '#FFFFFF', text: '#102A2A', primary: '#0F766E', accent: '#0284C7', border: '#C9DED8' } },
  { id: 'deep-ocean', label: 'Deep Ocean', group: 'dark', dark: true, description: 'Navy depth with bioluminescent teal and cyan.', preview: { canvas: '#06151F', panel: '#0B2432', text: '#D8F3F8', primary: '#2DD4BF', accent: '#38BDF8', border: '#21485A' } },
  { id: 'graphite-lab', label: 'Graphite Lab', group: 'dark', dark: true, description: 'Neutral charcoal with restrained Research Core accents.', preview: { canvas: '#151A1D', panel: '#20272B', text: '#EDF7F5', primary: '#5EEAD4', accent: '#67E8F9', border: '#3B494E' } },
  { id: 'arctic-research', label: 'Arctic Research', group: 'light', dark: false, description: 'Cool white with glacial cyan focus.', preview: { canvas: '#F4FAFC', panel: '#FFFFFF', text: '#122A35', primary: '#0F766E', accent: '#0284C7', border: '#C7DBE2' } },
  { id: 'archive-paper', label: 'Archive Paper', group: 'light', dark: false, description: 'Warm archival paper with teal and brass accents.', preview: { canvas: '#F7F1E5', panel: '#FFFDF8', text: '#2B332E', primary: '#0F766E', accent: '#A16207', border: '#D8CDBB' } },
  { id: 'high-contrast-dark', label: 'High Contrast Dark', group: 'accessibility', dark: true, description: 'Maximum dark contrast and unambiguous states.', preview: { canvas: '#000000', panel: '#111111', text: '#FFFFFF', primary: '#5EEAD4', accent: '#67E8F9', border: '#FFFFFF' } },
  { id: 'high-contrast-light', label: 'High Contrast Light', group: 'accessibility', dark: false, description: 'Maximum light contrast and saturated focus.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#000000', primary: '#006B63', accent: '#005FCC', border: '#000000' } },
  { id: 'light-blue', label: 'Light Blue', group: 'classics', dark: false, description: 'Original clean blue workspace.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#1A2B3C', primary: '#2D7FF9', accent: '#5AB1FF', border: '#D8E5F5' } },
  { id: 'system', label: 'System', group: 'classics', dark: false, description: 'Follow the operating-system appearance.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#1A2B3C', primary: '#2D7FF9', accent: '#5AB1FF', border: '#D8E5F5' } },
  { id: 'solarized-light', label: 'Solarized Light', group: 'light', dark: false, description: 'Low-glare cream with balanced blue and teal.', preview: { canvas: '#FDF6E3', panel: '#FDF6E3', text: '#073642', primary: '#268BD2', accent: '#2AA198', border: '#D8D2BF' } },
  { id: 'github-light', label: 'GitHub Light', group: 'light', dark: false, description: 'Crisp neutral workspace with familiar blue.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#24292F', primary: '#0969DA', accent: '#1F883D', border: '#D0D7DE' } },
  { id: 'paper', label: 'Paper', group: 'light', dark: false, description: 'Warm cream reading environment.', preview: { canvas: '#FBF8F1', panel: '#FBF8F1', text: '#2A2520', primary: '#8B5A2B', accent: '#C0853D', border: '#DDD3BF' } },
  { id: 'catppuccin-latte', label: 'Catppuccin Latte', group: 'light', dark: false, description: 'Soft lavender-tinted light palette.', preview: { canvas: '#EFF1F5', panel: '#FFFFFF', text: '#4C4F69', primary: '#8839EF', accent: '#1E66F5', border: '#BCC0CC' } },
  { id: 'rose-pine-dawn', label: 'Rosé Pine Dawn', group: 'light', dark: false, description: 'Warm blush paper with muted violet.', preview: { canvas: '#FAF4ED', panel: '#FFFAF3', text: '#4B4661', primary: '#907AA9', accent: '#D7827E', border: '#DFDAD9' } },
  { id: 'dark', label: 'Dark', group: 'classics', dark: true, description: 'Original dark workspace with blue accents.', preview: { canvas: '#0F1419', panel: '#1A2330', text: '#E5EBF2', primary: '#5AB1FF', accent: '#2D7FF9', border: '#2A3540' } },
  { id: 'midnight-aurora', label: 'Midnight Aurora', group: 'classics', dark: true, description: 'Indigo and violet launch-era signature.', preview: { canvas: '#0D0E1D', panel: '#181A33', text: '#EEF0FF', primary: '#6C7BFF', accent: '#B96CFF', border: '#2A2D52' } },
  { id: 'tokyo-night', label: 'Tokyo Night', group: 'dark', dark: true, description: 'Deep navy with periwinkle focus.', preview: { canvas: '#1A1B26', panel: '#24283B', text: '#C0CAF5', primary: '#7AA2F7', accent: '#BB9AF7', border: '#3B4261' } },
  { id: 'catppuccin-mocha', label: 'Catppuccin Mocha', group: 'dark', dark: true, description: 'Soft dark violet with rose accents.', preview: { canvas: '#1E1E2E', panel: '#313244', text: '#CDD6F4', primary: '#CBA6F7', accent: '#F5C2E7', border: '#45475A' } },
  { id: 'rose-pine', label: 'Rosé Pine', group: 'dark', dark: true, description: 'Muted ink with lavender and rose.', preview: { canvas: '#191724', panel: '#1F1D2E', text: '#E0DEF4', primary: '#C4A7E7', accent: '#EBBCBA', border: '#403D52' } },
  { id: 'one-dark', label: 'One Dark', group: 'dark', dark: true, description: 'Editor-inspired graphite with blue and violet.', preview: { canvas: '#282C34', panel: '#21252B', text: '#C5CCD6', primary: '#61AFEF', accent: '#C678DD', border: '#3E4451' } },
  { id: 'gruvbox-dark', label: 'Gruvbox Dark', group: 'dark', dark: true, description: 'Earthy charcoal with amber emphasis.', preview: { canvas: '#282828', panel: '#3C3836', text: '#EBDBB2', primary: '#FABD2F', accent: '#FE8019', border: '#504945' } },
  { id: 'solarized-dark', label: 'Solarized Dark', group: 'dark', dark: true, description: 'Low-glare blue-green terminal palette.', preview: { canvas: '#002B36', panel: '#073642', text: '#EEE8D5', primary: '#268BD2', accent: '#2AA198', border: '#14424F' } },
  { id: 'dracula', label: 'Dracula', group: 'dark', dark: true, description: 'High-energy charcoal with violet and pink.', preview: { canvas: '#282A36', panel: '#343746', text: '#F8F8F2', primary: '#BD93F9', accent: '#FF79C6', border: '#44475A' } },
  { id: 'nord', label: 'Nord', group: 'dark', dark: true, description: 'Arctic charcoal with quiet blue focus.', preview: { canvas: '#2E3440', panel: '#3B4252', text: '#ECEFF4', primary: '#88C0D0', accent: '#5E81AC', border: '#4C566A' } },
] as const satisfies readonly ThemeDefinition[]
```

Export:

```ts
export type ThemeId = (typeof THEME_CATALOG)[number]['id']
export const THEME_BY_ID = Object.fromEntries(
  THEME_CATALOG.map(theme => [theme.id, theme]),
) as Record<ThemeId, (typeof THEME_CATALOG)[number]>
export const DARK_THEME_IDS = THEME_CATALOG.filter(theme => theme.dark).map(theme => theme.id)
export function isThemeId(value: string): value is ThemeId {
  return Object.prototype.hasOwnProperty.call(THEME_BY_ID, value)
}
```

- [ ] **Step 4: Run the catalog test**

Run:

```bash
cd frontend && npm test -- src/lib/themes/catalog.test.ts
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit the catalog**

```bash
git add frontend/src/lib/themes/catalog.ts frontend/src/lib/themes/catalog.test.ts
git commit -m "feat: define Research Core theme catalog"
```

### Task 2: Desktop Palettes, API Lockstep, and Fresh Default

**Files:**
- Modify: `desktop/window.py`
- Modify: `desktop/config.py`
- Modify: `desktop/tests/test_window.py`
- Modify: `desktop/tests/test_config.py`
- Modify: `api/routers/deeper_notebook.py`
- Modify: `tests/test_deeper_notebook_router.py`

**Interfaces:**
- Consumes: the exact 25 IDs from Task 1.
- Produces: `_THEMES`, `_theme_tokens(theme_id: str) -> dict[str, str]`, `_VALID_THEMES`, and fresh-install default `research-core-dark`.

- [ ] **Step 1: Add failing exact-ID, semantic-token, focus-contrast, and default tests**

Add to `desktop/tests/test_window.py`:

```py
EXPECTED_THEME_IDS = {
    "research-core-dark", "research-core-light", "deep-ocean", "graphite-lab",
    "arctic-research", "archive-paper", "high-contrast-dark", "high-contrast-light",
    "light-blue", "system", "solarized-light", "github-light", "paper",
    "catppuccin-latte", "rose-pine-dawn", "dark", "midnight-aurora",
    "tokyo-night", "catppuccin-mocha", "rose-pine", "one-dark",
    "gruvbox-dark", "solarized-dark", "dracula", "nord",
}

def test_theme_catalog_contains_exact_research_core_os_ids():
    assert set(_THEMES) == EXPECTED_THEME_IDS

@pytest.mark.parametrize("theme_id", list(_THEMES))
def test_every_theme_exposes_research_core_semantic_tokens(theme_id):
    tokens = _theme_tokens(theme_id)
    required = {
        "--dn-canvas", "--dn-panel", "--dn-panel-raised", "--dn-separator",
        "--dn-focus", "--dn-selection", "--dn-evidence", "--dn-warning",
        "--dn-editable", "--dn-read-only", "--dn-model-local", "--dn-model-cloud",
        "--dn-graph-node", "--dn-graph-edge", "--dn-graph-selected",
    }
    assert required <= set(tokens)

@pytest.mark.parametrize("theme_id", list(_THEMES))
def test_focus_ring_has_three_to_one_contrast_against_background(theme_id):
    tokens = _theme_tokens(theme_id)
    assert _contrast_ratio(tokens["--ring"], tokens["--background"]) >= 3.0
```

Change `desktop/tests/test_config.py`:

```py
def test_theme_defaults_to_research_core_dark(tmp_path):
    cfg = load_or_create(tmp_path / "config.toml")
    assert cfg.theme == "research-core-dark"

def test_existing_theme_is_not_replaced_by_new_default(tmp_path):
    cfg_path = tmp_path / "config.toml"
    Config(model_dir=tmp_path, provider="none", default_model="",
           surreal_user="root", surreal_password="A" * 24,
           theme="light-blue").save(cfg_path)
    assert load_or_create(cfg_path).theme == "light-blue"
```

Change the missing-config assertion in `tests/test_deeper_notebook_router.py` to
expect `research-core-dark`, then add a parameterized POST test for the eight new
IDs.

- [ ] **Step 2: Run focused Python tests and verify failure**

Run:

```bash
pytest -q desktop/tests/test_window.py desktop/tests/test_config.py tests/test_deeper_notebook_router.py
```

Expected: FAIL on missing IDs/tokens and the old `light-blue` default.

- [ ] **Step 3: Add the eight palettes and semantic token derivation**

Prepend these palettes to `_THEMES` in `desktop/window.py`:

```py
"research-core-dark": {"is_dark": True, "bg": "#071B1D", "fg": "#D8FFF8", "card": "#0B292B", "muted": "#12383A", "muted_fg": "#A3CEC8", "primary": "#2DD4BF", "primary_fg": "#041313", "accent": "#38BDF8", "accent_fg": "#041313", "border": "#225053", "destructive": "#FB7185"},
"research-core-light": {"is_dark": False, "bg": "#F5FBF9", "fg": "#102A2A", "card": "#FFFFFF", "muted": "#E5F2EE", "muted_fg": "#526E69", "primary": "#0F766E", "primary_fg": "#FFFFFF", "accent": "#0284C7", "accent_fg": "#FFFFFF", "border": "#C9DED8", "destructive": "#DC2626"},
"deep-ocean": {"is_dark": True, "bg": "#06151F", "fg": "#D8F3F8", "card": "#0B2432", "muted": "#123446", "muted_fg": "#9FC6CE", "primary": "#2DD4BF", "primary_fg": "#041619", "accent": "#38BDF8", "accent_fg": "#041619", "border": "#21485A", "destructive": "#FB7185"},
"graphite-lab": {"is_dark": True, "bg": "#151A1D", "fg": "#EDF7F5", "card": "#20272B", "muted": "#2A3438", "muted_fg": "#B5C6C3", "primary": "#5EEAD4", "primary_fg": "#0D1718", "accent": "#67E8F9", "accent_fg": "#0D1718", "border": "#3B494E", "destructive": "#FB7185"},
"arctic-research": {"is_dark": False, "bg": "#F4FAFC", "fg": "#122A35", "card": "#FFFFFF", "muted": "#E3EFF3", "muted_fg": "#4F6974", "primary": "#0F766E", "primary_fg": "#FFFFFF", "accent": "#0284C7", "accent_fg": "#FFFFFF", "border": "#C7DBE2", "destructive": "#DC2626"},
"archive-paper": {"is_dark": False, "bg": "#F7F1E5", "fg": "#2B332E", "card": "#FFFDF8", "muted": "#ECE3D3", "muted_fg": "#665F52", "primary": "#0F766E", "primary_fg": "#FFFFFF", "accent": "#A16207", "accent_fg": "#FFFFFF", "border": "#D8CDBB", "destructive": "#B91C1C"},
"high-contrast-dark": {"is_dark": True, "bg": "#000000", "fg": "#FFFFFF", "card": "#111111", "muted": "#1E1E1E", "muted_fg": "#E6E6E6", "primary": "#5EEAD4", "primary_fg": "#000000", "accent": "#67E8F9", "accent_fg": "#000000", "border": "#FFFFFF", "destructive": "#FF5A67"},
"high-contrast-light": {"is_dark": False, "bg": "#FFFFFF", "fg": "#000000", "card": "#FFFFFF", "muted": "#EFEFEF", "muted_fg": "#333333", "primary": "#006B63", "primary_fg": "#FFFFFF", "accent": "#005FCC", "accent_fg": "#FFFFFF", "border": "#000000", "destructive": "#B00020"},
```

In `_theme_tokens`, derive the required `--dn-*` values exclusively from the
current palette. Use `primary` for focus/local/editable, `accent` for evidence
and graph selection, `muted_fg` for graph edges/read-only, and the existing
warning constant `#D97706` on light themes or `#FBBF24` on dark themes. Do not
branch on individual theme IDs.

Add these entries to the returned token dictionary:

```py
warning = "#FBBF24" if is_dark else "#D97706"
research_tokens = {
    "--dn-canvas": bg,
    "--dn-panel": card,
    "--dn-panel-raised": f"color-mix(in oklab, {card} 88%, {primary})",
    "--dn-separator": border,
    "--dn-focus": primary,
    "--dn-selection": f"color-mix(in oklab, {primary} 22%, transparent)",
    "--dn-evidence": accent,
    "--dn-warning": f"var(--warning, {warning})",
    "--dn-editable": primary,
    "--dn-read-only": muted_fg,
    "--dn-model-local": primary,
    "--dn-model-cloud": f"var(--info, {accent})",
    "--dn-graph-node": primary,
    "--dn-graph-edge": muted_fg,
    "--dn-graph-selected": accent,
}
```

Merge `research_tokens` into the existing return value using dictionary
unpacking so every theme receives the same semantic contract.

- [ ] **Step 4: Update allowlist and defaults**

Add all eight IDs to `_VALID_THEMES`. Change only fresh/missing fallbacks from
`light-blue` to `research-core-dark` in:

- `Config.theme`;
- `load_or_create()` creation and missing-key fallback;
- `get_theme()` unreadable-config fallback;
- `_theme_tokens()` unknown-ID fallback;
- `_theme_injection_js()` unknown and unstyled fallback.

Do not rewrite a loaded valid value.

- [ ] **Step 5: Run focused Python tests**

Run:

```bash
pytest -q desktop/tests/test_window.py desktop/tests/test_config.py tests/test_deeper_notebook_router.py
```

Expected: PASS.

- [ ] **Step 6: Commit the runtime theme contract**

```bash
git add desktop/window.py desktop/config.py desktop/tests/test_window.py desktop/tests/test_config.py api/routers/deeper_notebook.py tests/test_deeper_notebook_router.py
git commit -m "feat: add Research Core runtime themes"
```

### Task 3: Pre-Hydration Theme Application and Semantic CSS

**Files:**
- Modify: `frontend/src/lib/theme-script.ts`
- Create: `frontend/src/lib/theme-script.test.ts`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/deeper-notebook/tokens.css`
- Modify: `frontend/src/components/vault/ResearchCoreVisualSystem.test.tsx`

**Interfaces:**
- Consumes: `DEFAULT_THEME_ID`, `DARK_THEME_IDS`, and `isThemeId` from Task 1.
- Produces: `themeScript` with canonical storage precedence and semantic CSS variables available to every component.

- [ ] **Step 1: Write failing pre-hydration and token tests**

Create `frontend/src/lib/theme-script.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { themeScript } from './theme-script'

describe('pre-hydration Research Core theme script', () => {
  it('prefers canonical storage, then legacy, then old Zustand storage', () => {
    expect(themeScript.indexOf("getItem('dn-theme')")).toBeLessThan(themeScript.indexOf("getItem('onp-theme')"))
    expect(themeScript.indexOf("getItem('onp-theme')")).toBeLessThan(themeScript.indexOf("getItem('theme-storage')"))
  })

  it('falls back to Research Core Dark and sets dark class from the catalog', () => {
    expect(themeScript).toContain("'research-core-dark'")
    expect(themeScript).toContain('research-core-dark')
    expect(themeScript).toContain("classList.toggle('dark'")
  })

  it('normalizes legacy light values and rejects unknown theme IDs', () => {
    expect(themeScript).toContain("theme === 'light'")
    expect(themeScript).toContain("theme = 'light-blue'")
    expect(themeScript).toContain('validThemes.includes(theme)')
  })
})
```

Extend `ResearchCoreVisualSystem.test.tsx` to require:

```ts
for (const token of [
  '--dn-canvas', '--dn-panel', '--dn-panel-raised', '--dn-separator',
  '--dn-focus', '--dn-selection', '--dn-evidence', '--dn-warning',
  '--dn-editable', '--dn-read-only', '--dn-model-local', '--dn-model-cloud',
  '--dn-graph-node', '--dn-graph-edge', '--dn-graph-selected',
]) expect(tokens).toMatch(new RegExp(`${token}:`))
```

- [ ] **Step 2: Run the frontend tests and verify failure**

Run:

```bash
cd frontend && npm test -- src/lib/theme-script.test.ts src/components/vault/ResearchCoreVisualSystem.test.tsx
```

Expected: FAIL on old storage precedence/default and missing tokens.

- [ ] **Step 3: Implement canonical pre-hydration selection**

Import the catalog constants into `theme-script.ts` and emit a script that:

```ts
import { DARK_THEME_IDS, DEFAULT_THEME_ID, THEME_CATALOG } from '@/lib/themes/catalog'

const darkIds = JSON.stringify(DARK_THEME_IDS)
const validIds = JSON.stringify(THEME_CATALOG.map(theme => theme.id))

export const themeScript = `
(function() {
  try {
    var canonical = localStorage.getItem('dn-theme');
    var legacy = localStorage.getItem('onp-theme');
    var persisted = JSON.parse(localStorage.getItem('theme-storage') || '{}').state?.theme;
    var theme = canonical || legacy || persisted || '${DEFAULT_THEME_ID}';
    var systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (theme === 'light') theme = 'light-blue';
    if (theme === 'system') theme = systemDark ? 'dark' : 'light-blue';
    var validThemes = ${validIds};
    if (!validThemes.includes(theme)) theme = '${DEFAULT_THEME_ID}';
    var darkThemes = ${darkIds};
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle('dark', darkThemes.includes(theme));
  } catch (error) {
    document.documentElement.dataset.theme = '${DEFAULT_THEME_ID}';
    document.documentElement.classList.add('dark');
  }
})();
`
```

The desktop injection remains authoritative after load; this script prevents a
wrong-theme flash before that bridge is available.

- [ ] **Step 4: Add semantic CSS variables**

Add the required `--dn-*` tokens to `tokens.css` using `color-mix()` against
`--background`, `--card`, `--foreground`, `--primary`, `--accent`, `--border`,
and the semantic status tokens. Keep component CSS theme-agnostic. Retain the
global reduced-motion block in `globals.css` unchanged.

Use this root contract:

```css
:root {
  --dn-canvas: var(--background);
  --dn-panel: var(--card);
  --dn-panel-raised: color-mix(in oklab, var(--card) 88%, var(--primary));
  --dn-separator: var(--border);
  --dn-focus: var(--ring);
  --dn-selection: color-mix(in oklab, var(--primary) 22%, transparent);
  --dn-evidence: var(--accent);
  --dn-warning: var(--warning);
  --dn-editable: var(--primary);
  --dn-read-only: var(--muted-foreground);
  --dn-model-local: var(--primary);
  --dn-model-cloud: var(--info);
  --dn-graph-node: var(--primary);
  --dn-graph-edge: var(--muted-foreground);
  --dn-graph-selected: var(--accent);
}
```

- [ ] **Step 5: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- src/lib/theme-script.test.ts src/components/vault/ResearchCoreVisualSystem.test.tsx src/lib/brand.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit theme application and tokens**

```bash
git add frontend/src/lib/theme-script.ts frontend/src/lib/theme-script.test.ts frontend/src/app/globals.css frontend/src/components/deeper-notebook/tokens.css frontend/src/components/vault/ResearchCoreVisualSystem.test.tsx
git commit -m "feat: apply Research Core themes before hydration"
```

### Task 4: Categorized Theme Switcher and Appearance Gallery

**Files:**
- Create: `frontend/src/components/deeper-notebook/ThemePreviewCard.tsx`
- Create: `frontend/src/components/deeper-notebook/ThemeGallery.tsx`
- Create: `frontend/src/components/deeper-notebook/ThemeGallery.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/ThemeSwitcher.tsx`
- Modify: `frontend/src/components/deeper-notebook/ThemeSwitcher.test.tsx`
- Modify: `frontend/src/components/deeper-notebook/index.ts`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

**Interfaces:**
- Consumes: `THEME_CATALOG`, `THEME_BY_ID`, `ThemeDefinition`, `ThemeId`, `isThemeId`, `readStoredTheme`, `writeStoredTheme`, and the `window.DN ?? window.ONP` bridge.
- Produces: `ThemePreviewCard({ theme, selected, previewing, onPreview, onApply })` and `ThemeGallery()`.

- [ ] **Step 1: Write failing gallery behavior tests**

Create tests that render the gallery with mocked dropdown primitives and a
canonical `DN.setTheme` spy. Preview changes only the document theme; Apply is
the only action that calls the persistent bridge. Assert:

```ts
expect(screen.getByRole('heading', { name: 'Featured' })).toBeVisible()
expect(screen.getByRole('button', { name: /Preview Research Core Light/ })).toBeVisible()
expect(screen.getByText('High Contrast Dark')).toBeVisible()
fireEvent.click(screen.getByRole('button', { name: /Preview Archive Paper/ }))
expect(document.documentElement.dataset.theme).toBe('archive-paper')
expect(canonical.setTheme).not.toHaveBeenCalled()
fireEvent.click(screen.getByRole('button', { name: 'Restore previous theme' }))
expect(document.documentElement.dataset.theme).toBe('research-core-dark')
fireEvent.click(screen.getByRole('button', { name: 'Apply Archive Paper' }))
expect(canonical.setTheme).toHaveBeenCalledWith('archive-paper')
expect(localStorage.getItem('dn-theme')).toBe('archive-paper')
```

Extend `ThemeSwitcher.test.tsx` to assert the compact menu contains Featured,
Light, Dark, Accessibility, and Classics labels and selects
`research-core-light` through the canonical bridge.

- [ ] **Step 2: Run component tests and verify failure**

Run:

```bash
cd frontend && npm test -- src/components/deeper-notebook/ThemeGallery.test.tsx src/components/deeper-notebook/ThemeSwitcher.test.tsx
```

Expected: FAIL because the gallery and catalog-driven switcher do not exist.

- [ ] **Step 3: Implement the semantic miniature preview**

`ThemePreviewCard.tsx` must render a small shell using inline custom properties
from `theme.preview`, not hardcoded Tailwind colors:

```tsx
<div
  className="overflow-hidden rounded-lg border shadow-sm"
  style={{
    '--preview-canvas': theme.preview.canvas,
    '--preview-panel': theme.preview.panel,
    '--preview-text': theme.preview.text,
    '--preview-primary': theme.preview.primary,
    '--preview-accent': theme.preview.accent,
    '--preview-border': theme.preview.border,
  } as React.CSSProperties}
>
  <div className="grid h-24 grid-cols-[1.35rem_1fr_.8fr] bg-[var(--preview-canvas)] text-[var(--preview-text)]">
    <div className="border-r border-[var(--preview-border)] bg-[var(--preview-panel)]" />
    <div className="space-y-2 p-2"><div className="h-2 w-10 rounded bg-[var(--preview-primary)]" /><div className="h-1.5 w-full rounded bg-[var(--preview-border)]" /><div className="h-1.5 w-3/4 rounded bg-[var(--preview-border)]" /></div>
    <div className="m-2 rounded border border-[var(--preview-border)] bg-[var(--preview-panel)]"><div className="m-2 h-2 rounded bg-[var(--preview-accent)]" /></div>
  </div>
</div>
```

- [ ] **Step 4: Implement preview/apply/restore and grouping**

`ThemeGallery` records the active theme when mounted. Preview sets
`document.documentElement.dataset.theme` and toggles `.dark` from
`THEME_BY_ID[themeId].dark`; it must not call the desktop bridge or write
storage. Apply calls the canonical bridge plus `writeStoredTheme`. Restore sets
the original dataset/class directly and leaves persisted configuration
untouched. Render
sections in this order: Featured, Light, Dark, Accessibility, Classics. Include
a text search over label and description.

Refactor `ThemeSwitcher` to map the same catalog into compact grouped menu
items. Preserve `iconOnly`, canonical bridge precedence, API fallback, and
legacy storage mirroring.

- [ ] **Step 5: Add Appearance to Settings**

Insert before `SettingsForm`:

```tsx
<section aria-labelledby="appearance-heading" className="space-y-4">
  <div>
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Appearance</p>
    <h2 id="appearance-heading" className="mt-1 text-xl font-semibold">Choose your research environment</h2>
    <p className="mt-1 text-sm text-muted-foreground">Preview a complete workspace theme, then apply it when it feels right.</p>
  </div>
  <ThemeGallery />
</section>
```

- [ ] **Step 6: Run component and settings tests**

Run:

```bash
cd frontend && npm test -- src/components/deeper-notebook/ThemeGallery.test.tsx src/components/deeper-notebook/ThemeSwitcher.test.tsx
npm run lint -- src/components/deeper-notebook/ThemeGallery.tsx src/components/deeper-notebook/ThemePreviewCard.tsx src/components/deeper-notebook/ThemeSwitcher.tsx 'src/app/(dashboard)/settings/page.tsx'
```

Expected: tests PASS and ESLint exits 0.

- [ ] **Step 7: Commit the gallery**

```bash
git add frontend/src/components/deeper-notebook/ThemePreviewCard.tsx frontend/src/components/deeper-notebook/ThemeGallery.tsx frontend/src/components/deeper-notebook/ThemeGallery.test.tsx frontend/src/components/deeper-notebook/ThemeSwitcher.tsx frontend/src/components/deeper-notebook/ThemeSwitcher.test.tsx frontend/src/components/deeper-notebook/index.ts 'frontend/src/app/(dashboard)/settings/page.tsx'
git commit -m "feat: add Research Core theme gallery"
```

### Task 5: Generated First-Run and Auxiliary Theme Assets

**Files:**
- Create: `scripts/render_theme_static_assets.py`
- Create: `desktop/tests/test_theme_static_assets.py`
- Create: `desktop/first_run/static/theme-catalog.generated.js`
- Modify: `desktop/first_run/static/themes.css`
- Modify: `desktop/model_manager/static/themes.css`
- Modify/Create: `desktop/memory_dashboard/static/themes.css`
- Modify: `desktop/first_run/static/index.html`
- Modify: `desktop/first_run/static/wizard.js`
- Modify: `desktop/first_run/server.py`
- Modify: `desktop/model_manager/static/index.html`
- Modify: `desktop/model_manager/server.py`
- Modify: `desktop/memory_dashboard/static/index.html`
- Modify: `desktop/memory_dashboard/static/dashboard.js`
- Modify: `desktop/memory_dashboard/server.py`

**Interfaces:**
- Consumes: `desktop.window._THEMES` and `_theme_tokens`.
- Produces: `render_assets(check: bool) -> int`, three identical generated CSS files, and `window.DN_THEME_CATALOG` for first run.

- [ ] **Step 1: Write the failing freshness test**

```py
import json
from pathlib import Path
from desktop.window import _THEMES
from scripts.render_theme_static_assets import render_assets

ROOT = Path(__file__).resolve().parents[2]

def test_generated_theme_assets_are_current():
    assert render_assets(check=True) == 0

def test_first_run_catalog_contains_every_runtime_theme():
    source = (ROOT / "desktop/first_run/static/theme-catalog.generated.js").read_text()
    prefix = "window.DN_THEME_CATALOG = "
    assert source.startswith(prefix)
    catalog = json.loads(source.removeprefix(prefix).removesuffix(";\n"))
    assert {entry["id"] for entry in catalog} == set(_THEMES)
```

- [ ] **Step 2: Run the test and verify the missing generator failure**

Run:

```bash
pytest -q desktop/tests/test_theme_static_assets.py
```

Expected: FAIL because `scripts.render_theme_static_assets` does not exist.

- [ ] **Step 3: Implement deterministic generation**

Create `scripts/render_theme_static_assets.py` with this metadata and rendering
contract. The helper may split the expressions over more lines, but the output
and public interface remain exact:

```py
from __future__ import annotations

import json
import sys
from pathlib import Path

from desktop.window import _THEMES

ROOT = Path(__file__).resolve().parents[1]
CSS_PATHS = (
    ROOT / "desktop/first_run/static/themes.css",
    ROOT / "desktop/model_manager/static/themes.css",
    ROOT / "desktop/memory_dashboard/static/themes.css",
)
CATALOG_PATH = ROOT / "desktop/first_run/static/theme-catalog.generated.js"
THEME_META = {
    "research-core-dark": ("Research Core Dark", "featured"),
    "research-core-light": ("Research Core Light", "featured"),
    "deep-ocean": ("Deep Ocean", "dark"),
    "graphite-lab": ("Graphite Lab", "dark"),
    "arctic-research": ("Arctic Research", "light"),
    "archive-paper": ("Archive Paper", "light"),
    "high-contrast-dark": ("High Contrast Dark", "accessibility"),
    "high-contrast-light": ("High Contrast Light", "accessibility"),
    "light-blue": ("Light Blue", "classics"),
    "system": ("System", "classics"),
    "solarized-light": ("Solarized Light", "light"),
    "github-light": ("GitHub Light", "light"),
    "paper": ("Paper", "light"),
    "catppuccin-latte": ("Catppuccin Latte", "light"),
    "rose-pine-dawn": ("Rosé Pine Dawn", "light"),
    "dark": ("Dark", "classics"),
    "midnight-aurora": ("Midnight Aurora", "classics"),
    "tokyo-night": ("Tokyo Night", "dark"),
    "catppuccin-mocha": ("Catppuccin Mocha", "dark"),
    "rose-pine": ("Rosé Pine", "dark"),
    "one-dark": ("One Dark", "dark"),
    "gruvbox-dark": ("Gruvbox Dark", "dark"),
    "solarized-dark": ("Solarized Dark", "dark"),
    "dracula": ("Dracula", "dark"),
    "nord": ("Nord", "dark"),
}

def render_css() -> str:
    blocks = ["/* Generated by scripts/render_theme_static_assets.py. */"]
    for theme_id, palette in _THEMES.items():
        blocks.append(
            f'[data-theme="{theme_id}"] {{\n'
            f'  --bg: {palette["bg"]};\n'
            f'  --surface: {palette["card"]};\n'
            f'  --text: {palette["fg"]};\n'
            f'  --muted: {palette["muted_fg"]};\n'
            f'  --border: {palette["border"]};\n'
            f'  --primary: {palette["primary"]};\n'
            f'  --accent: {palette["accent"]};\n'
            f'  --on-primary: {palette["primary_fg"]};\n'
            '}\n'
        )
    return "\n".join(blocks) + "\n"

def render_catalog() -> str:
    assert set(THEME_META) == set(_THEMES)
    entries = []
    for theme_id, palette in _THEMES.items():
        label, group = THEME_META[theme_id]
        entries.append({
            "id": theme_id,
            "name": label,
            "group": group,
            "dark": bool(palette["is_dark"]),
            "bg": palette["bg"],
            "fg": palette["primary"],
        })
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    return f"window.DN_THEME_CATALOG = {payload};\n"

def render_assets(*, check: bool = False) -> int:
    expected = {path: render_css() for path in CSS_PATHS}
    expected[CATALOG_PATH] = render_catalog()
    if check:
        stale = [path for path, content in expected.items()
                 if not path.exists() or path.read_text(encoding="utf-8") != content]
        return 1 if stale else 0
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(render_assets(check="--check" in sys.argv))
```

- [ ] **Step 4: Generate assets and wire first run**

Run:

```bash
python scripts/render_theme_static_assets.py
```

Load `theme-catalog.generated.js` before `wizard.js`. Replace the hardcoded
`THEMES` array with:

```js
const THEMES = window.DN_THEME_CATALOG;
let chosenTheme = 'research-core-dark';
```

The dark quick toggle switches between `research-core-dark` and
`research-core-light` using the selected catalog entry's `dark` field.

Change the initial `data-theme` value in all three auxiliary `index.html` files
to `research-core-dark`. Add `<link rel="stylesheet" href="/static/themes.css">`
before `style.css` in the memory dashboard. Change the missing/request-failure
fallback literals in `desktop/model_manager/server.py`,
`desktop/memory_dashboard/server.py`, and
`desktop/memory_dashboard/static/dashboard.js` from `light-blue` to
`research-core-dark`. These are fresh or unavailable-config fallbacks only; do
not override a returned stored theme.

Change `body.get("theme", "light-blue")` in `desktop/first_run/server.py` to
`body.get("theme", "research-core-dark")`.

- [ ] **Step 5: Run static and desktop theme tests**

Run:

```bash
python scripts/render_theme_static_assets.py --check
pytest -q desktop/tests/test_theme_static_assets.py desktop/tests/test_first_run.py desktop/tests/test_model_manager_server.py desktop/tests/test_memory_dashboard_server.py
```

Expected: generator exits 0 and tests PASS.

- [ ] **Step 6: Commit generated assets with their generator**

```bash
git add scripts/render_theme_static_assets.py desktop/tests/test_theme_static_assets.py desktop/first_run/static/theme-catalog.generated.js desktop/first_run/static/themes.css desktop/model_manager/static/themes.css desktop/memory_dashboard/static/themes.css desktop/first_run/static/index.html desktop/first_run/static/wizard.js desktop/first_run/server.py desktop/model_manager/static/index.html desktop/model_manager/server.py desktop/memory_dashboard/static/index.html desktop/memory_dashboard/static/dashboard.js desktop/memory_dashboard/server.py
git commit -m "feat: synchronize desktop theme surfaces"
```

### Task 6: Deterministic Theme Visual Proof

**Files:**
- Create: `frontend/e2e/fixtures/theme-visuals.ts`
- Create: `frontend/e2e/theme-gallery-visual.spec.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/playwright.config.ts`

**Interfaces:**
- Consumes: `/settings`, the strict mocked auth/settings endpoints, and theme IDs from Task 1.
- Produces: `installThemeVisualFixture(page: Page)`, stable shell/gallery screenshots, and `npm run test:e2e:themes`.

- [ ] **Step 1: Write the visual fixture and failing screenshot test**

The fixture must fulfill `/api/auth/get-session`, `/api/auth/status`, settings,
version, observability, and theme GET/POST endpoints. Reject unhandled API calls
by recording them and failing the test. Seed `dn-theme` before navigation.

Create this test structure:

```ts
import { expect, test } from '@playwright/test'
import { installThemeVisualFixture } from './fixtures/theme-visuals'

const captures = [
  { theme: 'research-core-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'research-core-light', viewport: { width: 1440, height: 900 } },
  { theme: 'deep-ocean', viewport: { width: 1280, height: 800 } },
  { theme: 'archive-paper', viewport: { width: 1280, height: 800 } },
  { theme: 'high-contrast-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'high-contrast-light', viewport: { width: 1440, height: 900 } },
] as const

for (const capture of captures) {
  test(`${capture.theme} theme gallery`, async ({ page }) => {
    const fixture = await installThemeVisualFixture(page, capture.theme)
    await page.setViewportSize(capture.viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Choose your research environment' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', capture.theme)
    await expect(page).toHaveScreenshot(`${capture.theme}-${capture.viewport.width}x${capture.viewport.height}.png`, {
      animations: 'disabled',
      caret: 'hide',
      fullPage: true,
    })
    expect(fixture.unexpectedRequests).toEqual([])
  })
}
```

- [ ] **Step 2: Add a focused Playwright command**

Add to `frontend/package.json`:

```json
"test:e2e:themes": "playwright test e2e/theme-gallery-visual.spec.ts --project=mocked-browser"
```

Set the mocked browser project's locale to `en-US`, color scheme to dark, and
device scale factor to 1. Do not change the `native-runtime` or
`packaged-device` projects.

- [ ] **Step 3: Generate and inspect baseline screenshots**

Run:

```bash
cd frontend && npm run test:e2e:themes -- --update-snapshots
```

Expected: six screenshots created and tests PASS. Inspect each image for clipped
content, wrong-theme flash, unreadable muted text, broken portals, inconsistent
selection, and generic card-grid appearance. If a defect is visible, fix the
responsible component or token and regenerate; do not approve the baseline by
raising screenshot thresholds.

- [ ] **Step 4: Re-run without updating baselines**

Run:

```bash
cd frontend && npm run test:e2e:themes
```

Expected: PASS with no changed pixels beyond Playwright's default comparator.

- [ ] **Step 5: Commit visual proof**

```bash
git add frontend/e2e/fixtures/theme-visuals.ts frontend/e2e/theme-gallery-visual.spec.ts frontend/e2e/theme-gallery-visual.spec.ts-snapshots frontend/package.json frontend/playwright.config.ts
git commit -m "test: add Research Core theme visual proof"
```

### Task 7: Local Contextual Guided Tips

**Files:**
- Create: `frontend/src/lib/guided-tips/catalog.ts`
- Create: `frontend/src/lib/guided-tips/catalog.test.ts`
- Create: `frontend/src/lib/stores/guided-tips-store.ts`
- Create: `frontend/src/lib/stores/guided-tips-store.test.ts`
- Create: `frontend/src/components/guided-tips/GuidedTipsProvider.tsx`
- Create: `frontend/src/components/guided-tips/GuidedTipsProvider.test.tsx`
- Create: `frontend/src/components/guided-tips/index.ts`
- Modify: `frontend/src/components/layout/AppShell.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

**Interfaces:**
- Produces: `GuidedTipDefinition`, `GUIDED_TIPS`, `getGuidedTipForPath(pathname: string)`, `useGuidedTipsStore`, and `GuidedTipsProvider`.
- Consumes: authenticated dashboard routing, stable sidebar `data-guided-tip-anchor` attributes, and the Settings Appearance section created in Task 4.

- [ ] **Step 1: Write failing catalog and persistence tests**

Create `frontend/src/lib/guided-tips/catalog.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { GUIDED_TIPS, getGuidedTipForPath } from './catalog'

describe('Guided Tips catalog', () => {
  it('covers the approved major sections with stable unique IDs', () => {
    expect(GUIDED_TIPS.map(tip => tip.id)).toEqual([
      'dashboard-overview', 'sources-overview', 'capture-overview',
      'notebooks-overview', 'knowledge-overview', 'search-overview',
      'studio-overview', 'podcasts-overview', 'study-overview',
      'models-overview', 'settings-overview',
    ])
    expect(new Set(GUIDED_TIPS.map(tip => tip.id)).size).toBe(GUIDED_TIPS.length)
    expect(GUIDED_TIPS.every(tip => tip.version === 1)).toBe(true)
  })

  it('uses path boundaries and chooses the most specific route', () => {
    expect(getGuidedTipForPath('/settings/api-keys')?.id).toBe('models-overview')
    expect(getGuidedTipForPath('/settings')?.id).toBe('settings-overview')
    expect(getGuidedTipForPath('/sources/example')?.id).toBe('sources-overview')
    expect(getGuidedTipForPath('/source-code')).toBeUndefined()
  })
})
```

Create a store test that resets the Zustand state before each test and asserts:

```ts
const tip = { id: 'knowledge-overview', version: 1 }
expect(useGuidedTipsStore.getState().isComplete(tip)).toBe(false)
useGuidedTipsStore.getState().complete(tip)
expect(useGuidedTipsStore.getState().isComplete(tip)).toBe(true)
expect(useGuidedTipsStore.getState().isComplete({ ...tip, version: 2 })).toBe(false)
useGuidedTipsStore.getState().setEnabled(false)
useGuidedTipsStore.getState().replayAll()
expect(useGuidedTipsStore.getState().enabled).toBe(false)
expect(useGuidedTipsStore.getState().completed).toEqual({})
```

- [ ] **Step 2: Run the focused tests and verify missing-module failures**

Run:

```bash
cd frontend && npm test -- src/lib/guided-tips/catalog.test.ts src/lib/stores/guided-tips-store.test.ts
```

Expected: FAIL because the catalog and store do not exist.

- [ ] **Step 3: Implement the exact initial tip catalog**

```ts
export interface GuidedTipDefinition {
  id: string
  version: number
  pathPrefix: string
  anchor: string
  title: string
  body: string
}

export const GUIDED_TIPS = [
  { id: 'dashboard-overview', version: 1, pathPrefix: '/', anchor: '/', title: 'Your research home', body: 'Resume recent work, create a notebook, or check active research and podcast production.' },
  { id: 'sources-overview', version: 1, pathPrefix: '/sources', anchor: '/sources', title: 'Sources', body: 'Add and organize the material Deeper Notebook can cite in answers and outputs.' },
  { id: 'capture-overview', version: 1, pathPrefix: '/capture', anchor: '/capture', title: 'Capture', body: 'Collect a quick idea or reference now, then organize it when you are ready.' },
  { id: 'notebooks-overview', version: 1, pathPrefix: '/notebooks', anchor: '/notebooks', title: 'Notebooks', body: 'Group sources, notes, grounded conversations, and generated research artifacts by project.' },
  { id: 'knowledge-overview', version: 1, pathPrefix: '/knowledge', anchor: '/knowledge', title: 'Knowledge workspace', body: 'Explore notes, backlinks, graphs, searches, and read-only external vaults in one persistent workspace.' },
  { id: 'search-overview', version: 1, pathPrefix: '/search', anchor: '/search', title: 'Ask and Search', body: 'Choose the sources you trust, ask a grounded question, and open citations in context.' },
  { id: 'studio-overview', version: 1, pathPrefix: '/studio', anchor: '/studio', title: 'Studio', body: 'Turn selected research into a controlled output. Opening Studio never starts generation.' },
  { id: 'podcasts-overview', version: 1, pathPrefix: '/podcasts', anchor: '/podcasts', title: 'Podcasts', body: 'Create optional source-grounded audio, review its outline, and inspect the transcript and citations.' },
  { id: 'study-overview', version: 1, pathPrefix: '/study', anchor: '/study', title: 'Study', body: 'Build focused review material from selected notebook sources.' },
  { id: 'models-overview', version: 1, pathPrefix: '/settings/api-keys', anchor: '/settings/api-keys', title: 'Models', body: 'Choose local or connected models by role and verify readiness before using them.' },
  { id: 'settings-overview', version: 1, pathPrefix: '/settings', anchor: '/settings', title: 'Settings', body: 'Control appearance, guided tips, providers, privacy, and advanced application behavior.' },
] as const satisfies readonly GuidedTipDefinition[]

export function getGuidedTipForPath(pathname: string): GuidedTipDefinition | undefined {
  return [...GUIDED_TIPS]
    .filter(tip => tip.pathPrefix === '/'
      ? pathname === '/'
      : pathname === tip.pathPrefix || pathname.startsWith(`${tip.pathPrefix}/`))
    .sort((a, b) => b.pathPrefix.length - a.pathPrefix.length)[0]
}
```

- [ ] **Step 4: Implement local versioned completion state**

Create a persisted Zustand store named `dn-guided-tips-v1` with:

```ts
interface TipIdentity { id: string; version: number }
interface GuidedTipsState {
  enabled: boolean
  completed: Record<string, number>
  setEnabled: (enabled: boolean) => void
  complete: (tip: TipIdentity) => void
  replayAll: () => void
  isComplete: (tip: TipIdentity) => boolean
}
```

The default is `enabled: true`. `complete` stores the highest seen version for
the ID. `isComplete` returns true only when the stored version is greater than
or equal to the catalog version. `replayAll` clears `completed` and preserves
`enabled` exactly.

- [ ] **Step 5: Write failing provider behavior tests**

Mock `usePathname()` as `/knowledge`, render an element with
`data-guided-tip-anchor="/knowledge"`, and assert:

```ts
expect(await screen.findByRole('note', { name: 'Knowledge workspace tip' })).toBeVisible()
expect(screen.getByText(/read-only external vaults/)).toBeVisible()
fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
expect(screen.queryByRole('note', { name: 'Knowledge workspace tip' })).not.toBeInTheDocument()
```

Add tests that an open `[aria-modal="true"]` suppresses the tip, a missing
anchor fails closed, `Don't show again` sets `enabled` false, Escape dismisses
only the current version, and the callout contains no focus trap.

- [ ] **Step 6: Implement the anchored non-modal provider**

`GuidedTipsProvider` selects the longest matching route, checks `enabled` and
`isComplete`, finds `[data-guided-tip-anchor="${tip.anchor}"]`, and positions a
fixed-width callout beside the anchor using `getBoundingClientRect()`. Clamp top
and left to a 16-pixel viewport inset. Recalculate on resize and capture-phase
scroll.

Use an `aside` with `role="note"`, `aria-label={`${tip.title} tip`}`, and no
focus-trap behavior. `Got it` and Escape call `complete(tip)`. `Don't show
again` calls `setEnabled(false)`. A `MutationObserver` hides the callout while
any of these selectors exists:

```ts
'[aria-modal="true"], [data-guided-tips-suspend="true"]'
```

When the anchor disappears, hide the tip rather than moving it to an unrelated
corner. Disconnect observers and event listeners on cleanup.

- [ ] **Step 7: Add stable anchors and Settings controls**

Add `data-guided-tip-anchor="/"` to the expanded/collapsed brand area in
`AppSidebar`. Add `data-guided-tip-anchor={item.href}` to each navigation
button without changing its accessible name or click behavior.

Mount `<GuidedTipsProvider />` once inside `AppShell` after the main content.

In the Settings Appearance section, add:

```tsx
<div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3">
  <div>
    <p className="text-sm font-medium">Guided tips</p>
    <p className="text-sm text-muted-foreground">Show small contextual messages when you visit a section for the first time.</p>
  </div>
  <div className="flex gap-2">
    <Button type="button" variant="outline" role="switch" aria-checked={tipsEnabled} onClick={() => setTipsEnabled(!tipsEnabled)}>
      {tipsEnabled ? 'On' : 'Off'}
    </Button>
    <Button type="button" variant="ghost" onClick={replayAllTips}>Replay all tips</Button>
  </div>
</div>
```

The toggle changes only `enabled`. Replay changes only completion state.

- [ ] **Step 8: Run Guided Tips tests and lint**

Run:

```bash
cd frontend && npm test -- src/lib/guided-tips/catalog.test.ts src/lib/stores/guided-tips-store.test.ts src/components/guided-tips/GuidedTipsProvider.test.tsx
npm run lint -- src/lib/guided-tips src/lib/stores/guided-tips-store.ts src/components/guided-tips src/components/layout/AppShell.tsx src/components/layout/AppSidebar.tsx 'src/app/(dashboard)/settings/page.tsx'
```

Expected: tests PASS and ESLint exits 0.

- [ ] **Step 9: Commit Guided Tips**

```bash
git add frontend/src/lib/guided-tips frontend/src/lib/stores/guided-tips-store.ts frontend/src/lib/stores/guided-tips-store.test.ts frontend/src/components/guided-tips frontend/src/components/layout/AppShell.tsx frontend/src/components/layout/AppSidebar.tsx 'frontend/src/app/(dashboard)/settings/page.tsx'
git commit -m "feat: add local contextual guided tips"
```

### Task 8: Foundation Regression Gate and Written Handoff

**Files:**
- Modify: `docs/verification/2026-08-01-research-core-os-theme-foundation.md`

**Interfaces:**
- Consumes: exact implementation commit and outputs from Tasks 1-7.
- Produces: a reproducible verification record and the stable dependency boundary for the shell-redesign plan.

- [ ] **Step 1: Run frontend component and contract tests**

Run:

```bash
cd frontend && npm test -- src/lib/themes/catalog.test.ts src/lib/theme-script.test.ts src/lib/brand.test.ts src/components/vault/ResearchCoreVisualSystem.test.tsx src/components/deeper-notebook/ThemeSwitcher.test.tsx src/components/deeper-notebook/ThemeGallery.test.tsx
```

Expected: PASS.

Also run:

```bash
cd frontend && npm test -- src/lib/guided-tips/catalog.test.ts src/lib/stores/guided-tips-store.test.ts src/components/guided-tips/GuidedTipsProvider.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run desktop/API theme tests**

Run:

```bash
pytest -q desktop/tests/test_window.py desktop/tests/test_config.py desktop/tests/test_theme_static_assets.py desktop/tests/test_first_run.py desktop/tests/test_model_manager_server.py desktop/tests/test_memory_dashboard_server.py tests/test_deeper_notebook_router.py
```

Expected: PASS.

- [ ] **Step 3: Run static checks and production build**

Run:

```bash
python scripts/render_theme_static_assets.py --check
cd frontend && npm run lint && npm run build
```

Expected: generator check exits 0, ESLint exits 0, and Next production build succeeds.

- [ ] **Step 4: Run deterministic visual proof**

Run:

```bash
cd frontend && npm run test:e2e:themes
```

Expected: six screenshot comparisons PASS with no updated baselines.

- [ ] **Step 5: Record exact proof**

Create `docs/verification/2026-08-01-research-core-os-theme-foundation.md`
with the exact commit, commands, pass counts, screenshot filenames, viewport
sizes, and known boundary:

The record starts with `# Research Core OS Theme Foundation Verification` and
records the literal 40-character output of `git rev-parse HEAD` on its Commit
line. It then records this exact scope statement: `25-theme runtime, fresh
default, semantic tokens, gallery, auxiliary surfaces, Guided Tips, and theme
visual proof`.
It also records that source authority is unchanged and that the Dashboard,
Knowledge, chat, and Podcast Studio anchor matrices are outside this foundation
proof and remain assigned to their subsequent redesign plans.

- [ ] **Step 6: Commit verification**

```bash
git add docs/verification/2026-08-01-research-core-os-theme-foundation.md
git commit -m "docs: verify Research Core theme foundation"
```

## Final-review repair progress (2026-08-02)

- [x] Restored canonical persisted `system` selection authority and one
  provider-owned OS listener, with dark/light transition, cleanup, and
  explicit-theme stability regressions.
- [x] Enforced >=4.5:1 primary/accent foreground contrast across all runtime
  palettes, refreshed generated auxiliary assets, and added the permanent
  parametrized test.
- [x] Added the stable Settings scroll-viewport selector, capture-only
  unclip, final Classics/Midnight Aurora visibility assertions, and refreshed
  six full-page baselines to 6382px while retaining the two selected-card
  proofs unchanged.
- [x] Product repair commit: `b7b90cf0f2da49fc62cc546267e5f582ebf82d8e`.
- [x] Final verification: frontend focused contracts 44 tests, Guided Tips
  11 tests, desktop/API theme suite 247 tests, generated-asset check, scoped
  ESLint, production build, and Playwright 8/8 no-update all pass.
- [ ] Repository-wide Podcast/Vault ESLint findings remain outside this plan
  and require a separate cleanup scope.

## Final-review authority follow-up progress (2026-08-02)

- [x] ThemeGallery System preview and restore resolve the current OS palette
  through the shared catalog resolver/application helper.
- [x] `useTheme()` no longer installs an OS media-query listener; effective
  theme consumers follow the provider/application-applied signal while
  ThemeProvider owns the sole OS listener.
- [x] ThemeSwitcher and ThemeGallery subscribe to the shared canonical
  selection event, synchronize Current state, clear external previews, and
  refresh the restore baseline with cleanup regressions.
- [x] Product follow-up commit: `e99ba815bcc31ea65669d5083cebdaacea39a8c7`.
- [x] Follow-up verification: focused frontend 12 files / 59 tests, scoped
  ESLint, production build, generator freshness, Playwright 8/8 no-update,
  and diff checks all pass.
- [ ] Repository-wide Podcast/Vault ESLint findings remain outside this plan
  and require a separate cleanup scope.

## Final-review persistence closure progress (2026-08-02)

- [x] Legacy Zustand theme commands now normalize `light`, `dark`, and
  `system` to canonical catalog selections, persist both theme storage keys,
  emit the shared selection event, and apply the resolved live palette.
- [x] Storage-write failures remain fail-soft for both persistence and the live
  provider/application-applied effective-theme signal.
- [x] Mounted ThemeSwitcher/ThemeGallery synchronization, CommandPalette
  routing, canonical-over-legacy prehydration precedence, and the three-way
  legacy mapping/event regressions are covered.
- [x] Product persistence-closure commit:
  `c9b19424a971194dc532d24dc2f1701083d6768f`.
- [x] Persistence-closure verification: focused frontend 12 files / 66 tests,
  scoped ESLint, production build, generator freshness, Playwright 8/8
  no-update, and diff checks all pass.
- [ ] Repository-wide Podcast/Vault ESLint findings remain outside this plan
  and require a separate cleanup scope.

## Final approval stale-override closure progress (2026-08-02)

- [x] Successful legacy canonical persistence clears `legacyThemeOverride`,
  while canonical storage failures preserve the live legacy override and
  fail-soft palette application.
- [x] ThemeProvider clears stale legacy authority before re-resolving every
  canonical selection event; later Gallery/ThemeSwitcher selections now win
  over CommandPalette state and explicit themes remove stale System listeners.
- [x] Actual CommandPalette, mounted ThemeSwitcher/ThemeGallery, storage,
  painted-DOM, picker Current-state, and OS-listener regressions are covered.
- [x] Product stale-override closure commit:
  `0a9aefb39671fc5ecd0a0636aea9120e7dc50c84`.
- [x] Final-closure verification: focused frontend 13 files / 102 tests,
  scoped ESLint, production build, generator freshness, Playwright 8/8
  no-update, and diff checks all pass. Desktop/API surfaces were untouched.
- [ ] Repository-wide Podcast/Vault ESLint findings remain outside this plan
  and require a separate cleanup scope.

## Program Boundary After This Plan

This plan ends with working themes, gallery, persistence, auxiliary desktop
surfaces, Guided Tips, and visual-proof infrastructure. It intentionally does not bundle the
larger screen redesign into the same review unit. The next coordinated plans
use these stable tokens and fixtures in this order:

1. Research Core OS application shell, Dashboard, and Settings information architecture.
2. Knowledge workspace, grounded chat, evidence, and contradiction presentation.
3. Podcast Intelligence Studio visual production workspace.
4. Complete anchor-route render matrix, native visual smoke, contact sheet, and human approval gate.
