import { expect, test } from '@playwright/test'

import {
  initialKnowledgeFixtureState,
  installKnowledgeRoutes,
  installKnowledgeShellMocks,
} from './fixtures/knowledge-editor-modes'

test.describe('knowledge navigation productivity', () => {
  test('bookmark random note metrics and named workspace survive mocked restart', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []
    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(page, state, vaultWrites, unexpectedApiTraffic)
    await page.goto('/knowledge')

    await page.getByRole('treeitem', { name: 'pages/plan.md', exact: true }).click()
    await page.getByRole('button', { name: 'Bookmarks' }).click()
    await page.getByRole('button', { name: 'Bookmark Current Target' }).click()
    await expect(page.getByRole('navigation', { name: 'Bookmarks' })).toContainText('Plan')
    await page.getByRole('button', { name: 'Random Note' }).click()
    await expect(page.getByRole('tab', { name: 'Evidence', exact: true })).toHaveAttribute('aria-selected', 'true')

    await page.getByTestId('knowledge-workspace').focus()
    await page.keyboard.press('/')
    await page.getByRole('option', { name: 'Toggle document metrics' }).click()
    await expect(page.getByRole('status')).toContainText('words')

    await page.getByRole('button', { name: 'Workspaces' }).click()
    await page.getByRole('button', { name: 'Save Current As' }).click()
    await page.getByLabel('Workspace name').fill('Research desk')
    await page.getByRole('button', { name: 'Save workspace' }).click()
    await expect.poll(() => state.namedWorkspaces.map((workspace) => workspace.name)).toContain('Research desk')
    await page.reload()
    await page.getByRole('button', { name: 'Workspaces' }).click()
    await expect(page.getByText('Research desk', { exact: true })).toBeVisible()

    expect(vaultWrites).toEqual([])
    expect(unexpectedApiTraffic).toEqual([])
  })
})
