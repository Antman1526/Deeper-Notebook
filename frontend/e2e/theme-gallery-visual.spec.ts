import { expect, test } from '@playwright/test'

import { installThemeVisualFixture } from './fixtures/theme-visuals'

const captures = [
  { theme: 'research-core-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'research-core-light', viewport: { width: 1440, height: 900 } },
  { theme: 'deep-ocean', viewport: { width: 1280, height: 800 } },
  { theme: 'archive-paper', viewport: { width: 1280, height: 800 } },
  { theme: 'high-contrast-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'high-contrast-light', viewport: { width: 1440, height: 900 } },
] as const

for (const capture of captures) {
  test(`${capture.theme} theme gallery`, async ({ page }) => {
    const fixture = await installThemeVisualFixture(page, capture.theme)
    await page.setViewportSize(capture.viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Choose your research environment' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', capture.theme)
    await expect(page).toHaveScreenshot(`${capture.theme}-${capture.viewport.width}x${capture.viewport.height}.png`, {
      animations: 'disabled',
      caret: 'hide',
      fullPage: true,
    })
    expect(fixture.unexpectedRequests).toEqual([])
  })
}

for (const capture of captures.filter(capture => capture.theme.startsWith('high-contrast'))) {
  test(`${capture.theme} selected accessibility gallery`, async ({ page }) => {
    const fixture = await installThemeVisualFixture(page, capture.theme)
    await page.setViewportSize(capture.viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/settings')

    const label = capture.theme === 'high-contrast-dark' ? 'High Contrast Dark' : 'High Contrast Light'
    const card = page.getByRole('article', { name: `${label} theme` })
    await card.scrollIntoViewIfNeeded()
    await expect(card).toContainText('Current')
    await page.getByRole('button', { name: `Preview ${label}` }).click()
    await expect(card).toContainText('Previewing')

    const selectedCard = await card.screenshot({
      animations: 'disabled',
      caret: 'hide',
    })
    expect(selectedCard).toMatchSnapshot(`${capture.theme}-selected-accessibility.png`)
    expect(fixture.unexpectedRequests).toEqual([])
  })
}
