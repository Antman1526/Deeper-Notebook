import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, test } from './fixtures/research-workbench'

// Phase 1 of the 2026-09-30 UI audit: new primitives, proven in the production build.

test.beforeEach(async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
})

test('Settings: guided tips is a switch named by its heading, and toggles', async ({ page }) => {
  await page.goto('/settings')
  const tips = page.getByRole('switch', { name: 'Guided tips' })
  await expect(tips).toBeVisible()

  const before = await tips.getAttribute('aria-checked')
  await tips.click()
  await expect(tips).toHaveAttribute('aria-checked', before === 'true' ? 'false' : 'true')
  // The state is conveyed by the control, not by "On"/"Off" button text.
  await expect(tips).not.toHaveText(/^(On|Off)$/)
})

test('the command bar shortcut uses the shared key chip at the 12px floor', async ({ page }) => {
  await page.goto('/notebooks')
  const chip = page.getByTestId('command-shortcut')
  await expect(chip).toBeVisible()
  await expect(chip).toHaveAttribute('data-slot', 'kbd')
  const size = await chip.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
  expect(size).toBeGreaterThanOrEqual(12)
})
