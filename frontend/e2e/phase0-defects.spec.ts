import type { Page } from '@playwright/test'

import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, researchWorkbenchFixtures, test } from './fixtures/research-workbench'

// Phase 0 of the 2026-09-30 UI audit, proven against the PRODUCTION BUILD (the
// styling defects below only exist after Tailwind compiles the stylesheet, so
// jsdom cannot see them). Each test names the audit item it guards.

const notebook = researchWorkbenchFixtures.notebook

// The generic fixture answers unmatched endpoints with `{}`, and the notebook
// page maps over several list responses, so it crashes into the app's Recovery
// Center (also on the unmodified baseline). These are the same list mocks the
// repo's all-screen audit spec installs for this page.
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
}

test.beforeEach(async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'gemini-forward-light' })
  await mockNotebookPage(page)
})

test.describe('build-level Tailwind config (T0-1, T0-2)', () => {
  test('`prose` produces real typography rules (T0-1)', async ({ page }) => {
    await page.goto('/notebooks')

    const styles = await page.evaluate(() => {
      const host = document.createElement('div')
      host.className = 'prose'
      host.innerHTML = '<p id="p">Body</p><h2 id="h2">Heading</h2><p><code id="code">x</code></p>'
      document.body.appendChild(host)
      const size = (id: string) => parseFloat(getComputedStyle(document.getElementById(id)!).fontSize)
      return {
        body: size('p'),
        heading: size('h2'),
        weight: Number(getComputedStyle(document.getElementById('h2')!).fontWeight),
        codeBefore: getComputedStyle(document.getElementById('code')!, '::before').content,
      }
    })

    expect(styles.heading).toBeGreaterThan(styles.body)
    expect(styles.weight).toBeGreaterThanOrEqual(600)
    // The plugin's inline-code backticks are switched off.
    expect(['none', 'normal']).toContain(styles.codeBefore)
  })

  test('`dark:` follows the theme class, not the OS colour scheme (T0-2)', async ({ page }) => {
    // Light theme selected, but the operating system asks for dark.
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.goto('/notebooks')

    const colors = await page.evaluate(() => {
      const probe = document.createElement('p')
      probe.className = 'dark:text-amber-400'
      document.body.appendChild(probe)
      const light = getComputedStyle(probe).color
      document.documentElement.classList.add('dark')
      const dark = getComputedStyle(probe).color
      document.documentElement.classList.remove('dark')
      return { light, dark }
    })

    expect(colors.dark).not.toBe(colors.light)
  })
})

test.describe('elevation tokens (T0-8)', () => {
  test('dark themes get their own shadow values, not Tailwind\'s near-invisible default', async ({ page }) => {
    await page.goto('/notebooks')

    const shadows = await page.evaluate(() => {
      const probe = document.createElement('div')
      probe.className = 'shadow-md'
      document.body.appendChild(probe)
      const light = getComputedStyle(probe).boxShadow
      document.documentElement.classList.add('dark')
      const dark = getComputedStyle(probe).boxShadow
      document.documentElement.classList.remove('dark')
      return { light, dark }
    })

    // Light keeps the project's slate-tinted shadow; dark gets a real, stronger one.
    expect(shadows.light).toContain('rgba(15, 23, 42')
    expect(shadows.dark).toContain('rgba(0, 0, 0, 0.5)')
    expect(shadows.dark).not.toBe(shadows.light)
  })
})

test.describe('shell (T0-3, T0-4, T0-9)', () => {
  test('the Create button shows its icon (T0-3)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    const icon = page.locator('.dn-dock-create > button svg').first()
    await expect(icon).toBeVisible()
    const box = await icon.boundingBox()
    expect(box?.width ?? 0).toBeGreaterThan(8)
  })

  test('the active navigation link fills its row (T0-4)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    const link = page.locator('.dn-navigator-link.is-active')
    await expect(link).toBeVisible()
    const linkWidth = (await link.boundingBox())?.width ?? 0
    const rowWidth = (await link.locator('xpath=..').boundingBox())?.width ?? Infinity
    expect(linkWidth).toBeGreaterThanOrEqual(rowWidth - 2)
  })

  test('the command bar fits a phone and keeps the product name (T0-9)', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/notebooks')

    const focus = page.getByRole('button', { name: 'Enter Focus mode' })
    await expect(focus).toBeVisible()
    expect((await focus.boundingBox())?.x ?? 0).toBeGreaterThanOrEqual(0)
    const right = (await focus.boundingBox())!.x + (await focus.boundingBox())!.width
    expect(right).toBeLessThanOrEqual(390)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    expect((await page.locator('.dn-command-title').boundingBox())?.width ?? 0).toBeGreaterThan(40)
  })
})

test.describe('notebook list (T0-6)', () => {
  test('a notebook opens with the keyboard', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    const link = page.getByRole('link', { name: notebook.name })
    await link.focus()
    await expect(link).toBeFocused()
    await page.keyboard.press('Enter')
    // A generous timeout: navigation has taken >10s when the machine is saturated.
    await expect(page).toHaveURL(new RegExp(`/notebooks/${notebook.id}`), { timeout: 30_000 })
  })

  test('clicking anywhere on the card still opens it', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')
    await expect(page.getByRole('link', { name: notebook.name })).toBeVisible()

    const card = page.locator('[data-slot="card"]').first()
    const box = (await card.boundingBox())!
    const center = async (locator: ReturnType<typeof page.locator>) => {
      const rect = (await locator.boundingBox())!
      return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
    }
    const points = {
      'the title': await center(card.locator('[data-slot="card-title"]')),
      'the description': await center(page.getByText(notebook.description)),
      'the updated line': await center(page.getByText(/^Updated /)),
      'the empty bottom corner': { x: box.x + box.width - 16, y: box.y + box.height - 12 },
    }

    for (const [where, point] of Object.entries(points)) {
      await page.mouse.click(point.x, point.y)
      await expect(page, `click on ${where}`).toHaveURL(new RegExp(`/notebooks/${notebook.id}`), { timeout: 30_000 })
      await page.goBack()
      await expect(page.getByRole('link', { name: notebook.name })).toBeVisible()
    }
  })

  test('the actions menu still opens without navigating', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    await page.getByRole('button', { name: `Actions for ${notebook.name}` }).click()
    await expect(page.getByRole('menuitem').first()).toBeVisible()
    await expect(page).toHaveURL(/\/notebooks$/)
  })

  test('a long notebook name still truncates with an ellipsis', async ({ page }) => {
    const longName = 'An unusually long notebook title that keeps going well past the width of a single card'
    await page.route('**/api/notebooks**', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      await route.fulfill({ json: [{ ...notebook, name: longName }] })
    })
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    const title = page.locator('[data-slot="card-title"]').first()
    await expect(title).toContainText('An unusually long')
    const metrics = await title.evaluate((element) => ({
      overflow: getComputedStyle(element).textOverflow,
      truncated: element.scrollWidth > element.clientWidth,
    }))
    expect(metrics).toEqual({ overflow: 'ellipsis', truncated: true })
  })
})

test.describe('notebook layout toggle', () => {
  test('switches notebooks between grid and list and remembers the choice', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    const grid = page.getByRole('button', { name: 'Grid view' })
    const list = page.getByRole('button', { name: 'List view' })
    await expect(grid).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('[data-slot="card"]').first()).toBeVisible()

    await list.click()
    await expect(list).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('[data-slot="card"]')).toHaveCount(0)
    await expect(page.getByRole('link', { name: notebook.name })).toBeVisible()

    await page.reload()
    await expect(page.getByRole('button', { name: 'List view' })).toHaveAttribute('aria-pressed', 'true')
  })
})

test.describe('copy and wrapping (T0-11, T0-12)', () => {
  test('the Add Source dialog states the AI-processing sentence once', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/notebooks')

    await page.locator('.dn-dock-create > button').click()
    await page.getByRole('menuitem', { name: /source/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()

    await expect(page.getByText('Content will be processed and analyzed by AI.')).toHaveCount(1)
  })

  test('the notebook header spaces its bullet and wraps words whole', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/notebooks/${notebook.id}`)

    await expect(page.getByText(/ago • Updated /)).toBeVisible()
    // `break-all` split words mid-word; `overflow-wrap: anywhere` only splits a
    // word that cannot fit on a line of its own and still lets the row shrink.
    const description = page.getByRole('button', { name: notebook.description })
    expect(await description.evaluate((element) => getComputedStyle(element).overflowWrap)).toBe('anywhere')
    expect(await description.evaluate((element) => getComputedStyle(element).wordBreak)).not.toBe('break-all')
  })
})

test.describe('Studio layout (T0-10)', () => {
  test('the output-mode panel stacks below the source desk on a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/studio')

    const primary = page.locator('[data-dn-folio-variant="evidence-studio"] > [data-dn-folio-primary]')
    const secondary = page.locator('[data-dn-folio-variant="evidence-studio"] > [data-dn-folio-secondary]')
    await expect(primary).toBeVisible()
    const a = (await primary.boundingBox())!
    const b = (await secondary.boundingBox())!
    expect(a.width).toBeGreaterThan(280)
    expect(b.y).toBeGreaterThanOrEqual(a.y + a.height - 1)
  })
})
