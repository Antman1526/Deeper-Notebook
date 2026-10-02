import { installVisualSystemFixture } from './fixtures/visual-system'
import { expect, test } from './fixtures/research-workbench'

const researchRun = {
  id: 'research-run-fixture-001',
  notebook_id: 'notebook-fixture-001',
  objective: 'Verify evidence provenance in the approval step.',
  stage: 'await_source_approval',
  plan: {},
  hypotheses: [],
  search_query: 'evidence provenance',
  candidates: [
    {
      candidate_id: 'candidate-fixture-001',
      url: 'https://example.com/research',
      title: 'Evidence-backed research source',
      domain: 'example.com',
      snippet: 'A deterministic source used for browser acceptance.',
      search_query: 'evidence provenance',
      decision: 'pending',
      evidence: {
        query: 'evidence provenance',
        provider: 'tavily',
        title: 'Evidence-backed research source',
        url: 'https://example.com/research',
        snippet: 'A deterministic source used for browser acceptance.',
        retrieved_at: '2026-08-09T12:00:00Z',
        freshness: 'stale',
        degraded: true,
        source_fingerprint: '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
        evidence_id: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
      },
    },
  ],
  source_ids: [],
  errors: [],
  cancelled: false,
  comparison: { agreements: [], contradictions: [], gaps: [] },
}

test('renders immutable evidence provenance in the approval step', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  // v0.8.130 — the spec mocked only its own routes, so ~20 shell requests answered 500
  // and a "Server error" toast landed on the receipt. The visual-system fixture serves
  // this notebook hermetically; the routes below are registered later and win.
  await installVisualSystemFixture(page, { theme: 'research-core-dark' })
  const serverErrors: string[] = []
  page.on('response', (response) => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${new URL(response.url()).pathname}`)
  })
  await page.route(/\/config$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ apiUrl: '' }) })
  })
  await page.route(/\/api\/config$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ version: 'fixture', latestVersion: null, hasUpdate: false, dbStatus: 'healthy' }),
    })
  })
  await page.route(/\/api\/auth\/status$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ auth_required: false }) })
  })
  await page.route(/\/api\/healthz\/deep$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'healthy',
        checks: {
          database: { status: 'ready', ok: true, error: null },
          migrations: { status: 'ready', ok: true, error: null },
          embedding_model: { status: 'ready', ok: true, error: null },
          chat_model: { status: 'ready', ok: true, error: null },
          command_registry: { status: 'ready', ok: true, error: null },
        },
      }),
    })
  })
  await page.route(/\/api\/notebooks\/notebook-fixture-001$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'notebook-fixture-001',
        name: 'Deterministic Research Notebook',
        description: 'A browser-harness notebook with fixed evidence.',
        archived: false,
        created: '2026-01-01T00:00:00Z',
        updated: '2026-01-01T00:00:00Z',
        source_count: 1,
        note_count: 0,
      }),
    })
  })
  await page.route(/\/api\/sources(?:\?.*)?$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route(/\/api\/notes(?:\?.*)?$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route(/\/api\/notebooks\/notebook-fixture-001\/research-runs\/research-run-fixture-001$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(researchRun) })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('onp-research-run:notebook-fixture-001', 'research-run-fixture-001')
    window.localStorage.setItem('dn-theme', 'research-core-dark')
    window.localStorage.setItem(
      'dn-guided-tips-v1',
      JSON.stringify({ state: { enabled: false, completed: {} }, version: 0 }),
    )
    window.localStorage.setItem(
      'dn-display-preferences-v1',
      JSON.stringify({
        state: { wallpaper: 'static', motion: 'reduced', transparency: 'solid' },
        version: 0,
      }),
    )
  })
  await page.context().addCookies([
    { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
    { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
  ])
  await page.goto('/notebooks/notebook-fixture-001')
  const workspace = page.getByRole('region', { name: 'Guided research workspace' })
  await expect(workspace).toBeVisible({ timeout: 30_000 })
  await expect(workspace.getByRole('heading', { name: 'Approve sources before import' })).toBeVisible()
  await expect(workspace.getByRole('group', { name: 'Evidence receipt' })).toBeVisible()
  await expect(workspace.getByText('tavily')).toBeVisible()
  await expect(workspace.getByText('Stale')).toBeVisible()
  await expect(workspace.getByText('Fallback provider')).toBeVisible()
  await expect(workspace.getByText('Retrieved')).toBeVisible()
  await expect(workspace.locator('code[aria-label^="Source fingerprint:"]')).toHaveAttribute(
    'title',
    researchRun.candidates[0].evidence.source_fingerprint,
  )
  await expect(workspace.locator('code[aria-label^="Evidence fingerprint:"]')).toHaveAttribute(
    'title',
    researchRun.candidates[0].evidence.evidence_id,
  )
  expect(serverErrors).toEqual([])
  // v0.8.130 — the region now sits in a scrolling Studio column (274px at 1440, four
  // columns) and is taller than the viewport, so an element screenshot of it stitched
  // in page chrome. The receipt itself fits on screen and is what this test is about.
  const receipt = workspace.getByRole('group', { name: 'Evidence receipt' })
  await receipt.scrollIntoViewIfNeeded()
  await expect(receipt).toHaveScreenshot('research-evidence-receipt-group.png', {
    animations: 'disabled',
    caret: 'hide',
  })
})
