import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// v0.8.130 — stationery beyond the shelf (user direction 2026-10-04/05: carry the
// notebook design across the app). Every page is a desk of paper: panels are sheets
// resting on it with a soft layered shadow, the page title sits on a letterhead rule,
// and tabs are index tabs. No gradient, glass or shine is involved, so the flat rules
// in premium-pass.spec.ts still hold on these pages. High-contrast themes keep plain
// panels, and nothing moves under reduced motion.

type Theme = NonNullable<Parameters<typeof installVisualSystemFixture>[1]>['theme']

async function open(page: Page, route: string, theme: Theme = 'gemini-forward-light') {
  await installVisualSystemFixture(page, { theme })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(route)
  await expect(page.locator('main h1').first()).toBeVisible()
}

const SHEET = 'main :is([data-slot="card"], .rounded-xl.border.bg-card)'
const layers = (shadow: string) => (shadow === 'none' ? 0 : shadow.split(/,(?![^(]*\))/).length)

for (const route of ['/study', '/capture', '/studio', '/search'] as const) {
  test(`${route}: panels are sheets of paper resting on the desk`, async ({ page }) => {
    await open(page, route)
    const sheet = page.locator(SHEET).first()
    await expect(sheet).toBeVisible()
    const style = await sheet.evaluate((el) => ({
      shadow: getComputedStyle(el).boxShadow,
      image: getComputedStyle(el).backgroundImage,
    }))
    expect(layers(style.shadow), `a contact shadow and a soft far shadow: ${style.shadow}`).toBeGreaterThanOrEqual(2)
    expect(style.shadow, 'the soft far shadow').toMatch(/ 24px /)
    expect(style.shadow).not.toMatch(/inset/)
    expect(style.image).toBe('none')
  })
}

test('the page title sits on a letterhead rule with a marker in the brand ink', async ({ page }) => {
  await open(page, '/podcasts')
  const rule = await page.locator('[data-dn-folio-page-header]').first().evaluate((el) => {
    const probe = document.createElement('span')
    probe.style.color = 'var(--primary)'
    document.body.appendChild(probe)
    const primary = getComputedStyle(probe).color
    probe.remove()
    const line = getComputedStyle(el, '::before')
    const marker = getComputedStyle(el, '::after')
    return {
      line: line.content !== 'none' && parseFloat(line.height) === 1,
      marker: marker.content !== 'none' && parseFloat(marker.height) === 2 && parseFloat(marker.width) >= 32,
      ink: marker.backgroundColor === primary,
    }
  })
  expect(rule).toEqual({ line: true, marker: true, ink: true })
})

test('Studio, which has its own header, carries the same letterhead rule', async ({ page }) => {
  await open(page, '/studio')
  const marker = await page.locator('main [data-dn-letterhead]').first().evaluate((el) => {
    const style = getComputedStyle(el, '::after')
    return style.content !== 'none' && parseFloat(style.height) === 2
  })
  expect(marker).toBe(true)
})

test('tabs are index tabs: the open one is a raised paper tab marked in the brand ink', async ({ page }) => {
  await open(page, '/podcasts')
  const tabs = await page.evaluate(() => {
    const read = (el: Element) => {
      const style = getComputedStyle(el)
      const edge = getComputedStyle(el, '::after')
      return { shadow: style.boxShadow, edge: edge.content !== 'none' && parseFloat(edge.height) === 2 }
    }
    return {
      open: read(document.querySelector('main [role="tab"][data-state="active"]')!),
      closed: read(document.querySelector('main [role="tab"][data-state="inactive"]')!),
      list: getComputedStyle(document.querySelector('main [role="tablist"]')!).borderTopLeftRadius,
    }
  })
  expect(tabs.open.shadow).not.toBe('none')
  expect(tabs.open.edge).toBe(true)
  expect(tabs.closed.shadow).toBe('none')
  expect(tabs.closed.edge).toBe(false)
  // A tray of index tabs, not a pill.
  expect(parseFloat(tabs.list)).toBeLessThanOrEqual(10)
})

test('sheets settle onto the desk in sequence, and stay still under reduced motion', async ({ page }) => {
  await open(page, '/study')
  const animation = () => page.locator(SHEET).first().evaluate((el) => getComputedStyle(el).animationName)
  // The fixture pins reduced motion.
  expect(await animation()).toBe('none')
  await page.evaluate(() => { document.documentElement.dataset.dnMotion = 'full' })
  expect(await animation()).toBe('dn-sheet-settle')
})

test('high-contrast themes keep plain panels and tabs', async ({ page }) => {
  await open(page, '/study', 'high-contrast-light')
  const sheet = page.locator(SHEET).first()
  await expect(sheet).toBeVisible()
  // Not the sheet's soft far shadow (24px blur): the panel keeps whatever it had before.
  expect(await sheet.evaluate((el) => getComputedStyle(el).boxShadow)).not.toMatch(/ 24px /)
  expect(await page.locator('[data-dn-folio-page-header]').first().evaluate((el) => getComputedStyle(el, '::after').content)).toBe('none')
})
