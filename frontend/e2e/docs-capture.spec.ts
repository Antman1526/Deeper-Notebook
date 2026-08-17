// Documentation screenshot harness for the end-user PDF guide.
//
// Visits every dashboard route against the mocked-browser fixtures and writes a
// PNG per screen into DOCS_CAPTURE_DIR. It asserts nothing about the app — it is
// a capture tool, not a gate — so it is excluded from the mocked-browser project's
// default run via testIgnore in playwright.config.ts. Run it on demand:
//
//   DOCS_CAPTURE_DIR=../docs/user-guide/shots \
//     npx playwright test e2e/docs-capture.spec.ts --project=mocked-browser
//
// See docs/user-guide/README.md for the full regeneration flow.
import { mkdirSync } from 'node:fs'
import { installLuminousFolioFixture } from './fixtures/luminous-folio'
import { expect, researchWorkbenchFixtures, test } from './fixtures/research-workbench'

const outDir = process.env.DOCS_CAPTURE_DIR ?? '/tmp/dn-guide-shots'

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


const shots: ReadonlyArray<{ name: string; path: string; theme: string; width?: number; height?: number }> = [
  { name: '01-home', path: '/', theme: 'research-core-dark' },
  { name: '02-notebooks', path: '/notebooks', theme: 'research-core-dark' },
  { name: '03-notebook-workspace', path: '/notebooks/notebook-fixture-001', theme: 'research-core-dark' },
  { name: '04-sources', path: '/sources', theme: 'research-core-dark' },
  { name: '05-source-reader', path: '/sources/source-fixture-001', theme: 'research-core-dark' },
  { name: '06-search', path: '/search', theme: 'research-core-dark' },
  { name: '07-knowledge', path: '/knowledge', theme: 'research-core-dark' },
  { name: '08-studio', path: '/studio', theme: 'research-core-dark' },
  { name: '09-podcasts', path: '/podcasts', theme: 'research-core-dark' },
  { name: '10-podcast-studio', path: '/podcasts/studio', theme: 'research-core-dark' },
  { name: '11-study', path: '/study', theme: 'research-core-dark' },
  { name: '12-transformations', path: '/transformations', theme: 'research-core-dark' },
  { name: '13-capture', path: '/capture', theme: 'research-core-dark' },
  { name: '14-advanced', path: '/advanced', theme: 'research-core-dark' },
  { name: '15-settings', path: '/settings', theme: 'research-core-dark' },
  { name: '16-settings-api-keys', path: '/settings/api-keys', theme: 'research-core-dark' },
  { name: '17-settings-local-models', path: '/settings/local-models', theme: 'research-core-dark' },
  { name: '18-settings-mcp', path: '/settings/mcp', theme: 'research-core-dark' },
  { name: '19-settings-launcher-prefs', path: '/settings/launcher-prefs', theme: 'research-core-dark' },
  { name: '20-notebooks-light', path: '/notebooks', theme: 'research-core-light' },
  { name: '21-notebooks-archive-paper', path: '/notebooks', theme: 'archive-paper' },
  { name: '22-notebooks-deep-ocean', path: '/notebooks', theme: 'deep-ocean' },
  { name: '23-notebooks-high-contrast', path: '/notebooks', theme: 'high-contrast-dark' },
  { name: '24-notebooks-mobile', path: '/notebooks', theme: 'research-core-dark', width: 390, height: 844 },
]

test('capture every guide screen', async ({ page }) => {
  test.setTimeout(600_000)
  mkdirSync(outDir, { recursive: true })
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
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

  for (const shot of shots) {
    await page.addInitScript((theme) => {
      localStorage.setItem('dn-theme', theme)
    }, shot.theme)
    await page.setViewportSize({ width: shot.width ?? 1440, height: shot.height ?? 900 })
    await page.goto(shot.path)
    await expect(page.locator('body')).toBeVisible({ timeout: 20_000 })
    await page.waitForLoadState('networkidle').catch(() => undefined)
    await page.mouse.move(0, 0)
    await page.keyboard.press('Escape').catch(() => undefined)
    await page.waitForTimeout(1200)
    await page.screenshot({ path: `${outDir}/${shot.name}.png`, fullPage: false })
  }
})
