import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, test } from './fixtures/research-workbench'

const viewports = [
  { label: 'phone', width: 320, height: 740 },
  { label: 'tablet', width: 768, height: 1024 },
] as const

for (const viewport of viewports) {
  test(`rollback Focus mode keeps legacy content usable at ${viewport.label} width`, async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })

    await installLuminousFolioFixture(page, { theme: 'archive-paper' })
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/notebooks')

    await expect(page.locator('.dn-legacy-shell')).toBeVisible()
    await expect(page.locator('.dn-legacy-shell > .app-sidebar')).toBeVisible()
    await page.getByRole('button', { name: 'Enter Focus mode' }).click()

    await expect(page.locator('html')).toHaveAttribute('data-dn-focus-mode', 'true')
    await expect(page.getByRole('button', { name: 'Exit Focus mode' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()

    const sidebar = page.locator('.dn-legacy-shell > .app-sidebar')
    await expect.poll(() => sidebar.evaluate(element => element.getBoundingClientRect().width)).toBeLessThanOrEqual(48)
    await expect.poll(() => page.locator('.dn-legacy-shell > main').evaluate(element => element.getBoundingClientRect().width)).toBeGreaterThan(viewport.width - 64)

    const sourceLink = page.locator('a[href="/sources"]').first()
    await sourceLink.focus()
    await expect(sourceLink).toBeFocused()
    expect(consoleErrors).toEqual([])
  })
}
