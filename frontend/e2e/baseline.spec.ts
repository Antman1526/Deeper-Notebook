import { expect, test } from './fixtures/research-workbench'

test('opens the deterministic research notebook', async ({ page, researchWorkbench }) => {
  await page.goto('/notebooks')

  await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()
  await expect(page.getByText(researchWorkbench.notebook.name)).toBeVisible()
  await expect(page.getByText(researchWorkbench.notebook.description)).toBeVisible()
})
