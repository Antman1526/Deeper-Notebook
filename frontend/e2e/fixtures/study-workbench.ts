import { expect, type Page, type Route } from '@playwright/test'

export const STUDY_PLAN_ID = 'study_plan:fixture'
// Next can preserve one encoded route-param layer before the API client adds
// its own encoding (`%3A` -> `%253A`). Keep matching exact fixture paths while
// normalizing those two equivalent representations for the request ledger.
const PLAN_PATH = `/api/study/plans/${STUDY_PLAN_ID}`
const NOW = '2026-01-01T00:00:00.000Z'
const PACKAGE_SHA256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'

export const STUDY_STATES = [
  'empty',
  'loading',
  'source-processing',
  'syllabus-proposed',
  'approved',
  'generating',
  'active',
  'degraded-model',
  'offline',
  'error-retry',
  'tutor',
  'progress',
  'anki-preview',
  'import-receipt',
] as const

export type StudyFixtureState = typeof STUDY_STATES[number]

export interface StudyRequestLedger {
  expected: string[]
  seen: string[]
  unexpected: string[]
}

export interface StudyWorkbenchFixtureOptions {
  state?: StudyFixtureState
  ledger?: StudyRequestLedger
  unexpectedExternalRequests?: string[]
  manualRetryState?: { enabled: boolean }
}

export const studyWorkbenchFixtures = {
  plan: {
    plan_id: STUDY_PLAN_ID,
    goal: 'Build a reliable study habit',
    starting_level: 'beginner',
    target_date: '2026-06-01',
    preferences: {
      weekly_minutes: 180,
      session_minutes: 30,
      model_route: 'local',
      network_allowed: false,
      approved_network_scope: [],
    },
    source_links: [{ source_id: 'source:fixture' }],
    approved_syllabus_version: 1,
    state: 'approved',
    version: 2,
    created_at: NOW,
    updated_at: NOW,
  },
  syllabus: {
    plan_id: STUDY_PLAN_ID,
    version: 1,
    source_manifest_sha256: PACKAGE_SHA256,
    approved_at: NOW,
    units: [{
      unit_id: 'foundations',
      title: 'Foundations',
      objectives: ['Explain the core idea'],
      prerequisite_unit_ids: [],
      estimated_minutes: 30,
      source_ids: ['source:fixture'],
      activities: [{
        activity_id: 'lesson',
        kind: 'lesson',
        title: 'Read the foundation',
        estimated_minutes: 30,
        source_ids: ['source:fixture'],
      }],
    }],
  },
  readiness: {
    ready: true,
    items: [{
      source_id: 'source:fixture',
      title: 'Fixture source',
      kind: 'text',
      ready: true,
      command_id: null,
      fingerprint_status: 'available',
      reason: 'ready',
    }],
  },
  progress: {
    schema_version: 1,
    concepts: [{
      concept_id: 'core-idea',
      unit_id: 'foundations',
      score: 0.72,
      status: 'developing',
      attempts: 3,
      last_activity_at: NOW,
      lapses: 1,
    }],
    review_consistency: { reviews: 3, lapses: 1, due_reviews: 2, on_time_rate: 0.8 },
    proposals: [],
    generated_at: NOW,
    memory_writes: [],
  },
  cards: [],
  ankiPreview: {
    schema_version: 1,
    job_id: 'anki_job:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    status: 'preview_ready',
    card_count: 2,
    transformed_count: 2,
    skipped_count: 0,
    rejected_count: 0,
    package_sha256: PACKAGE_SHA256,
    collection_member: 'collection.anki2',
    message: null,
  },
  ankiReceipt: {
    schema_version: 1,
    receipt_id: 'anki_receipt:fixture',
    plan_id: STUDY_PLAN_ID,
    request_id: 'anki-import:fixture',
    payload_sha256: PACKAGE_SHA256,
    package_sha256: PACKAGE_SHA256,
    collection_sha256: PACKAGE_SHA256,
    collection_member: 'collection.anki2',
    card_count: 2,
    transformed_count: 2,
    skipped_count: 0,
    card_ids: ['study_card:one', 'study_card:two'],
    deck_names: ['Fixture deck'],
    tags: ['fixture'],
    media_names: [],
    syllabus_unit_id: 'foundations',
    created_at: NOW,
  },
} as const

export function canonicalStudyApiPath(pathname: string): string {
  let canonical = pathname
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const decoded = decodeURIComponent(canonical)
      if (decoded === canonical) break
      canonical = decoded
    } catch {
      break
    }
  }
  return canonical
}

function requestLabel(route: Route): string {
  return `${route.request().method()} ${canonicalStudyApiPath(new URL(route.request().url()).pathname)}`
}

function matchesPath(pathname: string, expectedPath: string): boolean {
  return canonicalStudyApiPath(pathname) === canonicalStudyApiPath(expectedPath)
}

function statePlan(state: StudyFixtureState) {
  const approvedStates = new Set<StudyFixtureState>([
    'approved', 'generating', 'active', 'degraded-model', 'offline', 'error-retry',
    'tutor', 'progress', 'anki-preview', 'import-receipt',
  ])
  const stateValue = state === 'source-processing'
    ? 'analyzing_sources'
    : state === 'syllabus-proposed' ? 'syllabus_proposed'
      : approvedStates.has(state) ? state === 'degraded-model' || state === 'offline' || state === 'error-retry' || state === 'tutor' || state === 'progress' || state === 'anki-preview' || state === 'import-receipt' ? 'approved' : state
        : 'draft'
  return {
    ...studyWorkbenchFixtures.plan,
    state: stateValue,
    approved_syllabus_version: approvedStates.has(state) ? 1 : null,
  }
}

function stateReadiness(state: StudyFixtureState) {
  if (state !== 'source-processing') return studyWorkbenchFixtures.readiness
  return {
    ready: false,
    items: [{ ...studyWorkbenchFixtures.readiness.items[0], ready: false, fingerprint_status: 'unknown' as const, reason: 'processing' as const, command_id: 'command:fixture' }],
  }
}

function stateSyllabus(state: StudyFixtureState) {
  return state === 'source-processing' || state === 'empty' || state === 'loading'
    ? null
    : { ...studyWorkbenchFixtures.syllabus, approved_at: state === 'syllabus-proposed' ? null : NOW }
}

async function jsonRoute(
  page: Page,
  ledger: StudyRequestLedger,
  pathname: string,
  body: unknown,
  method = 'GET',
): Promise<void> {
  await page.route((url) => matchesPath(url.pathname, pathname), async (route) => {
    const label = requestLabel(route)
    ledger.seen.push(label)
    if (route.request().method() !== method) {
      ledger.unexpected.push(label)
      await route.fulfill({ status: 405, contentType: 'application/json', body: JSON.stringify({ detail: 'method not allowed' }) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
}

export async function installStudyWorkbenchFixture(
  page: Page,
  {
    state = 'approved',
    ledger = { expected: [], seen: [], unexpected: [] },
    unexpectedExternalRequests = [],
    manualRetryState = { enabled: false },
  }: StudyWorkbenchFixtureOptions = {},
): Promise<StudyRequestLedger> {
  await page.context().grantPermissions(['microphone'])
  await page.context().addCookies([
    { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
    { name: 'onp_intro_seen', value: '1', domain: '127.0.0.1', path: '/' },
  ])
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) unexpectedExternalRequests.push(request.url())
  })
  page.on('requestfailed', (request) => {
    if (request.url().includes('/api/')) ledger.unexpected.push(`${request.method()} ${new URL(request.url()).pathname} (failed)`)
  })

  await page.addInitScript(() => {
    localStorage.setItem('dn-guided-tips-v1', JSON.stringify({ state: { enabled: false, completed: {} }, version: 0 }))
    localStorage.setItem('dn-display-preferences-v1', JSON.stringify({ state: { wallpaper: 'static', motion: 'reduced', transparency: 'solid' }, version: 0 }))
  })

  await jsonRoute(page, ledger, '/config', { apiUrl: '' })
  await jsonRoute(page, ledger, '/api/config', { version: 'fixture', latestVersion: null, hasUpdate: false, dbStatus: 'healthy' })
  await jsonRoute(page, ledger, '/api/auth/status', { auth_required: false })
  await jsonRoute(page, ledger, '/api/version', { version: 'fixture' })
  await jsonRoute(page, ledger, '/api/readyz', { status: 'ready', checks: { database: 'online', database_error: null, migrations_applied: true, migrations_pending: false, migrations_error: null } })
  await jsonRoute(page, ledger, '/healthz/deep', { status: 'healthy', checks: { database: { status: 'ready', ok: true, error: null }, migrations: { status: 'ready', ok: true, error: null }, embedding_model: { status: state === 'degraded-model' ? 'degraded' : 'ready', ok: state !== 'degraded-model', error: null }, chat_model: { status: 'ready', ok: true, error: null }, command_registry: { status: 'ready', ok: true, error: null } } })
  await jsonRoute(page, ledger, '/api/healthz/deep', { status: 'healthy', checks: { database: { status: 'ready', ok: true, error: null }, migrations: { status: 'ready', ok: true, error: null }, embedding_model: { status: 'ready', ok: true, error: null }, chat_model: { status: 'ready', ok: true, error: null }, command_registry: { status: 'ready', ok: true, error: null } } })
  await jsonRoute(page, ledger, '/api/runtime/snapshot', { schema_version: 'runtime-snapshot-v1', status: state === 'offline' ? 'degraded' : 'ready', reasons: [], readiness: { state: 'ready', database: 'online', migrations: 'applied' }, startup: { state: 'ready', stages: [] }, updates: { state: 'ready', enabled: false, update_available: false, current_version: 'fixture' }, vault: { state: 'ready', ready: 0, degraded: 0, unavailable: 0 }, knowledge: { state: 'ready', projected: 0, unchanged: 0, failed: 0 }, backup: { state: 'ready', file_count: 0, newest_age_seconds: 0 } })
  await jsonRoute(page, ledger, '/api/local-models/health', {
    overall: state === 'degraded-model' ? 'degraded' : 'healthy',
    models: state === 'degraded-model'
      ? [{ name: 'degraded model', status: 'unhealthy', detail: 'fixture model is degraded', latency_ms: null }]
      : [],
  })
  await jsonRoute(page, ledger, '/api/system/db-repair-needed', { needs_repair: false })
  await jsonRoute(page, ledger, '/api/updates/check', { current: 'fixture', latest: null, update_available: false, skipped: false, skipped_version: null, html_url: null, published_at: null, enabled: false, last_check: null })
  await jsonRoute(page, ledger, '/api/system/network-status', { status: state === 'offline' ? 'offline' : 'online', forced_offline: state === 'offline', local_fallback_model: null, checked_epoch_ms: 0 })
  await jsonRoute(page, ledger, '/api/deeper-notebook/vaults', [])
  await jsonRoute(page, ledger, '/api/deeper-notebook/overlay/notes', [])
  await jsonRoute(page, ledger, '/api/settings', { configured: {}, source: {}, encryption_configured: true })
  await jsonRoute(page, ledger, '/api/launcher-prefs', { preferences: {} })
  await jsonRoute(page, ledger, '/api/mcp/web-search', { enabled: false, provider: null, tool_name: 'web_search' })
  await jsonRoute(page, ledger, '/api/deeper-notebook/workspace/knowledge', { schema_version: 1, panes: [] })
  await jsonRoute(page, ledger, '/api/deeper-notebook/knowledge/bookmarks', { items: [], next_cursor: null })
  await jsonRoute(page, ledger, '/api/deeper-notebook/knowledge/bookmark-folders', { items: [] })
  await jsonRoute(page, ledger, '/api/deeper-notebook/knowledge/workspaces', { items: [] })
  await jsonRoute(page, ledger, '/api/settings/observability', { enabled: false })
  await jsonRoute(page, ledger, '/api/deeper-notebook/gmail/status', { connected: false, configured: false })
  await jsonRoute(page, ledger, '/api/credentials/status', { configured: {}, source: {}, encryption_configured: true })
  await jsonRoute(page, ledger, '/api/credentials/env-status', {})
  await jsonRoute(page, ledger, '/api/notebooks', [])
  await jsonRoute(page, ledger, '/api/transformations', [])
  await jsonRoute(page, ledger, '/api/episode-profiles', [])
  await jsonRoute(page, ledger, '/api/speaker-profiles', [])
  await jsonRoute(page, ledger, '/api/podcasts/episodes', [])
  await jsonRoute(page, ledger, '/api/models', [])
  await jsonRoute(page, ledger, '/api/models/defaults', {})

  const cardsPath = '/api/study/cards/due'
  if (state === 'empty' || state === 'loading') await jsonRoute(page, ledger, cardsPath, studyWorkbenchFixtures.cards)
  const plansPath = '/api/study/plans'
  await page.route((url) => matchesPath(url.pathname, plansPath), async (route) => {
    ledger.seen.push(requestLabel(route))
    if (state === 'loading') await new Promise((resolve) => setTimeout(resolve, 900))
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(state === 'empty' ? [] : [statePlan(state)]) })
  })

  await page.route((url) => matchesPath(url.pathname, PLAN_PATH), async (route) => {
    const label = requestLabel(route)
    ledger.seen.push(label)
    // Keep every automatic React Query retry in the explicit error state. The
    // test flips this gate immediately before clicking the visible Retry
    // control, proving that recovery is user initiated rather than incidental.
    if (state === 'error-retry' && !manualRetryState.enabled) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'fixture outage' }) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(statePlan(state)) })
  })
  const readinessPath = `${PLAN_PATH}/sources/readiness`
  await page.route((url) => matchesPath(url.pathname, readinessPath), async (route) => {
    ledger.seen.push(requestLabel(route))
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(stateReadiness(state)) })
  })
  await page.route((url) => matchesPath(url.pathname, `${PLAN_PATH}/syllabus`), async (route) => {
    ledger.seen.push(requestLabel(route))
    const body = stateSyllabus(state)
    if (body === null) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'no syllabus' }) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  if (state !== 'empty' && state !== 'loading') await jsonRoute(page, ledger, `${PLAN_PATH}/progress`, studyWorkbenchFixtures.progress)
  if (state === 'anki-preview' || state === 'import-receipt') {
    await jsonRoute(page, ledger, `${PLAN_PATH}/anki/import`, studyWorkbenchFixtures.ankiPreview, 'POST')
    await jsonRoute(page, ledger, `${PLAN_PATH}/anki/import/${studyWorkbenchFixtures.ankiPreview.job_id}`, { ...studyWorkbenchFixtures.ankiPreview, receipt_id: null })
    await jsonRoute(page, ledger, `${PLAN_PATH}/anki/import/${studyWorkbenchFixtures.ankiPreview.job_id}:publish`, { schema_version: 1, status: 'published', receipt: studyWorkbenchFixtures.ankiReceipt }, 'POST')
  }

  await page.route((url) => matchesPath(url.pathname, `${PLAN_PATH}/assistants/source_guide:invoke`) || matchesPath(url.pathname, `${PLAN_PATH}/assistants/practice_coach:invoke`), async (route) => {
    ledger.seen.push(requestLabel(route))
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
      schema_version: 1,
      response_id: 'study_assistant_response:fixture',
      session_id: 'study_assistant_session:fixture',
      plan_id: STUDY_PLAN_ID,
      role: route.request().url().includes('practice_coach') ? 'practice_coach' : 'source_guide',
      authority: 'source_only',
      status: 'completed',
      answer: 'A bounded fixture answer grounded in the selected source.',
      citations: [{ source_id: 'source:fixture', locator: null, quote: 'Fixture source text.', title: 'Fixture source' }],
      proposed_actions: [],
      retrieval_receipt: { source_ids: ['source:fixture'], citation_count: 1 },
      error_code: null,
      created_at: NOW,
      completed_at: NOW,
    }) })
  })

  // The ledger's required set is intentionally limited to the study calls
  // that define each state. Shell telemetry is mocked for hermeticity but is
  // not a contract of this state matrix.
  if (state === 'empty' || state === 'loading') {
    ledger.expected.push(`GET ${cardsPath}`, `GET ${plansPath}`)
  } else {
    ledger.expected.push(
      `GET ${PLAN_PATH}`,
      `GET ${PLAN_PATH}/syllabus`,
      `GET ${PLAN_PATH}/sources/readiness`,
      `GET ${PLAN_PATH}/progress`,
    )
  }
  if (state === 'anki-preview' || state === 'import-receipt') {
    const importPath = `${PLAN_PATH}/anki/import`
    const jobPath = `${importPath}/${studyWorkbenchFixtures.ankiPreview.job_id}`
    ledger.expected.push(`POST ${importPath}`)
    if (state === 'import-receipt') {
      ledger.expected.push(`POST ${jobPath}:publish`)
    }
  }

  return ledger
}

export { expect }
