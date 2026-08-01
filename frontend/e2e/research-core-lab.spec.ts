import { expect, test } from '@playwright/test'

import {
  installStrictKnowledgeFixture,
  openExternalEvidenceNote,
} from './fixtures/knowledge-editor-modes'

const modifier = process.platform === 'darwin' ? 'Meta' : 'Control'

test.describe('Research Core Lab browser acceptance', () => {
  test('opens every research mode through its launcher and command palette without external writes', async ({ page }) => {
    const fixture = await installStrictKnowledgeFixture(page)
    await page.goto('/knowledge')

    await openExternalEvidenceNote(page)
    await expect(page.getByRole('button', { name: 'Write (Alt+2)' })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Read (Alt+1)' })).toBeEnabled()

    for (const label of ['Ask', 'Search', 'Graph', 'Podcast']) {
      await page.getByRole('button', { name: `${label} (Alt+${['Ask', 'Search', 'Graph', 'Podcast'].indexOf(label) + 3})` }).click()
      await expect(page.getByRole('tab', { name: label, exact: true })).toHaveAttribute('aria-selected', 'true')
    }

    await page.getByRole('button', { name: 'New unique note' }).click()
    await page.getByLabel('Unique note title').fill('Command draft')
    await page.getByRole('button', { name: 'Create note' }).click()
    for (const label of ['Read', 'Write', 'Ask', 'Search', 'Graph', 'Podcast']) {
      await page.getByTestId('knowledge-workspace').focus()
      await page.keyboard.press('/')
      const palette = page.getByRole('dialog', { name: 'Quick actions' })
      await palette.getByRole('combobox').fill(label.toLowerCase())
      await palette.getByRole('option', { name: label }).click()
      await expect(palette).toBeHidden()
    }

    expect(fixture.externalMutationRequests).toEqual([])
    expect(fixture.unexpectedRequests).toEqual([])
  })

  test('preserves an app-owned overlay draft across split, current-session reload, named restore, and keyboard drawers', async ({ page }) => {
    const fixture = await installStrictKnowledgeFixture(page)
    await page.setViewportSize({ width: 900, height: 800 })
    await page.goto('/knowledge')

    await page.getByRole('button', { name: 'New unique note' }).click()
    await page.getByLabel('Unique note title').fill('Research draft')
    await page.getByRole('button', { name: 'Create note' }).click()
    await expect(page.getByRole('tab', { name: 'Research draft', exact: true })).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('button', { name: 'Write (Alt+2)' }).click()
    await page.getByRole('textbox').last().fill('# Research draft\n\nUnsaved overlay evidence')

    await page.getByRole('button', { name: 'Split pane right' }).click()
    await expect(page.getByRole('tab', { name: 'Research draft', exact: true })).toHaveCount(2)
    await page.reload()
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
    await page.getByRole('button', { name: 'Close sources drawer' }).click()
    await expect(sourcesDrawer).toBeFocused()

    const intelligenceDrawer = page.getByRole('button', { name: 'Open intelligence drawer' })
    await intelligenceDrawer.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('complementary', { name: 'Intelligence' })).toBeVisible()
    await page.getByRole('button', { name: 'Close intelligence drawer' }).click()
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
})
