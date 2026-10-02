import { expect, test } from '@playwright/test'

import { installVisualSystemFixture } from './fixtures/visual-system'

// Phase 3b of the 2026-09-30 UI audit: the shell diet. One rail instead of a
// 68px dock plus a 272px "Notebook index" (340px of chrome at every width), eight
// destinations instead of fourteen, the shell mounted once, and the small
// accessibility gaps (skip link, sign-out confirm, mobile sheet).

test.beforeEach(async ({ page }) => {
  await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
})

const SETTINGS_FAMILY = ['Models', 'Transformations', 'MCP Servers', 'Launch Preferences', 'Advanced']

test.describe('3b — one rail', () => {
  test('a single 240px rail replaces the dock and the notebook index', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    const rail = page.getByRole('navigation', { name: 'Primary' })
    await expect(rail).toBeVisible()
    await expect(page.locator('.dn-instrument-dock, .dn-adaptive-navigator')).toHaveCount(0)

    const [railBox, canvasBox] = await Promise.all([
      rail.boundingBox(),
      page.locator('.dn-workspace-canvas').boundingBox(),
    ])
    expect(railBox!.width).toBeLessThanOrEqual(256)
    // Chrome left of the content was 340px.
    expect(canvasBox!.x).toBeLessThanOrEqual(256)
  })

  test('eight destinations, with the settings family under Settings', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    const rail = page.getByRole('navigation', { name: 'Primary' })
    const destinations = rail.getByRole('list', { name: 'Destinations' }).getByRole('link')
    await expect(destinations).toHaveCount(8)
    await expect(rail.getByRole('link', { name: 'Settings', exact: true })).toBeVisible()
    for (const name of SETTINGS_FAMILY) {
      await expect(rail.getByRole('link', { name, exact: true }), name).toHaveCount(0)
    }

    await page.goto('/settings/mcp')
    for (const name of SETTINGS_FAMILY) {
      await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name, exact: true }), name).toBeVisible()
    }
    await expect(page.getByRole('link', { name: 'MCP Servers', exact: true })).toHaveAttribute('aria-current', 'page')
  })

  test('the shell stays mounted across navigation', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    const rail = page.getByRole('navigation', { name: 'Primary' })
    await expect(rail).toBeVisible()
    await rail.evaluate((el) => { (el as HTMLElement & { __dnMarker?: number }).__dnMarker = 1 })

    await rail.getByRole('link', { name: 'Sources', exact: true }).click()
    await expect(page).toHaveURL(/\/sources$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Sources' })).toBeVisible()
    // Each page mounted its own shell, so the rail (and its scroll) reset on every click.
    expect(await page.getByRole('navigation', { name: 'Primary' }).evaluate((el) => (el as HTMLElement & { __dnMarker?: number }).__dnMarker)).toBe(1)
  })
})

test.describe('3b — command bar and accessibility', () => {
  test('one keyboard hint, on Quick actions', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    const bar = page.getByRole('banner', { name: 'Command bar' })
    await expect(bar.getByRole('button', { name: 'Open command palette' })).toBeVisible()
    await expect(bar.locator('kbd, [data-slot="kbd"]')).toHaveCount(1)
  })

  test('a skip link leads to the content', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    await expect(page.getByRole('heading', { level: 1, name: 'Notebooks' })).toBeVisible()
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Skip to content' })
    await expect(skip).toBeFocused()
    await expect(skip).toBeInViewport()
    await page.keyboard.press('Enter')
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest('.dn-workspace-canvas')))).toBe(true)
  })

  test('signing out asks first', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    await page.getByRole('button', { name: 'Sign Out' }).click()
    const confirm = page.getByRole('alertdialog')
    await expect(confirm).toBeVisible()
    await confirm.getByRole('button', { name: 'Cancel' }).click()
    await expect(confirm).toHaveCount(0)
    await expect(page).toHaveURL(/\/notebooks$/)
  })

  test('on a phone the rail is a sheet with a scrim, closed by Escape', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/notebooks')
    const rail = page.getByRole('navigation', { name: 'Primary' })
    await expect(rail).toBeHidden()

    await page.getByRole('button', { name: 'Menu' }).click()
    await expect(rail).toBeVisible()
    await expect(page.locator('[data-dn-rail-scrim]')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(rail).toBeHidden()

    await page.getByRole('button', { name: 'Menu' }).click()
    await page.locator('[data-dn-rail-scrim]').click({ position: { x: 370, y: 400 } })
    await expect(rail).toBeHidden()
  })
})
