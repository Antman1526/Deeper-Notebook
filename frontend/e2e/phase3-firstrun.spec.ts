import { expect, test, type Page } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// Phase 3c of the 2026-09-30 UI audit: the first run. The first thing a new user saw
// was a developer health table — red "offline / error / missing" pills, "Command
// registry", a raw shell command. Now it is a "Getting ready" screen that says what
// is happening in plain words, with the diagnostics one click away. Login said
// "Deeper Notebook" three times and ended in a "Version fixture" footer.

test.beforeEach(async ({ page }) => {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
})

const DEGRADED = {
  status: 'degraded',
  checks: {
    database: { status: 'online', ok: true, error: null },
    migrations: { status: 'applied', ok: true, error: null },
    embedding_model: { status: 'missing', ok: false, error: 'No default embedding model assigned.' },
    chat_model: { status: 'missing', ok: false, error: 'No default chat model assigned.' },
    command_registry: { status: 'loaded', ok: true, error: null },
    worker: { status: 'online', ok: true, error: null },
  },
}

async function serveHealth(page: Page, body: unknown) {
  await page.route('**/healthz/deep', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) }),
  )
}

test.describe('3c — getting ready', () => {
  test('a new user sees "Getting ready", not a health table', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/setup-wizard')
    const main = page.locator('#dn-main')

    await expect(main.getByRole('heading', { level: 1 })).toHaveText('Getting ready')
    await expect(main.getByRole('heading', { level: 2, name: 'Waiting for the database' })).toBeVisible()
    await expect(page.getByTestId('continue-button')).toBeDisabled()

    // The diagnostics are behind a disclosure, closed by default.
    const details = main.getByRole('button', { name: 'Show details' })
    await expect(details).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByTestId('subsystem-list')).toHaveCount(0)
    await expect(main.getByText('Command registry')).toHaveCount(0)
    await expect(main.getByText(/surreal-commands-worker/)).toHaveCount(0)
    await expect(main.locator('[data-slot="badge"]')).toHaveCount(0)
  })

  test('the details hold every check, without red pills', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/setup-wizard')
    const main = page.locator('#dn-main')

    const details = main.getByRole('button', { name: 'Show details' })
    await details.click()
    await expect(main.getByRole('button', { name: 'Hide details' })).toHaveAttribute('aria-expanded', 'true')

    const list = page.getByTestId('subsystem-list')
    await expect(list).toBeVisible()
    await expect(list.getByRole('listitem')).toHaveCount(6)
    await expect(list.getByText('Command registry')).toBeVisible()
    await expect(page.getByTestId('subsystem-hint-worker')).toContainText('surreal-commands-worker')
    await expect(list.getByRole('link', { name: /Fix this/ }).first()).toHaveAttribute('href', '/settings/api-keys')
    await expect(list.locator('[data-slot="badge"]')).toHaveCount(0)
  })

  test('degraded: you can start, and it says how many checks need attention', async ({ page }) => {
    await serveHealth(page, DEGRADED)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/setup-wizard')
    const main = page.locator('#dn-main')

    await expect(main.getByRole('heading', { level: 2, name: 'Almost ready' })).toBeVisible()
    await expect(main.getByText('2 of 6 checks need attention')).toBeVisible()
    await expect(page.getByTestId('continue-button')).toBeEnabled()
  })

  test('the summary keeps its height when the check returns', async ({ page }) => {
    let release: () => void = () => {}
    let held = Promise.resolve()
    await page.route('**/healthz/deep', async (route) => {
      await held
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(DEGRADED) })
    })
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      held = new Promise<void>((resolve) => { release = resolve })
      await page.setViewportSize(viewport)
      await page.goto('/setup-wizard')
      const summary = page.locator('.dn-first-run-summary')
      await expect(summary.getByRole('heading', { name: 'Checking your setup' })).toBeVisible()
      const before = await summary.boundingBox()
      release()
      await expect(summary.getByRole('heading', { name: 'Almost ready' })).toBeVisible()
      const after = await summary.boundingBox()
      expect(Math.abs(after!.height - before!.height)).toBeLessThanOrEqual(1)
    }
  })

  test('fits a phone without sideways scroll', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/setup-wizard')
    await page.locator('#dn-main').getByRole('button', { name: 'Show details' }).click()
    await expect(page.getByTestId('subsystem-list')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
})

test.describe('3c — login', () => {
  test('the brand appears once, with one heading', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/login')
    const main = page.getByRole('main')
    await expect(main.getByRole('heading', { level: 1, name: 'Welcome back' })).toBeVisible()
    await expect(main.getByRole('heading')).toHaveCount(1)

    const text = await main.innerText()
    expect(text.match(/Deeper Notebook/g) ?? []).toHaveLength(1)
  })

  test('the version is behind "Connection details", not a footer', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/login')
    const main = page.getByRole('main')
    await expect(main.getByLabel('Password', { exact: true })).toBeVisible()
    await expect(main.getByText(/Version/)).toBeHidden()

    await main.getByText('Connection details').click()
    await expect(main.getByText(/Version/)).toBeVisible()
  })

  test('the password field is labelled for autofill, and errors are announced', async ({ page }) => {
    await page.route('**/api/notebooks', (route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' }),
    )
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/login')
    const password = page.getByLabel('Password', { exact: true })
    await expect(password).toHaveAttribute('autocomplete', 'current-password')

    await password.fill('not-the-password')
    await page.getByRole('button', { name: /sign in/i }).click()
    // Scoped to main: Next's route announcer is also role=alert.
    await expect(page.getByRole('main').getByRole('alert')).toBeVisible()
  })
})
