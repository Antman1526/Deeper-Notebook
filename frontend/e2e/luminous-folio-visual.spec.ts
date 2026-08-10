import { expect, test } from '@playwright/test'

import { installLuminousFolioFixture } from './fixtures/luminous-folio'

const captures = [
  { theme: 'research-core-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'research-core-light', viewport: { width: 1440, height: 900 } },
  { theme: 'archive-paper', viewport: { width: 1280, height: 800 } },
  { theme: 'deep-ocean', viewport: { width: 1280, height: 800 } },
] as const

for (const capture of captures) {
  test(`Luminous notebook index — ${capture.theme}`, async ({ page }) => {
    await installLuminousFolioFixture(page, { theme: capture.theme })
    await page.setViewportSize(capture.viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/notebooks')

    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', capture.theme)
    await expect(page).toHaveScreenshot(
      `notebooks-${capture.theme}-${capture.viewport.width}x${capture.viewport.height}.png`,
      { animations: 'disabled', caret: 'hide' },
    )
  })
}
