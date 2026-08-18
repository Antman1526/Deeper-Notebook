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

// Real seeded transformations (names/titles/descriptions read from migrations
// 5 and 47) so the transformations shot shows actual product content instead
// of an empty list — Cornell Notes included, since it has no other capture.
const transformationsFixture = [
  {
    id: 'transformation-cornell-notes',
    name: 'Cornell Notes',
    title: 'Cornell Notes',
    description:
      'Restructures a source into Cornell-method study notes: cue questions, notes, and a summary',
    prompt: '# IDENTITY and PURPOSE\n\nYou convert source material into Cornell-method study notes…',
    apply_default: false,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
  },
  {
    id: 'transformation-analyze-paper',
    name: 'Analyze Paper',
    title: 'Paper Analysis',
    description: 'Analyses a technical/scientific paper',
    prompt: '# IDENTITY and PURPOSE\n\nYou analyse a technical or scientific paper…',
    apply_default: false,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
  },
  {
    id: 'transformation-key-insights',
    name: 'Key Insights',
    title: 'Key Insights',
    description: 'Extracts important insights and actionable items',
    prompt: '# IDENTITY and PURPOSE\n\nYou extract important insights and actionable items…',
    apply_default: false,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
  },
  {
    id: 'transformation-dense-summary',
    name: 'Dense Summary',
    title: 'Dense Summary',
    description: 'Creates a rich, deep summary of the content',
    prompt: '# IDENTITY and PURPOSE\n\nYou create a rich, deep summary of the content…',
    apply_default: false,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
  },
] as const

// A completed quiz artifact for ExamLab (§13 in the guide) — matches the
// StudioArtifact shape ExamLab reads (id/notebook_id/artifact_type/status/title
// only; the setup view never inspects output_payload).
const quizArtifactFixture = {
  id: 'studio-artifact-quiz-fixture-001',
  notebook_id: 'notebook-fixture-001',
  artifact_type: 'quiz',
  status: 'completed',
  title: 'Research Methods — Quiz',
  source_ids: ['source-fixture-001'],
  output_format: 'quiz',
  output_payload: {},
  citations: [],
  export_paths: {},
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
} as const

// The in-progress attempt POST /api/study/exams/attempts returns — taking
// view: questions populated, results null, matching the real taking/results
// split (api/schemas/study_exams.py). Deadline is computed at capture time so
// the countdown always renders a normal (non-overtime) remaining time.
function buildExamAttemptFixture() {
  const startedAt = new Date()
  const deadline = new Date(startedAt.getTime() + 20 * 60_000)
  return {
    id: 'study_exam_attempt:fixture001',
    artifact_id: quizArtifactFixture.id,
    notebook_id: 'notebook-fixture-001',
    title: quizArtifactFixture.title,
    question_count: 3,
    duration_sec: 1200,
    started_at: startedAt.toISOString(),
    deadline: deadline.toISOString(),
    submitted_at: null,
    late: null,
    correct_count: null,
    score_percent: null,
    seeded_indices: [],
    results: null,
    questions: [
      {
        index: 0,
        prompt: 'What is the primary purpose of a control group in an experiment?',
        options: [
          { id: 'a', text: 'To isolate the effect of the variable being tested' },
          { id: 'b', text: 'To increase the sample size' },
          { id: 'c', text: 'To reduce the cost of the study' },
          { id: 'd', text: 'To speed up data collection' },
        ],
      },
      {
        index: 1,
        prompt: 'Which of the following best describes a peer-reviewed source?',
        options: [
          { id: 'a', text: 'Any article published online' },
          { id: 'b', text: 'Work evaluated by independent experts before publication' },
          { id: 'c', text: 'A source with more than 100 citations' },
          { id: 'd', text: 'A source written by a single author' },
        ],
      },
      {
        index: 2,
        prompt: 'What does a p-value below 0.05 typically indicate in a study?',
        options: [
          { id: 'a', text: 'The effect size is large' },
          { id: 'b', text: 'The result is unlikely to be due to chance alone' },
          { id: 'c', text: 'The study is definitely correct' },
          { id: 'd', text: 'The sample size was too small' },
        ],
      },
    ],
  } as const
}

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
  ['/api/transformations', transformationsFixture],
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

// Shared route setup used by the main capture run and by the two additional,
// interaction-driven captures below (debate mode, ExamLab). Extracted so a
// route added for one shot can't silently drift out of sync with the others —
// there is exactly one definition of what a mocked dashboard looks like.
async function installGuideBackgroundRoutes(page: import('@playwright/test').Page): Promise<void> {
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
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(transformationsFixture) })
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
  // ExamLab's setup view GETs this list on mount ("recent attempts") — empty
  // by default. Same pathname is also POSTed to (start a new attempt), so
  // this only fulfills GET and falls through otherwise; the ExamLab-specific
  // test below registers its own POST handler, which — added after this one
  // — is tried first and only reaches this fallback for the GET it ignores.
  await page.route(url => url.pathname === '/api/study/exams/attempts', async route => {
    if (route.request().method() !== 'GET') {
      await route.fallback()
      return
    }
    await route.fulfill({ contentType: 'application/json', body: '[]' })
  })
}

test('capture every guide screen', async ({ page }) => {
  test.setTimeout(600_000)
  mkdirSync(outDir, { recursive: true })
  await installGuideBackgroundRoutes(page)

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

test('capture debate mode toggled on', async ({ page }) => {
  test.setTimeout(60_000)
  mkdirSync(outDir, { recursive: true })
  await installGuideBackgroundRoutes(page)

  await page.addInitScript((theme) => {
    localStorage.setItem('dn-theme', theme)
  }, 'research-core-dark')
  await page.setViewportSize({ width: 1440, height: 900 })
  // Same route as shot 03 — the toggle already renders there, off. This
  // capture is that exact screen with one extra click.
  await page.goto('/notebooks/notebook-fixture-001')
  await expect(page.locator('body')).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState('networkidle').catch(() => undefined)
  const toggle = page.getByTestId('debate-mode-toggle')
  await toggle.waitFor({ state: 'visible', timeout: 20_000 })
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await page.mouse.move(0, 0)
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${outDir}/25-chat-debate-mode.png`, fullPage: false })
})

test('capture ExamLab in-progress attempt', async ({ page }) => {
  test.setTimeout(60_000)
  mkdirSync(outDir, { recursive: true })
  await installGuideBackgroundRoutes(page)

  // Override the shared "no quizzes" default with one completed quiz, and
  // handle the start-exam POST — registered after installGuideBackgroundRoutes
  // so both are tried before that function's fallback-only handlers. Computed
  // once so the POST (start) and the GET-by-id useExamAttempt fires right
  // after agree on the same attempt — the earlier failed run served that
  // second GET from installResearchWorkbenchMocks's generic `{}` catch-all,
  // where undefined !== null made submitted_at look non-null and ExamLab
  // rendered the finished/results view instead of the taking view.
  const attemptFixture = buildExamAttemptFixture()
  await page.route('**/api/studio/notebooks/notebook-fixture-001/artifacts**', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([quizArtifactFixture]) })
  })
  await page.route(url => url.pathname === '/api/study/exams/attempts', async route => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(attemptFixture),
    })
  })
  await page.route(
    // The id contains ':' (a SurrealDB record id) — the client percent-encodes
    // it via encodeURIComponent, so pathname arrives encoded; decode before
    // comparing rather than embedding the raw id in the matcher.
    url => decodeURIComponent(url.pathname) === `/api/study/exams/attempts/${attemptFixture.id}`,
    async route => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(attemptFixture) })
    },
  )

  await page.addInitScript((theme) => {
    localStorage.setItem('dn-theme', theme)
  }, 'research-core-dark')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/study')
  await expect(page.locator('body')).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState('networkidle').catch(() => undefined)

  await page.getByTestId('examlab-notebook-select').selectOption('notebook-fixture-001')
  const quizSelect = page.getByTestId('examlab-quiz-select')
  await expect(quizSelect.locator(`option[value="${quizArtifactFixture.id}"]`)).toHaveCount(1, { timeout: 20_000 })
  await quizSelect.selectOption(quizArtifactFixture.id)
  await page.getByTestId('examlab-start').click()

  const taking = page.getByTestId('examlab-taking')
  await taking.waitFor({ state: 'visible', timeout: 20_000 })
  // Answer the first question only, so the screenshot reads as an attempt
  // genuinely in progress rather than either extreme (untouched or complete).
  await page.locator('input[name="exam-q-0"]').first().check()

  await page.mouse.move(0, 0)
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${outDir}/26-study-examlab.png`, fullPage: false })
})
