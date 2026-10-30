import type { Page } from '@playwright/test'

import { THEME_CATALOG } from '../src/lib/themes/catalog'
import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, test } from './fixtures/research-workbench'

// Phase 1 of the 2026-09-30 UI audit: the colour contract every catalog theme
// must meet, measured in the PRODUCTION BUILD. Colours are resolved by the
// browser (so var(), color-mix() and oklch() are all evaluated for real) and
// then painted onto a 1x1 canvas over the theme's own card colour, so
// translucent tokens are judged against the surface they actually sit on.

type Rgb = [number, number, number]

const STATUSES = ['success', 'warning', 'info', 'destructive'] as const
const HIGH_CONTRAST = new Set(['high-contrast-dark', 'high-contrast-light'])

interface StatusPaint { solid: Rgb; foreground: Rgb; softOnCard: Rgb; ink: Rgb }
interface ThemePaint {
  missing: string[]
  unparsed: string[]
  card: Rgb
  background: Rgb
  accentOnCard: Rgb
  accentForeground: Rgb
  statuses: Record<(typeof STATUSES)[number], StatusPaint>
}

async function measure(page: Page): Promise<ThemePaint> {
  return page.evaluate((statuses) => {
    const root = getComputedStyle(document.documentElement)
    const missing: string[] = []
    const unparsed: string[] = []
    const canvas = document.createElement('canvas')
    canvas.width = 1
    canvas.height = 1
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!

    // An undefined custom property makes `color: var(--x)` silently inherit the
    // body colour, so a missing token is reported instead of measured.
    const token = (name: string) => {
      if (!root.getPropertyValue(name).trim()) missing.push(name)
      const probe = document.createElement('span')
      probe.style.color = `var(${name})`
      document.body.appendChild(probe)
      const value = getComputedStyle(probe).color
      probe.remove()
      return value
    }
    const paint = (...layers: string[]): [number, number, number] => {
      ctx.clearRect(0, 0, 1, 1)
      for (const layer of layers) {
        ctx.fillStyle = '#010203'
        ctx.fillStyle = layer
        // An unparseable colour leaves the sentinel in place; say so rather
        // than measure the sentinel.
        if (ctx.fillStyle === '#010203') unparsed.push(layer)
        ctx.fillRect(0, 0, 1, 1)
      }
      const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data
      return [r, g, b]
    }

    const card = token('--card')
    const background = token('--background')
    const result = {
      missing,
      unparsed,
      card: paint(card),
      background: paint(background),
      accentOnCard: paint(card, token('--accent')),
      accentForeground: paint(card, token('--accent-foreground')),
      statuses: {} as Record<string, unknown>,
    }
    for (const status of statuses) {
      const solid = token(`--${status}`)
      result.statuses[status] = {
        solid: paint(card, solid),
        foreground: paint(card, token(`--${status}-foreground`)),
        softOnCard: paint(card, token(`--${status}-soft`)),
        ink: paint(card, token(`--${status}-ink`)),
      }
    }
    return result
  }, [...STATUSES]) as Promise<ThemePaint>
}

function luminance([r, g, b]: Rgb): number {
  const channel = (value: number) => {
    const c = value / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

function contrast(a: Rgb, b: Rgb): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (high + 0.05) / (low + 0.05)
}

test.describe('theme colour contract', () => {
  for (const theme of THEME_CATALOG) {
    test(`${theme.id}: status colours are readable`, async ({ page }) => {
      await installLuminousFolioFixture(page, { theme: theme.id })
      await page.goto('/notebooks')
      // `system` is an alias: the theme script resolves it from the OS scheme,
      // and this project emulates a dark OS (playwright.config.ts).
      const applied = theme.id === 'system' ? 'dark' : theme.id
      await expect(page.locator('html')).toHaveAttribute('data-theme', applied)

      const paint = await measure(page)
      expect(paint.missing, 'every status token is defined').toEqual([])
      expect(paint.unparsed, 'every token resolves to a paintable colour').toEqual([])

      for (const status of STATUSES) {
        const s = paint.statuses[status]
        // Text drawn in the -ink role: on its own soft tint, on cards, on the canvas.
        expect.soft(contrast(s.ink, s.softOnCard), `${status}-ink on ${status}-soft`).toBeGreaterThanOrEqual(4.5)
        expect.soft(contrast(s.ink, paint.card), `${status}-ink on card`).toBeGreaterThanOrEqual(4.5)
        expect.soft(contrast(s.ink, paint.background), `${status}-ink on background`).toBeGreaterThanOrEqual(4.5)
        // Text on the solid fill (buttons, solid badges).
        expect.soft(contrast(s.foreground, s.solid), `${status}-foreground on ${status}`).toBeGreaterThanOrEqual(4.5)
      }
      // `text-destructive` is the established idiom for error text, so the solid
      // destructive colour must itself be readable on a card.
      expect.soft(contrast(paint.statuses.destructive.solid, paint.card), 'destructive as text on card').toBeGreaterThanOrEqual(4.5)

      // The hover/selected fill (`bg-accent`) is a subtle neutral tint: visible,
      // but nowhere near a solid brand fill (which measured 2–8:1 against the card).
      const tint = contrast(paint.accentOnCard, paint.card)
      expect.soft(tint, 'accent tint is perceptible').toBeGreaterThanOrEqual(1.08)
      expect.soft(tint, 'accent tint is not a solid brand fill').toBeLessThanOrEqual(1.5)
      expect.soft(contrast(paint.accentForeground, paint.accentOnCard), 'accent-foreground on accent').toBeGreaterThanOrEqual(4.5)
    })
  }

  // One focus indicator: the global 3px outline (v0.7.121, for low-vision users).
  // The shadcn primitives used to add their own 3px translucent box-shadow ring on
  // top of it, drawing a ~6px band around every focused button and input.
  test('keyboard focus draws exactly one 3px ring, even on outline-none controls', async ({ page }) => {
    await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/notebooks')
    await expect(page.getByRole('heading', { name: 'Notebooks', level: 1 })).toBeVisible()

    let focused: { slot: string | null; outlineStyle: string; outlineWidth: string; boxShadow: string } | null = null
    for (let i = 0; i < 40 && focused?.slot !== 'button'; i++) {
      await page.keyboard.press('Tab')
      focused = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null
        if (!el) return null
        const style = getComputedStyle(el)
        return { slot: el.dataset.slot ?? null, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow }
      })
    }
    expect(focused?.slot, 'Tab reached a <Button>').toBe('button')
    expect(focused?.outlineStyle).toBe('solid')
    expect(focused?.outlineWidth).toBe('3px')
    expect(focused?.boxShadow, 'no second, box-shadow focus ring').not.toMatch(/0px 0px 0px 3px/)
  })

  // Decision of 2026-10-04 (replacing "headings are sans" of 2026-09-30): page
  // titles are set in the book serif; the body and its controls stay sans.
  test('page headings use the book serif; the body stays sans', async ({ page }) => {
    await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/notebooks')
    const heading = page.getByRole('heading', { name: 'Notebooks', level: 1 })
    await expect(heading).toBeVisible()
    const fonts = await heading.evaluate((el) => ({
      heading: getComputedStyle(el).fontFamily,
      body: getComputedStyle(document.body).fontFamily,
    }))
    expect(fonts.heading).toMatch(/Newsreader|Georgia|Iowan/)
    expect(fonts.body).not.toMatch(/Newsreader|Georgia|Palatino|Iowan/)
  })

  test('chart colours follow the theme', async ({ page }) => {
    await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/notebooks')
    const colours = await page.evaluate(() => {
      const probe = (name: string) => {
        const el = document.createElement('span')
        el.style.color = `var(${name})`
        document.body.appendChild(el)
        const value = getComputedStyle(el).color
        el.remove()
        return value
      }
      return { chart1: probe('--chart-1'), primary: probe('--primary'), chart2: probe('--chart-2'), brand: probe('--brand-accent') }
    })
    expect(colours.chart1).toBe(colours.primary)
    expect(colours.chart2).toBe(colours.brand)
  })

  // Status hues are fixed: a catalog theme may pick the light or the dark set,
  // but never its own. Before Phase 1 `html[data-theme]` rewired success to the
  // theme's primary and warning/info to its accent, so "warning" was pink in
  // Dracula and "success" yellow in Gruvbox. High-contrast themes keep their own
  // stronger set by design.
  test('status colours are identical across every theme of the same mode', async ({ page }) => {
    await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/notebooks')

    const seen: Record<'light' | 'dark', Map<string, string>> = { light: new Map(), dark: new Map() }
    for (const theme of THEME_CATALOG) {
      if (HIGH_CONTRAST.has(theme.id)) continue
      // Same switch the pre-hydration theme script performs.
      await page.evaluate(({ id, dark }) => {
        document.documentElement.dataset.theme = id
        document.documentElement.classList.toggle('dark', dark)
      }, { id: theme.id, dark: theme.dark })
      const paint = await measure(page)
      const mode = theme.dark ? 'dark' : 'light'
      for (const status of ['success', 'warning', 'info'] as const) {
        const value = paint.statuses[status].solid.join(',')
        const key = `${status}`
        const first = seen[mode].get(key)
        if (first === undefined) {
          seen[mode].set(key, value)
        } else {
          expect.soft(value, `${theme.id} ${status} matches the other ${mode} themes`).toBe(first)
        }
      }
    }
  })
})
