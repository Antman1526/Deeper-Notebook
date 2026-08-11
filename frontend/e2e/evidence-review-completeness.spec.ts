import { expect, test } from './fixtures/research-workbench'

const notebookId = 'notebook-fixture-001'
const messageId = 'message-ai-001'
const artifactId = 'artifact-fixture-001'

const evaluation = {
  run: {
    id: 'evaluation-run-fixture-001',
    notebook_id: notebookId,
    artifact_id: null,
    message_id: messageId,
    evaluator_version: 'fixture-evaluator-v1',
    model_id: 'fixture-model',
    metrics: {},
    error: null,
    created: '2026-01-01T00:00:00Z',
  },
  status: 'completed',
  counts: { supported: 1, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
  verdicts: [
    {
      claim: 'The fixture source supports the deterministic answer.',
      status: 'supported',
      confidence: 0.98,
      citation_markers: ['source-fixture-001'],
      evidence: [
        {
          source_id: 'source-fixture-001',
          source_content_sha256: 'fixture-source-sha256',
          source_state: 'current',
          start: 0,
          end: 45,
          quote: 'The fixture source states a fixed research finding.',
        },
      ],
      explanation: 'The answer is directly supported by the immutable fixture source.',
    },
  ],
}

const artifactEvaluation = {
  ...evaluation,
  run: {
    ...evaluation.run,
    id: 'evaluation-run-artifact-fixture-001',
    artifact_id: artifactId,
    message_id: null,
  },
  verdicts: [],
  counts: { supported: 0, partial: 0, contradicted: 0, unsupported: 0, uncited: 0 },
}

const session = {
  id: 'session-fixture-001',
  notebook_id: notebookId,
  title: 'Evidence review fixture chat',
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
  message_count: 2,
  model_override: null,
  disabled_mcp_servers: [],
}

const messages = [
  {
    id: 'message-human-001',
    type: 'human' as const,
    content: 'What does the fixture source say?',
    timestamp: '2026-01-01T00:00:01Z',
  },
  {
    id: messageId,
    type: 'ai' as const,
    content: 'The fixture source states a fixed research finding.',
    timestamp: '2026-01-01T00:00:02Z',
  },
]

const artifact = {
  id: artifactId,
  notebook_id: notebookId,
  artifact_type: 'report' as const,
  title: 'Fixture evidence report',
  status: 'completed' as const,
  source_ids: ['source-fixture-001'],
  prompt: null,
  model_id: 'fixture-model',
  provider: 'fixture-provider',
  output_format: 'markdown',
  output_payload: { markdown: '# Fixture evidence report\n\nA deterministic report.' },
  citations: [],
  export_paths: {},
  revision_of_id: null,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
}

test('renders notebook Chat and selected Studio evidence review with keyboard access', async ({ page, researchWorkbench }) => {
  void researchWorkbench
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: 'reduce' })

  const evaluationRequests: Array<{ method: string; pathname: string }> = []
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.includes('/api/evaluations')) {
      evaluationRequests.push({ method: request.method(), pathname: url.pathname })
    }
  })
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => pageErrors.push(error.stack || error.message))

  await page.addInitScript(() => {
    window.localStorage.setItem('dn-guided-tips-v1', JSON.stringify({
      state: { enabled: false, completed: {} },
      version: 0,
    }))
    const nativeFetch = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      if (url.endsWith('/config') || url.endsWith('/api/config')) {
        return new Response(JSON.stringify({
          apiUrl: window.location.origin,
          version: 'fixture',
          latestVersion: null,
          hasUpdate: false,
          dbStatus: 'healthy',
        }), { status: 200, headers: { 'content-type': 'application/json' } })
      }
      if (url.endsWith('/api/auth/status')) {
        return new Response(JSON.stringify({ auth_required: false }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
      return nativeFetch(input, init)
    }
  })

  // The built shell may resolve the backend URL to the development proxy
  // (localhost:5055) before the client runtime config settles. Keep both
  // config hops hermetic regardless of which origin is selected.
  await page.route(/\/config(?:\?.*)?$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ apiUrl: '' }) })
  })
  await page.route('**/api/config**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ version: 'fixture', latestVersion: null, hasUpdate: false, dbStatus: 'healthy' }),
    })
  })
  await page.route('**/api/auth/status**', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ auth_required: false }) })
  })

  await page.route(/\/api\/notebooks\/notebook-fixture-001$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      id: notebookId,
      name: 'Deterministic Research Notebook',
      description: 'A browser-harness notebook with fixed evidence.',
      archived: false,
      created: '2026-01-01T00:00:00Z',
      updated: '2026-01-01T00:00:00Z',
      source_count: 1,
      note_count: 0,
    }) })
  })
  await page.route(/\/api\/sources(?:\?.*)?$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([{
      id: 'source-fixture-001',
      title: 'Deterministic source',
      source_type: 'text',
      content: 'The fixture source states a fixed research finding.',
      status: 'completed',
      created_at: '2026-01-01T00:00:00Z',
    }]) })
  })
  await page.route(/\/api\/notes(?:\?.*)?$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route(/\/api\/chat\/sessions\?[^?]*notebook_id=notebook-fixture-001[^?]*$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([session]) })
  })
  await page.route(/\/api\/chat\/sessions\/session-fixture-001$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ...session, messages }) })
  })
  await page.route(/\/api\/studio\/notebooks\/notebook-fixture-001\/artifacts$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([artifact]) })
  })
  await page.route(/\/api\/studio\/artifacts\/artifact-fixture-001\/revisions$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route(/\/api\/studio\/artifacts\/artifact-fixture-001\/workflow-runs$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
  await page.route(/\/api\/evaluations\/latest\/batch$/, async (route) => {
    expect(route.request().method()).toBe('POST')
    const payload = route.request().postDataJSON() as { notebook_id?: string; message_ids?: string[] }
    expect(payload).toEqual({ notebook_id: notebookId, message_ids: [messageId] })
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ [messageId]: evaluation }) })
  })
  await page.route(/\/api\/evaluations\/latest(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    expect(url.searchParams.get('notebook_id')).toBe(notebookId)
    expect(url.searchParams.get('artifact_id')).toBe(artifactId)
    expect(url.searchParams.get('message_id')).toBeNull()
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(artifactEvaluation) })
  })

  // Next's proxy can resolve API calls to localhost:5055 in a production
  // build. This final origin-agnostic handler keeps every shell request
  // deterministic while recording any endpoint that this proof forgot to
  // model. Specific routes above still provide the evidence payloads.
  const unexpectedApiRequests: string[] = []
  const expectedBackgroundRequests: string[] = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const pathname = url.pathname
    const method = route.request().method()
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })

    if (pathname === '/api/config') return json({ version: 'fixture', latestVersion: null, hasUpdate: false, dbStatus: 'healthy' })
    if (pathname === '/api/auth/status') return json({ auth_required: false })
    if (pathname === '/api/notebooks') return json([{
      id: notebookId,
      name: 'Deterministic Research Notebook',
      description: 'A browser-harness notebook with fixed evidence.',
      archived: false,
      created: '2026-01-01T00:00:00Z',
      updated: '2026-01-01T00:00:00Z',
      source_count: 1,
      note_count: 0,
    }])
    if (pathname === `/api/notebooks/${notebookId}`) return json({
      id: notebookId,
      name: 'Deterministic Research Notebook',
      description: 'A browser-harness notebook with fixed evidence.',
      archived: false,
      created: '2026-01-01T00:00:00Z',
      updated: '2026-01-01T00:00:00Z',
      source_count: 1,
      note_count: 0,
    })
    if (pathname === `/api/notebooks/${notebookId}/suggested-questions`) {
      expectedBackgroundRequests.push(`${method} ${pathname}`)
      return json({ questions: [] })
    }
    if (pathname === '/api/sources') return json([{
      id: 'source-fixture-001',
      title: 'Deterministic source',
      source_type: 'text',
      content: 'The fixture source states a fixed research finding.',
      status: 'completed',
      created_at: '2026-01-01T00:00:00Z',
    }])
    if (pathname === '/api/notes') return json([])
    if (pathname === '/api/chat/sessions' && method === 'GET') return json([session])
    if (pathname === '/api/chat/sessions/session-fixture-001') return json({ ...session, messages })
    if (pathname === `/api/studio/notebooks/${notebookId}/artifacts`) return json([artifact])
    if (pathname === `/api/studio/artifacts/${artifactId}/revisions`) return json([])
    if (pathname === `/api/studio/artifacts/${artifactId}/workflow-runs`) return json([])
    if (pathname === '/api/chat/context' && method === 'POST') {
      expectedBackgroundRequests.push(`${method} ${pathname}`)
      return json({
        context: { sources: [], notes: [] },
        token_count: 0,
        char_count: 0,
      })
    }
    if (pathname === '/api/evaluations/latest/batch' && method === 'POST') {
      const payload = route.request().postDataJSON() as {
        notebook_id?: string
        message_ids?: string[]
      }
      expect(payload).toEqual({ notebook_id: notebookId, message_ids: [messageId] })
      return json({ [messageId]: evaluation })
    }
    if (pathname === '/api/evaluations/latest' && method === 'GET') {
      const search = new URL(route.request().url()).searchParams
      expect(search.get('notebook_id')).toBe(notebookId)
      expect(search.get('artifact_id')).toBe(artifactId)
      expect(search.get('message_id')).toBeNull()
      return json(artifactEvaluation)
    }

    if (pathname === '/api/local-models/health') return json({ overall: 'healthy', models: [] })
    if (pathname === '/api/credentials/status') return json({ encryption_configured: true, source: {} })
    if (pathname === '/api/credentials/env-status') return json({})
    if (pathname === '/api/system/db-repair-needed') return json({ needs_repair: false })
    if (pathname === '/api/system/network-status') return json({ status: 'online' })
    if (pathname === '/api/updates/check') return json({
      update_available: false,
      skipped: false,
      verification: 'unknown',
      latest: null,
      release_url: null,
      enabled: false,
    })
    if (pathname === '/api/settings') return json({ default_embedding_option: 'always' })
    if (pathname === '/api/runtime/snapshot') return json({
      schema_version: 'runtime-snapshot-v1',
      status: 'ready',
      reasons: [],
      readiness: { state: 'ready', database: 'online', migrations: 'applied' },
      startup: { state: 'ready', stages: [] },
      updates: { state: 'ready', enabled: true, update_available: false, current_version: 'fixture' },
      vault: { state: 'ready', ready: 0, degraded: 0, unavailable: 0 },
      knowledge: { state: 'ready', projected: 0, unchanged: 0, failed: 0 },
      backup: { state: 'ready', file_count: 0, newest_age_seconds: 0 },
    })
    if (pathname === '/api/readyz') return json({ status: 'ready', checks: {} })
    if (pathname === '/api/healthz/deep') return json({ status: 'healthy', checks: {} })
    if (pathname === '/api/deeper-notebook/gmail/status') return json({ connected: false })
    if (pathname === '/api/deeper-notebook/vaults') return json([])
    if (pathname === '/api/deeper-notebook/overlay/notes') return json([])
    if (pathname === '/api/transformations') return json([])
    if (pathname === '/api/episode-profiles' || pathname === '/api/speaker-profiles') return json([])
    if (pathname === '/api/podcasts/episodes') return json([])
    if (pathname === '/api/mcp') return json([])
    if (pathname === '/api/mcp/web-search') return json({ enabled: false, provider: null, tool_name: 'web_search' })
    if (pathname === '/api/version') return json({ version: 'fixture' })
    if (pathname === '/api/models') return json([])
    if (pathname === '/api/models/defaults') return json({})
    unexpectedApiRequests.push(`${method} ${pathname}`)
    return json({})
  })

  await page.goto(`/notebooks/${notebookId}`)
  await page.waitForTimeout(1_000)
  await page.screenshot({ path: '/tmp/evidence-review-completeness.png', fullPage: true })
  if (pageErrors.length > 0) console.log(`browser page errors: ${pageErrors.join('\n---\n')}`)
  if (consoleErrors.length > 0) console.log(`browser console errors: ${consoleErrors.join('\n---\n')}`)
  await expect(page.getByText('Deterministic Research Notebook', { exact: true })).toBeVisible()
  await expect(page.getByText('The fixture source states a fixed research finding.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Evidence supported' })).toHaveCount(1)
  const chatBadge = page.getByRole('button', { name: 'Evidence supported' })
  await chatBadge.focus()
  await page.keyboard.press('Enter')
  const claimDialog = page.getByRole('dialog', { name: 'Evidence review' })
  await expect(claimDialog).toBeVisible()
  await expect(claimDialog).toContainText('The fixture source supports the deterministic answer.')
  await page.keyboard.press('Escape')
  await expect(claimDialog).not.toBeVisible()

  await page.getByRole('button', { name: 'Open Fixture evidence report' }).click()
  const artifactDialog = page.getByRole('dialog', { name: 'Fixture evidence report' })
  await expect(artifactDialog).toBeVisible()
  await expect(artifactDialog.getByRole('button', { name: 'No claims reviewed' })).toBeVisible()
  const artifactBadge = artifactDialog.getByRole('button', { name: 'No claims reviewed' })
  await artifactBadge.focus()
  await page.keyboard.press(' ')
  const artifactClaimDialog = page.getByRole('dialog', { name: 'Evidence review' })
  await expect(artifactClaimDialog).toBeVisible()
  await expect(artifactClaimDialog).toContainText('No material claims were found to review.')
  await page.keyboard.press('Escape')
  await expect(artifactClaimDialog).not.toBeVisible()

  expect(evaluationRequests).toEqual([
    { method: 'POST', pathname: '/api/evaluations/latest/batch' },
    { method: 'GET', pathname: '/api/evaluations/latest' },
  ])
  const chatContextRequests = expectedBackgroundRequests.filter(
    (request) => request === 'POST /api/chat/context'
  )
  expect(expectedBackgroundRequests.filter(
    (request) => request === 'GET /api/notebooks/notebook-fixture-001/suggested-questions',
  )).toHaveLength(1)
  expect(chatContextRequests.length).toBeGreaterThanOrEqual(2)
  expect(chatContextRequests.length).toBeLessThanOrEqual(3)
  expect(expectedBackgroundRequests.every((request) => (
    request === 'GET /api/notebooks/notebook-fixture-001/suggested-questions'
      || request === 'POST /api/chat/context'
  ))).toBe(true)
  expect(unexpectedApiRequests).toEqual([])
  expect(consoleErrors).toEqual([])
})
