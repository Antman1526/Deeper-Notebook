import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, researchWorkbenchFixtures, test } from './fixtures/research-workbench'

test('compact shell keeps the focus control clear of the command title', async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/notebooks')

  const title = page.locator('.dn-command-title')
  const focusControl = page.getByRole('button', { name: 'Enter Focus mode' })
  await expect(title).toBeVisible()
  await expect(focusControl).toBeVisible()

  const boxes = await Promise.all([title.boundingBox(), focusControl.boundingBox()])
  expect(boxes[0]).not.toBeNull()
  expect(boxes[1]).not.toBeNull()
  const [titleBox, focusBox] = boxes as [{ x: number; y: number; width: number; height: number }, { x: number; y: number; width: number; height: number }]
  const overlaps = titleBox.x < focusBox.x + focusBox.width
    && titleBox.x + titleBox.width > focusBox.x
    && titleBox.y < focusBox.y + focusBox.height
    && titleBox.y + titleBox.height > focusBox.y
  expect(overlaps).toBe(false)
})

const routeInventory = [
  '/settings/local-models',
  '/settings/mcp',
  '/settings/launcher-prefs',
  '/',
  '/capture',
  '/notebooks',
  '/notebooks/notebook-fixture-001',
  '/sources',
  '/sources/source-fixture-001',
  '/knowledge',
  '/search',
  '/studio',
  '/study',
  '/transformations',
  '/podcasts',
  '/podcasts/studio',
  '/advanced',
  '/settings',
  '/settings/api-keys',
] as const

const canonicalViewports = [
  { width: 320, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
] as const

const sourceListFixture = {
  id: 'source-fixture-001',
  title: 'Deterministic source',
  topics: [],
  provenance: { origin: 'browser fixture' },
  source_type: 'text',
  notebook_count: 1,
  is_shared: false,
  asset: null,
  embedded: false,
  embedded_chunks: 0,
  insights_count: 0,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
  file_available: true,
  extracted_char_count: 51,
  extraction_quality: 'ok',
  status: 'completed',
} as const

const sourceDetailFixture = {
  ...sourceListFixture,
  full_text: 'The fixture source states a fixed research finding.',
  notebooks: ['notebook-fixture-001'],
} as const

test('tracked dashboard routes preserve landmarks, bounds, and hermetic browser state', async ({ page }) => {
  test.setTimeout(240_000)
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => {
    const url = new URL(request.url())
    if (!url.hostname.endsWith('127.0.0.1') && !url.hostname.endsWith('localhost')) {
      externalRequests.push(request.url())
    }
  })

  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.route('**/api/notebooks/notebook-fixture-001', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(researchWorkbenchFixtures.notebook) })
  })
  await page.route('**/api/notes**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/chat/sessions**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/notebooks/notebook-fixture-001/suggested-questions**', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ questions: [] }) })
  })
  await page.route('**/api/studio/notebooks/notebook-fixture-001/artifacts**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/models', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/models/defaults', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) })
  })
  await page.route('**/api/credentials/status', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ configured: {}, source: {}, encryption_configured: true }),
    })
  })
  await page.route('**/api/credentials/env-status', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) })
  })
  await page.route('**/api/credentials', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/credentials/detect-osaurus', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ running: false, port: 1337, models_registered: 0, credential_id: null, detail: 'not running' }),
    })
  })
  await page.route('**/api/deeper-notebook/gmail/status', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ connected: false, configured: false }),
    })
  })
  await page.route('**/api/local-models/inventory', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ model_dir: 'redacted', available: false, models: [] }),
    })
  })
  await page.route('**/api/local-models/settings', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        model_dir: 'redacted',
        execution_policy: 'strict_local',
        compute_profile: 'balanced',
        local_model_memory_limit_bytes: null,
        role_overrides: {},
        trusted_external_model_roots: [],
      }),
    })
  })
  await page.route('**/api/local-models/health', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ overall: 'healthy', models: [] }) })
  })
  await page.route('**/api/local-models/recommendations', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ recommendations: [] }) })
  })
  await page.route('**/api/local-models/downloads', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ downloads: [] }) })
  })
  await page.route('**/api/mcp', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/mcp/recommendations', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ recommendations: [] }) })
  })
  await page.route(/\/api\/sources\/source-fixture-001(?:\?|$)/, async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(sourceDetailFixture) })
  })
  await page.route('**/api/sources/source-fixture-001/insights**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/sources/source-fixture-001/chat/sessions**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/transformations**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/study/cards/due', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/podcasts/episodes', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route(/\/api\/sources(?:\?|$)/, async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([sourceListFixture]) })
  })
  await page.route('**/api/capture/roots', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route('**/api/capture/items', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  for (const route of routeInventory) {
    for (const viewport of canonicalViewports) {
      await page.setViewportSize(viewport)
      await page.goto(route)
      await expect(page.locator('body')).toBeVisible()
      await expect(page.locator('h1'), `${route} ${viewport.width}px heading`).toHaveCount(1)
      await expect(page.locator('main'), `${route} ${viewport.width}px main`).toHaveCount(1)
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await expect.poll(
        () => page.locator('main').evaluate(element => element.getBoundingClientRect().width > 0),
        `${route} ${viewport.width}px main width`,
      ).toBe(true)

      const duplicateIds = await page.evaluate(() => {
        const ids = Array.from(document.querySelectorAll('[id]'), element => element.id)
        return ids.filter((id, index) => id && ids.indexOf(id) !== index)
      })
      expect(duplicateIds, `${route} ${viewport.width}px duplicate IDs`).toEqual([])

      const clippedControls = await page.evaluate(() => {
        const controls = Array.from(document.querySelectorAll('button, a, [role="button"]'))
          .filter(element => {
            const style = window.getComputedStyle(element)
            return style.display !== 'none' && style.visibility !== 'hidden'
          })
        return controls.flatMap(element => {
          const rect = element.getBoundingClientRect()
          return rect.width > 0 && (rect.left < -1 || rect.right > window.innerWidth + 1)
            ? [{
              label: element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName,
              tag: element.tagName,
              className: element.getAttribute('class'),
              rect: { left: rect.left, right: rect.right, top: rect.top, width: rect.width },
              ancestors: Array.from({ length: 9 }, (_, index) => {
                let node: Element | null = element
                for (let step = 0; step <= index && node; step += 1) node = node.parentElement
                if (!node) return null
                const ancestorRect = node.getBoundingClientRect()
                return {
                  tag: node.tagName,
                  className: node.getAttribute('class'),
                  left: ancestorRect.left,
                  width: ancestorRect.width,
                  overflow: window.getComputedStyle(node).overflow,
                }
              }),
            }]
            : []
        })
      })
      expect(clippedControls, `${route} ${viewport.width}px clipped controls`).toEqual([])
    }
  }

  expect(consoleErrors).toEqual([])
  expect(pageErrors).toEqual([])
  expect(externalRequests).toEqual([])
})

test('login retains a named main landmark and page heading', async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.route('**/api/auth/status', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ auth_required: true }) })
  })
  await page.goto('/login')
  await expect(page.locator('main[aria-label="Deeper Notebook sign in"]')).toBeVisible()
  await expect(page.locator('main h1')).toHaveCount(1)
})

test('first-launch setup retains a named main landmark and page heading', async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.route('**/healthz/deep', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'degraded',
        checks: {
          database: { status: 'ready', ok: true, error: null },
          migrations: { status: 'ready', ok: true, error: null },
          embedding_model: { status: 'degraded', ok: false, error: null },
          chat_model: { status: 'ready', ok: true, error: null },
          command_registry: { status: 'ready', ok: true, error: null },
        },
      }),
    })
  })
  await page.route('**/api/notebooks**', async route => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.goto('/setup-wizard')
  await expect(page.getByRole('heading', { name: 'Setup Wizard', exact: true })).toBeVisible()
  await expect(page.locator('main')).toHaveCount(1)
  await expect(page.locator('h1')).toHaveCount(1)
})
