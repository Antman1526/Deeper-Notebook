import { expect, test, type Page } from '@playwright/test'

import {
  fulfillKnowledgeRequest,
  initialKnowledgeFixtureState,
  installKnowledgeShellMocks,
  type KnowledgeFixtureState,
} from './fixtures/knowledge-editor-modes'

async function installKnowledgeRoutes(
  page: Page,
  state: KnowledgeFixtureState,
  vaultWrites: string[],
): Promise<void> {
  await page.route('**/api/deeper-notebook/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (
      url.pathname.includes('/api/deeper-notebook/vaults') &&
      !['GET', 'HEAD'].includes(request.method())
    ) {
      vaultWrites.push(`${request.method()} ${url.pathname}`)
    }

    await fulfillKnowledgeRequest(route, state)
  })
}

test.describe('knowledge editor modes', () => {
  test('persists Live Preview without writing to the vault', async ({ page }) => {
    const state: KnowledgeFixtureState = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []

    await installKnowledgeShellMocks(page)
    await installKnowledgeRoutes(page, state, vaultWrites)

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

  test('records collection-level vault writes', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []

    await installKnowledgeShellMocks(page)
    await installKnowledgeRoutes(page, state, vaultWrites)
    await page.goto('/knowledge')

    const status = await page.evaluate(async () => {
      const response = await fetch('/api/deeper-notebook/vaults', {
        method: 'POST',
      })
      return response.status
    })

    expect(status).toBe(200)
    expect(vaultWrites).toEqual(['POST /api/deeper-notebook/vaults'])
  })
})
