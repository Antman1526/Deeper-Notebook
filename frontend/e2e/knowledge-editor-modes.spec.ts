import { expect, test } from '@playwright/test'

import {
  fulfillKnowledgeRequest,
  initialKnowledgeFixtureState,
  installKnowledgeShellMocks,
  type KnowledgeFixtureState,
} from './fixtures/knowledge-editor-modes'

test.describe('knowledge editor modes', () => {
  test('persists Live Preview without writing to the vault', async ({ page }) => {
    const state: KnowledgeFixtureState = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []

    await installKnowledgeShellMocks(page)
    await page.route('**/api/deeper-notebook/**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())

      if (
        url.pathname.includes('/api/deeper-notebook/vaults/') &&
        !['GET', 'HEAD'].includes(request.method())
      ) {
        vaultWrites.push(`${request.method()} ${url.pathname}`)
      }

      await fulfillKnowledgeRequest(route, state)
    })

    await page.goto('/knowledge')
    await page.getByRole('treeitem', { name: 'pages/plan.md', exact: true }).click()
    await page.getByRole('button', { name: 'Live Preview', exact: true }).click()

    const livePreview = page.locator(
      '[aria-label="Plan live preview"][aria-readonly="true"]',
    )
    await expect(livePreview).toBeVisible()

    await expect
      .poll(() => JSON.stringify(state.workspace))
      .toContain('"view_mode":"live-preview"')

    await page.reload()

    await expect(livePreview).toBeVisible()
    await expect(livePreview).toHaveAttribute('aria-readonly', 'true')
    expect(vaultWrites).toEqual([])
  })
})
