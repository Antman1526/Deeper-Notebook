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
  })
  await page.context().addCookies([
    { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
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
})
