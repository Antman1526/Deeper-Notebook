import { expect, test, type Page } from '@playwright/test'

import {
  fulfillKnowledgeRequest,
  initialKnowledgeFixtureState,
  installKnowledgeShellMocks,
  type KnowledgeFixtureState,
} from './fixtures/knowledge-editor-modes'

const testOnlyLegacyVaultPath = `/${['api', 'onp', 'vaults'].join('/')}`
const unknownPageDescendantPath =
  '/api/deeper-notebook/vaults/vault%3Afixture/pages/note%3Aplan/unknown'

async function installKnowledgeRoutes(
  page: Page,
  state: KnowledgeFixtureState,
  vaultWrites: string[],
  unexpectedApiTraffic: string[],
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

    await fulfillKnowledgeRequest(route, state, unexpectedApiTraffic)
  })
}

test.describe('knowledge editor modes', () => {
  test('persists Live Preview without writing to the vault', async ({ page }) => {
    const state: KnowledgeFixtureState = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []

    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(
      page,
      state,
      vaultWrites,
      unexpectedApiTraffic,
    )

    await page.goto('/knowledge')
    const modifier = process.platform === 'darwin' ? 'Meta' : 'Control'
    await page.getByTestId('knowledge-workspace').focus()
    await page.keyboard.press(`${modifier}+o`)
    const switcher = page.getByRole('dialog', { name: 'Quick switcher' })
    await switcher.getByRole('combobox').fill('plan')
    await switcher.getByRole('option', { name: 'plan pages/plan.md · Fixture vault', exact: true }).click()
    await page.getByRole('button', { name: 'Live Preview', exact: true }).click()

    const livePreview = page.locator(
      '[aria-label="Plan live preview"][aria-readonly="true"]',
    )
    await expect(livePreview).toBeVisible()

    await expect
      .poll(() => JSON.stringify(state.workspace))
      .toContain('"render_mode":"live-preview"')

    await page.reload()

    await expect(livePreview).toBeVisible()
    await expect(livePreview).toHaveAttribute('aria-readonly', 'true')
    expect(vaultWrites).toEqual([])
    expect(unexpectedApiTraffic).toEqual([])
  })

  test('records collection-level vault writes', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []

    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(
      page,
      state,
      vaultWrites,
      unexpectedApiTraffic,
    )
    await page.goto('/knowledge')

    const status = await page.evaluate(async () => {
      const response = await fetch('/api/deeper-notebook/vaults', {
        method: 'POST',
      })
      return response.status
    })

    expect(status).toBe(405)
    expect(vaultWrites).toEqual(['POST /api/deeper-notebook/vaults'])
    expect(unexpectedApiTraffic).toEqual([
      'POST /api/deeper-notebook/vaults',
    ])
  })

  test('rejects off-namespace and wrong-method API traffic', async ({ page }) => {
    const unexpectedApiTraffic: string[] = []

    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await page.goto('/knowledge')
    await expect(page.getByTestId('knowledge-workspace')).toBeVisible()

    const statuses = await page.evaluate(async (legacyVaultPath) => {
      const legacyVaultResponse = await fetch(legacyVaultPath, {
        method: 'POST',
      })
      const wrongMethodResponse = await fetch('/api/notebooks', {
        method: 'POST',
      })
      return [legacyVaultResponse.status, wrongMethodResponse.status]
    }, testOnlyLegacyVaultPath)

    expect(statuses).toEqual([501, 405])
    expect(
      unexpectedApiTraffic.filter((entry) => !entry.startsWith('GET /api/deeper-notebook/')),
    ).toEqual([`POST ${testOnlyLegacyVaultPath}`, 'POST /api/notebooks'])
  })

  test('rejects unknown canonical page descendants', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []

    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(
      page,
      state,
      vaultWrites,
      unexpectedApiTraffic,
    )
    await page.goto('/knowledge')

    const status = await page.evaluate(async (unknownPath) => {
      const response = await fetch(unknownPath)
      return response.status
    }, unknownPageDescendantPath)

    expect(status).toBe(501)
    expect(vaultWrites).toEqual([])
    expect(unexpectedApiTraffic).toEqual([
      `GET ${unknownPageDescendantPath}`,
    ])
  })
})
