import type { Page } from '@playwright/test'

// v0.8.130 — screenshot baselines flaked under heavy machine load: toHaveScreenshot's
// "two identical frames" check could pass before a slow mocked response re-rendered a
// tall page. Track in-flight requests from the start of the test and wait for a quiet
// network and loaded fonts before capturing. (`networkidle` is not enough: it resolves
// at once if the page was idle earlier.)

const inFlight = new WeakMap<Page, { count: number }>()

export function trackRequests(page: Page) {
  const state = { count: 0 }
  inFlight.set(page, state)
  page.on('request', () => { state.count += 1 })
  const done = () => { state.count = Math.max(0, state.count - 1) }
  page.on('requestfinished', done)
  page.on('requestfailed', done)
}

export async function settleForScreenshot(page: Page, quietMs = 500, timeoutMs = 10_000) {
  const state = inFlight.get(page)
  const deadline = Date.now() + timeoutMs
  let quietSince = Date.now()
  while (state && Date.now() < deadline) {
    if (state.count > 0) quietSince = Date.now()
    else if (Date.now() - quietSince >= quietMs) break
    await page.waitForTimeout(50)
  }
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
}
