import { expect, test, type Page } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// v0.8.130 — the stationery layer (user direction 2026-10-04: "premium, in a notebook
// way… modern, motion flow… spectacular"). Notebooks are bound books that lift and open
// on a hinge, headings are set in the editorial serif, the open notebook wears its
// cover, and Home leads with your books. Motion is decoration: it stops under either
// reduced-motion setting, and high-contrast themes keep plain cards.

const COVERS = ['ink', 'forest', 'oxblood', 'ochre', 'slate', 'plum']

type Theme = NonNullable<Parameters<typeof installVisualSystemFixture>[1]>['theme']

async function open(page: Page, theme: Theme, route = '/notebooks') {
  await installVisualSystemFixture(page, { theme })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(route)
  await expect(page.locator('main').first()).toBeVisible()
}

/** The fixture pins reduced motion; these tests need the real thing. */
const allowMotion = (page: Page) => page.evaluate(() => { document.documentElement.dataset.dnMotion = 'full' })

const luminance = (rgb: string) => {
  const [r, g, b] = (rgb.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

test('a notebook is a bound book: cloth cover, page block, ribbon, and a paper label for its name', async ({ page }) => {
  await open(page, 'gemini-forward-light')
  const book = page.locator('[data-dn-notebook-card]').first()
  await expect(book).toBeVisible()
  expect(COVERS).toContain(await book.getAttribute('data-dn-cover'))

  const look = await book.evaluate((el) => {
    const cover = el.querySelector('[data-dn-book-cover]')!
    const label = el.querySelector('[data-slot="card"]')!
    const title = el.querySelector('[data-slot="card-title"]')!
    const shown = (selector: string) => getComputedStyle(el.querySelector(selector)!).display !== 'none'
    return {
      cloth: getComputedStyle(cover).backgroundColor,
      label: getComputedStyle(label).backgroundColor,
      titleFont: getComputedStyle(title).fontFamily,
      titleInk: getComputedStyle(title).color,
      pages: shown('[data-dn-book-pages]'),
      ribbon: shown('[data-dn-book-ribbon]'),
      monogram: getComputedStyle(el.querySelector('[data-dn-book-monogram]')!, '::before').content,
      box: el.getBoundingClientRect().toJSON() as { width: number; height: number },
      footerInk: getComputedStyle(el.querySelector('[data-dn-cover-footer]')!).color,
      blur: getComputedStyle(cover).backdropFilter,
    }
  })
  // Deep cloth; the name is ink on light paper, in the serif.
  expect(luminance(look.cloth)).toBeLessThan(110)
  expect(luminance(look.label)).toBeGreaterThan(235)
  expect(luminance(look.titleInk)).toBeLessThan(80)
  expect(look.titleFont).toMatch(/Newsreader/i)
  expect(look.pages).toBe(true)
  expect(look.ribbon).toBe(true)
  expect(look.monogram).toBe('"D"')
  // A book stands upright, and what it holds is written on the cloth in a light ink.
  expect(look.box.height).toBeGreaterThan(look.box.width)
  expect(luminance(look.footerInk)).toBeGreaterThan(220)
  expect(look.blur === 'none' || look.blur === '').toBe(true)
  await expect(book.getByText('1 source', { exact: true })).toBeVisible()
})

test('the cover lifts and opens on its hinge under the pointer, and for keyboard focus', async ({ page }) => {
  await open(page, 'gemini-forward-light')
  await allowMotion(page)
  const book = page.locator('[data-dn-notebook-card]').first()
  const cover = book.locator('[data-dn-book-cover]')
  const hinge = () => cover.evaluate((el) => getComputedStyle(el).transform)

  expect(await hinge()).toMatch(/^(none|matrix\(1, 0, 0, 1, 0, 0\))$/)
  await book.hover({ position: { x: 120, y: 120 } })
  await expect.poll(hinge).toMatch(/^matrix3d\(/)

  await page.mouse.move(5, 5)
  await expect.poll(hinge).toMatch(/^(none|matrix\(1, 0, 0, 1, 0, 0\))$/)
  await book.getByRole('link').focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  await expect.poll(hinge).toMatch(/^matrix3d\(/)
})

test('reduced motion keeps the book shut and still', async ({ page }) => {
  await open(page, 'gemini-forward-light')
  // The fixture's display preference is reduced motion.
  await expect(page.locator('html')).toHaveAttribute('data-dn-motion', 'reduced')
  const book = page.locator('[data-dn-notebook-card]').first()
  await book.hover({ position: { x: 120, y: 120 } })
  await page.waitForTimeout(300)
  const still = await book.evaluate((el) => ({
    cover: getComputedStyle(el.querySelector('[data-dn-book-cover]')!).transform,
    animation: getComputedStyle(el).animationName,
    transition: getComputedStyle(el).transitionDuration,
  }))
  expect(still.cover).toMatch(/^(none|matrix\(1, 0, 0, 1, 0, 0\))$/)
  expect(still.animation).toBe('none')
  expect(still.transition).toBe('0s')
})

test('opening a notebook swings the cover, then arrives in the notebook, which wears its cloth', async ({ page }) => {
  await open(page, 'gemini-forward-light')
  await allowMotion(page)
  const book = page.locator('[data-dn-notebook-card]').first()
  const cover = await book.getAttribute('data-dn-cover')
  await book.getByRole('link').click()
  await expect(book).toHaveAttribute('data-dn-opening', '')
  await expect(page).toHaveURL(/\/notebooks\/notebook/)
  expect(COVERS).toContain(cover)
})

test('a modified click still opens the notebook in a new tab at once', async ({ page, context }) => {
  await open(page, 'gemini-forward-light')
  await allowMotion(page)
  const book = page.locator('[data-dn-notebook-card]').first()
  const [tab] = await Promise.all([
    context.waitForEvent('page'),
    book.getByRole('link').click({ modifiers: ['ControlOrMeta'] }),
  ])
  await expect(book).not.toHaveAttribute('data-dn-opening', '')
  // The new tab has no fixture behind it, so it never finishes loading: where it
  // was sent is the evidence, and this page staying put.
  await expect.poll(() => tab.url()).toMatch(/\/notebooks\/notebook/)
  await expect(page).toHaveURL(/\/notebooks$/)
  await tab.close()
})

test('headings are set in the editorial serif; controls and readouts stay sans', async ({ page }) => {
  await open(page, 'gemini-forward-light')
  const fonts = await page.evaluate(() => ({
    title: getComputedStyle(document.querySelector('main h1')!).fontFamily,
    section: getComputedStyle(document.querySelector('main h2')!).fontFamily,
    button: getComputedStyle(document.querySelector('main button')!).fontFamily,
  }))
  expect(fonts.title).toMatch(/Newsreader/i)
  expect(fonts.section).toMatch(/Newsreader/i)
  expect(fonts.button).not.toMatch(/Newsreader/i)

  await page.goto('/')
  await expect(page.locator('[data-dn-runtime-status]').first()).toBeVisible()
  const readout = await page.locator('[data-dn-runtime-status] :is(h1, h2)').first().evaluate((el) => getComputedStyle(el).fontFamily)
  expect(readout).not.toMatch(/Newsreader/i)
})

test('home leads with your books: the recent shelf sits above the ways to start', async ({ page }) => {
  await open(page, 'gemini-forward-light', '/')
  const shelf = page.locator('[data-dn-home-shelf]')
  await expect(shelf).toBeVisible()
  const first = shelf.locator('a[data-dn-cover]').first()
  expect(COVERS).toContain(await first.getAttribute('data-dn-cover'))
  const box = (await first.boundingBox())!
  expect(box.height).toBeGreaterThan(box.width)
  // Big enough to hit, and its name is readable ink on paper.
  expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44)
  const name = await first.locator('.dn-workspace-notebook-name').evaluate((el) => ({ ink: getComputedStyle(el).color, paper: getComputedStyle(el).backgroundColor }))
  expect(luminance(name.paper) - luminance(name.ink)).toBeGreaterThan(150)

  const today = page.locator('section[aria-labelledby="workspace-actions-title"]')
  expect((await shelf.boundingBox())!.y).toBeLessThan((await today.boundingBox())!.y)
})

test('the rail has one marker, on the current page', async ({ page }) => {
  await open(page, 'gemini-forward-light')
  const rail = page.getByRole('navigation', { name: 'Primary' })
  await expect(rail.locator('.dn-rail-marker')).toHaveCount(1)
  await expect(rail.locator('a[aria-current="page"] .dn-rail-marker')).toHaveCount(1)
  await rail.getByRole('link', { name: 'Sources' }).click()
  await expect(page).toHaveURL(/\/sources/)
  await expect(rail.locator('.dn-rail-marker')).toHaveCount(1)
  await expect(rail.getByRole('link', { name: 'Sources' }).locator('.dn-rail-marker')).toHaveCount(1)
})

test('the dark theme binds notebooks too, with a dark paper label', async ({ page }) => {
  await open(page, 'gemini-forward-dark')
  const book = page.locator('[data-dn-notebook-card]').first()
  await expect(book).toBeVisible()
  const look = await book.evaluate((el) => ({
    cloth: getComputedStyle(el.querySelector('[data-dn-book-cover]')!).backgroundColor,
    label: getComputedStyle(el.querySelector('[data-slot="card"]')!).backgroundColor,
  }))
  expect(look.cloth).not.toBe(look.label)
  expect(luminance(look.label)).toBeLessThan(60)
})

test('high-contrast themes keep plain cards', async ({ page }) => {
  await open(page, 'high-contrast-light')
  const book = page.locator('[data-dn-notebook-card]').first()
  await expect(book).toBeVisible()
  const plain = await book.evaluate((el) => {
    const cover = el.querySelector('[data-dn-book-cover]')!
    const hidden = (selector: string) => getComputedStyle(el.querySelector(selector)!).display === 'none'
    return {
      cloth: getComputedStyle(cover).backgroundColor,
      image: getComputedStyle(cover).backgroundImage,
      pages: hidden('[data-dn-book-pages]'),
      ribbon: hidden('[data-dn-book-ribbon]'),
      monogram: hidden('[data-dn-book-monogram]'),
      // One frame around the whole card, the date and actions included.
      frame: getComputedStyle(el).borderTopWidth,
      label: getComputedStyle(el.querySelector('[data-slot="card"]')!).borderTopWidth,
    }
  })
  expect(plain).toMatchObject({ frame: '1px', label: '0px' })
  expect(plain.cloth).toBe('rgba(0, 0, 0, 0)')
  expect(plain.image).toBe('none')
  expect(plain).toMatchObject({ pages: true, ribbon: true, monogram: true })
})

// v0.8.130 — found by looking at every theme, width and state of the shelf (2026-10-05).
async function openShelf(page: Page, opts: { names?: string[]; width?: number; height?: number; empty?: boolean } = {}) {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
  if (opts.names) {
    const names = opts.names
    await page.route((url) => url.pathname === '/api/notebooks', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      const archived = new URL(route.request().url()).searchParams.get('archived') === 'true'
      await route.fulfill({
        json: archived ? [] : names.map((name, index) => ({
          id: `notebook:shelf-${index}`, name, description: 'Notes and sources.', archived: false,
          created: '2026-09-01T10:00:00Z', updated: '2026-09-20T10:00:00Z',
          source_count: opts.empty ? 0 : 2, note_count: opts.empty ? 0 : 3,
        })),
      })
    })
  }
  await page.setViewportSize({ width: opts.width ?? 1440, height: opts.height ?? 900 })
  await page.goto('/notebooks')
  await expect(page.getByRole('heading', { name: 'Notebooks', level: 1 })).toBeVisible()
}

test('on a phone the book and the search field use the full width of the page', async ({ page }) => {
  await openShelf(page, { names: ['Field notes'], width: 390, height: 844 })
  const book = page.locator('[data-dn-notebook-card]').first()
  await expect(book).toBeVisible()
  const widths = await page.evaluate(() => {
    const width = (selector: string) => document.querySelector(selector)!.getBoundingClientRect().width
    return { shelf: width('[data-dn-notebook-shelf]'), book: width('[data-dn-notebook-card]'), search: width('#notebook-search') }
  })
  expect(widths.shelf).toBeGreaterThan(300)
  expect(widths.book).toBeGreaterThanOrEqual(widths.shelf - 1)
  expect(widths.search).toBeGreaterThanOrEqual(widths.shelf - 1)
})

test('a long name in the list view ends in an ellipsis instead of being cut mid-letter', async ({ page }) => {
  const longName = 'Reading: The Making of the Atomic Bomb and everything that followed from it in the decades after the war'
  await openShelf(page, { names: [longName] })
  await page.getByRole('button', { name: 'List view' }).click()
  const name = page.locator('[data-dn-notebook-row]').getByRole('link', { name: longName })
  await expect(name).toBeVisible()
  // The ellipsis is only drawn by a block box: a flex box (as links are here) clips without one.
  const metrics = await name.locator('span').evaluate((el) => ({
    overflow: getComputedStyle(el).textOverflow,
    hidden: getComputedStyle(el).overflowX,
    display: getComputedStyle(el).display,
    truncated: el.scrollWidth > el.clientWidth,
  }))
  expect(metrics).toEqual({ overflow: 'ellipsis', hidden: 'hidden', display: 'block', truncated: true })
})

test('an empty shelf says it is empty and shows a blank book, not "No results"', async ({ page }) => {
  await openShelf(page, { names: [] })
  await expect(page.getByRole('heading', { name: 'Your shelf is empty' })).toBeVisible()
  await expect(page.getByText('No results')).toHaveCount(0)
  await expect(page.locator('[data-dn-empty-book]')).toBeVisible()
  await expect(page.getByRole('button', { name: 'New notebook' }).last()).toBeVisible()
})

// Seen in the packaged app on a new notebook: the reason sat faint and cut off at the foot of the book.
test('on an empty notebook the reason the podcast button is off is readable and inside the cover', async ({ page }) => {
  await openShelf(page, { names: ['A long enough name to wrap onto a second line'], empty: true })
  const book = page.locator('[data-dn-notebook-card]').first()
  const reason = book.getByText('No readable content', { exact: false })
  await expect(reason).toBeVisible()
  const fit = await book.evaluate((el) => {
    const cover = el.querySelector('[data-dn-book-cover]')!.getBoundingClientRect()
    const note = el.querySelector('[data-dn-cover-footer] p')!
    const box = note.getBoundingClientRect()
    // Any CSS colour syntax (color-mix resolves to `color(srgb …)`) painted to 8-bit RGB.
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const ink = canvas.getContext('2d', { willReadFrequently: true })!
    ink.fillStyle = getComputedStyle(note).color
    ink.fillRect(0, 0, 1, 1)
    const [r, g, b] = ink.getImageData(0, 0, 1, 1).data
    return { inside: box.bottom <= cover.bottom - 8 && box.right <= cover.right - 8, colour: `rgb(${r}, ${g}, ${b})` }
  })
  expect(fit.inside).toBe(true)
  // Cream ink on the cloth, not the page's grey.
  expect(luminance(fit.colour)).toBeGreaterThan(170)
})
