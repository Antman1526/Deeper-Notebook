import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, test } from './fixtures/research-workbench'

const viewports = [
  { label: 'phone', width: 320, height: 740 },
  { label: 'tablet', width: 768, height: 1024 },
  { label: 'laptop', width: 1024, height: 800 },
  { label: 'desktop', width: 1440, height: 900 },
] as const

for (const viewport of viewports) {
  test(`Focus mode keeps route and keyboard paths available at ${viewport.label} width`, async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })

    await installLuminousFolioFixture(page, { theme: 'archive-paper' })
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/notebooks')
    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeAttached()

    const enter = page.getByRole('button', { name: 'Enter Focus mode' })
    await expect(enter).toBeVisible()
    await enter.click()

    await expect(page.locator('html')).toHaveAttribute('data-dn-focus-mode', 'true')
    await expect(page.getByRole('button', { name: 'Exit Focus mode' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()

    // v0.8.130 — Phase 3b: below 1024px the rail is a sheet behind the Menu button, so
    // the keyboard route path goes through it.
    if (viewport.width < 1024) {
      const menu = page.getByRole('button', { name: 'Menu' })
      await menu.focus()
      await page.keyboard.press('Enter')
      await expect(menu).toHaveAttribute('aria-expanded', 'true')
    }
    const navigationLink = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: /Sources/ }).first()
    await expect(navigationLink).toBeAttached()
    await navigationLink.focus()
    await expect(navigationLink).toBeFocused()

    const commandTrigger = page.getByRole('button', { name: 'Open command palette' })
    await commandTrigger.focus()
    await expect(commandTrigger).toBeFocused()

    expect(consoleErrors).toEqual([])
  })
}
