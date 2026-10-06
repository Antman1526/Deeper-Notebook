import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// Tailwind v4 does not read tailwind.config.ts unless the CSS opts in with
// `@config`. Anything the old config used to provide (the typography plugin,
// `darkMode: "class"`) must therefore be declared in CSS itself, or the
// utilities silently compile to nothing / to the wrong media query.
const css = fs.readFileSync(path.resolve(__dirname, 'globals.css'), 'utf8')

describe('globals.css Tailwind v4 contract', () => {
  it('loads the typography plugin so `prose` classes generate rules', () => {
    expect(css).toMatch(/@plugin\s+["']@tailwindcss\/typography["']\s*;/)
  })

  it('binds `dark:` to the .dark class the theme script toggles, not prefers-color-scheme', () => {
    expect(css).toMatch(/@custom-variant\s+dark\s*\(\s*&:where\(\s*\.dark\s*,\s*\.dark \*\s*\)\s*\)\s*;/)
  })

  it('maps prose colors to theme tokens so prose text follows the active theme', () => {
    expect(css).toMatch(/\.prose\s*\{[^}]*--tw-prose-body:\s*var\(--foreground\)/)
    expect(css).toMatch(/\.prose\s*\{[^}]*--tw-prose-links:\s*var\(--primary\)/)
  })

  // Tailwind inlines a shadow value into each utility, so a `.dark` override of
  // a token that was only declared in plain CSS never reached `shadow-*`. Mapping
  // the theme key to a var() makes Tailwind emit `--tw-shadow: var(--elevation-X)`
  // for every variant (shadow-md, hover:shadow-md, shadow-md/30), and the `.dark`
  // block then changes the real shadow by ordinary cascade.
  it.each(['xs', 'sm', 'md', 'lg', 'xl'])('maps shadow-%s to its themeable elevation token', (step) => {
    expect(css).toMatch(new RegExp(`@theme inline \\{[\\s\\S]*?--shadow-${step}:\\s*var\\(--elevation-${step}\\)`))
  })

  it('gives dark themes their own, stronger elevation values', () => {
    const dark = css.slice(css.indexOf('.dark {'), css.indexOf('html[data-theme]'))
    expect(dark).toMatch(/--elevation-md:\s*0 4px 6px -1px rgba\(0, 0, 0, 0\.5\)/)
  })

  it('no longer declares the old plain --shadow-* values that nothing could apply', () => {
    expect(css).not.toMatch(/^\s*--shadow-(xs|sm|md|lg|xl):\s*0 /m)
  })

  it('suppresses the plugin backticks around inline code', () => {
    expect(css).toMatch(/\.prose code::before,\s*\.prose code::after\s*\{\s*content:\s*none;/)
  })
})

// Status colours are fixed hues. Every catalog theme goes through the shared
// `html[data-theme]` block, which used to set success to the theme's primary
// and warning/info to its accent, so no theme ever showed a real green, amber
// or blue. The measured contrast of each role, in every theme, is checked in
// e2e/theme-contract.spec.ts; this file pins the source contract.
const block = (source: string, selector: string) => {
  const start = source.indexOf(`${selector} {`)
  expect(start, `${selector} block exists`).toBeGreaterThanOrEqual(0)
  return source.slice(start, source.indexOf('}', start))
}
const STATUSES = ['success', 'warning', 'info', 'destructive'] as const

describe('status colour contract', () => {
  it('no catalog theme rewires the status colours', () => {
    expect(block(css, 'html[data-theme]')).not.toMatch(/--(success|warning|info|destructive)(-[a-z]+)?:/)
  })

  it.each(STATUSES)('defines foreground, soft and ink roles for %s in light and dark', (status) => {
    for (const selector of [':root', '.dark']) {
      const scope = block(css, selector)
      expect(scope).toMatch(new RegExp(`--${status}:`))
      expect(scope).toMatch(new RegExp(`--${status}-foreground:`))
      expect(scope).toMatch(new RegExp(`--${status}-soft:`))
      expect(scope).toMatch(new RegExp(`--${status}-ink:`))
    }
  })

  it.each(STATUSES)('exposes the soft, ink and foreground roles of %s as Tailwind colours', (status) => {
    const theme = block(css, '@theme inline')
    expect(theme).toMatch(new RegExp(`--color-${status}-soft:\\s*var\\(--${status}-soft\\)`))
    expect(theme).toMatch(new RegExp(`--color-${status}-ink:\\s*var\\(--${status}-ink\\)`))
    expect(theme).toMatch(new RegExp(`--color-${status}-foreground:\\s*var\\(--${status}-foreground\\)`))
  })

  it('keeps the high-contrast themes on their own, stronger status set', () => {
    for (const theme of ['high-contrast-dark', 'high-contrast-light']) {
      const scope = block(css, `html[data-theme="${theme}"]`)
      for (const status of ['success', 'warning', 'info']) {
        expect(scope).toMatch(new RegExp(`--${status}:`))
        expect(scope).toMatch(new RegExp(`--${status}-ink:`))
      }
    }
  })
})

// `--accent` is shadcn's hover/selected fill (49 hover and focus states plus the
// selected rows use `bg-accent`), but this project had pointed it at a second
// brand hue, so hovering a menu row painted it solid violet or cyan. It is now a
// neutral state layer; the few surfaces that want the brand's second hue use
// `--brand-accent`.
describe('accent is a neutral state layer', () => {
  it('defines --accent once, as a tint of the foreground', () => {
    expect(block(css, ':root')).toMatch(/--accent:\s*color-mix\(in oklab, var\(--foreground\) 8%, transparent\);/)
    expect(block(css, ':root')).toMatch(/--accent-foreground:\s*var\(--foreground\);/)
    expect(block(css, '.dark')).not.toMatch(/--accent(-foreground)?:/)
    expect(block(css, 'html[data-theme]')).not.toMatch(/--accent(-foreground)?:/)
  })

  it('keeps the theme second hue available as --brand-accent', () => {
    expect(block(css, 'html[data-theme]')).toMatch(/--brand-accent:\s*var\(--dn-theme-accent\);/)
    expect(block(css, ':root')).toMatch(/--brand-accent:/)
  })

  it('points every brand use in tokens.css at --brand-accent', () => {
    const tokens = fs.readFileSync(path.resolve(__dirname, '../components/deeper-notebook/tokens.css'), 'utf8')
    expect(tokens).not.toMatch(/var\(--accent\b/)
    expect(tokens).toMatch(/--dn-graph-selected:\s*var\(--brand-accent\);/)
  })
})

// The Phase 1 token spec (UI audit 4.2). The radius scale is remapped rather
// than given new names so that every existing `rounded-*` lands on the spec:
// seven radii in use collapse onto five steps plus `rounded-full`.
describe('design token scale', () => {
  it.each([
    // v0.8.130 — premium pass (user decision 2026-10-01): tighter corners.
    ['sm', '0.375rem'], // chips, tooltips: 6px
    ['md', '0.5rem'], // buttons, inputs, menu items: 8px
    ['lg', '0.625rem'], // menus, popovers: 10px
    ['xl', '0.75rem'], // cards: 12px
    ['2xl', '1rem'], // dialogs, hero surfaces: 16px
  ])('rounded-%s is %s', (step, value) => {
    expect(block(css, '@theme inline')).toMatch(new RegExp(`--radius-${step}:\\s*${value.replace('.', '\\.')};`))
  })

  it('uses one standard easing for every transition, with no springs', () => {
    const theme = block(css, '@theme inline')
    expect(theme).toMatch(/--default-transition-timing-function:\s*cubic-bezier\(0\.2, 0, 0, 1\);/)
    const root = block(css, ':root')
    for (const step of ['fast', 'base', 'slow']) {
      expect(root).toMatch(new RegExp(`--motion-${step}:\\s*\\d+ms cubic-bezier\\(0\\.2, 0, 0, 1\\);`))
    }
    expect(css).not.toMatch(/--motion-spring/)
  })

  it('defines --font-serif (the note editor uses it and fell back to Palatino/Georgia)', () => {
    expect(block(css, '@theme inline')).toMatch(/--font-serif:\s*var\(--font-dn-editorial\)/)
  })
})

// v0.7.121 made keyboard focus a 3px ring for low-vision users, with !important
// so the 57 `outline-none` utilities could not remove it. An unlayered rule wins
// over every layered utility just the same, without !important. The rendered
// result is checked in e2e/theme-contract.spec.ts.
describe('focus ring', () => {
  it('keeps the 3px keyboard ring without !important', () => {
    const rule = /:focus-visible\s*\{\s*outline:\s*3px solid var\(--ring\);\s*outline-offset:\s*2px;\s*\}/
    expect(css).toMatch(rule)
    const at = css.search(rule)
    // Not inside `@layer base`, where a utility such as `outline-none` would beat it.
    const layerStart = css.lastIndexOf('@layer base {', at)
    const layerEnd = layerStart === -1 ? -1 : css.indexOf('\n}\n', layerStart)
    expect(layerStart === -1 || layerEnd < at, 'focus rule is outside @layer base').toBe(true)
    expect(css).not.toMatch(/outline(-offset)?:[^;]*!important/)
  })

  it('draws the ring inside menu rows and options, where an outer ring is clipped', () => {
    expect(css).toMatch(/\[role='option'\]:focus-visible[\s\S]*?outline-offset:\s*-3px/)
    expect(css).toMatch(/\[role='menuitem'\]:focus-visible/)
  })
})

// Decisions of 2026-09-30: indigo (Gemini-Forward) is the one brand, and headings
// are sans. The serif stays only on the note editor's writing surface.
const stylesheets = (dir: string): string[] =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return stylesheets(full)
    return entry.name.endsWith('.css') ? [full] : []
  })

describe('brand and heading decisions', () => {
  // v0.8.130 — notebook layer (user decision 2026-10-01): reading text (answers and
  // note previews) is also set in the book serif.
  // v0.8.130 — stationery (user decision 2026-10-04, replacing "headings are sans"
  // of 2026-09-30): titles are set in the book serif too, but only by the
  // stationery layer and only in the new visual system, so the rollback shell
  // keeps its sans headings. Controls and body UI stay sans everywhere.
  it('sets the serif face only on writing and reading surfaces and on stationery titles', () => {
    const offenders: string[] = []
    for (const file of stylesheets(path.resolve(__dirname, '..'))) {
      const source = fs.readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
      for (const match of source.matchAll(/([^{}]+)\{[^{}]*font-family:\s*var\(--font-(?:serif|dn-editorial)\)/g)) {
        const selectors = match[1].trim()
        const stationery = path.basename(file) === 'stationery.css'
        // Top-level commas only: `:is(a, b)` is one selector.
        const allowed = selectors.split(/,(?![^()]*\))/).every((selector) => (
          stationery
            ? /^\s*\[data-dn-visual-system='v2'\]\s/.test(selector)
            : /\.cm-scroller/.test(selector) || /^\s*\[data-dn-message='ai'\]\s*$|^\s*\[data-dn-reading\]\s*$/.test(selector)
        ))
        if (!allowed) offenders.push(`${path.basename(file)}: ${selectors.replace(/\s+/g, ' ')}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('retires the unused font-editorial utility', () => {
    expect(block(css, '@theme inline')).not.toMatch(/--font-editorial:/)
  })

  // Charts were fixed Research Core teal/cyan (--dn-teal, --dn-cyan, a near-white
  // --dn-light) in every theme, because no theme block set them.
  it('derives chart colours from the active theme, once', () => {
    const root = block(css, ':root')
    expect(root).toMatch(/--chart-1:\s*var\(--primary\);/)
    expect(root).toMatch(/--chart-2:\s*var\(--brand-accent\);/)
    expect(root).not.toMatch(/--chart-\d:\s*var\(--dn-(teal|cyan|light|dark-teal)\)/)
    expect(block(css, '.dark')).not.toMatch(/--chart-\d:/)
  })
})

describe('tokens.css status aliases', () => {
  const tokens = fs.readFileSync(path.resolve(__dirname, '../components/deeper-notebook/tokens.css'), 'utf8')

  // One source of truth: the older names stay (artifact viewers use them) but
  // only as aliases, so they can no longer drift from the canonical values.
  it.each(['success', 'warning', 'info'])('aliases --dn-status-%s to the canonical token', (status) => {
    expect(tokens).toMatch(new RegExp(`--dn-status-${status}:\\s*var\\(--${status}\\);`))
    expect(tokens).toMatch(new RegExp(`--dn-status-${status}-foreground:\\s*var\\(--${status}-foreground\\);`))
    expect(tokens).not.toMatch(new RegExp(`--dn-status-${status}:\\s*oklch`))
  })

  it('stops treating info as the brand colour', () => {
    expect(tokens).toMatch(/--dn-success:\s*var\(--success\);/)
    expect(tokens).toMatch(/--dn-info:\s*var\(--info\);/)
    expect(tokens).not.toMatch(/--dn-info:\s*var\(--primary\)/)
  })
})
