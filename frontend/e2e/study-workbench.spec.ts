import { test, expect, type Page } from '@playwright/test'
import {
  addExpectedStudyCalls,
  installStudyWorkbenchFixture,
  canonicalStudyApiPath,
  STUDY_PLAN_ID,
  STUDY_STATES,
  type StudyRequestLedger,
  type StudyFixtureState,
} from './fixtures/study-workbench'

const viewports = [
  { width: 320, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
] as const
const planUrl = `/study/plans/${encodeURIComponent(STUDY_PLAN_ID)}`
const planApiPath = `/api/study/plans/${STUDY_PLAN_ID}`
// The production flag is default-on.  Only an explicit `0` is a rollback
// build; an unset value (and the canonical enabled values) must exercise the
// full workbench matrix.
const studyWorkbenchRollbackBuild = process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH === '0'
const studyWorkbenchEnabledBuild = !studyWorkbenchRollbackBuild

function expectedStateCalls(state: StudyFixtureState): string[] {
  if (state === 'empty' || state === 'loading') {
    return ['GET /api/study/cards/due', 'GET /api/study/plans']
  }
  if (state === 'error-retry') {
    return [
      ...Array.from({ length: 4 }, () => `GET ${planApiPath}`),
      ...Array.from({ length: 2 }, () => `GET ${planApiPath}/syllabus`),
      ...Array.from({ length: 2 }, () => `GET ${planApiPath}/sources/readiness`),
      ...Array.from({ length: 2 }, () => `GET ${planApiPath}/progress`),
    ]
  }
  const calls = [
    `GET ${planApiPath}`,
    `GET ${planApiPath}/syllabus`,
    `GET ${planApiPath}/sources/readiness`,
    `GET ${planApiPath}/progress`,
  ]
  if (state === 'tutor') calls.push(`GET ${planApiPath}/voice:capability`)
  return calls
}

function callCounts(calls: readonly string[]): Record<string, number> {
  return calls.reduce<Record<string, number>>((counts, call) => {
    counts[call] = (counts[call] ?? 0) + 1
    return counts
  }, {})
}

async function assertNoClippedControls(page: Page, label: string): Promise<void> {
  const report = await page.evaluate(() => {
    const markerSelector = '[data-dn-horizontal-scroll="sources-table"], [data-dn-horizontal-scroll="study-tabs"]'
    const controls = Array.from(document.querySelectorAll<HTMLElement>('button, a, [role="button"]')).filter((element) => {
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
    })
    const inViewport = (rect: DOMRect) => (
      rect.right > -1
      && rect.left < window.innerWidth + 1
      && rect.bottom > -1
      && rect.top < window.innerHeight + 1
    )
    const containedHorizontally = (rect: DOMRect, boundary = { left: -1, right: window.innerWidth + 1 }) => (
      rect.left >= boundary.left
      && rect.right <= boundary.right
    )
    const containedInViewport = (rect: DOMRect) => (
      containedHorizontally(rect)
      && rect.top >= -1
      && rect.bottom <= window.innerHeight + 1
    )
    const violations: string[] = []
    for (const control of controls) {
      const rect = control.getBoundingClientRect()
      if (containedHorizontally(rect)) continue
      const container = control.closest<HTMLElement>(markerSelector)
      if (!container) {
        violations.push(control.textContent?.trim() || control.getAttribute('aria-label') || control.tagName)
        continue
      }
      const style = getComputedStyle(container)
      const scrollable = ['auto', 'scroll'].includes(style.overflowX) && container.scrollWidth > container.clientWidth + 1
      const boundary = container.getBoundingClientRect()
      if (!scrollable || !containedInViewport(boundary)) {
        violations.push(control.textContent?.trim() || control.getAttribute('aria-label') || control.tagName)
        continue
      }
      const initial = container.scrollLeft
      const max = Math.max(0, container.scrollWidth - container.clientWidth)
      const target = Math.min(
        max,
        Math.max(
          0,
          initial + rect.left - boundary.left - Math.max(0, (container.clientWidth - rect.width) / 2),
        ),
      )
      const positions = [...new Set([0, max, initial, target])]
      let reachable = false
      try {
        for (const position of positions) {
          container.scrollLeft = position
          const candidate = control.getBoundingClientRect()
          if (inViewport(candidate)
            && candidate.left >= boundary.left - 1
            && candidate.right <= boundary.right + 1) {
            reachable = true
            break
          }
        }
      } finally {
        container.scrollLeft = initial
      }
      if (!reachable) violations.push(control.textContent?.trim() || control.getAttribute('aria-label') || control.tagName)
    }
    return violations
  })
  expect(report, `${label}: visible controls are not partially clipped`).toEqual([])
}

async function assertStudySurface(page: Page, label: string): Promise<void> {
  await expect(page.locator('main'), `${label}: exactly one main landmark`).toHaveCount(1)
  await expect(page.locator('h1:visible'), `${label}: exactly one visible heading`).toHaveCount(1)
  await expect(page.locator('h1:visible').first(), `${label}: heading visible`).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-dn-motion', 'reduced')
  await expect.poll(
    () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    `${label}: no unbounded horizontal scroll`,
  ).toBe(true)
  await assertNoClippedControls(page, label)

  const firstFocusable = page.locator('button:visible, a:visible, input:visible, textarea:visible, select:visible').first()
  await expect(firstFocusable, `${label}: keyboard entry point`).toBeVisible()
  await firstFocusable.focus()
  await expect.poll(() => page.evaluate(() => {
    const active = document.activeElement as HTMLElement | null
    if (!active) return false
    const style = window.getComputedStyle(active)
    const rect = active.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0 && (style.outlineWidth !== '0px' || style.boxShadow !== 'none')
  }), `${label}: visible focus indicator`).toBe(true)
  await page.keyboard.press('Tab')
  await expect.poll(() => page.evaluate(() => document.activeElement !== document.body), `${label}: focus advances`).toBe(true)

  const undersized = await page.evaluate(() => Array.from(
    document.querySelectorAll<HTMLElement>('button, a, [role="button"]'),
  ).filter((element) => {
    const style = window.getComputedStyle(element)
    const rect = element.getBoundingClientRect()
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
      // Inline prose links remain intentionally text-sized; button-like links
      // and every explicit control still satisfy the 28px target floor.
      && !(element.matches('a') && style.display === 'inline')
      && (rect.width < 28 || rect.height < 28)
  }).map((element) => element.textContent?.trim() || element.getAttribute('aria-label') || element.tagName))
  expect(undersized, `${label}: bounded touch targets`).toEqual([])
}

function statePath(state: StudyFixtureState): string {
  if (state === 'progress') return `${planUrl}?tab=progress`
  if (state === 'tutor') return `${planUrl}?tab=learn`
  if (state === 'anki-preview' || state === 'import-receipt') return `${planUrl}?tab=package`
  return `${planUrl}?tab=syllabus`
}

test.describe.configure({ mode: 'serial' })

for (const state of STUDY_STATES) {
  test(`Study ${state} state is accessible and hermetic at every canonical width`, async ({ browser }) => {
    test.skip(!studyWorkbenchEnabledBuild, 'run only against a Study Workbench-enabled build')
    test.setTimeout(180_000)
    const context = await browser.newContext({ locale: 'en-US' })
    const page = await context.newPage()
    const consoleErrors: Array<{ text: string; url: string }> = []
    const pageErrors: string[] = []
    const externalRequests: string[] = []
    const apiRequests: string[] = []
    const failedResponses: string[] = []
    const ledger: StudyRequestLedger = { expected: [], seen: [], unexpected: [], expectedByViewport: {}, seenByViewport: {} }
    const manualRetryState = { enabled: false }
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push({ text: message.text(), url: message.location().url })
    })
    page.on('pageerror', (error) => pageErrors.push(error.message))
    page.on('response', (response) => {
      if (response.status() >= 400) {
        failedResponses.push(`${response.status()} ${response.request().method()} ${canonicalStudyApiPath(new URL(response.url()).pathname)}`)
      }
    })
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) externalRequests.push(request.url())
      if (url.pathname.startsWith('/api/')) apiRequests.push(`${request.method()} ${canonicalStudyApiPath(url.pathname)}`)
    })
    await installStudyWorkbenchFixture(page, { state, ledger, manualRetryState })

    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      addExpectedStudyCalls(ledger, viewport.width, ...expectedStateCalls(state))
      if (state === 'error-retry') {
        // A successful manual retry is cached by React Query. Use a unique
        // query-string navigation before each canonical width so every width
        // gets a fresh document/cache while preserving same-origin fixtures.
        manualRetryState.enabled = false
      }
      if (state === 'empty' || state === 'loading') {
        await page.goto('/study')
        if (state === 'loading') {
          await expect(page.getByRole('status').filter({ hasText: 'Loading study plans' })).toBeVisible()
          // Let the intentionally delayed fixture settle before the next
          // viewport navigation so no in-flight request is aborted.
          await expect(page.getByText('Build a reliable study habit')).toBeVisible()
        }
      } else {
        const path = `${statePath(state)}&viewport=${viewport.width}`
        await page.goto(path)
      }
      await assertStudySurface(page, `${state} ${viewport.width}px`)

      if (state === 'source-processing') {
        await expect(page.getByText('No syllabus proposal yet')).toBeVisible()
        await expect(page.getByText('Syllabus proposal is available after source analysis')).toBeVisible()
      }
      if (state === 'empty') {
        await expect(page.getByText('Start a focused plan')).toBeVisible()
        await expect(page.getByRole('button', { name: 'Create your first plan' })).toBeVisible()
        await expect(page.getByText('Build a reliable study habit')).toHaveCount(0)
        await expect(page.getByRole('link', { name: 'Open plan' })).toHaveCount(0)
      }
      if (state === 'syllabus-proposed') await expect(page.getByText('Version 1 is immutable')).toBeVisible()
      if (state === 'approved' || state === 'generating' || state === 'active') {
        await expect(page.locator('main').getByText(state, { exact: true }).first()).toBeVisible()
      }
      if (state === 'degraded-model') await expect(page.getByText(/degraded/i).first()).toBeVisible()
      if (state === 'offline') await expect(page.getByTestId('network-status-badge').getByText(/offline/i)).toBeVisible()
      if (state === 'error-retry') {
        await expect(page.getByRole('alert')).toBeVisible()
        const retry = page.getByRole('button', { name: 'Retry' })
        await expect(retry).toBeVisible({ timeout: 8_000 })
        const planCallsBeforeRetry = ledger.seen.filter((call) => call === `GET ${'/api/study/plans/' + STUDY_PLAN_ID}`).length
        expect(planCallsBeforeRetry).toBeGreaterThan(0)
        manualRetryState.enabled = true
        await retry.click()
        await expect(page.locator('h1')).toBeVisible()
        const planCallsAfterRetry = ledger.seen.filter((call) => call === `GET ${'/api/study/plans/' + STUDY_PLAN_ID}`).length
        expect(planCallsAfterRetry).toBeGreaterThan(planCallsBeforeRetry)
      }
      if (state === 'tutor') {
        await expect(page.getByRole('region', { name: 'Tutor dock' })).toBeVisible()
        await expect(page.getByRole('textbox', { name: 'Tutor prompt' })).toBeVisible()
        addExpectedStudyCalls(ledger, viewport.width, `POST ${planApiPath}/assistants/source_guide:invoke`)
        await page.getByLabel('Tutor role').selectOption('source_guide')
        await page.getByRole('textbox', { name: 'Tutor prompt' }).fill('Explain the fixture source finding.')
        await page.getByRole('button', { name: 'Ask tutor' }).click()
        await expect(page.getByText('A bounded fixture answer grounded in the selected source.')).toBeVisible()
        await expect(page.getByRole('region', { name: 'Tutor citations' })).toContainText('Fixture source')
      }
      if (state === 'progress') {
        await expect(page.locator('[aria-label="Study progress"]')).toBeVisible()
        await expect(page.getByRole('button', { name: 'Accept Add one more foundation exercise' })).toBeVisible()
        addExpectedStudyCalls(
          ledger,
          viewport.width,
          `POST ${planApiPath}/progress:decision`,
          ...Array.from({ length: 2 }, () => `GET ${planApiPath}`),
          ...Array.from({ length: 2 }, () => `GET ${planApiPath}/syllabus`),
          ...Array.from({ length: 2 }, () => `GET ${planApiPath}/sources/readiness`),
          ...Array.from({ length: 3 }, () => `GET ${planApiPath}/progress`),
        )
        await page.getByRole('button', { name: 'Accept Add one more foundation exercise' }).click()
        await expect(page.getByRole('dialog')).toBeVisible()
        await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click()
        await expect(page.getByRole('dialog')).toBeHidden()
      }
      if (state === 'anki-preview' || state === 'import-receipt') {
        await expect(page.locator('[aria-label="Anki package portability"]')).toBeVisible()
        if (state === 'anki-preview' || state === 'import-receipt') {
          addExpectedStudyCalls(ledger, viewport.width, `POST ${planApiPath}/anki/import`)
          await page.getByRole('tabpanel', { name: 'Anki package' }).locator('input[type="file"]').setInputFiles({ name: 'fixture.apkg', mimeType: 'application/octet-stream', buffer: Buffer.from('fixture') })
          await expect(page.getByRole('heading', { name: 'Import preview' })).toBeVisible()
          if (state === 'import-receipt') {
            addExpectedStudyCalls(
              ledger,
              viewport.width,
              `POST ${planApiPath}/anki/import/${'anki_job:' + 'a'.repeat(32)}:publish`,
              ...Array.from({ length: 2 }, () => `GET ${planApiPath}`),
              ...Array.from({ length: 2 }, () => `GET ${planApiPath}/syllabus`),
              ...Array.from({ length: 2 }, () => `GET ${planApiPath}/sources/readiness`),
              ...Array.from({ length: 3 }, () => `GET ${planApiPath}/progress`),
            )
            await page.getByText('Confirm explicit import into this Study Plan').click()
            await page.getByRole('button', { name: 'Import cards' }).click()
            await expect(page.getByText('Cards imported into the native Study deck.')).toBeVisible()
          }
        }
      }
      if (state === 'empty' || state === 'approved') {
        const invoker = page.getByRole('button', { name: 'Open command palette' })
        await invoker.focus()
        await page.keyboard.press('Control+k')
        await expect(page.getByRole('dialog')).toBeVisible()
        await page.keyboard.press('Escape')
        await expect(invoker).toBeFocused()
      }
    }

    const expectedPlan503Path = canonicalStudyApiPath(`/api/study/plans/${STUDY_PLAN_ID}`)
    const expectedPlan503ConsoleErrorText = 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)'
    const allowedConsoleErrors = state === 'source-processing' || state === 'error-retry'
      ? consoleErrors.filter((entry) => (
        (state === 'error-retry' && entry.text === expectedPlan503ConsoleErrorText
          && (() => {
            try {
              return canonicalStudyApiPath(new URL(entry.url).pathname) === expectedPlan503Path
            } catch {
              return false
            }
          })())
      ))
      : []
    const unexpectedConsoleErrors = consoleErrors.filter((entry) => !allowedConsoleErrors.includes(entry))
    const unexpectedFailedResponses = failedResponses.filter((entry) => (
      !(state === 'error-retry' && entry === `503 GET ${expectedPlan503Path}`)
    ))
    if (state === 'error-retry') {
      const observed503Count = failedResponses.filter((entry) => entry === `503 GET ${expectedPlan503Path}`).length
      expect(observed503Count, `${state}: bounded expected 503 responses`).toBeGreaterThan(0)
      expect(observed503Count, `${state}: exact expected 503 responses`).toBe(viewports.length * 3)
    }
    expect(unexpectedConsoleErrors, `${state}: console errors; failed responses: ${failedResponses.join(', ')}`).toEqual([])
    expect(unexpectedFailedResponses, `${state}: unexpected failed responses`).toEqual([])
    expect(pageErrors).toEqual([])
    expect(externalRequests).toEqual([])
    expect(apiRequests.filter((call) => !ledger.seen.includes(call))).toEqual([])
    expect(ledger.unexpected).toEqual([])
    expect(ledger.seen.length).toBeGreaterThan(0)
    for (const viewport of viewports) {
      const expected = ledger.expectedByViewport?.[String(viewport.width)] ?? []
      const seen = ledger.seenByViewport?.[String(viewport.width)] ?? []
      expect(callCounts(seen), `${state} ${viewport.width}px: exact study request ledger`).toEqual(callCounts(expected))
    }
    await context.close()
  })
}

test('Study fixture rejects every declared custom route with an unexpected method', async ({ page }) => {
  test.skip(!studyWorkbenchEnabledBuild, 'run only against a Study Workbench-enabled build')
  const ledger: StudyRequestLedger = { expected: [], seen: [], unexpected: [], expectedByViewport: {}, seenByViewport: {} }
  await installStudyWorkbenchFixture(page, { state: 'import-receipt', ledger })
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto(`${planUrl}?tab=package`)
  const wrongMethodProbes: Array<[string, string]> = [
    ['/api/study/cards/due', 'POST'],
    ['/api/study/plans', 'POST'],
    [planApiPath, 'POST'],
    [`${planApiPath}/sources/readiness`, 'POST'],
    [`${planApiPath}/syllabus`, 'POST'],
    [`${planApiPath}/progress`, 'POST'],
    [`${planApiPath}/progress:decision`, 'GET'],
    [`${planApiPath}/anki/import`, 'GET'],
    [`${planApiPath}/anki/import/${'anki_job:' + 'a'.repeat(32)}`, 'POST'],
    [`${planApiPath}/anki/import/${'anki_job:' + 'a'.repeat(32)}:publish`, 'GET'],
    [`${planApiPath}/assistants/source_guide:invoke`, 'GET'],
    [`${planApiPath}/assistants/practice_coach:invoke`, 'GET'],
    [`${planApiPath}/voice:capability`, 'POST'],
    [`${planApiPath}/voice:transcribe`, 'GET'],
    [`${planApiPath}/voice:synthesize`, 'GET'],
  ]

  const statuses = await page.evaluate(async (probes) => {
    const responses: number[] = []
    for (const [path, method] of probes) responses.push((await fetch(path, { method })).status)
    return responses
  }, wrongMethodProbes)
  expect(statuses).toEqual(wrongMethodProbes.map(() => 405))
  expect(ledger.unexpected).toEqual(wrongMethodProbes.map(([path, method]) => `${method} ${path}`))
})

test('Study feature-off build is a real rollback with no Study plan navigation or API calls', async ({ page }) => {
  test.skip(!studyWorkbenchRollbackBuild, 'run only against the exact rollback build')
  const ledger: StudyRequestLedger = { expected: [], seen: [], unexpected: [], expectedByViewport: {}, seenByViewport: {} }
  await installStudyWorkbenchFixture(page, { state: 'empty', ledger })
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/study')
  await expect(page.locator('[data-study-workbench="enabled"]')).toHaveCount(0)
  await expect(page.locator('main')).toHaveCount(1)
  await expect(page.locator('h1:visible')).toHaveCount(1)
  await expect(page.getByText('Nothing is due')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Study' })).toHaveCount(0)
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('option', { name: 'Study' })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await page.goto(planUrl)
  await expect(page.locator('[data-study-workbench="enabled"]')).toHaveCount(0)
  await expect(page.locator('main')).toHaveCount(1)
  await expect(page.locator('h1:visible')).toHaveCount(1)
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('option', { name: 'Study' })).toHaveCount(0)
  await page.keyboard.press('Escape')
  expect(ledger.seen.filter((call) => call.includes('/api/study/'))).toEqual([])
})
