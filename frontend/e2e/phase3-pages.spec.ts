import { expect, test } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// Phase 3 of the 2026-09-30 UI audit: page anatomy, shell and first run, proven
// against the production build.

test.beforeEach(async ({ page }) => {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
})

// v0.8.130 — every route shared the title "Deeper Notebook", so tabs, history and
// window lists could not tell pages apart.
const TITLES: readonly [route: string, title: string][] = [
  ['/', 'Deeper Notebook'],
  ['/notebooks', 'Notebooks · Deeper Notebook'],
  ['/sources', 'Sources · Deeper Notebook'],
  ['/capture', 'Capture · Deeper Notebook'],
  ['/knowledge', 'Knowledge · Deeper Notebook'],
  ['/search', 'Ask and search · Deeper Notebook'],
  ['/studio', 'Studio · Deeper Notebook'],
  ['/podcasts', 'Podcasts · Deeper Notebook'],
  ['/podcasts/studio', 'Podcast intelligence studio · Deeper Notebook'],
  ['/study', 'Study · Deeper Notebook'],
  ['/transformations', 'Transformations · Deeper Notebook'],
  ['/settings', 'Settings · Deeper Notebook'],
  ['/settings/api-keys', 'Models · Deeper Notebook'],
  ['/settings/local-models', 'Local models · Deeper Notebook'],
  ['/settings/mcp', 'MCP servers · Deeper Notebook'],
  ['/settings/launcher-prefs', 'Launch preferences · Deeper Notebook'],
  ['/advanced', 'Advanced · Deeper Notebook'],
  ['/setup-wizard', 'Setup · Deeper Notebook'],
]

test.describe('3a — page titles', () => {
  test('each route names itself in the document title', async ({ page }) => {
    // v0.8.130 — titles are set on the client from the navigation labels (so they follow
    // the UI language), hence a polling assertion per route.
    for (const [route, title] of TITLES) {
      await page.goto(route)
      await expect(page, route).toHaveTitle(title)
    }
  })
})

test.describe('3a — home', () => {
  // v0.8.130 — stationery layer: your books come first (the recent shelf sits under the
  // hero), then the ways to start, and the runtime readout closes the page.
  test('the hero, recent shelf, Today and runtime status follow in that order, spaced apart', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/')
    const hero = page.locator('.dn-workspace-hero')
    const recent = page.locator('section[aria-labelledby="workspace-recent-title"]')
    const today = page.locator('section[aria-labelledby="workspace-actions-title"]')
    const status = page.locator('section[aria-label^="Runtime status"]')
    await expect(status).toBeVisible()

    const boxes = await Promise.all([hero, recent, today, status].map((part) => part.boundingBox()))
    for (let index = 1; index < boxes.length; index += 1) {
      const above = boxes[index - 1]!
      expect(boxes[index]!.y - (above.y + above.height), `section ${index} sits below section ${index - 1}`).toBeGreaterThanOrEqual(16)
    }
  })

  test('the runtime status panel is a neutral surface, not a selected-looking tint', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/')
    const status = page.locator('section[aria-label^="Runtime status"]')
    await expect(status).toBeVisible()
    const [panel, card] = await status.evaluate((el) => {
      const probe = document.createElement('div')
      probe.style.backgroundColor = 'var(--card)'
      el.parentElement!.appendChild(probe)
      const resolved = [getComputedStyle(el).backgroundColor, getComputedStyle(probe).backgroundColor]
      probe.remove()
      return resolved
    })
    expect(panel).toBe(card)
  })
})

test.describe('3a — notebooks list', () => {
  test('a notebook card reads as one block with labelled counts', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    const card = page.locator('[data-dn-notebook-card]').first()
    await expect(card).toBeVisible()

    const gap = await card.evaluate((el) => {
      const title = el.querySelector('[data-slot="card-title"]')!.getBoundingClientRect()
      const description = el.querySelector('[data-slot="card-description"]')!.getBoundingClientRect()
      return description.top - title.bottom
    })
    // A ~60px blank band sat between the title and the description.
    expect(gap).toBeLessThanOrEqual(16)
    // The counts were bare "1" and "0" chips.
    await expect(card.getByText('1 source', { exact: true })).toBeVisible()
    await expect(card.getByText('0 notes', { exact: true })).toBeVisible()
  })

  test('the search field shows a search icon', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    const search = page.getByRole('textbox', { name: 'Search notebooks' })
    await expect(search).toBeVisible()
    expect(await search.evaluate((el) => Boolean(el.parentElement?.querySelector('svg')))).toBe(true)
  })
})

test.describe('3a — studio', () => {
  test('the header and columns sit on the canvas instead of nested tinted panels', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/studio')
    const heading = page.getByRole('heading', { level: 1, name: 'Studio' })
    await expect(heading).toBeVisible()

    const tinted = await heading.evaluate((h1) => {
      // Every box between the h1 and the page frame was a tinted block ("heavy tinted header").
      const out: string[] = []
      for (let el = h1.parentElement; el && !el.matches('main, [data-dn-workspace-canvas], .dn-workspace-canvas'); el = el.parentElement) {
        const bg = getComputedStyle(el).backgroundColor
        if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') out.push(`${el.tagName}.${el.className.toString().slice(0, 40)} ${bg}`)
      }
      return out
    })
    expect(tinted).toEqual([])

    for (const name of ['Source desk', 'Editorial brief']) {
      const column = page.getByRole('region', { name })
      await expect(column).toBeVisible()
      // The right column was a tinted panel holding white cards (card-in-card-in-card).
      expect(await column.evaluate((el) => getComputedStyle(el).backgroundColor), name).toBe('rgba(0, 0, 0, 0)')
    }
  })
})

test.describe('3a — sources gallery', () => {
  test('a lone source is a card, not a full-width ~500px tile', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/sources')
    const grid = page.locator('[data-dn-source-gallery] [role="list"]')
    const card = grid.locator('[role="listitem"]').first()
    await expect(card).toBeVisible()
    const [gridBox, cardBox] = await Promise.all([grid.boundingBox(), card.boundingBox()])
    // auto-fit collapsed the empty tracks, so one source stretched across the whole row.
    expect(cardBox!.width).toBeLessThanOrEqual(gridBox!.width / 2)
  })
})
