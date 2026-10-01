import type { Page } from '@playwright/test'

import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, researchWorkbenchFixtures, test } from './fixtures/research-workbench'

// Phase 2 of the 2026-09-30 UI audit: the notebook workspace recomposition,
// proven against the production build.

const notebook = researchWorkbenchFixtures.notebook

// Same list mocks as phase0-defects.spec.ts: the generic fixture answers unmatched
// endpoints with `{}`, which crashes the notebook page into the Recovery Center.
async function mockNotebookPage(page: Page) {
  const json = (pattern: string, body: unknown) => page.route(pattern, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  await json(`**/api/notebooks/${notebook.id}`, notebook)
  await json('**/api/notes**', [])
  await json('**/api/chat/sessions**', [])
  await json(`**/api/notebooks/${notebook.id}/suggested-questions**`, { questions: [] })
  await json(`**/api/studio/notebooks/${notebook.id}/artifacts**`, [])
  await json('**/api/models', [])
  await json('**/api/models/defaults', {})
  await json('**/api/mcp', [])
  await json('**/api/mcp/web-search', { enabled: false, provider: null, tool_name: 'web_search' })
}

test.beforeEach(async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
  await mockNotebookPage(page)
})

test.describe('2a — bounded frame', () => {
  for (const viewport of [
    { label: 'desktop', width: 1440, height: 900 },
    { label: 'phone', width: 390, height: 844 },
  ]) {
    test(`the page does not scroll itself on load (${viewport.label})`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`/notebooks/${notebook.id}`)
      const heading = page.getByRole('heading', { level: 1, name: notebook.name })
      await expect(heading).toBeVisible()
      // Give the chat's scroll-to-bottom effect time to run (it used to scroll the
      // canvas ~936px on desktop and ~2,229px on a phone).
      await page.waitForTimeout(1500)

      const scroll = await page.evaluate(() => ({
        window: window.scrollY,
        canvas: document.querySelector('.dn-workspace-canvas')?.scrollTop ?? 0,
      }))
      expect(scroll).toEqual({ window: 0, canvas: 0 })
      const box = await heading.boundingBox()
      expect(box?.y ?? -1).toBeGreaterThanOrEqual(0)
      expect((box?.y ?? Infinity) + (box?.height ?? 0)).toBeLessThanOrEqual(viewport.height)
    })
  }

  test('the workspace fits the viewport and the chat composer is on screen', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)

    const main = page.getByRole('main', { name: notebook.name })
    await expect(main).toBeVisible()
    const mainBox = await main.boundingBox()
    expect((mainBox?.y ?? 0) + (mainBox?.height ?? Infinity)).toBeLessThanOrEqual(900)

    const composer = page.locator('main textarea[name="chat-message"]')
    await expect(composer).toBeInViewport()
  })

  test('the title bar holds the actions; Archive, Export and Delete are in the menu', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)

    await expect(page.getByTestId('executive-synthesis-button')).toBeVisible()
    await page.getByRole('button', { name: 'Notebook actions' }).click()
    await expect(page.getByRole('menuitem', { name: 'Archive' })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /export/i })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Delete' })).toBeVisible()
  })

  test('Guided research and the Evidence Studio band live in the Studio column', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/notebooks/${notebook.id}`)

    const studio = page.getByRole('region', { name: 'Studio', exact: true })
    await expect(studio).toBeVisible()
    await expect(studio.getByRole('region', { name: 'Guided research workspace' })).toBeAttached()
    await expect(studio.getByRole('region', { name: 'Evidence Studio artifacts' })).toBeAttached()
  })
})
