import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// v0.8.130 — on a narrow screen the page header stacks its actions under the
// subtitle, which suits a labelled button ("Add new source") but left a lone icon
// button (Settings' and Transformations' refresh) stranded on its own line above the
// letterhead rule. A lone icon button stays on the title row, at its end.
const css = fs.readFileSync(path.resolve(__dirname, 'folio.css'), 'utf8')

describe('folio page header on a narrow screen', () => {
  it('keeps a lone icon button beside the title', () => {
    const narrow = css.slice(css.indexOf('@media (max-width: 52rem)'))
    expect(narrow).toMatch(
      /\[data-dn-folio-page-header\]:has\(>\s*\[data-dn-folio-page-actions\]\s*>\s*button\[aria-label\]:only-child\s*>\s*svg:only-child\)\s*\{[^}]*flex-direction:\s*row/,
    )
  })

  // A labelled button ("+ Add new source") also has its icon as its only element:
  // the label is a text node, which CSS cannot see. Only an icon-only button needs,
  // and has, an aria-label, so every rule here asks for one.
  it('leaves a labelled button stacked', () => {
    const rules = css.match(/[^{}]*svg:only-child[^{}]*\{/g) ?? []
    expect(rules.length).toBeGreaterThan(0)
    for (const rule of rules) expect(rule).toContain('button[aria-label]:only-child')
  })

  // A :has() inside another :has() is invalid CSS; the browser drops the whole rule.
  it('never nests :has()', () => {
    expect(css).not.toMatch(/:has\([^)]*:has\(/)
  })
})
