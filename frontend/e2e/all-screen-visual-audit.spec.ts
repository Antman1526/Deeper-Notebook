import type { Page } from '@playwright/test'
import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, researchWorkbenchFixtures, test } from './fixtures/research-workbench'
import {
  isAllowedLoopbackHostname,
  isExternalRequest,
} from '../src/lib/visual-audit-request-policy'

const rollbackBuild = process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO === '0'

test('compact shell keeps the focus control clear of the command title', async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/notebooks')

  const focusControl = page.getByRole('button', { name: 'Enter Focus mode' })
  if (rollbackBuild) {
    await expect(page.locator('.dn-legacy-shell')).toBeVisible()
    await expect(focusControl).toBeVisible()
    return
  }

  const title = page.locator('.dn-command-title')
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

// v0.8.96 — the sibling guard above only ever compared the focus control with
// .dn-command-title, and only at 320px. It therefore never saw the real defect:
// .dn-focus-mode-control was position:absolute at the shell's top-right and sat
// directly on top of .dn-command-trigger ("Quick actions ⌘K") at EVERY canonical
// width, so both labels rendered stacked in the corner. An earlier reservation
// fix targeted `.dn-workspace-shell-body > .dn-command-bar`, but the command bar's
// real parent is .dn-luminous-workspace, so the rule never matched and the
// regression went unnoticed. Compare against every command-row control, at every
// width, so a reappearance cannot hide in the gap between the two selectors.
test('focus control never overlaps a command-row control at any audit width', async ({ page }) => {
  test.setTimeout(120_000)
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })

  const focusControl = page.getByRole('button', { name: 'Enter Focus mode' })

  for (const viewport of canonicalViewports) {
    await page.setViewportSize(viewport)
    await page.goto('/notebooks')

    if (rollbackBuild) {
      // The legacy shell has no command bar; the control is deliberately floated.
      await expect(page.locator('.dn-legacy-shell')).toBeVisible()
      await expect(focusControl).toBeVisible()
      continue
    }

    await expect(focusControl).toBeVisible()

    const report = await page.evaluate(() => {
      const focus = document.querySelector<HTMLElement>('.dn-focus-mode-control')
      if (!focus) return { found: false, collisions: [] as string[] }
      const focusRect = focus.getBoundingClientRect()
      const collisions: string[] = []
      for (const selector of ['.dn-command-trigger', '.dn-command-title', '.dn-command-kicker']) {
        const other = document.querySelector<HTMLElement>(selector)
        if (!other) continue
        const rect = other.getBoundingClientRect()
        const hit = rect.left < focusRect.right
          && rect.right > focusRect.left
          && rect.top < focusRect.bottom
          && rect.bottom > focusRect.top
        if (hit) {
          collisions.push(
            `${selector} [${Math.round(rect.left)},${Math.round(rect.top)},`
            + `${Math.round(rect.right)},${Math.round(rect.bottom)}] vs focus `
            + `[${Math.round(focusRect.left)},${Math.round(focusRect.top)},`
            + `${Math.round(focusRect.right)},${Math.round(focusRect.bottom)}]`,
          )
        }
      }
      return { found: true, collisions }
    })

    expect(report.found, `${viewport.width}px focus control present`).toBe(true)
    expect(report.collisions, `${viewport.width}px command-row overlap`).toEqual([])
  }
})

test('external-request detector rejects hostile loopback-looking hostnames without network access', async () => {
  expect(isExternalRequest('http://localhost:3117/api/health')).toBe(false)
  expect(isExternalRequest('http://127.0.0.1:3117/api/health')).toBe(false)
  expect(isExternalRequest('http://[::1]:3117/api/health')).toBe(false)
  expect(isAllowedLoopbackHostname('attacker127.0.0.1')).toBe(false)
  expect(isAllowedLoopbackHostname('notlocalhost')).toBe(false)
  expect(isExternalRequest('http://attacker127.0.0.1.example/api/health')).toBe(true)
  expect(isExternalRequest('http://notlocalhost/api/health')).toBe(true)
})

test('request ledger records unmatched same-origin API calls while allowing explicit mocks', async ({ page }) => {
  const unexpectedApiRequests: string[] = []
  await installLuminousFolioFixture(page, {
    theme: 'research-core-dark',
    unexpectedApiRequests,
  })
  await page.route('**/api/explicit-request-ledger-probe', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ mocked: true }) })
  })

  await page.goto('/')
  const explicitResponse = await page.evaluate(async () => {
    const response = await fetch('/api/explicit-request-ledger-probe')
    return { status: response.status, body: await response.json() }
  })
  const unmatchedResponse = await page.evaluate(async () => {
    const response = await fetch('/api/unmatched-request-ledger-probe')
    return { status: response.status, body: await response.json() }
  })

  expect(explicitResponse).toEqual({ status: 200, body: { mocked: true } })
  expect(unmatchedResponse).toEqual({ status: 200, body: {} })
  expect(unexpectedApiRequests).toContain('GET /api/unmatched-request-ledger-probe')
  expect(unexpectedApiRequests).not.toContain('GET /api/explicit-request-ledger-probe')
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

function expectedMainLandmarks(_route: string): number {
  return 1
}

async function inspectClippedControls(page: Page) {
  return page.evaluate(() => {
    const markerSelector = '[data-dn-horizontal-scroll="sources-table"]'
    const controls = Array.from(document.querySelectorAll<HTMLElement>('button, a, [role="button"]'))
      .filter(element => {
        const style = window.getComputedStyle(element)
        return style.display !== 'none' && style.visibility !== 'hidden'
      })
    const inViewport = (rect: DOMRect) => (
      rect.right > -1
      && rect.left < window.innerWidth + 1
      && rect.bottom > -1
      && rect.top < window.innerHeight + 1
    )
    const containedInViewport = (rect: DOMRect) => (
      rect.left >= -1
      && rect.right <= window.innerWidth + 1
      && rect.top >= -1
      && rect.bottom <= window.innerHeight + 1
    )
    const exemptedContainers = new Set<HTMLElement>()
    const markedContainers = Array.from(document.querySelectorAll<HTMLElement>(markerSelector)).map(container => {
      const rect = container.getBoundingClientRect()
      const style = window.getComputedStyle(container)
      return {
        element: container,
        insideViewport: inViewport(rect),
        containedInViewport: containedInViewport(rect),
        overflowX: style.overflowX,
        scrollable: ['auto', 'scroll'].includes(style.overflowX)
          && container.scrollWidth > container.clientWidth + 1,
        rect: { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom },
      }
    })
    const violations: Array<{ label: string; reason: string }> = []
    const unreachable: string[] = []

    for (const element of controls) {
      const rect = element.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) continue

      const horizontallyClipped = rect.left < -1 || rect.right > window.innerWidth + 1
      if (!horizontallyClipped) continue

      const container = element.closest<HTMLElement>(markerSelector)
      const containerStyle = container ? window.getComputedStyle(container) : null
      const markedScrollable = Boolean(container && containerStyle
        && ['auto', 'scroll'].includes(containerStyle.overflowX)
        && container.scrollWidth > container.clientWidth + 1)

      if (!container || !markedScrollable || !containedInViewport(container.getBoundingClientRect())) {
        violations.push({
          label: element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName,
          reason: 'partially clipped outside the marked scroll container',
        })
        continue
      }
      exemptedContainers.add(container)

      const boundary = container.getBoundingClientRect()
      const initial = container.scrollLeft
      const max = Math.max(0, container.scrollWidth - container.clientWidth)
      const target = Math.min(
        max,
        Math.max(
          0,
          initial + rect.left - boundary.left - Math.max(0, (container.clientWidth - rect.width) / 2),
        ),
      )
      const positions = [...new Set([0, max, initial, target])]
      let reachable = false
      try {
        for (const position of positions) {
          container.scrollLeft = position
          const candidate = element.getBoundingClientRect()
          if (containedInViewport(candidate)
            && candidate.left >= boundary.left - 1
            && candidate.right <= boundary.right + 1) {
            reachable = true
            break
          }
        }
      } finally {
        container.scrollLeft = initial
      }
      if (!reachable) {
        unreachable.push(element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName)
      }
    }

    const serializeContainer = (item: typeof markedContainers[number]) => ({
      insideViewport: item.insideViewport,
      containedInViewport: item.containedInViewport,
      overflowX: item.overflowX,
      scrollable: item.scrollable,
      rect: item.rect,
    })

    return {
      markedContainers: markedContainers.map(serializeContainer),
      exemptedContainers: markedContainers
        .filter(item => exemptedContainers.has(item.element))
        .map(serializeContainer),
      violations,
      unreachable,
    }
  })
}

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

const sharedBackgroundResponses: ReadonlyArray<readonly [string, unknown]> = [
  ['/api/system/db-repair-needed', { needs_repair: false }],
  ['/api/updates/check', {
    current: 'fixture', latest: null, update_available: false, skipped: false,
    skipped_version: null, html_url: null, published_at: null, enabled: false, last_check: null,
  }],
  ['/api/system/network-status', {
    status: 'online', forced_offline: false, local_fallback_model: null, checked_epoch_ms: 0,
  }],
  ['/api/deeper-notebook/vaults', []],
  ['/api/deeper-notebook/overlay/notes', []],
  ['/api/settings', {}],
  ['/api/launcher-prefs', {}],
  ['/api/mcp/web-search', { enabled: false, provider: null, tool_name: 'web_search' }],
  ['/api/deeper-notebook/workspace/knowledge', {}],
  ['/api/deeper-notebook/knowledge/bookmarks', { items: [], next_cursor: null }],
  ['/api/deeper-notebook/knowledge/bookmark-folders', { items: [] }],
  ['/api/deeper-notebook/knowledge/workspaces', { items: [] }],
  ['/api/settings/observability', {}],
  ['/api/deeper-notebook/gmail/status', { connected: false, configured: false }],
  ['/api/credentials/status', { configured: {}, source: {}, encryption_configured: true }],
  ['/api/credentials/env-status', {}],
  ['/api/transformations', []],
]

test('tracked dashboard routes preserve landmarks, bounds, and hermetic browser state', async ({ page }) => {
  test.setTimeout(240_000)
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const externalRequests: string[] = []
  const unexpectedApiRequests: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => {
    if (isExternalRequest(request.url())) {
      externalRequests.push(request.url())
    }
  })

  await installLuminousFolioFixture(page, {
    theme: 'research-core-dark',
    unexpectedApiRequests,
  })
  await page.setViewportSize({ width: 320, height: 240 })
  await page.setContent(`
    <main style="position: relative; width: 320px; height: 120px; margin: 0;">
      <button style="position: absolute; left: 280px; top: 24px; width: 80px; height: 40px;">
        Unmarked overflow canary
      </button>
    </main>
  `)
  const canaryReport = await inspectClippedControls(page)
  expect(canaryReport.markedContainers).toEqual([])
  expect(canaryReport.violations.map(item => item.label)).toContain('Unmarked overflow canary')

  for (const [pathname, body] of sharedBackgroundResponses) {
    await page.route(url => url.pathname === pathname, async route => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    })
  }
  await page.route('**/api/local-models/route-plan', async route => {
    const request = route.request().postDataJSON() as { role?: unknown }
    const role = typeof request.role === 'string' ? request.role : 'unknown'
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        role,
        outcome: 'blocked',
        selected_model_id: null,
        selected_provider: null,
        resource_tier: null,
        selection_source: null,
        route_reason: 'No local model is configured in the visual fixture.',
        escalation_model_ids: [],
        blocked_reason: 'No local model is configured in the visual fixture.',
        selected_fingerprint: null,
        selected_measurements: {},
      }),
    })
  })
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
  await page.route(url => url.pathname === '/api/study/plans', async route => {
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
      await expect(page.locator('h1').first(), `${route} ${viewport.width}px visible heading`).toBeVisible()
      await expect(page.locator('main'), `${route} ${viewport.width}px main`).toHaveCount(expectedMainLandmarks(route))
      await expect(
        page.locator(rollbackBuild ? '.dn-legacy-shell' : '.dn-luminous-shell'),
        `${route} ${viewport.width}px shell mode`,
      ).toBeVisible()
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await expect.poll(
        () => page.locator('main').first().evaluate(element => element.getBoundingClientRect().width > 0),
        `${route} ${viewport.width}px main width`,
      ).toBe(true)

      const duplicateIds = await page.evaluate(() => {
        const ids = Array.from(document.querySelectorAll('[id]'), element => element.id)
        return ids.filter((id, index) => id && ids.indexOf(id) !== index)
      })
      expect(duplicateIds, `${route} ${viewport.width}px duplicate IDs`).toEqual([])

      const clippedReport = await inspectClippedControls(page)
      expect(
        clippedReport.markedContainers.every(container => container.containedInViewport),
        `${route} ${viewport.width}px marked scroll container fully contained in viewport`,
      ).toBe(true)
      expect(
        clippedReport.exemptedContainers.every(container => container.scrollable),
        `${route} ${viewport.width}px marked exemption is genuinely scrollable`,
      ).toBe(true)
      expect(clippedReport.unreachable, `${route} ${viewport.width}px marked controls reachable`).toEqual([])
      expect(clippedReport.violations, `${route} ${viewport.width}px clipped controls`).toEqual([])
    }
  }

  expect(consoleErrors).toEqual([])
  expect(pageErrors).toEqual([])
  expect(externalRequests).toEqual([])
  expect(unexpectedApiRequests).toEqual([])
})

test('login retains a named main landmark and page heading at every audit width', async ({ page }) => {
  test.setTimeout(120_000)
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const externalRequests: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => {
    if (isExternalRequest(request.url())) externalRequests.push(request.url())
  })

  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.route('**/api/auth/status', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ auth_required: true }) })
  })
  for (const viewport of canonicalViewports) {
    await page.setViewportSize(viewport)
    await page.goto('/login')
    await expect(page.locator('main[aria-label="Deeper Notebook sign in"]')).toBeVisible()
    await expect(page.locator('main h1')).toHaveCount(1)
    await expect(page.locator('main h1').first()).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  expect(consoleErrors).toEqual([])
  expect(pageErrors).toEqual([])
  expect(externalRequests).toEqual([])
})

test('first-launch setup retains a named main landmark and page heading at every audit width', async ({ page }) => {
  test.setTimeout(120_000)
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const externalRequests: string[] = []
  const unexpectedApiRequests: string[] = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => {
    if (isExternalRequest(request.url())) externalRequests.push(request.url())
  })

  await installLuminousFolioFixture(page, {
    theme: 'research-core-dark',
    unexpectedApiRequests,
  })
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
  for (const [pathname, body] of sharedBackgroundResponses) {
    await page.route(url => url.pathname === pathname, async route => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    })
  }
  for (const viewport of canonicalViewports) {
    await page.setViewportSize(viewport)
    await page.goto('/setup-wizard')
    await expect(page.getByRole('heading', { name: 'Setup Wizard', exact: true })).toBeVisible()
    await expect(page.locator('main')).toHaveCount(1)
    await expect(page.locator('h1')).toHaveCount(1)
    await expect(page.locator('h1').first()).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  expect(consoleErrors).toEqual([])
  expect(pageErrors).toEqual([])
  expect(externalRequests).toEqual([])
  expect(unexpectedApiRequests).toEqual([])
})

test('representative states and keyboard contracts remain bounded at every audit width', async ({ page }) => {
  test.setTimeout(240_000)
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const externalRequests: string[] = []
  const unexpectedApiRequests: string[] = []
  let notebookState: 'loading' | 'empty' | 'populated' = 'populated'
  let sourceState: 'loading' | 'error' | 'populated' = 'populated'

  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('request', request => {
    if (isExternalRequest(request.url())) externalRequests.push(request.url())
  })

  await installLuminousFolioFixture(page, {
    theme: 'research-core-dark',
    motion: 'reduced',
    unexpectedApiRequests,
  })
  for (const [pathname, body] of sharedBackgroundResponses) {
    await page.route(url => url.pathname === pathname, async route => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
    })
  }
  await page.route('**/api/notebooks**', async route => {
    if (notebookState === 'loading') await new Promise(resolve => setTimeout(resolve, 900))
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(notebookState === 'populated' ? [researchWorkbenchFixtures.notebook] : []),
    })
  })
  await page.route('**/api/sources**', async route => {
    if (sourceState === 'loading') {
      await new Promise(resolve => setTimeout(resolve, 900))
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify([sourceListFixture]) })
      return
    }
    if (sourceState === 'error') {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'fixture outage' }) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([sourceListFixture]) })
  })

  const assertLayout = async (route: string, viewport: typeof canonicalViewports[number]) => {
    await expect(page.locator('body')).toBeVisible()
    await expect(page.locator('h1'), `${route} ${viewport.width}px heading`).toHaveCount(1)
    await expect(page.locator('h1').first(), `${route} ${viewport.width}px visible heading`).toBeVisible()
    await expect(page.locator('main'), `${route} ${viewport.width}px main`).toHaveCount(expectedMainLandmarks(route))
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect.poll(
      () => page.locator('main').first().evaluate(element => element.getBoundingClientRect().width > 0),
      `${route} ${viewport.width}px main width`,
    ).toBe(true)
    await expect(page.locator('html')).toHaveAttribute('data-dn-motion', 'reduced')

    const focusables = page.locator('button:visible, a:visible, input:visible, textarea:visible, select:visible, [tabindex="0"]:visible')
    await expect(focusables.first()).toBeVisible()
    await focusables.first().focus()
    const focusBefore = await page.evaluate(() => {
      const element = document.activeElement as HTMLElement | null
      if (!element) return null
      const rect = element.getBoundingClientRect()
      const style = getComputedStyle(element)
      return {
        tag: element.tagName,
        text: element.textContent?.trim() ?? '',
        visible: rect.width > 0 && rect.height > 0,
        focusStyle: style.outlineWidth !== '0px' || style.boxShadow !== 'none',
      }
    })
    expect(focusBefore?.visible, `${route} ${viewport.width}px focused control visible`).toBe(true)
    expect(focusBefore?.focusStyle, `${route} ${viewport.width}px focused control has visible focus`).toBe(true)
    await page.keyboard.press('Tab')
    const focusAfter = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 160) ?? '')
    expect(focusAfter).not.toBe('')

    const undersizedTargets = await page.evaluate((isRollback) => Array.from(
      document.querySelectorAll<HTMLElement>('button, a, [role="button"]'),
    ).filter(element => {
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && rect.width > 0
        && rect.height > 0
        && !(element.matches('a') && element.querySelector('button, [role="button"]'))
        && (rect.width < (isRollback ? 28 : 32) || rect.height < (isRollback ? 28 : 32))
    }).map(element => element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName), rollbackBuild)
    expect(undersizedTargets, `${route} ${viewport.width}px interactive target floor`).toEqual([])

    // A half-width viewport is the deterministic responsive proxy for compact layout;
    // it is not native browser-zoom proof. Keep the real viewport matrix above intact.
    await page.setViewportSize({ width: Math.max(320, Math.floor(viewport.width / 2)), height: viewport.height })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect.poll(() => page.locator('main').first().evaluate(element => element.getBoundingClientRect().width > 0)).toBe(true)
    await page.setViewportSize(viewport)
  }

  for (const viewport of canonicalViewports) {
    await page.setViewportSize(viewport)

    notebookState = 'loading'
    await page.goto('/')
    await expect(page.getByRole('status', { name: 'Loading your notebook desk' })).toBeVisible()
    await expect(page.getByRole('status', { name: 'Loading your notebook desk' })).toHaveAttribute('aria-live', 'polite')

    notebookState = 'empty'
    await page.goto('/notebooks')
    await expect(page.getByRole('heading', { name: /No results|No notebooks/i })).toBeVisible()
    await assertLayout('/notebooks (empty)', viewport)

    notebookState = 'populated'
    await page.goto('/notebooks')
    await expect(page.getByText('Deterministic Research Notebook', { exact: true })).toBeVisible()
    await assertLayout('/notebooks (populated)', viewport)

    const createTrigger = page.getByRole('button', { name: /New Notebook/i }).first()
    await expect(createTrigger).toBeVisible()
    await createTrigger.click()
    const dialog = page.getByRole('dialog').first()
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('input, textarea, button').first()).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(createTrigger).toBeFocused()

    sourceState = 'loading'
    await page.goto('/sources')
    await expect(page.getByTestId('loading-spinner')).toBeVisible()
    sourceState = 'error'
    await page.goto('/sources')
    await expect(page.locator('main').getByText('Failed to load sources', { exact: true })).toBeVisible()
    sourceState = 'populated'
    await page.reload()
    await expect(page.getByText('Deterministic source', { exact: true })).toBeVisible()
    await expect(page.locator('[data-dn-horizontal-scroll="sources-table"]')).toHaveCount(1)
    await assertLayout('/sources (recovered)', viewport)
  }

  expect(pageErrors).toEqual([])
  expect(externalRequests).toEqual([])
  expect(unexpectedApiRequests).toEqual([])
  expect(consoleErrors.filter(error => (
    !error.includes('Failed to fetch sources') && !error.includes('status of 503')
  ))).toEqual([])
})
