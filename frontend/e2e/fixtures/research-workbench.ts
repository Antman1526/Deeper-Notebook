import { test as base, expect, type Page } from '@playwright/test'

export const researchWorkbenchFixtures = {
  notebook: {
    id: 'notebook-fixture-001',
    name: 'Deterministic Research Notebook',
    description: 'A browser-harness notebook with fixed evidence.',
    archived: false,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
    source_count: 1,
    note_count: 0,
  },
  source: {
    id: 'source-fixture-001',
    title: 'Deterministic source',
    source_type: 'text',
    content: 'The fixture source states a fixed research finding.',
    created_at: '2026-01-01T00:00:00Z',
  },
  citation: {
    source_id: 'source-fixture-001',
    start: 0,
    end: 45,
    quote: 'The fixture source states a fixed research finding.',
  },
  modelResponse: {
    content: 'The fixed answer is grounded in the deterministic source.',
    citations: ['source-fixture-001'],
  },
  stt: {
    text: 'deterministic spoken research question',
    language: 'en',
  },
  tts: {
    audio_url: '/fixtures/deterministic-audio.wav',
    duration_seconds: 1.25,
  },
  watchedFolderEvent: {
    path: '/fixtures/watched/research-note.txt',
    event: 'created',
    observed_at: '2026-01-01T00:00:00Z',
  },
  generatedMedia: {
    id: 'media-fixture-001',
    kind: 'audio_overview',
    title: 'Deterministic media',
    duration_seconds: 1.25,
    content_sha256: '7d4ea8f1de2d4705ad535bad5bc55e2e4c1d80b15cf24ece0c7795c8d3f9b3f7',
  },
} as const

async function fulfillJson(page: Page, pathname: string, body: unknown): Promise<void> {
  await page.route(`**${pathname}`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

export async function installResearchWorkbenchMocks(page: Page): Promise<void> {
  await page.context().grantPermissions(['microphone'])
  await page.context().addCookies([
    { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
    { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
  ])

  // Keep the baseline hermetic when layout-only integrations add a request.
  // Specific fixture routes below are registered afterwards and win first.
  await page.route('**/api/**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: '{}',
    })
  })

  await fulfillJson(page, '/config', { apiUrl: '' })
  await fulfillJson(page, '/api/config', {
    version: 'fixture',
    latestVersion: null,
    hasUpdate: false,
    dbStatus: 'healthy',
  })
  await fulfillJson(page, '/api/auth/status', { auth_required: false })
  await fulfillJson(page, '/api/version', { version: 'fixture' })
  await fulfillJson(page, '/api/local-models/health', {
    overall: 'healthy',
    models: [],
  })
  await fulfillJson(page, '/api/readyz', {
    status: 'ready',
    checks: {
      database: 'online',
      database_error: null,
      migrations_applied: true,
      migrations_pending: false,
      migrations_error: null,
    },
  })
  await fulfillJson(page, '/api/runtime/snapshot', {
    schema_version: 'runtime-snapshot-v1',
    status: 'ready',
    reasons: [],
    readiness: { state: 'ready', database: 'online', migrations: 'applied' },
    startup: { state: 'ready', stages: [] },
    updates: { state: 'ready', enabled: true, update_available: false, current_version: '0.8.70' },
    vault: { state: 'ready', ready: 1, degraded: 0, unavailable: 0 },
    knowledge: { state: 'ready', projected: 1, unchanged: 0, failed: 0 },
    backup: { state: 'ready', file_count: 1, newest_age_seconds: 0 },
  })
  await fulfillJson(page, '/healthz/deep', {
    status: 'healthy',
    checks: {
      database: { status: 'ready', ok: true, error: null },
      migrations: { status: 'ready', ok: true, error: null },
      embedding_model: { status: 'ready', ok: true, error: null },
      chat_model: { status: 'ready', ok: true, error: null },
      command_registry: { status: 'ready', ok: true, error: null },
    },
  })
  await fulfillJson(page, '/api/healthz/deep', {
    status: 'healthy',
    checks: {
      database: { status: 'ready', ok: true, error: null },
      migrations: { status: 'ready', ok: true, error: null },
      embedding_model: { status: 'ready', ok: true, error: null },
      chat_model: { status: 'ready', ok: true, error: null },
      command_registry: { status: 'ready', ok: true, error: null },
    },
  })
  await fulfillJson(page, '/api/notebooks**', [researchWorkbenchFixtures.notebook])
  await fulfillJson(page, '/api/sources**', [researchWorkbenchFixtures.source])
  await fulfillJson(page, '/api/episode-profiles**', [])
  await fulfillJson(page, '/api/speaker-profiles**', [])
  await fulfillJson(page, '/api/chat**', researchWorkbenchFixtures.modelResponse)
  await fulfillJson(page, '/api/voice/stt**', researchWorkbenchFixtures.stt)
  await fulfillJson(page, '/api/voice/tts**', researchWorkbenchFixtures.tts)
  await fulfillJson(page, '/api/capture/events**', [researchWorkbenchFixtures.watchedFolderEvent])
  await fulfillJson(page, '/api/media**', [researchWorkbenchFixtures.generatedMedia])
}

type ResearchWorkbenchFixtures = {
  researchWorkbench: typeof researchWorkbenchFixtures
}

export const test = base.extend<ResearchWorkbenchFixtures>({
  researchWorkbench: async ({ page }, use) => {
    await installResearchWorkbenchMocks(page)
    await use(researchWorkbenchFixtures)
  },
})

export { expect }
