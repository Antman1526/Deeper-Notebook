import { expect, test } from '@playwright/test'

import {
  initialKnowledgeFixtureState,
  installKnowledgeRoutes,
  installKnowledgeShellMocks,
} from './fixtures/knowledge-editor-modes'

test.describe('knowledge navigation productivity', () => {
  const workspace = {
    id: 'named_knowledge_workspace:fixture_restore', name: 'Restore desk', revision: 1,
    updated_at: '2026-07-31T00:00:00Z',
  }
  const descriptor = {
    document_id: 'knowledge_engine_document:evidence', space_id: 'knowledge_engine_space:fixture',
    authority_kind: 'external_read_only', source_kind: 'obsidian', title: 'Evidence',
    relative_locator: 'pages/evidence.md', legacy_note_id: 'note:evidence', legacy_container_id: 'vault:fixture',
  }

  test('bookmark random note metrics and named workspace survive mocked restart', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []
    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(page, state, vaultWrites, unexpectedApiTraffic)
    await page.goto('/knowledge')

    const plan = page.getByRole('treeitem', { name: 'pages/plan.md', exact: true })
    await plan.focus()
    await page.keyboard.press('Enter')
    await page.getByRole('button', { name: 'Bookmarks', exact: true }).click()
    await page.getByRole('button', { name: 'Bookmark Current Target' }).click()
    await expect.poll(() => state.bookmarks.map((bookmark) => bookmark.display_label)).toContain('Plan')
    await expect(page.getByRole('region', { name: 'Bookmark library' })).toContainText('Plan')
    await page.getByRole('button', { name: 'Random Note' }).click()
    await expect(page.getByRole('tab', { name: 'Read: Evidence', exact: true })).toHaveAttribute('aria-selected', 'true')

    await page.getByTestId('knowledge-workspace').focus()
    const metricsBefore = (state.workspace.navigation as { metrics_visible?: boolean } | undefined)?.metrics_visible
    await page.keyboard.press('/')
    const metricsCommand = page.getByRole('option', { name: 'Toggle document metrics' })
    await metricsCommand.click()
    await expect.poll(() => (state.workspace.navigation as { metrics_visible?: boolean } | undefined)?.metrics_visible).not.toBe(metricsBefore)
    if ((state.workspace.navigation as { metrics_visible?: boolean } | undefined)?.metrics_visible) {
      await expect(page.getByRole('status', { name: /words/ })).toBeVisible()
    } else {
      await expect(page.getByRole('status', { name: /words/ })).not.toBeVisible()
    }

    await page.getByRole('button', { name: 'Workspaces', exact: true }).click()
    await page.getByRole('button', { name: 'Save Current As' }).click()
    await page.getByLabel('Workspace name').fill('Research desk')
    await page.getByRole('button', { name: 'Save workspace' }).click()
    await expect.poll(() => state.namedWorkspaces.map((workspace) => workspace.name)).toContain('Research desk')
    await page.reload()
    await page.getByRole('button', { name: 'Workspaces', exact: true }).click()
    await expect(page.getByText('Research desk', { exact: true })).toBeVisible()

    expect(vaultWrites).toEqual([])
    expect(unexpectedApiTraffic).toEqual([])
  })

  test('stale restore cancels unchanged then opens available targets and returns focus', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []
    state.namedWorkspaces.push(workspace)
    state.restorePlan = {
      workspace_id: workspace.id, revision: 1, active_pane_id: 'pane-restore', next_id: 2,
      panes: { 'pane-restore': { id: 'pane-restore', active_tab_id: 'tab-evidence', tabs: [
        { id: 'tab-evidence', target: { kind: 'document', document_id: descriptor.document_id }, display_label: 'Evidence', view_mode: 'reading', target_state: 'available', target_document: descriptor },
        { id: 'tab-stale', target: { kind: 'document', document_id: 'knowledge_engine_document:stale' }, display_label: 'Stale', view_mode: 'reading', target_state: 'stale', target_document: null },
      ] } },
      layout: { type: 'pane', pane_id: 'pane-restore' },
      navigation: {}, summary: { available: 1, stale: 1, unavailable: 0, missing: 0 },
    }
    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(page, state, vaultWrites, unexpectedApiTraffic)
    await page.goto('/knowledge')
    await page.getByRole('button', { name: 'Workspaces', exact: true }).click()
    const open = page.getByRole('button', { name: 'Open Restore desk' })
    await open.click()
    await expect(page.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).not.toBeVisible()
    await expect(open).toBeFocused()
    await expect(page.getByRole('tab', { name: 'Read: Evidence', exact: true })).not.toBeVisible()
    await open.click()
    await page.getByRole('button', { name: 'Open available' }).click()
    await expect(page.getByRole('tab', { name: 'Read: Evidence', exact: true })).toHaveAttribute('aria-selected', 'true')
    expect(vaultWrites).toEqual([])
    expect(unexpectedApiTraffic).toEqual([])
  })

  test('workspace revision conflict leaves the current session intact and refetches metadata', async ({ page }) => {
    const state = initialKnowledgeFixtureState()
    const vaultWrites: string[] = []
    const unexpectedApiTraffic: string[] = []
    state.namedWorkspaces.push(workspace)
    state.conflictWorkspaceUpdate = true
    await installKnowledgeShellMocks(page, unexpectedApiTraffic)
    await installKnowledgeRoutes(page, state, vaultWrites, unexpectedApiTraffic)
    await page.goto('/knowledge')
    await page.getByRole('treeitem', { name: 'pages/plan.md', exact: true }).focus()
    await page.keyboard.press('Enter')
    await page.getByRole('button', { name: 'Workspaces', exact: true }).click()
    const readsBefore = state.workspaceListReads
    await page.getByRole('button', { name: 'Replace With Current' }).click()
    await expect(page.getByText('Workspace changed elsewhere.')).toBeVisible()
    await expect.poll(() => state.workspaceListReads).toBeGreaterThan(readsBefore)
    await expect(page.getByRole('tab', { name: 'Read: Plan', exact: true })).toHaveAttribute('aria-selected', 'true')
    expect(vaultWrites).toEqual([])
    expect(unexpectedApiTraffic).toEqual([])
  })
})
