import { expect, type Page, type Route } from '@playwright/test'

import {
  type SourceGalleryCell,
  type SourceGalleryState,
} from '../../src/lib/visual-system/route-manifest'
import {
  installVisualSystemFixture,
  frequencyMapFromLabels,
  VISUAL_MATRIX_THEMES,
  VISUAL_MATRIX_VIEWPORTS,
  type VisualSystemFixtureHandle,
  type VisualMatrixTheme,
  type VisualMatrixViewport,
} from './visual-system'
import { canonicalStudyApiPath } from './study-workbench'

export const SOURCE_GALLERY_THEMES = VISUAL_MATRIX_THEMES
export const SOURCE_GALLERY_VIEWPORTS = VISUAL_MATRIX_VIEWPORTS

export type SourceGalleryTheme = VisualMatrixTheme
export type SourceGalleryViewport = VisualMatrixViewport

export interface SourceGalleryRequestReceipt {
  viewport: string
  method: string
  canonicalPath: string
  status: number
}

export interface SourceGalleryRequestLedger {
  expected: Record<string, number>
  seen: Record<string, number>
  receipts: SourceGalleryRequestReceipt[]
  unexpected: string[]
  external: string[]
}

export interface SourceGalleryFixtureHandle {
  base: VisualSystemFixtureHandle
  ledger: SourceGalleryRequestLedger
  expectCall: (label: string, count?: number) => void
  releaseData: () => void
}

type InstallOptions = {
  cell: SourceGalleryCell
  theme: SourceGalleryTheme
  viewport: SourceGalleryViewport
}

const SOURCE_ID = 'source:fixture'
const CONTENT_SHA = 'a'.repeat(64)
const ASSET_SHA = 'b'.repeat(64)
const OPAQUE_TOKEN = 'c'.repeat(64)
const NOW = '2026-08-15T12:00:00Z'
const WEBP_FIXTURE = Buffer.from(
  'UklGRkgAAABXRUJQVlA4IDwAAACQAwCdASpAACQAPm02mEkkIqKhIqgAgA2JZwB2AAAqNMY4fBmAAP7tBy/60LQgc//+Fa3s9geToAAAAAA=',
  'base64',
)
const CORRUPT_WEBP_FIXTURE = Buffer.from('not-a-webp', 'utf8')

function requestLabel(method: string, pathname: string): string {
  return `${method} ${canonicalStudyApiPath(pathname)}`
}

function increment(map: Record<string, number>, key: string, count = 1): void {
  map[key] = (map[key] ?? 0) + count
}

function mergeFrequencyMaps(...maps: readonly Record<string, number>[]): Record<string, number> {
  return maps.reduce<Record<string, number>>((merged, map) => {
    for (const [label, count] of Object.entries(map)) {
      merged[label] = (merged[label] ?? 0) + count
    }
    return merged
  }, {})
}

function delegatedLabel(label: string): boolean {
  const separator = label.indexOf(' ')
  if (separator <= 0) return false
  const path = label.slice(separator + 1)
  return ['/api/sources', '/api/search', '/api/capture'].some((prefix) => (
    path === prefix || path.startsWith(`${prefix}/`)
  ))
}

function withoutDelegatedFrequency(map: Record<string, number>): Record<string, number> {
  return Object.fromEntries(Object.entries(map).filter(([label]) => !delegatedLabel(label)))
}

function pageOrigin(url: string): boolean {
  try {
    const configuredPort = process.env.PLAYWRIGHT_PORT ?? '3117'
    const configured = process.env.PLAYWRIGHT_BASE_URL
      ? new URL(process.env.PLAYWRIGHT_BASE_URL).origin
      : `http://127.0.0.1:${configuredPort}`
    return new URL(url).origin === configured
  } catch {
    return false
  }
}

function sourceVisual(state: SourceGalleryState) {
  if (state === 'processing' || state === 'failed' || state === 'feature-off') return null
  return {
    source_id: SOURCE_ID,
    content_sha256: CONTENT_SHA,
    asset_sha256: ASSET_SHA,
    alt_text: 'Teal source-derived diagram with a calm geometric field',
    width: 64,
    height: 36,
    mime_type: 'image/webp',
    asset_url: `/api/sources/source%3Afixture/visual?v=${OPAQUE_TOKEN}`,
    created_at: NOW,
    updated_at: NOW,
    origin: 'embedded',
    source_locator: { page: 1 },
  } as const
}

function sourceStatus(state: SourceGalleryState) {
  // v0.8.86 — the backend stamps a 'disabled' capability sentinel when its
  // feature flag is off; the fixture mirrors that for feature-off cells so
  // the enabled-build/disabled-backend matrix exercises the real contract.
  if (state === 'feature-off') {
    return {
      state: 'disabled',
      command_id: null,
      error_code: null,
      updated_at: NOW,
    } as const
  }
  if (state !== 'processing' && state !== 'failed') return null
  return {
    state,
    command_id: 'command:fixture',
    error_code: state === 'failed' ? 'extractor.failed' : null,
    updated_at: NOW,
  } as const
}

function sourceRow(state: SourceGalleryState) {
  return {
    id: SOURCE_ID,
    title: 'Fixture field notes',
    topics: ['evidence'],
    provenance: { origin: 'local fixture' },
    source_type: 'upload',
    notebook_count: 1,
    is_shared: false,
    asset: null,
    embedded: true,
    embedded_chunks: 3,
    insights_count: 1,
    summary_preview: 'A source used to verify local visual presentation.',
    created: NOW,
    updated: NOW,
    file_available: true,
    extracted_char_count: 128,
    extraction_quality: 'ok',
    command_id: null,
    status: 'completed',
    processing_info: null,
    visual: sourceVisual(state),
    visual_status: sourceStatus(state),
  }
}

function sourceDetail(state: SourceGalleryState) {
  return {
    ...sourceRow(state),
    full_text: 'Exact fixture passage for evidence focus and return.',
    notebooks: ['notebook-fixture-001'],
  }
}

function captureItem(state: SourceGalleryState) {
  return {
    id: 'capture:fixture',
    root_path: '/fixture/capture',
    relative_path: 'field-notes.pdf',
    filename: 'field-notes.pdf',
    extension: '.pdf',
    state: 'imported',
    sha256: CONTENT_SHA,
    byte_size: 4096,
    modified_ns: 1,
    reason: null,
    linked_source: {
      id: SOURCE_ID,
      visual: sourceVisual(state),
    },
  }
}

function initialExpected(cell: SourceGalleryCell): Record<string, number> {
  const expected: Record<string, number> = {}
  if (cell.route === '/sources') increment(expected, 'GET /api/sources')
  if (cell.route === '/notebooks/[id]') {
    increment(expected, 'GET /api/sources', 2)
  }
  if (cell.route === '/knowledge' && cell.flags === 'enabled') increment(expected, 'GET /api/sources')
  if (cell.route === '/capture') {
    increment(expected, 'GET /api/capture/roots')
    increment(expected, 'GET /api/capture/items')
  }
  if (cell.route === '/search') increment(expected, 'POST /api/search')
  if (
    cell.flags === 'enabled'
    && (cell.state === 'ready' || cell.state === 'compact' || cell.state === 'missing-corrupt')
  ) {
    increment(expected, 'GET /api/sources/source:fixture/visual')
  }
  return expected
}

function record(
  page: Page,
  ledger: SourceGalleryRequestLedger,
  route: Route,
  status: number,
): string {
  const request = route.request()
  const canonicalPath = canonicalStudyApiPath(new URL(request.url()).pathname)
  const label = requestLabel(request.method(), canonicalPath)
  increment(ledger.seen, label)
  ledger.receipts.push({
    viewport: String(page.viewportSize()?.width ?? 'unknown'),
    method: request.method(),
    canonicalPath,
    status,
  })
  return label
}

function installExactRoute(
  page: Page,
  ledger: SourceGalleryRequestLedger,
  pathname: string,
  method: string,
  body: unknown | (() => unknown | Promise<unknown>),
): void {
  const canonical = canonicalStudyApiPath(pathname)
  page.route(url => pageOrigin(url.href) && canonicalStudyApiPath(url.pathname) === canonical, async (route) => {
    const accepted = route.request().method() === method
    const status = accepted ? 200 : 405
    const label = record(page, ledger, route, status)
    if (!accepted) ledger.unexpected.push(label)
    const responseBody = accepted
      ? typeof body === 'function' ? await body() : body
      : { detail: 'method not allowed' }
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(responseBody),
    })
  })
}

export async function installSourceGalleryFixture(
  page: Page,
  { cell, theme, viewport }: InstallOptions,
): Promise<SourceGalleryFixtureHandle> {
  await page.setViewportSize({ width: viewport.width, height: viewport.height })
  const base = await installVisualSystemFixture(page, {
    route: cell.route,
    theme,
    viewport,
    delegatedApiPrefixes: ['/api/sources', '/api/search', '/api/capture'],
  })

  const ledger: SourceGalleryRequestLedger = {
    expected: initialExpected(cell),
    seen: {},
    receipts: [],
    unexpected: [],
    external: [],
  }
  const expectCall = (label: string, count = 1) => increment(ledger.expected, label, count)
  let releaseData!: () => void
  const dataReady = new Promise<void>((resolve) => {
    releaseData = resolve
  })

  // The broad source guard is installed first. Playwright dispatches the most
  // recently registered matching route first, so exact handlers below win.
  await page.route(url => (
    pageOrigin(url.href)
    && canonicalStudyApiPath(url.pathname).startsWith('/api/sources/')
  ), async (route) => {
    const label = record(page, ledger, route, 0)
    ledger.unexpected.push(`${label} (failed)`)
    await route.abort()
  })

  installExactRoute(page, ledger, '/api/sources', 'GET', async () => {
    await dataReady
    return [sourceRow(cell.state)]
  })
  installExactRoute(page, ledger, '/api/sources/source:fixture', 'GET', () => sourceDetail(cell.state))
  installExactRoute(page, ledger, '/api/search', 'POST', () => ({
    total_count: 1,
    search_type: 'text',
    results: [{
      id: SOURCE_ID,
      title: 'Fixture field notes',
      parent_id: '',
      final_score: 0.98,
      matches: ['Exact fixture passage'],
      created: NOW,
      updated: NOW,
      source_type: 'upload',
      visual: sourceVisual(cell.state),
      visual_status: sourceStatus(cell.state),
    }],
  }))
  installExactRoute(page, ledger, '/api/capture/roots', 'GET', () => [{ path: '/fixture/capture' }])
  installExactRoute(page, ledger, '/api/capture/items', 'GET', async () => {
    await dataReady
    return [captureItem(cell.state)]
  })
  installExactRoute(page, ledger, '/api/sources/source:fixture/locate-passage', 'POST', {
    match: { start: 0, end: 21, score: 0.98, snippet: 'Exact fixture passage' },
  })
  installExactRoute(page, ledger, '/api/sources/source:fixture/visual:refresh', 'POST', {
    source_id: SOURCE_ID,
    command_id: 'command:refresh',
    content_sha256: CONTENT_SHA,
    asset_sha256: ASSET_SHA,
    origin: 'embedded',
    width: 64,
    height: 36,
    duration_ms: 10,
    outcome: 'queued',
    error_code: null,
  })
  const assetPath = '/api/sources/source:fixture/visual'
  page.route(url => (
    pageOrigin(url.href)
    && canonicalStudyApiPath(url.pathname) === assetPath
  ), async (route) => {
    const method = route.request().method()
    const accepted = method === 'GET' || method === 'DELETE'
    const status = accepted ? 200 : 405
    const label = record(page, ledger, route, status)
    if (!accepted) ledger.unexpected.push(label)
    await route.fulfill({
      status,
      contentType: method === 'GET' && accepted ? 'image/webp' : 'application/json',
      body: method === 'GET' && accepted
        ? cell.state === 'missing-corrupt' ? CORRUPT_WEBP_FIXTURE : WEBP_FIXTURE
        : JSON.stringify(method === 'DELETE' && accepted
          ? {
              source_id: SOURCE_ID,
              command_id: null,
              content_sha256: CONTENT_SHA,
              asset_sha256: null,
              origin: null,
              width: null,
              height: null,
              duration_ms: 0,
              outcome: 'deleted',
              error_code: null,
            }
          : { detail: 'method not allowed' }),
    })
  })

  await page.route(url => !pageOrigin(url.href), async (route) => {
    const url = route.request().url()
    ledger.external.push(url)
    await route.abort()
  })

  return { base, ledger, expectCall, releaseData }
}

export async function revealSourceGalleryCell(page: Page, cell: SourceGalleryCell): Promise<void> {
  if (cell.route === '/search') {
    const input = page.getByRole('textbox', { name: /search query/i })
    await input.fill('fixture evidence')
    await page.getByRole('button', { name: /search knowledge base/i }).click()
    await expect(page.getByRole('button', { name: 'Fixture field notes', exact: true })).toBeVisible()
  }
  if (cell.route === '/notebooks/[id]' && (page.viewportSize()?.width ?? 0) < 1024) {
    await page.getByRole('tab', { name: /^sources$/i }).click()
  }
}

export function sourceGalleryFrequency(labels: readonly string[]): Record<string, number> {
  return labels.reduce<Record<string, number>>((result, label) => {
    increment(result, label)
    return result
  }, {})
}

export function assertExactSourceGalleryLedger(fixture: SourceGalleryFixtureHandle): void {
  const baseExpected = withoutDelegatedFrequency(fixture.base.ledger.expected)
  const baseSeen = mergeFrequencyMaps(
    withoutDelegatedFrequency(fixture.base.ledger.seen),
    withoutDelegatedFrequency(frequencyMapFromLabels(fixture.base.studyLedger.seen)),
  )
  const delegatedExpected = { ...fixture.ledger.expected }
  const delegatedSeen = { ...fixture.ledger.seen }

  expect(fixture.base.ledger.unexpected, 'base unexpected same-origin API requests').toEqual([])
  expect(fixture.base.studyLedger.unexpected, 'base unexpected Study API requests').toEqual([])
  expect(fixture.base.ledger.external, 'base external requests').toEqual([])
  expect(fixture.ledger.unexpected, 'delegated unexpected API requests').toEqual([])
  expect(fixture.ledger.external, 'delegated external requests').toEqual([])
  expect(baseSeen, 'base expected-vs-seen').toEqual(baseExpected)
  expect(delegatedSeen, 'delegated expected-vs-seen').toEqual(delegatedExpected)
  expect(
    mergeFrequencyMaps(baseSeen, delegatedSeen),
    'combined base and delegated expected-vs-seen',
  ).toEqual(mergeFrequencyMaps(baseExpected, delegatedExpected))
}
