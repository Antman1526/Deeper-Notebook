import { expect, test } from './fixtures/research-workbench'

const viewports = [
  { label: 'mobile', width: 390, height: 844, compact: true },
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

    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/notebooks')

    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()
    await expect(page.locator('main')).toHaveCount(1)
    await expect(page.locator('h1')).toHaveCount(1)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

    const dismissTip = page.getByRole('button', { name: 'Got it' })
    if (await dismissTip.isVisible()) await dismissTip.click()

    const notebookIndex = page.getByRole('navigation', { name: 'Notebook index' })
    const contextLens = page.getByRole('complementary', { name: 'Context lens' })
    if (viewport.compact) {
      await page.getByRole('button', { name: 'Notebook index' }).click()
      await expect(notebookIndex).toBeVisible()
      await page.getByRole('button', { name: 'Context lens' }).click()
      await expect(contextLens).toBeVisible()
    } else {
      await expect(notebookIndex).toBeVisible()
      await expect(contextLens).toBeVisible()
    }

    expect(consoleErrors).toEqual([])
  })
}
