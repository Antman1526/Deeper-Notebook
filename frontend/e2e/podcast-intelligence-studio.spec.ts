import { expect, test, type Page, type Route } from '@playwright/test'

import { installStrictKnowledgeFixture } from './fixtures/knowledge-editor-modes'

const proofRevisionPattern = /^[0-9a-f]{40}$/
const proofRuntimeUrl = process.env.PODCAST_STUDIO_NATIVE_URL ?? 'http://127.0.0.1:65060'

function expectedProofRevision(): string {
  const revision = process.env.PODCAST_STUDIO_EXPECTED_REVISION
  if (!revision || !proofRevisionPattern.test(revision)) {
    throw new Error('PODCAST_STUDIO_EXPECTED_REVISION must be a lowercase 40-hex revision')
  }
  return revision
}

type Receipt = {
  method: string
  path: string
  host: string
  body: Record<string, unknown> | null
}

type BrowserRequestReceipt = {
  observedHosts: string[]
  blockedHosts: string[]
}

const browserRequestReceipts = new WeakMap<Page, BrowserRequestReceipt>()
const taskOwnedLoopbackHosts = new Set([
  '127.0.0.1:3117', '127.0.0.1:65060', 'localhost:3117', 'localhost:65060',
])

function isTaskOwnedLoopback(url: URL): boolean {
  return taskOwnedLoopbackHosts.has(url.host)
}

async function installLoopbackRequestGuard(page: Page): Promise<void> {
  const receipt: BrowserRequestReceipt = { observedHosts: [], blockedHosts: [] }
  browserRequestReceipts.set(page, receipt)
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.protocol === 'http:' || url.protocol === 'https:') receipt.observedHosts.push(url.host)
  })
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if ((url.protocol === 'http:' || url.protocol === 'https:') && !isTaskOwnedLoopback(url)) {
      receipt.blockedHosts.push(url.host)
      await route.abort()
      return
    }
    await route.fallback()
  })
}

const fixtureEpisodeProfile = {
  id: 'episode_profile:fixture',
  name: 'Fixture episode profile',
  description: 'Owned browser fixture',
  speaker_config: 'Fixture speaker profile',
  outline_llm: 'fixture-outline',
  transcript_llm: 'fixture-script',
  default_briefing: '',
  num_segments: 2,
}

const fixtureSpeakerProfile = {
  id: 'speaker_profile:fixture',
  name: 'Fixture speaker profile',
  description: 'Owned browser fixture',
  voice_model: 'fixture-voice',
  speakers: [{ name: 'Fixture host', voice_id: 'fixture-host', backstory: '', personality: '' }],
}

const fixtureEpisodes = [
  {
    id: 'episode:review',
    name: 'Fixture outline review',
    episode_profile: fixtureEpisodeProfile,
    speaker_profile: fixtureSpeakerProfile,
    briefing: '',
    mode: 'deep_dive',
    job_status: 'completed',
    generation_stage: 'awaiting_review',
    created: '2026-08-03T00:00:00Z',
    outline: { segments: [
      { name: 'Fixture opening', description: 'Opening evidence', size: 'short' },
      { name: 'Fixture conclusion', description: 'Conclusion evidence', size: 'medium' },
    ] },
    selection_summary: { authority_counts: { app_owned: 1 }, included_count: 1 },
  },
  {
    id: 'episode:active',
    name: 'Fixture active episode',
    episode_profile: fixtureEpisodeProfile,
    speaker_profile: fixtureSpeakerProfile,
    briefing: '',
    mode: 'brief',
    job_status: 'running',
    generation_stage: 'generating_audio',
    created: '2026-08-03T00:00:00Z',
    selection_summary: { authority_counts: { app_owned: 1 }, included_count: 1 },
  },
  {
    id: 'episode:failed',
    name: 'Fixture failed episode',
    episode_profile: fixtureEpisodeProfile,
    speaker_profile: fixtureSpeakerProfile,
    briefing: '',
    mode: 'critique',
    job_status: 'failed',
    generation_stage: 'failed',
    error_message: 'Synthetic fixture failure',
    created: '2026-08-03T00:00:00Z',
    selection_summary: { authority_counts: { external_read_only: 1 }, included_count: 1 },
  },
  {
    id: 'episode:completed',
    name: 'Fixture completed episode',
    episode_profile: fixtureEpisodeProfile,
    speaker_profile: fixtureSpeakerProfile,
    briefing: '',
    mode: 'debate',
    job_status: 'completed',
    generation_stage: 'completed',
    created: '2026-08-03T00:00:00Z',
    audio_url: '/api/podcasts/episodes/episode:completed/audio',
    transcript_segments: [{ start_seconds: 0, end_seconds: 1, speaker: 'Fixture host', text: 'Synthetic transcript', citation_ids: [] }],
    selection_summary: { authority_counts: { app_owned: 1 }, included_count: 1 },
  },
]

function routeJson(route: Route, value: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) })
}

function requestBody(route: Route): Record<string, unknown> | null {
  const data = route.request().postData()
  if (!data) return null
  try {
    return JSON.parse(data) as Record<string, unknown>
  } catch {
    return null
  }
}

async function setReturningUser(page: Page) {
  await page.context().addCookies([{
    name: 'wizard_completed',
    value: '1',
    url: 'http://127.0.0.1:3117',
  }])
}

async function installPodcastFixtures(page: Page): Promise<Receipt[]> {
  const receipts: Receipt[] = []
  const record = (route: Route) => {
    receipts.push({
      method: route.request().method(),
      path: new URL(route.request().url()).pathname,
      host: new URL(route.request().url()).host,
      body: requestBody(route),
    })
  }
  const preview = {
    selection_fingerprint: 'fixture-selection-fingerprint',
    entries: [{
      stable_id: 'note:fixture', title: 'Fixture research selection', authority_kind: 'app_owned',
      relative_locator: 'Fixture.md', revision_id: 'knowledge_engine_revision:fixture', fingerprint: 'fixture',
      state: 'included', reason: 'Synthetic selection fixture', estimated_characters: 120,
    }],
    included_characters: 120,
    requires_batch_engine: false,
    current_worker_eligible: true,
    blocked_reasons: [],
  }
  const readiness = {
    preview,
    ready: true,
    blocked_reasons: [],
    stage_plans: [
      { role: 'podcast_outline', outcome: 'ready', model_id: 'fixture-outline', provider: 'mlx', resource_tier: 'light', selection_source: 'automatic', reason: 'Fixture local outline route.', blocked_reason: null, override_choices: ['safe-local-outline'] },
      { role: 'podcast_script', outcome: 'ready', model_id: 'fixture-script', provider: 'mlx', resource_tier: 'light', selection_source: 'automatic', reason: 'Fixture local script route.', blocked_reason: null, override_choices: [] },
      { role: 'text_to_speech', outcome: 'ready', model_id: 'fixture-voice', provider: 'piper', resource_tier: 'light', selection_source: 'automatic', reason: 'Fixture local voice route.', blocked_reason: null, override_choices: [] },
      { role: 'speech_to_text', outcome: 'ready', model_id: 'fixture-stt', provider: 'whisper', resource_tier: 'light', selection_source: 'automatic', reason: 'Fixture local transcription route.', blocked_reason: null, override_choices: [] },
    ],
  }

  await page.route('**/api/episode-profiles', (route) => routeJson(route, [fixtureEpisodeProfile]))
  await page.route('**/api/speaker-profiles', (route) => routeJson(route, [fixtureSpeakerProfile]))
  await page.route('**/api/podcasts/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path === '/api/podcasts/episodes' && method === 'GET') return routeJson(route, fixtureEpisodes)
    if (path === '/api/podcasts/readiness' && method === 'POST') {
      record(route)
      const body = requestBody(route)
      if (body?.production_overrides && (body.production_overrides as Record<string, unknown>).podcast_outline === 'safe-local-outline') {
        return routeJson(route, {
          ...readiness,
          ready: false,
          blocked_reasons: ['Fixture rejected the selected outline override.'],
          stage_plans: readiness.stage_plans.map((stagePlan) => stagePlan.role === 'podcast_outline'
            ? { ...stagePlan, outcome: 'blocked', blocked_reason: 'Fixture rejected the selected outline override.' }
            : stagePlan),
        })
      }
      return routeJson(route, readiness)
    }
    if (path === '/api/podcasts/studio/submit' && method === 'POST') {
      record(route)
      return routeJson(route, { detail: 'submission must not run in browser verification' }, 500)
    }
    if (path === '/api/podcasts/episodes/episode:review/outline' && method === 'PUT') {
      record(route)
      return routeJson(route, { message: 'Synthetic outline saved', outline: fixtureEpisodes[0].outline })
    }
    if (path === '/api/podcasts/episodes/episode:review/approve-outline' && method === 'POST') {
      record(route)
      return routeJson(route, { job_id: 'command:fixture-outline', message: 'Synthetic outline approved' })
    }
    if (path === '/api/podcasts/episodes/episode:active/cancel' && method === 'POST') {
      record(route)
      return routeJson(route, { message: 'Synthetic cancellation requested' })
    }
    if (path === '/api/podcasts/episodes/episode:failed/retry' && method === 'POST') {
      record(route)
      return routeJson(route, {
        status: 'preview_required', code: 'podcast_selection_changed', message: 'Synthetic retry requires preview',
        episode_id: 'episode:failed', selection_fingerprint: null, preview: null,
        selections: [{ kind: 'app_note', note_id: 'note:fixture' }],
      })
    }
    if (path === '/api/podcasts/episodes/episode:completed/audio' && method === 'GET') {
      record(route)
      return route.fulfill({ status: 200, contentType: 'audio/mpeg', body: Buffer.from('ID3fixture') })
    }
    record(route)
    return routeJson(route, { detail: `Unhandled fixture request ${method} ${path}` }, 404)
  })
  return receipts
}

async function createOwnedNotebookFixture(page: Page) {
  const label = `Task 8 browser fixture ${Date.now()}`
  const notebookResponse = await page.request.post('http://127.0.0.1:65060/api/notebooks', {
    data: { name: label, description: 'Owned synthetic browser verification fixture' },
  })
  expect(notebookResponse.ok()).toBe(true)
  const notebook = await notebookResponse.json() as { id: string; name: string }
  const noteResponse = await page.request.post('http://127.0.0.1:65060/api/notes', {
    data: {
      title: `${label} note`, content: 'Owned synthetic browser fixture content.',
      note_type: 'human', notebook_id: notebook.id,
    },
  })
  expect(noteResponse.ok()).toBe(true)
  const note = await noteResponse.json() as { id: string; title: string }
  return { notebook, note }
}

async function carryQuickSelectionIntoStudio(
  page: Page,
  receipts: Receipt[],
  expectedSelection: Record<string, unknown>,
  quickReadinessCount: number,
  studioReadinessCount: number,
) {
  const returnUrl = page.url()
  const dialog = page.getByRole('dialog', { name: 'Review selection' })
  await expect(dialog).toBeVisible()
  await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length)
    .toBe(quickReadinessCount)
  expect(receipts.at(-1)?.body?.selections).toEqual([expectedSelection])

  await dialog.getByRole('button', { name: 'Customize in Studio' }).click()
  await page.waitForURL('**/podcasts/studio')
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('heading', { name: 'Podcast Intelligence Studio' })).toBeVisible()
  const prepareReview = page.getByRole('button', { name: 'Prepare production review' })
  await prepareReview.focus()
  await expect(prepareReview).toBeFocused()
  await prepareReview.press('Enter')
  await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length)
    .toBe(studioReadinessCount)
  expect(receipts.at(-1)?.body?.selections).toEqual([expectedSelection])

  await page.getByRole('button', { name: 'Close Studio without producing' }).click()
  await expect.poll(() => page.url()).toBe(returnUrl)
  await expect(page.getByRole('heading', { name: 'Podcast Intelligence Studio' })).toBeHidden()
}

test.describe('Podcast Intelligence Studio browser acceptance', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await installLoopbackRequestGuard(page)
    const revision = expectedProofRevision()
    testInfo.annotations.push({ type: 'podcast_studio_runtime_revision', description: revision })
    const health = await page.request.get(`${proofRuntimeUrl}/health`)
    expect(health.ok()).toBe(true)
    expect(await health.json() as Record<string, unknown>).toMatchObject({
      status: 'healthy',
      name: 'Deeper Notebook',
      proof_revision: revision,
    })
  })

  test.afterEach(async ({ page }) => {
    const receipt = browserRequestReceipts.get(page)
    expect(receipt).toBeDefined()
    expect(receipt?.observedHosts.filter((host) => !taskOwnedLoopbackHosts.has(host)))
      .toEqual(receipt?.blockedHosts)
    expect(receipt?.observedHosts.filter((host) => !receipt.blockedHosts.includes(host))
      .every((host) => taskOwnedLoopbackHosts.has(host))).toBe(true)
  })

  test('opens as a sequential, no-selection review surface without submitting production', async ({ page }) => {
    const submissions: string[] = []
    // This test deliberately uses the isolated persistent local API. The app
    // shell performs its own health/readiness reads; stubbing only the
    // submission route would create a partial, misleading browser proof.
    await page.route('**/api/podcasts/studio/submit', async (route) => {
      submissions.push(route.request().method())
      await route.fulfill({ status: 500, body: 'unexpected submission' })
    })

    // Studio acceptance starts from the documented returning-user state. Setup
    // Wizard navigation is separately covered; coupling to its home redirect
    // would make this test depend on an unrelated first-run workflow.
    await setReturningUser(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/podcasts/studio')
    const nonLoopbackAborted = await page.evaluate(async () => {
      try {
        await fetch('https://podcast-task8.invalid/non-loopback-guard')
        return false
      } catch {
        return true
      }
    })
    expect(nonLoopbackAborted).toBe(true)
    expect(browserRequestReceipts.get(page)?.blockedHosts).toContain('podcast-task8.invalid')

    await expect(page.getByRole('heading', { name: 'Podcast Intelligence Studio' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Research Set' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Editorial Brief' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Outline Storyboard' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Production Timeline' })).toBeVisible()
    await expect(page.getByText('Available after intellectual engine upgrade').first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Prepare production review' })).toBeDisabled()
    await expect(page.getByText('Choose at least one readable source before production review.')).toBeVisible()
    expect(submissions).toEqual([])
  })

  test('keeps intercepted episode, retry, studio, and local-only controls explicitly reviewed', async ({ page }) => {
    await setReturningUser(page)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 640, height: 844 })
    const receipts = await installPodcastFixtures(page)

    await page.goto('/podcasts')
    await expect(page.getByRole('heading', { name: 'Fixture outline review' })).toBeVisible()
    await page.getByRole('button', { name: 'Review outline' }).click()
    await expect(page.getByRole('dialog', { name: 'Review the outline' })).toBeVisible()
    await page.getByPlaceholder('Segment title').first().fill('Fixture revised opening')
    await page.getByRole('button', { name: 'Approve & generate audio' }).click()
    await expect(page.getByRole('dialog', { name: 'Review the outline' })).toBeHidden()

    await page.getByLabel('Continue Production').getByRole('button', { name: 'Cancel' }).click()
    await expect.poll(() => receipts.some((receipt) => receipt.path.endsWith('/episode:active/cancel'))).toBe(true)

    await page.getByRole('button', { name: 'Open Episode Lab for Fixture completed episode' }).click()
    await expect(page.getByRole('region', { name: 'Episode Lab' })).toBeVisible()
    await page.getByRole('button', { name: 'Play in global player' }).click()
    await expect(page.getByLabel('Audio overview player')).toBeVisible()
    await expect(page.getByLabel('Audio overview player').getByText('Fixture completed episode')).toBeVisible()

    await page.getByRole('button', { name: 'Retry' }).click()
    await page.waitForURL('**/podcasts/studio')
    await expect(page.getByRole('heading', { name: 'Podcast Intelligence Studio' })).toBeVisible()
    await page.getByRole('button', { name: 'Prepare production review' }).click()
    await expect(page.getByText('Fixture research selection')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue to confirmation' })).toBeEnabled()

    await page.getByRole('button', { name: 'Move Introduction later' }).press('Enter')
    await expect(page.getByRole('status')).toContainText('Introduction moved to position 2')
    await page.getByRole('tab', { name: 'Research Set Preview' }).press('End')
    await expect(page.getByRole('tab', { name: 'Episode' })).toBeFocused()

    await page.getByLabel('Override Outline route model').selectOption('safe-local-outline')
    await expect(page.getByRole('button', { name: 'Prepare production review' })).toBeEnabled()
    await page.getByRole('button', { name: 'Prepare production review' }).click()
    await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length).toBe(2)
    await expect(page.getByText('Fixture rejected the selected outline override.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue to confirmation' })).toBeDisabled()

    const readinessBodies = receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').map((receipt) => receipt.body)
    expect(readinessBodies.every((body) => body?.execution_policy === 'strict_local')).toBe(true)
    expect(readinessBodies.at(-1)?.production_overrides).toEqual({ podcast_outline: 'safe-local-outline' })
    expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
    expect(receipts.every((receipt) => receipt.host === '127.0.0.1:65060')).toBe(true)
    const sequentialLayoutFits = await page.locator('[data-studio-layout]').evaluate((element) => element.scrollWidth <= element.clientWidth)
    expect(sequentialLayoutFits).toBe(true)
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Emulation.setPageScaleFactor', { pageScaleFactor: 2 })
    await expect.poll(() => page.evaluate(() => window.visualViewport?.scale ?? 1)).toBe(2)
    await expect(page.getByRole('heading', { name: 'Podcast Intelligence Studio' })).toBeVisible()
  })

  test('fails a whole-notebook oversize preview closed before production confirmation', async ({ page }) => {
    await setReturningUser(page)
    const receipts = await installPodcastFixtures(page)
    await page.route('**/api/podcasts/episodes/episode:failed/retry', (route) => routeJson(route, {
      status: 'preview_required', code: 'podcast_selection_changed', message: 'Synthetic notebook retry requires preview',
      episode_id: 'episode:failed', selection_fingerprint: null, preview: null,
      selections: [{ kind: 'notebook', notebook_id: 'notebook:fixture' }],
    }))
    await page.route('**/api/podcasts/readiness', (route) => {
      const body = requestBody(route)
      receipts.push({ method: route.request().method(), path: new URL(route.request().url()).pathname, host: new URL(route.request().url()).host, body })
      return routeJson(route, {
        preview: {
          selection_fingerprint: 'fixture-oversize-fingerprint',
          entries: [{
            stable_id: 'notebook:fixture', title: 'Synthetic whole notebook', authority_kind: 'app_owned',
            relative_locator: null, revision_id: 'notebook-revision:fixture', fingerprint: 'fixture-oversize',
            state: 'oversize', reason: 'combined_input_limit', estimated_characters: 60001,
          }],
          included_characters: 0,
          requires_batch_engine: true,
          current_worker_eligible: false,
          blocked_reasons: ['selection_oversize'],
        },
        ready: false,
        blocked_reasons: ['selection_oversize'],
        stage_plans: [],
      })
    })

    await page.goto('/podcasts')
    await page.getByRole('button', { name: 'Retry' }).click()
    await page.waitForURL('**/podcasts/studio')
    await page.getByRole('button', { name: 'Prepare production review' }).click()
    await expect(page.getByLabel('Oversize')).toContainText('Synthetic whole notebook')
    await expect(page.getByText('Selection requires a batch engine; the current worker will not truncate it.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Continue to confirmation' })).toBeDisabled()
    expect(receipts.at(-1)?.body?.execution_policy).toBe('strict_local')
    expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
  })

  test('opens and dismisses app notebook, app note, and app source review entries without submitting', async ({ page }) => {
    test.setTimeout(120_000)
    await setReturningUser(page)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const receipts = await installPodcastFixtures(page)
    const { notebook, note } = await createOwnedNotebookFixture(page)
    await page.route('**/api/sources?*', (route) => routeJson(route, [{
      id: 'source:fixture', title: 'Fixture app source', topics: [], source_type: 'text',
      asset: null, embedded: true, embedded_chunks: 1, insights_count: 0,
      created: '2026-08-03T00:00:00Z', updated: '2026-08-03T00:00:00Z',
      extracted_char_count: 42, extraction_quality: 'ok', status: 'completed',
    }]))
    await page.route('**/api/notes?*', (route) => routeJson(route, [{
      id: note.id, title: note.title, content: 'Owned synthetic browser fixture content.', note_type: 'human',
      created: '2026-08-03T00:00:00Z', updated: '2026-08-03T00:00:00Z',
    }]))

    await page.goto('/notebooks')
    await expect(page.getByText(notebook.name, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Turn into podcast' }).first().click()
    await carryQuickSelectionIntoStudio(
      page, receipts, { kind: 'notebook', notebook_id: notebook.id }, 1, 2,
    )

    await page.goto(`/notebooks/${encodeURIComponent(notebook.id)}`)
    const noteTitle = page.getByText(note.title, { exact: true })
    await expect(noteTitle).toBeVisible()
    const guidedTipsDismiss = page.getByRole('button', { name: 'Got it', exact: true })
    if (await guidedTipsDismiss.isVisible()) await guidedTipsDismiss.click()
    const toastDismiss = page.locator('[data-sonner-toast] [data-close-button]')
    if (await toastDismiss.isVisible()) await toastDismiss.click()
    const noteActions = page.getByRole('button', { name: 'Turn into podcast', exact: true })
    await expect(noteActions).toHaveCount(1)
    await expect(noteActions).toBeVisible()
    await expect(noteActions).toBeEnabled()
    await noteActions.focus()
    await expect(noteActions).toBeFocused()
    await noteActions.press('Enter')
    await carryQuickSelectionIntoStudio(
      page, receipts, { kind: 'app_note', note_id: note.id }, 3, 4,
    )

    const sourceActions = page.getByRole('button', { name: 'Source actions', exact: true })
    await expect(sourceActions).toHaveCount(1)
    await expect(sourceActions).toBeVisible()
    await expect(sourceActions).toBeEnabled()
    await sourceActions.focus()
    await expect(sourceActions).toBeFocused()
    await sourceActions.press('Enter')
    const sourcePodcastAction = page.getByRole('menuitem', { name: 'Turn source into podcast', exact: true })
    await expect(sourcePodcastAction).toBeVisible()
    await sourcePodcastAction.focus()
    await expect(sourcePodcastAction).toBeFocused()
    await sourcePodcastAction.press('Enter')
    await carryQuickSelectionIntoStudio(
      page, receipts,
      { kind: 'app_source', source_id: 'source:fixture', inclusion_mode: 'full' },
      5, 6,
    )
    expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
  })

  test('opens and dismisses real Knowledge search, graph, external-document, and selected-block review controls without submitting', async ({ page }) => {
    test.setTimeout(180_000)
    await setReturningUser(page)
    const knowledge = await installStrictKnowledgeFixture(page)
    const receipts = await installPodcastFixtures(page)
    const navigation = knowledge.state.workspace.navigation as Record<string, unknown>
    navigation.search_mode = 'exact'
    navigation.selected_space_ids = ['knowledge_engine_space:fixture']
    navigation.authority_filters = ['external_read_only']
    const pane = (knowledge.state.workspace.panes as Record<string, Record<string, unknown>>)['pane-1']
    pane.active_tab_id = 'tab-search-exact'
    pane.tabs = [
      {
        id: 'tab-search-exact', mode: 'search', title: 'Exact search',
        target: {
          kind: 'search', query: '', search_mode: 'exact',
          space_ids: ['knowledge_engine_space:fixture'], authority_kinds: ['external_read_only'],
        },
      },
      {
        id: 'tab-search-text', mode: 'search', title: 'Text search',
        target: {
          kind: 'search', query: '', search_mode: 'text',
          space_ids: ['knowledge_engine_space:fixture'], authority_kinds: ['external_read_only'],
        },
      },
    ]

    await page.goto('/knowledge')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('knowledge-workspace')).toBeVisible()

    await page.getByRole('tab', { name: 'Search: Exact search' }).click()
    const searchInput = page.getByRole('textbox', { name: 'Search knowledge' })
    await expect(searchInput).toBeVisible()
    await searchInput.fill('Evidence')
    await page.getByRole('button', { name: 'Search knowledge' }).click()
    await page.getByRole('button', { name: 'Turn into podcast', exact: true }).click()
    await carryQuickSelectionIntoStudio(page, receipts, {
      kind: 'saved_search', query: 'Evidence', search_mode: 'exact',
      space_ids: ['knowledge_engine_space:fixture'], authority_kinds: ['external_read_only'],
    }, 1, 2)

    await page.getByRole('tab', { name: 'Search: Text search' }).click()
    await searchInput.fill('Plan')
    await page.getByRole('button', { name: 'Search knowledge' }).click()
    await page.getByRole('button', { name: 'Turn into podcast', exact: true }).click()
    await carryQuickSelectionIntoStudio(page, receipts, {
      kind: 'saved_search', query: 'Plan', search_mode: 'text',
      space_ids: ['knowledge_engine_space:fixture'], authority_kinds: ['external_read_only'],
    }, 3, 4)

    await page.getByLabel(/Mounted vaults|Mounts/).selectOption('external-vault:vault:fixture')
    const fileFilter = page.getByRole('textbox', { name: 'Filter files' })
    await expect(fileFilter).toBeVisible()
    await fileFilter.focus()
    await page.keyboard.press('Escape')
    const guidedTipsDismiss = page.getByRole('button', { name: 'Got it', exact: true })
    if (await guidedTipsDismiss.isVisible()) await guidedTipsDismiss.click()
    const evidenceNote = page.getByRole('treeitem', { name: 'pages/evidence.md', exact: true })
    await evidenceNote.focus()
    await page.keyboard.press('Enter')
    await expect(evidenceNote).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByLabel('Evidence reading view').getByRole('heading', { name: 'Evidence' })).toBeVisible()

    await page.getByRole('button', { name: 'Graph (Alt+5)' }).click()
    await page.getByRole('button', { name: 'Turn graph into podcast' }).click()
    await carryQuickSelectionIntoStudio(page, receipts, {
      kind: 'graph_selection', document_ids: ['knowledge_engine_document:evidence', 'knowledge_engine_document:plan'],
    }, 5, 6)

    await page.getByRole('button', { name: 'Read (Alt+1)' }).click()
    await page.getByRole('button', { name: 'Turn note into podcast' }).click()
    await carryQuickSelectionIntoStudio(page, receipts, {
      kind: 'knowledge_document', document_id: 'knowledge_engine_document:evidence', expected_revision_id: null,
    }, 7, 8)

    await evidenceNote.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('tab', { name: 'Read: Evidence', exact: true })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByLabel('Evidence reading view')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Turn note into podcast' })).toBeVisible()
    // Allow the newly active Read tab to install its native selection listener
    // before exercising the same browser selection a reader would make.
    await page.evaluate(() => new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    }))
    const evidenceBlock = page.locator('[data-knowledge-block-id="knowledge_engine_block:evidence"]')
    await expect(evidenceBlock).toBeVisible()
    await page.getByLabel('Evidence reading view').getByRole('heading', { name: 'Evidence' }).dblclick()
    const selectionReceipt = await evidenceBlock.evaluate(() => {
      const selection = window.getSelection()
      const selectedBlockId = selection?.anchorNode?.parentElement
        ?.closest<HTMLElement>('[data-knowledge-block-id]')?.dataset.knowledgeBlockId
      return { isCollapsed: selection?.isCollapsed, text: selection?.toString(), selectedBlockId }
    })
    expect(selectionReceipt).toMatchObject({
      isCollapsed: false, selectedBlockId: 'knowledge_engine_block:evidence',
    })
    expect(selectionReceipt.text?.trim()).toBe('Evidence')
    await expect(page.getByRole('button', { name: 'Turn selected block into podcast' })).toBeVisible()
    await page.getByRole('button', { name: 'Turn selected block into podcast' }).click()
    await carryQuickSelectionIntoStudio(page, receipts, {
      kind: 'knowledge_block', document_id: 'knowledge_engine_document:evidence', block_id: 'knowledge_engine_block:evidence',
      expected_revision_id: 'knowledge_engine_revision:evidence', source_start: null, source_end: null,
    }, 9, 10)

    expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
    expect(knowledge.externalMutationRequests).toEqual([])
    expect(knowledge.unexpectedRequests).toEqual([])
  })
})
