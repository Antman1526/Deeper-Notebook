import { expect, test, type Page } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// Phase 4b of the 2026-09-30 UI audit: the axe gate. WCAG 2.1 A/AA plus axe's best
// practices on the main routes, in the flagship light and dark themes, at desktop and
// phone width. Nothing may fail, and nothing may be left undecided except one known
// axe limitation (below). Where axe cannot measure contrast, this test measures it.

const AXE_PATH = require.resolve('axe-core/axe.min.js')

const ROUTES = [
  '/', '/notebooks', '/notebooks/notebook-fixture-001', '/sources', '/studio', '/settings',
  '/search', '/podcasts', '/study', '/knowledge', '/login', '/setup-wizard',
] as const
const THEMES = ['gemini-forward-light', 'gemini-forward-dark'] as const
const WIDTHS = [1440, 390] as const

type AxeNode = { target: string[]; html: string; any: Array<{ message: string }>; none: Array<{ message: string }>; all: Array<{ message: string }> }
type AxeResult = { id: string; nodes: AxeNode[] }

function message(node: AxeNode) {
  return node.any[0]?.message ?? node.none[0]?.message ?? node.all[0]?.message ?? ''
}

async function runAxe(page: Page) {
  // The dotted desk and ruled notes are faint background images under the text; with
  // them on, axe reports contrast as undecidable on most pages. Text sits on the solid
  // paper colour, which is what is measured.
  await page.addStyleTag({ content: '* { background-image: none !important; }' })
  await page.addScriptTag({ path: AXE_PATH })
  return page.evaluate(async () => {
    const result = await (window as unknown as { axe: { run: (context: Document, options: object) => Promise<{ violations: AxeResult[]; incomplete: AxeResult[] }> } }).axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    })
    return { violations: result.violations, incomplete: result.incomplete }
  })
}

/** Contrast of each element's text against its nearest opaque background. */
async function measuredContrast(page: Page, selectors: string[]) {
  return page.evaluate((targets) => {
    // Computed colours come back as oklch() under Tailwind v4; a 1x1 canvas turns any
    // CSS colour into sRGB bytes.
    const canvas = document.createElement('canvas')
    canvas.width = 1
    canvas.height = 1
    const context = canvas.getContext('2d', { willReadFrequently: true })!
    const parse = (value: string) => {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = '#000'
      context.fillStyle = value
      context.fillRect(0, 0, 1, 1)
      const [r, g, b, alpha] = context.getImageData(0, 0, 1, 1).data
      return { r, g, b, a: alpha / 255 }
    }
    const luminance = ({ r, g, b }: { r: number; g: number; b: number }) => {
      const channel = (c: number) => {
        const s = c / 255
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
      }
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    }
    return targets.map((selector) => {
      const element = document.querySelector(selector)
      if (!element) return { selector, ratio: 0, required: 4.5, note: 'missing' }
      const style = getComputedStyle(element)
      const fg = parse(style.color)
      let node: Element | null = element
      let bg = null
      while (node) {
        const candidate = parse(getComputedStyle(node).backgroundColor)
        if (candidate && candidate.a === 1) {
          bg = candidate
          break
        }
        node = node.parentElement
      }
      if (!fg || !bg) return { selector, ratio: 0, required: 4.5, note: 'unparsed' }
      const [hi, lo] = [luminance(fg), luminance(bg)].sort((x, y) => y - x)
      const size = parseFloat(style.fontSize)
      const large = size >= 24 || (size >= 18.66 && Number(style.fontWeight) >= 700)
      return { selector, ratio: (hi + 0.05) / (lo + 0.05), required: large ? 3 : 4.5, note: '' }
    })
  }, selectors)
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    for (const route of ROUTES) {
      test(`axe · ${theme} · ${width} · ${route}`, async ({ page }) => {
        await installVisualSystemFixture(page, { theme })
        await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
        await page.goto(route)
        await expect(page.locator('main').first()).toBeVisible()
        await page.waitForTimeout(800)

        const { violations, incomplete } = await runAxe(page)
        expect(
          violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 100)).join(' | ')}`),
        ).toEqual([])

        // The one accepted unknown: a closed Radix trigger points aria-controls at
        // content that is not rendered until it opens, which axe cannot resolve.
        const undecided = incomplete
          .map((r) => ({
            ...r,
            nodes: r.nodes.filter((n) => !(r.id === 'aria-valid-attr-value' && /aria-controls/.test(message(n)))),
          }))
          .filter((r) => r.nodes.length > 0)
        const contrast = undecided.find((r) => r.id === 'color-contrast')
        expect(undecided.filter((r) => r.id !== 'color-contrast').map((r) => `${r.id}: ${r.nodes.map((n) => message(n)).join(' | ')}`)).toEqual([])

        if (contrast) {
          const measured = await measuredContrast(page, contrast.nodes.map((n) => n.target.join(' ')))
          expect(measured.filter((m) => m.ratio < m.required)).toEqual([])
        }
      })
    }
  }
}

test.describe('4b — named controls', () => {
  test.beforeEach(async ({ page }) => {
    await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
    await page.setViewportSize({ width: 1440, height: 900 })
  })

  test('the closed command palette leaves no stray heading in the page', async ({ page }) => {
    await page.goto('/notebooks')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.locator('[data-slot="dialog-header"], [data-slot="dialog-title"]')).toHaveCount(0)
  })

  test('the logo is a link home', async ({ page }) => {
    await page.goto('/notebooks')
    await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Deeper Notebook' })).toHaveAttribute('href', '/')
  })

  test('every icon-only rail button has a name and a tooltip', async ({ page }) => {
    await page.goto('/notebooks')
    const buttons = page.locator('.dn-rail-utilities button')
    await expect(buttons).toHaveCount(4)
    for (const button of await buttons.all()) {
      await expect(button).toHaveAttribute('aria-label', /\S/)
      await expect(button).toHaveAttribute('title', /\S/)
    }
  })
})
