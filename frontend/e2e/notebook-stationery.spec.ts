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
