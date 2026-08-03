import { expect, test, type Page, type Route } from '@playwright/test'

type Receipt = {
  method: string
  path: string
  host: string
  body: Record<string, unknown> | null
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

test.describe('Podcast Intelligence Studio browser acceptance', () => {
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
    const apiHosts: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.pathname.startsWith('/api/')) apiHosts.push(url.host)
    })

    await page.goto('/podcasts')
    await expect(page.getByRole('heading', { name: 'Fixture outline review' })).toBeVisible()
    await page.getByRole('button', { name: 'Review outline' }).click()
    await expect(page.getByRole('dialog', { name: 'Review the outline' })).toBeVisible()
    await page.getByPlaceholder('Segment title').first().fill('Fixture revised opening')
    await page.getByRole('button', { name: 'Approve & generate audio' }).click()
    await expect(page.getByRole('dialog', { name: 'Review the outline' })).toBeHidden()

    await page.getByLabel('Continue Production').getByRole('button', { name: 'Cancel' }).click()
    await expect.poll(() => receipts.some((receipt) => receipt.path.endsWith('/episode:active/cancel'))).toBe(true)

    await page.getByRole('button', { name: 'Listen' }).click()
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

    const readinessBodies = receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').map((receipt) => receipt.body)
    expect(readinessBodies.every((body) => body?.execution_policy === 'strict_local')).toBe(true)
    expect(readinessBodies.at(-1)?.production_overrides).toEqual({ podcast_outline: 'safe-local-outline' })
    expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
    expect(receipts.every((receipt) => receipt.host === '127.0.0.1:65060')).toBe(true)
    expect(apiHosts.every((host) => host === '127.0.0.1:3117' || host === '127.0.0.1:65060')).toBe(true)
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
    test.setTimeout(60_000)
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
    await expect(page.getByRole('dialog', { name: 'Review selection' })).toBeVisible()
    await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length).toBe(1)
    expect(receipts.at(-1)?.body?.selections).toEqual([{ kind: 'notebook', notebook_id: notebook.id }])
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog', { name: 'Review selection' })).toBeHidden()

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
    await expect(page.getByRole('dialog', { name: 'Review selection' })).toBeVisible()
    await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length).toBe(2)
    expect(receipts.at(-1)?.body?.selections).toEqual([{ kind: 'app_note', note_id: note.id }])
    await page.getByRole('button', { name: 'Cancel' }).click()

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
    await expect(page.getByRole('dialog', { name: 'Review selection' })).toBeVisible()
    await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length).toBe(3)
    expect(receipts.at(-1)?.body?.selections).toEqual([{ kind: 'app_source', source_id: 'source:fixture', inclusion_mode: 'full' }])
    await page.getByRole('button', { name: 'Cancel' }).click()
    expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
  })

  test('passes saved-search, graph, external-document, and selected-block values through the retry selection boundary', async ({ page }) => {
    await setReturningUser(page)
    const receipts = await installPodcastFixtures(page)
    const retrySelections = [
      { kind: 'saved_search', query: 'fixture search', search_mode: 'text', space_ids: ['knowledge_engine_space:fixture'], authority_kinds: ['external_read_only'] },
      { kind: 'graph_selection', document_ids: ['knowledge_engine_document:fixture'] },
      { kind: 'knowledge_document', document_id: 'knowledge_engine_document:fixture', expected_revision_id: 'knowledge_engine_revision:fixture' },
      { kind: 'knowledge_block', document_id: 'knowledge_engine_document:fixture', block_id: 'knowledge_engine_block:fixture', expected_revision_id: 'knowledge_engine_revision:fixture', source_start: 0, source_end: 12 },
    ]
    let selectionIndex = 0
    await page.route('**/api/podcasts/episodes/episode:failed/retry', (route) => routeJson(route, {
      status: 'preview_required', code: 'podcast_selection_changed', message: 'Synthetic selection boundary retry',
      episode_id: 'episode:failed', selection_fingerprint: null, preview: null,
      selections: [retrySelections[selectionIndex++]],
    }))

    for (const selection of retrySelections) {
      await page.goto('/podcasts')
      await page.getByRole('button', { name: 'Retry' }).click()
      await page.waitForURL('**/podcasts/studio')
      await page.getByRole('button', { name: 'Prepare production review' }).click()
      await expect.poll(() => receipts.filter((receipt) => receipt.path === '/api/podcasts/readiness').length).toBe(selectionIndex)
      expect(receipts.at(-1)?.body?.selections).toEqual([selection])
      expect(receipts.some((receipt) => receipt.path === '/api/podcasts/studio/submit')).toBe(false)
    }
  })
})
