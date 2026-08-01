import { expect, test } from '@playwright/test'

test.describe('Podcast Intelligence Studio browser acceptance', () => {
  test('opens as a sequential, no-selection review surface without submitting production', async ({ page }) => {
    const submissions: string[] = []
    // The native API is intentionally absent in this browser-only test. Stub
    // only the startup health/config check so the route can render its safe
    // no-selection state; production routes remain guarded separately below.
    await page.route('**/api/config', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ version: 'browser-test', dbStatus: 'online' }),
      })
    })
    await page.route('**/api/auth/status', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ auth_enabled: false }),
      })
    })
    await page.route('**/api/podcasts/studio/submit', async (route) => {
      submissions.push(route.request().method())
      await route.fulfill({ status: 500, body: 'unexpected submission' })
    })

    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/podcasts/studio')

    await expect(page.getByRole('heading', { name: 'Podcast Intelligence Studio' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Research Set' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Editorial Brief' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Outline Storyboard' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Production Timeline' })).toBeVisible()
    await expect(page.getByText('Available after intellectual engine upgrade').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Prepare production review' })).toBeDisabled()
    await expect(page.getByText('Choose at least one readable source before production review.')).toBeVisible()
    expect(submissions).toEqual([])
  })
})
