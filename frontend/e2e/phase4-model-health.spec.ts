import { expect, test, type Page } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// v0.8.130 — model health sits in the rail footer, and below 1024px the rail is a
// sheet behind the Menu button, so on a phone a down or degraded model was invisible
// until you opened the menu. The command bar now shows it there, only when something
// needs attention, and links to the page that explains and fixes it.

const unhealthy = { name: 'llama-server', status: 'unhealthy', detail: 'Connection refused', latency_ms: null }
const healthy = { name: 'llama-server', status: 'healthy', detail: null, latency_ms: 12 }

async function serveHealth(page: Page, overall: 'healthy' | 'degraded' | 'down') {
  const models = overall === 'healthy' ? [healthy] : [unhealthy]
  await page.route((url) => url.pathname === '/api/local-models/health', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ overall, models }) }),
  )
}

const indicator = (page: Page) => page.getByRole('banner', { name: 'Command bar' }).getByRole('link', { name: /local model/i })

test.beforeEach(async ({ page }) => {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
})

test('a phone shows degraded models in the command bar, without opening the menu', async ({ page }) => {
  await serveHealth(page, 'degraded')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/notebooks')

  const link = indicator(page)
  await expect(link).toBeVisible()
  await expect(link).toHaveAccessibleName('Some local models need attention')
  await expect(link).toHaveAttribute('href', '/settings/local-models')
  const box = (await link.boundingBox())!
  expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(44)
  await expect(page.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false')
})

test('a phone says so when local models are down', async ({ page }) => {
  await serveHealth(page, 'down')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/notebooks')
  await expect(indicator(page)).toHaveAccessibleName('Local models are unavailable')
})

test('nothing extra when every model is healthy', async ({ page }) => {
  await serveHealth(page, 'healthy')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/notebooks')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(indicator(page)).toHaveCount(0)
})

test('on desktop the rail shows model health, so the command bar does not', async ({ page }) => {
  await serveHealth(page, 'degraded')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/notebooks')
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByLabel(/llama-server/)).toBeVisible()
  await expect(indicator(page)).toBeHidden()
})

test('the indicator fits the narrowest phone without sideways scroll', async ({ page }) => {
  await serveHealth(page, 'down')
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/notebooks')
  await expect(indicator(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const bar = await page.getByRole('banner', { name: 'Command bar' }).evaluate((element) => element.scrollWidth - element.clientWidth)
  expect(bar).toBeLessThanOrEqual(0)
})

// The indicator takes a 44px slot, so the phone bar tightens (compact spacing, square
// icon buttons, the name at 16px) to keep the product name whole.
const titleTruncated = (page: Page) => page.locator('.dn-command-title--compact').evaluate((element) => element.scrollWidth > element.clientWidth)

for (const width of [390, 360]) {
  test(`the product name stays whole beside the indicator at ${width}`, async ({ page }) => {
    await serveHealth(page, 'degraded')
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/notebooks')
    await expect(indicator(page)).toBeVisible()
    expect(await titleTruncated(page)).toBe(false)
  })
}

test('a healthy phone bar keeps the whole name even at 320', async ({ page }) => {
  await serveHealth(page, 'healthy')
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/notebooks')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  expect(await titleTruncated(page)).toBe(false)
})
