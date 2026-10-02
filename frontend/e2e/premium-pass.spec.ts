import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// v0.8.130 — the premium pass and notebook layer (user decisions, 2026-10-01): no
// glass, glow, gradient or inset shine (the dotted desk and ruled Notes are the only
// textures); a paper-and-ink flagship palette; tighter corners; rectangular buttons;
// quiet grey sentence-case eyebrows. Pinned on the main V2 pages.

const ROUTES = ['/', '/notebooks', '/sources', '/studio', '/settings'] as const

async function open(page: Page, route: string) {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(route)
  await expect(page.locator('main').first()).toBeVisible()
  await page.waitForTimeout(800)
}

for (const route of ROUTES) {
  test.describe(`premium ${route}`, () => {
    test('no glass, glow, gradient or inset shine', async ({ page }) => {
      await open(page, route)
      const offenders = await page.evaluate(() => {
        const out: string[] = []
        const describe = (el: Element) => {
          const name = el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 30) || ''
          return `${el.tagName.toLowerCase()}.${String((el as HTMLElement).className).split(' ')[0] ?? ''} "${name}"`
        }
        for (const el of Array.from(document.querySelectorAll('body *'))) {
          const style = getComputedStyle(el)
          if (style.display === 'none' || style.visibility === 'hidden') continue
          if (el.closest('[data-dn-source-cover], img, svg, video, canvas')) continue
          // The notebook textures: the dotted desk and the ruled Notes column.
          if (el.matches('.dn-workspace-canvas, [data-dn-ruled]')) continue
          if (style.backdropFilter && style.backdropFilter !== 'none') out.push(`blur ${describe(el)}`)
          if (/gradient\(/.test(style.backgroundImage)) out.push(`gradient ${describe(el)}`)
          if (/inset/.test(style.boxShadow) && /rgba?\(255, 255, 255/.test(style.boxShadow)) out.push(`shine ${describe(el)}`)
        }
        return out
      })
      expect(offenders).toEqual([])
    })

    test('rectangular buttons and tight corners', async ({ page }) => {
      await open(page, route)
      const offenders = await page.evaluate(() => {
        const out: string[] = []
        const describe = (el: Element) => {
          const name = el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 30) || ''
          return `${el.tagName.toLowerCase()} "${name}"`
        }
        for (const el of Array.from(document.querySelectorAll('button, a[data-slot="button"], [role="button"]'))) {
          const rect = el.getBoundingClientRect()
          if (!rect.width || !rect.height) continue
          if (el.matches('[role="switch"], [role="checkbox"], [role="radio"], [role="tab"]')) continue
          const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius)
          // Card-sized choices (Studio's option tiles, the drop zone) follow the card limit.
          const limit = rect.height > 56 ? 12 : 10
          if (radius > limit) out.push(`button r${radius} ${describe(el)}`)
        }
        for (const el of Array.from(document.querySelectorAll('[data-slot="card"], .dn-visual-card, [data-dn-column], [data-dn-notebook-card], .dn-workspace-hero, [data-dn-runtime-status]'))) {
          const rect = el.getBoundingClientRect()
          if (!rect.width) continue
          const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius)
          if (radius > 12) out.push(`card r${radius} ${describe(el)}`)
        }
        return out
      })
      expect(offenders).toEqual([])
    })

    test('quiet sentence-case eyebrows', async ({ page }) => {
      await open(page, route)
      const offenders = await page.evaluate(() => {
        const probe = document.createElement('span')
        probe.style.color = 'var(--muted-foreground)'
        document.body.appendChild(probe)
        const muted = getComputedStyle(probe).color
        probe.remove()
        const out: string[] = []
        const selectors = [
          '.dn-workspace-page-eyebrow', '.dn-workspace-hero-eyebrow', '.dn-state-panel-kind',
          '.dn-navigator-section-title', '.dn-command-kicker', '.dn-workspace-auth-eyebrow',
          '[data-dn-folio-page-eyebrow]', '[data-dn-folio-state-kind-label]',
          '[data-dn-runtime-status] header p:first-child',
        ]
        const matched = Array.from(document.querySelectorAll(selectors.join(',')))
          .filter((el) => el.getBoundingClientRect().width > 0)
        if (matched.length === 0) out.push('no eyebrows matched: the selectors are stale')
        for (const el of matched) {
          const style = getComputedStyle(el)
          if (style.textTransform === 'uppercase') out.push(`uppercase "${el.textContent?.trim()}"`)
          if (style.color !== muted) out.push(`coloured ${style.color} "${el.textContent?.trim()}"`)
        }
        return out
      })
      expect(offenders).toEqual([])
    })
  })
}

test('the flagship light theme is paper and ink, not lavender', async ({ page }) => {
  await open(page, '/notebooks')
  const colours = await page.evaluate(() => {
    const probe = document.createElement('div')
    document.body.appendChild(probe)
    const read = (value: string, prop: 'backgroundColor' | 'borderTopColor' | 'color') => {
      probe.style.cssText = `background-color:${value};border-top:1px solid ${value};color:${value}`
      return getComputedStyle(probe)[prop]
    }
    const out = {
      background: read('var(--background)', 'backgroundColor'),
      card: read('var(--card)', 'backgroundColor'),
      border: read('var(--border)', 'borderTopColor'),
      foreground: read('var(--foreground)', 'color'),
    }
    probe.remove()
    return out
  })
  for (const [token, colour] of Object.entries(colours)) {
    const [r, , b] = colour.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number)
    // #F7F7FC canvas, #D9DDF0 border and #202235 text gave every surface a lavender
    // cast (blue above red). Paper and ink are warm: red at or above blue, and close.
    expect(r, `${token} ${colour} is not blue-cast`).toBeGreaterThanOrEqual(b)
    // Warm, not sepia: the paper hairline #E6E1D7 is the warmest token (15).
    expect(r - b, `${token} ${colour} stays a near-neutral warm`).toBeLessThanOrEqual(20)
  }
})
