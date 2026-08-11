import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, test } from './fixtures/research-workbench'

test('Research Core retains the outer navigator while Focus is active at compact desktop width', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await installLuminousFolioFixture(page, { theme: 'research-core-light' })
  await page.setViewportSize({ width: 1024, height: 800 })
  await page.goto('/knowledge')

  await expect(page.getByTestId('knowledge-workspace')).toBeVisible()
  await page.getByRole('button', { name: 'Enter Focus mode' }).click()

  await expect(page.locator('html')).toHaveAttribute('data-dn-focus-mode', 'true')
  const notebookIndex = page.getByRole('navigation', { name: 'Notebook index' })
  await expect(notebookIndex).toBeVisible()
  const sourceLink = notebookIndex.getByRole('link', { name: /Sources/ }).first()
  await sourceLink.focus()
  await expect(sourceLink).toBeFocused()
  expect(consoleErrors).toEqual([])
})
