import { expect, test } from '@playwright/test'

import { installThemeVisualFixture } from './fixtures/theme-visuals'

const captures = [
  { theme: 'research-core-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'research-core-light', viewport: { width: 1440, height: 900 } },
  { theme: 'gemini-forward-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'deep-ocean', viewport: { width: 1280, height: 800 } },
  { theme: 'archive-paper', viewport: { width: 1280, height: 800 } },
  { theme: 'high-contrast-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'high-contrast-light', viewport: { width: 1440, height: 900 } },
] as const

async function unclipSettingsViewport(page: Parameters<typeof installThemeVisualFixture>[0]) {
  const viewport = page.getByTestId('settings-scroll-viewport')
  await expect(viewport).toBeVisible()
  await viewport.evaluate((element) => {
    const settingsViewport = element as HTMLElement
    const main = settingsViewport.parentElement
    const shell = main?.parentElement

    // The application intentionally keeps Settings in an internal scroll
    // viewport. Full-page screenshots need a temporary capture-only layout so
    // that the internal gallery is painted instead of clipped at the first
    // viewport. The test selector keeps this adjustment scoped and explicit.
    for (const node of [settingsViewport, main, shell]) {
      if (!node) continue
      node.style.overflow = 'visible'
      node.style.height = 'auto'
      node.style.maxHeight = 'none'
      node.style.flex = 'none'
    }
    document.documentElement.style.overflow = 'visible'
    document.documentElement.style.height = 'auto'
    document.body.style.overflow = 'visible'
    document.body.style.height = 'auto'
    settingsViewport.dataset.themeVisualUnclipped = 'true'
  })
}

for (const capture of captures) {
  test(`${capture.theme} theme gallery`, async ({ page }) => {
    const fixture = await installThemeVisualFixture(page, capture.theme)
    await page.route('**/api/features', async route => {
      const method = route.request().method()
      if (method !== 'GET' && method !== 'HEAD') {
        fixture.unexpectedRequests.push(`${method} ${new URL(route.request().url()).pathname}`)
        await route.fulfill({
          status: 405,
          contentType: 'application/json',
          headers: { Allow: 'GET, HEAD' },
          body: JSON.stringify({ detail: 'Method not allowed by theme visual fixture' }),
        })
        return
      }

      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          features: {
            evidenceStudio: true,
            visualRefresh: true,
            modelFleet: true,
            researchRuns: true,
            studyWorkbench: true,
            sourceVisuals: true,
          },
        }),
      })
    })
    await page.setViewportSize(capture.viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Choose your research environment' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', capture.theme)
    await unclipSettingsViewport(page)
    await expect(page.getByRole('heading', { name: 'Classics', level: 3 })).toBeVisible()
    await expect(page.getByRole('article', { name: 'Midnight Aurora theme' })).toBeVisible()
    await expect(page).toHaveScreenshot(`${capture.theme}-${capture.viewport.width}x${capture.viewport.height}.png`, {
      animations: 'disabled',
      caret: 'hide',
      fullPage: true,
    })

    if (capture.theme === 'gemini-forward-dark') {
      const unsupportedMethod = await page.evaluate(async () => {
        const response = await fetch('/api/features', { method: 'POST', body: '{}' })
        return { status: response.status, allow: response.headers.get('allow') }
      })
      expect(unsupportedMethod).toEqual({ status: 405, allow: 'GET, HEAD' })
      expect(fixture.unexpectedRequests).toEqual(['POST /api/features'])
    } else {
      expect(fixture.unexpectedRequests).toEqual([])
    }
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
