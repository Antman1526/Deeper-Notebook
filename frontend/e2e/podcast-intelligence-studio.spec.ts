import { expect, test } from '@playwright/test'

test.describe('Podcast Intelligence Studio browser acceptance', () => {
  test('opens as a sequential, no-selection review surface without submitting production', async ({ page }) => {
    const submissions: string[] = []
    // This test deliberately uses the persistent local API. The app shell
    // performs its own health/readiness reads; stubbing only the submission
    // route would create a partial, misleading browser proof.
    await page.route('**/api/podcasts/studio/submit', async (route) => {
      submissions.push(route.request().method())
      await route.fulfill({ status: 500, body: 'unexpected submission' })
    })

    // Studio acceptance starts from the documented returning-user state. Setup
    // Wizard navigation is separately covered; coupling to its home redirect
    // would make this test depend on an unrelated first-run workflow.
    await page.context().addCookies([{
      name: 'wizard_completed',
      value: '1',
      url: 'http://127.0.0.1:3117',
    }])
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
