import { expect, test } from './fixtures/research-workbench'

const viewports = [
  { label: 'mobile', width: 390, height: 844, compact: true },
  // v0.8.130 — Phase 3b: below 1024px the V2 rail is a sheet behind the Menu button.
  { label: 'tablet', width: 768, height: 1024, compact: true },
  { label: 'laptop', width: 1280, height: 800, compact: false },
  { label: 'desktop', width: 1440, height: 900, compact: false },
] as const

for (const viewport of viewports) {
  test(`Luminous notebook shell stays navigable at ${viewport.label} width`, async ({ page, researchWorkbench }) => {
    void researchWorkbench
    const consoleErrors: string[] = []
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })

    await page.context().addCookies([
      { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
      { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
    ])
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/notebooks')

    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()
    await expect(page.locator('main')).toHaveCount(1)
    await expect(page.locator('h1')).toHaveCount(1)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

    const dismissTip = page.getByRole('button', { name: 'Got it' })
    if (await dismissTip.isVisible()) await dismissTip.click()

    // v0.8.130 — Phase 3b: one rail replaces the notebook index.
    const notebookIndex = page.getByRole('navigation', { name: 'Primary' })
    // v0.8.130 — the placeholder Context lens is no longer mounted in the V2 shell (it
    // was static copy that reserved a 320px rail, or floated a button over content).
    await expect(page.getByRole('complementary', { name: 'Context lens' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Context lens' })).toHaveCount(0)
    if (viewport.compact) {
      await page.getByRole('button', { name: 'Menu' }).click()
      await expect(notebookIndex).toBeVisible()
    } else {
      await expect(notebookIndex).toBeVisible()
    }

    expect(consoleErrors).toEqual([])
  })
}
