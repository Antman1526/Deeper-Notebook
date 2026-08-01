import { expect, test, type Page } from '@playwright/test'

import {
  installStrictKnowledgeFixture,
  openExternalEvidenceNote,
} from './fixtures/knowledge-editor-modes'

const modifier = process.platform === 'darwin' ? 'Meta' : 'Control'

const modeShortcuts = { Read: 1, Write: 2, Ask: 3, Search: 4, Graph: 5, Podcast: 6 } as const

async function installRoutePlanMocks(page: Page) {
  await page.route('**/api/local-models/settings', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        model_dir: 'synthetic-library', execution_policy: 'strict_local', compute_profile: 'balanced',
        local_model_memory_limit_bytes: null, role_overrides: {}, trusted_external_model_roots: [],
      }),
    })
  })
  await page.route('**/api/local-models/route-plan', async (route) => {
    const request = route.request().postDataJSON() as { role: string }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        role: request.role, outcome: 'ready', selected_model_id: `synthetic-${request.role}`,
        selected_provider: 'mlx', resource_tier: 'light', selection_source: 'automatic',
        route_reason: `Synthetic ${request.role} route reason`, escalation_model_ids: [],
        blocked_reason: null, selected_fingerprint: 'synthetic-fingerprint', selected_measurements: { latency_ms: 10 },
      }),
    })
  })
}

test.describe('Research Core Lab browser acceptance', () => {
  test('opens every research mode through its launcher and command palette without external writes', async ({ page }) => {
    const fixture = await installStrictKnowledgeFixture(page)
    await installRoutePlanMocks(page)
    await page.goto('/knowledge')

    await openExternalEvidenceNote(page)
    await expect(page.getByRole('button', { name: 'Write (Alt+2)' })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Read (Alt+1)' })).toBeEnabled()

    for (const label of ['Read', 'Ask', 'Search', 'Graph', 'Podcast'] as const) {
      await page.getByRole('button', { name: `${label} (Alt+${modeShortcuts[label]})` }).click()
      await expect(page.getByRole('tab', { selected: true })).toHaveAttribute('aria-label', new RegExp(`^${label}:`))
    }

    await page.getByRole('button', { name: 'New unique note' }).click()
    await page.getByLabel('Unique note title').fill('Command draft')
    await page.getByRole('button', { name: 'Create note' }).click()
    for (const label of ['Read', 'Write', 'Ask', 'Search', 'Graph', 'Podcast'] as const) {
      await page.getByRole('button', { name: `${label} (Alt+${modeShortcuts[label]})` }).click()
      await expect(page.getByRole('tab', { selected: true })).toHaveAttribute('aria-label', new RegExp(`^${label}:`))
    }
    for (const label of ['Read', 'Write', 'Ask', 'Search', 'Graph', 'Podcast'] as const) {
      await page.getByTestId('knowledge-workspace').focus()
      await page.keyboard.press('/')
      const palette = page.getByRole('dialog', { name: 'Quick actions' })
      await palette.getByRole('combobox').fill(label.toLowerCase())
      await palette.getByRole('option', { name: label }).click()
      await expect(palette).toBeHidden()
      await expect(page.getByRole('tab', { selected: true })).toHaveAttribute('aria-label', new RegExp(`^${label}:`))
    }

    expect(fixture.externalMutationRequests).toEqual([])
    expect(fixture.unexpectedRequests).toEqual([])
  })

  test('preserves an app-owned overlay draft across split, current-session reload, named restore, and keyboard drawers', async ({ page }) => {
    const fixture = await installStrictKnowledgeFixture(page)
    await installRoutePlanMocks(page)
    await page.setViewportSize({ width: 900, height: 800 })
    await page.goto('/knowledge')

    await page.getByRole('button', { name: 'New unique note' }).click()
    await page.getByLabel('Unique note title').fill('Research draft')
    await page.getByRole('button', { name: 'Create note' }).click()
    await expect(page.getByRole('tab', { name: 'Research draft', exact: true })).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('button', { name: 'Write (Alt+2)' }).click()
    await page.getByRole('textbox').last().fill('# Research draft\n\nUnsaved overlay evidence')

    await page.getByRole('button', { name: 'Split pane right' }).click()
    await expect(page.getByRole('region', { name: /Knowledge pane/ })).toHaveCount(2)
    await page.getByRole('button', { name: 'Search (Alt+4)' }).click()
    await expect(page.getByRole('tab', { selected: true })).toHaveAttribute('aria-label', /^Search:/)
    await expect.poll(() => JSON.stringify(fixture.state.workspace)).toContain('"type":"split"')
    await expect.poll(() => JSON.stringify(fixture.state.workspace)).toContain('"mode":"write"')
    await expect.poll(() => JSON.stringify(fixture.state.workspace)).toContain('"mode":"search"')
    await page.reload()
    await page.getByRole('tab', { name: 'Write: Research draft' }).first().click()
    await expect(page.getByText('Unsaved overlay evidence', { exact: false })).toBeVisible()

    await page.getByRole('button', { name: 'Workspaces', exact: true }).click()
    await page.getByRole('button', { name: 'Save Current As' }).click()
    await page.getByLabel('Workspace name').fill('Research Core restore')
    await page.getByRole('button', { name: 'Save workspace' }).click()
    await page.reload()
    await page.getByRole('button', { name: 'Workspaces', exact: true }).click()
    await page.getByRole('button', { name: 'Open Research Core restore' }).click()
    await expect(page.getByText('Unsaved overlay evidence', { exact: false })).toBeVisible()

    const sourcesDrawer = page.getByRole('button', { name: 'Open sources drawer' })
    await sourcesDrawer.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('complementary', { name: 'Sources' })).toBeVisible()
    await page.getByRole('button', { name: 'Close sources drawer' }).focus()
    await page.keyboard.press('Enter')
    await expect(sourcesDrawer).toBeFocused()

    const intelligenceDrawer = page.getByRole('button', { name: 'Open intelligence drawer' })
    await intelligenceDrawer.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('complementary', { name: 'Intelligence' })).toBeVisible()
    await page.getByRole('button', { name: 'Close intelligence drawer' }).focus()
    await page.keyboard.press('Enter')
    await expect(intelligenceDrawer).toBeFocused()

    expect(fixture.externalMutationRequests).toEqual([])
    expect(fixture.unexpectedRequests).toEqual([])
  })

  test('keeps command route reasons inspectable while an unavailable local route disables Ask', async ({ page }) => {
    const fixture = await installStrictKnowledgeFixture(page)
    await page.route('**/api/local-models/health', async (route) => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ overall: 'unhealthy', models: [] }) })
    })
    await page.goto('/knowledge')
    await expect(page.getByRole('button', { name: 'Ask (Alt+3)' })).toBeDisabled()

    await page.getByTestId('knowledge-workspace').focus()
    await page.keyboard.press(`${modifier}+k`)
    const ask = page.getByRole('option', { name: 'Ask' })
    await expect(ask).toBeDisabled()
    await expect(ask).toContainText('Local model readiness is unavailable')
    expect(fixture.externalMutationRequests).toEqual([])
  })

  test('renders the returned Ask and Search route-plan reasons without executing work', async ({ page }) => {
    const fixture = await installStrictKnowledgeFixture(page)
    await installRoutePlanMocks(page)
    await page.goto('/knowledge')

    await page.getByRole('button', { name: 'Ask (Alt+3)' }).click()
    await expect(page.getByTestId('route-plan-research-chat-route')).toContainText('Synthetic research_chat route reason')
    await page.getByRole('button', { name: 'Search (Alt+4)' }).click()
    await expect(page.getByTestId('route-plan-embedding-route')).toContainText('Synthetic embedding_retrieval route reason')
    expect(fixture.externalMutationRequests).toEqual([])
    expect(fixture.unexpectedRequests).toEqual([])
  })
})
