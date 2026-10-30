import { installVisualSystemFixture } from './fixtures/visual-system'
import type { Page } from '@playwright/test'
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

async function openGuidedResearch(page: Page, viewport = { width: 1440, height: 900 }, { studioTab = false } = {}) {
  await page.setViewportSize(viewport)
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
  // Below 1280 Studio is a tab beside Notes.
  if (studioTab) await page.getByRole('tab', { name: 'Studio' }).click()
  const workspace = page.getByRole('region', { name: 'Guided research workspace' })
  await expect(workspace).toBeVisible({ timeout: 30_000 })
  return { workspace, serverErrors }
}

test('renders immutable evidence provenance in the approval step', async ({ page }) => {
  const { workspace, serverErrors } = await openGuidedResearch(page)
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

// v0.8.130 — the Studio column is narrow (274px at 1440, four columns; about 225px at
// 1024, where Notes and Studio share a panel), and five nested paddings left the
// receipt ~147px: fingerprints broke mid-value and the source title wrapped one word
// per line.
async function receiptGeometry(page: Page) {
  const workspace = page.getByRole('region', { name: 'Guided research workspace' })
  const receipt = workspace.getByRole('group', { name: 'Evidence receipt' })
  await receipt.scrollIntoViewIfNeeded()
  return receipt.evaluate((element) => {
    const row = element.parentElement as HTMLElement
    const title = row.querySelector('span.font-medium') as HTMLElement
    const lineHeight = parseFloat(getComputedStyle(title).lineHeight)
    return {
      receiptWidth: Math.round(element.getBoundingClientRect().width),
      fingerprintLines: Array.from(element.querySelectorAll('code')).map((code) => code.getClientRects().length),
      titleLines: Math.round(title.getBoundingClientRect().height / lineHeight),
      overflow: element.scrollWidth - element.clientWidth,
    }
  })
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }]) {
  test(`the receipt has room in the Studio column at ${viewport.width}`, async ({ page }) => {
    await openGuidedResearch(page, viewport)
    const geometry = await receiptGeometry(page)
    expect(geometry.fingerprintLines, JSON.stringify(geometry)).toEqual([1, 1])
    expect(geometry.titleLines, JSON.stringify(geometry)).toBeLessThanOrEqual(2)
    expect(geometry.overflow, JSON.stringify(geometry)).toBeLessThanOrEqual(0)
  })
}

test('the receipt fits the shared Notes/Studio panel at 1024', async ({ page }) => {
  await openGuidedResearch(page, { width: 1024, height: 768 }, { studioTab: true })
  const geometry = await receiptGeometry(page)
  expect(geometry.fingerprintLines, JSON.stringify(geometry)).toEqual([1, 1])
  expect(geometry.overflow, JSON.stringify(geometry)).toBeLessThanOrEqual(0)
})

// Drag the handle before the last panel towards a target share of the group; the
// panel group clamps at the panel's minimum (the target stays above the collapse point).
async function dragLastPanelTo(page: Page, targetShare: number) {
  const group = (await page.locator('[data-panel-group]').first().boundingBox())!
  const panel = (await page.locator('[data-panel]').last().boundingBox())!
  const handle = (await page.locator('[data-panel-resize-handle-id]').last().boundingBox())!
  const delta = panel.width - group.width * targetShare
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(handle.x + handle.width / 2 + delta, handle.y + handle.height / 2, { steps: 12 })
  await page.mouse.up()
  const after = (await page.locator('[data-panel]').last().boundingBox())!
  return after.width / group.width
}

test('Studio at its narrowest still fits the receipt (1280, four columns)', async ({ page }) => {
  await openGuidedResearch(page, { width: 1280, height: 800 })
  const share = await dragLastPanelTo(page, 0.14)
  // Studio cannot be dragged below 22% of the group (it was 18%: about 179px at 1280).
  expect(share).toBeGreaterThanOrEqual(0.215)
  const geometry = await receiptGeometry(page)
  expect(geometry.fingerprintLines, JSON.stringify(geometry)).toEqual([1, 1])
  expect(geometry.overflow, JSON.stringify(geometry)).toBeLessThanOrEqual(0)
})

test('the shared Notes/Studio panel at its narrowest still fits the receipt (1024)', async ({ page }) => {
  await openGuidedResearch(page, { width: 1024, height: 768 }, { studioTab: true })
  const share = await dragLastPanelTo(page, 0.16)
  // The shared panel cannot be dragged below 28% of the group (it was 22%).
  expect(share).toBeGreaterThanOrEqual(0.275)
  const geometry = await receiptGeometry(page)
  expect(geometry.overflow, JSON.stringify(geometry)).toBeLessThanOrEqual(0)
})

// v0.8.130 — the candidate's checkbox was drawn as a large square: the V2 target rule
// makes every control 44px, and the native checkbox filled it (it also stretched to
// the label's height). It keeps the 44px target and draws a 16px box on the title line.
test('the candidate checkbox keeps a 44px target but draws a 16px box on the title line', async ({ page }) => {
  const { workspace } = await openGuidedResearch(page)
  const checkbox = workspace.getByRole('checkbox', { name: /Evidence-backed research source/ })
  await checkbox.scrollIntoViewIfNeeded()
  const geometry = await checkbox.evaluate((input) => {
    const box = input.getBoundingClientRect()
    const drawn = getComputedStyle(input, '::before')
    const titleElement = input.closest('label')!.querySelector('span.font-medium')!
    const title = titleElement.getBoundingClientRect()
    const lineHeight = parseFloat(getComputedStyle(titleElement).lineHeight)
    return {
      width: box.width, height: box.height,
      drawn: [drawn.width, drawn.height],
      appearance: getComputedStyle(input).appearance,
      centreOffset: Math.abs((box.top + box.height / 2) - (title.top + lineHeight / 2)),
    }
  })
  expect(Math.min(geometry.width, geometry.height), JSON.stringify(geometry)).toBeGreaterThanOrEqual(44)
  expect(geometry.appearance, JSON.stringify(geometry)).toBe('none')
  expect(geometry.drawn, JSON.stringify(geometry)).toEqual(['16px', '16px'])
  expect(geometry.centreOffset, JSON.stringify(geometry)).toBeLessThanOrEqual(3)
  // Still a working control: pending candidates start selected, and the label toggles it.
  await expect(checkbox).toBeChecked()
  await workspace.getByText('A deterministic source used for browser acceptance.').click()
  await expect(checkbox).not.toBeChecked()
})
