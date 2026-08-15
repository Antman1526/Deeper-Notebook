import { expect, test, type Locator } from '@playwright/test'
import { renameSync, writeFileSync } from 'node:fs'

import { SOURCE_GALLERY_CELLS } from '../src/lib/visual-system/route-manifest'
import {
  assertExactSourceGalleryLedger,
  installSourceGalleryFixture,
  revealSourceGalleryCell,
  SOURCE_GALLERY_THEMES,
  SOURCE_GALLERY_VIEWPORTS,
} from './fixtures/source-gallery'

const SOURCE_GALLERY_LOWER_CONTENT_SELECTOR_BY_ROUTE = {
  '/sources': 'main [data-dn-source-gallery="true"] [data-dn-source-cover] .dn-source-cover__actions button:last-child',
  '/notebooks/[id]': 'main [data-dn-source-cover="true"]',
  '/knowledge': '[data-dn-recent-source-slot="true"] [role="listitem"]:last-child',
  '/search': 'main [data-dn-source-cover="true"]',
  '/capture': 'main article:has([data-testid="capture-linked-source-cover"])',
} as const

const ROLLBACK_LEGACY_LANDMARK_BY_ROUTE = {
  '/sources': '[data-dn-sources-table="true"]',
  '/notebooks/[id]': 'role=button[name="Add Source"]',
  '/knowledge': 'role=button[name="Split pane right"]',
  '/search': 'main #search-query',
  '/capture': 'main input[aria-label="Capture folder path"]',
} as const

const ENABLED_BUILD = (
  process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 === '1'
  && process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS === '1'
)
const EXPLICIT_OFF_BUILD = (
  process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 === '0'
  && process.env.NEXT_PUBLIC_DN_SOURCE_VISUALS === '0'
)

const runtimeBudget = {
  maximumCls: 0,
  viewportCells: 0,
  requestCount: 0,
  visualRequestCount: 0,
  visualMutationCount: 0,
  unexpectedCount: 0,
  externalCount: 0,
  requestCounts: {} as Record<string, number>,
}

function recordRuntimeReceipt(
  fixture: Awaited<ReturnType<typeof installSourceGalleryFixture>>,
  cumulativeLayoutShift?: number,
): void {
  runtimeBudget.viewportCells += 1
  if (cumulativeLayoutShift !== undefined) {
    runtimeBudget.maximumCls = Math.max(runtimeBudget.maximumCls, cumulativeLayoutShift)
  }
  runtimeBudget.unexpectedCount += fixture.ledger.unexpected.length
  runtimeBudget.externalCount += fixture.ledger.external.length
  for (const receipt of fixture.ledger.receipts) {
    runtimeBudget.requestCount += 1
    const label = `${receipt.method} ${receipt.canonicalPath} ${receipt.status}`
    runtimeBudget.requestCounts[label] = (runtimeBudget.requestCounts[label] ?? 0) + 1
    if (receipt.canonicalPath.endsWith('/visual')) runtimeBudget.visualRequestCount += 1
    if (receipt.canonicalPath.endsWith('/visual:refresh') || (
      receipt.canonicalPath.endsWith('/visual') && receipt.method === 'DELETE'
    )) runtimeBudget.visualMutationCount += 1
  }
}

function writeRuntimeBudgetReceipt(): void {
  if (!ENABLED_BUILD && !EXPLICIT_OFF_BUILD) return
  const mode = ENABLED_BUILD ? 'enabled' : 'explicit-off'
  const expectedViewportCells = ENABLED_BUILD ? 96 : 20
  const passed = (
    runtimeBudget.viewportCells === expectedViewportCells
    && runtimeBudget.maximumCls <= 0.05
    && runtimeBudget.unexpectedCount === 0
    && runtimeBudget.externalCount === 0
    && (ENABLED_BUILD || (
      runtimeBudget.visualRequestCount === 0
      && runtimeBudget.visualMutationCount === 0
    ))
  )
  const receiptPath = process.env.SOURCE_GALLERY_RUNTIME_BUDGET_RECEIPT
    ?? `/tmp/deeper-notebook-source-gallery-runtime-${mode}.json`
  const temporaryPath = `${receiptPath}.tmp-${process.pid}`
  const receipt = {
    schema: 'deeper-notebook.source-gallery-runtime-budget.v1',
    mode,
    maximumCls: runtimeBudget.maximumCls,
    clsLimit: 0.05,
    viewportCells: runtimeBudget.viewportCells,
    expectedViewportCells,
    queryCounts: {
      total: runtimeBudget.requestCount,
      byMethodPathStatus: runtimeBudget.requestCounts,
    },
    visualRequestCount: runtimeBudget.visualRequestCount,
    visualMutationCount: runtimeBudget.visualMutationCount,
    unexpectedCount: runtimeBudget.unexpectedCount,
    externalCount: runtimeBudget.externalCount,
    passed,
  }
  writeFileSync(temporaryPath, `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 })
  renameSync(temporaryPath, receiptPath)
}

type GeometryReceipt = {
  brokenImages: string[]
  duplicateIds: string[]
  horizontalOverflow: number
  cardOverflow: string[]
  sourceSurfaceFailures: string[]
  sourceSurfaces: Array<{
    label: string
    horizontalClippingOwner: string
    horizontalClippingOwners: string[]
    failedHorizontalClippingOwners: string[]
    verticalClippingOwner: string
    verticalClippingOwners: string[]
    failedVerticalClippingOwners: string[]
    documentViewportContained: boolean
    verticalScrollOwner: string
    verticalScrollClientHeight: number
    verticalScrollHeight: number
    initialContained: boolean
    finallyContained: boolean
  }>
  undersizedActions: string[]
  cumulativeLayoutShift: number
  scroll: {
    marker: string
    horizontalClippingOwner: string
    horizontalClippingOwners: string[]
    failedHorizontalClippingOwners: string[]
    verticalClippingOwner: string
    verticalClippingOwners: string[]
    failedVerticalClippingOwners: string[]
    documentViewportContained: boolean
    verticalScrollOwner: string
    verticalScrollClientHeight: number
    verticalScrollHeight: number
    max: number
    before: number
    after: number
    initiallyContained: boolean
    finallyContained: boolean
  }
}

async function markRouteSpecificLowerContent(
  page: import('@playwright/test').Page,
  route: (typeof SOURCE_GALLERY_CELLS)[number]['route'],
): Promise<void> {
  const selector = SOURCE_GALLERY_LOWER_CONTENT_SELECTOR_BY_ROUTE[route]
  const marker = page.locator(selector)
  await expect(marker, `${route} exact lower-content selector`).toHaveCount(1)
  await marker.evaluate((element) => element.setAttribute('data-dn-source-gallery-lower', 'true'))
}

async function expectRollbackLegacyLandmark(
  page: import('@playwright/test').Page,
  route: (typeof SOURCE_GALLERY_CELLS)[number]['route'],
): Promise<void> {
  const selector = ROLLBACK_LEGACY_LANDMARK_BY_ROUTE[route]
  const landmark = route === '/notebooks/[id]'
    ? page.getByRole('button', { name: 'Add Source', exact: true })
    : route === '/knowledge'
      ? page.getByRole('button', { name: 'Split pane right', exact: true })
      : page.locator(selector)
  await expect(landmark, `${route} usable legacy landmark`).toHaveCount(1)
  await expect(landmark, `${route} usable legacy landmark`).toBeVisible()

  if (route === '/sources') {
    const action = landmark.locator(
      'button:enabled:visible, a[href]:visible, input:enabled:visible, select:enabled:visible, textarea:enabled:visible, [role="button"]:not([aria-disabled="true"]):visible',
    ).first()
    await expectEnabledFocusable(action, `${route} legacy table action`)
    return
  }

  if (route === '/search' || route === '/capture') {
    await expect(landmark, `${route} editable legacy field`).toBeEditable({ timeout: 1_000 })
  }
  await expectEnabledFocusable(landmark, `${route} usable legacy landmark`)
}

async function expectEnabledFocusable(control: Locator, label: string): Promise<void> {
  await expect(control, label).toBeEnabled({ timeout: 1_000 })
  await control.focus()
  await expect(control, `${label} focus`).toBeFocused()
}

async function inspectSourceGalleryGeometry(page: import('@playwright/test').Page): Promise<GeometryReceipt> {
  return page.evaluate(() => {
    type ScrollOwner = HTMLElement | null

    const visible = (element: Element): element is HTMLElement => {
      const style = window.getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return element instanceof HTMLElement
        && style.display !== 'none'
        && style.visibility !== 'hidden'
        && Number(style.opacity) !== 0
        && rect.width > 0
        && rect.height > 0
    }
    const contained = (inner: DOMRect, outer: DOMRect): boolean => (
      inner.left >= outer.left - 1
      && inner.right <= outer.right + 1
      && inner.top >= outer.top - 1
      && inner.bottom <= outer.bottom + 1
    )
    const describe = (element: Element): string => (
      element.getAttribute('aria-label')
      || element.textContent?.trim().slice(0, 80)
      || element.tagName.toLowerCase()
    )

    const clippingOwners = (element: HTMLElement, axis: 'x' | 'y'): HTMLElement[] => {
      const owners: HTMLElement[] = []
      let current = element.parentElement
      while (current) {
        const style = window.getComputedStyle(current)
        const overflow = axis === 'x' ? style.overflowX : style.overflowY
        if (['hidden', 'clip', 'auto', 'scroll'].includes(overflow)) owners.push(current)
        current = current.parentElement
      }
      return owners
    }
    const verticalScrollOwner = (element: HTMLElement): ScrollOwner => {
      let current = element.parentElement
      while (current) {
        const style = window.getComputedStyle(current)
        if (['auto', 'scroll'].includes(style.overflowY)
          && current.scrollHeight > current.clientHeight + 1) return current
        current = current.parentElement
      }
      return null
    }
    const ownerName = (owner: ScrollOwner): string => {
      if (!owner) return 'document'
      return owner.id
        || owner.getAttribute('data-testid')
        || owner.getAttribute('aria-label')
        || owner.tagName.toLowerCase()
    }
    const ownerViewport = (owner: ScrollOwner): DOMRect => (
      owner
        ? owner.getBoundingClientRect()
        : new DOMRect(0, 0, window.innerWidth, window.innerHeight)
    )
    const ownerMetrics = (owner: ScrollOwner) => {
      if (owner) return { clientHeight: owner.clientHeight, scrollHeight: owner.scrollHeight }
      return {
        clientHeight: window.innerHeight,
        scrollHeight: Math.max(
          document.documentElement?.scrollHeight ?? 0,
          document.body?.scrollHeight ?? 0,
        ),
      }
    }
    const readScrollTop = (owner: ScrollOwner): number => owner ? owner.scrollTop : window.scrollY
    const writeScrollTop = (owner: ScrollOwner, value: number): void => {
      if (owner) owner.scrollTop = value
      else window.scrollTo({ top: value, left: 0, behavior: 'auto' })
    }
    const maxScrollTop = (owner: ScrollOwner): number => {
      const metrics = ownerMetrics(owner)
      return Math.max(0, metrics.scrollHeight - metrics.clientHeight)
    }
    const clippingScrollOffsets = (horizontalOwners: HTMLElement[], verticalOwners: HTMLElement[]) => (
      Array.from(new Set([...horizontalOwners, ...verticalOwners])).map(owner => ({
        owner,
        scrollLeft: owner.scrollLeft,
        scrollTop: owner.scrollTop,
      }))
    )
    const restoreClippingOffsets = (offsets: Array<{ owner: HTMLElement; scrollLeft: number; scrollTop: number }>): void => {
      for (const { owner, scrollLeft, scrollTop } of offsets) {
        owner.scrollLeft = scrollLeft
        owner.scrollTop = scrollTop
      }
    }
    const isScrollableOnAxis = (owner: HTMLElement, axis: 'x' | 'y'): boolean => {
      const style = window.getComputedStyle(owner)
      const overflow = axis === 'x' ? style.overflowX : style.overflowY
      return ['auto', 'scroll'].includes(overflow)
        && (axis === 'x'
          ? owner.scrollWidth > owner.clientWidth + 1
          : owner.scrollHeight > owner.clientHeight + 1)
    }
    const revealWithinScrollChain = (
      element: HTMLElement,
      horizontalOwners: HTMLElement[],
      verticalOwners: HTMLElement[],
    ): void => {
      for (const owner of horizontalOwners) {
        if (!isScrollableOnAxis(owner, 'x')) continue
        const rect = element.getBoundingClientRect()
        const viewport = ownerViewport(owner)
        const delta = rect.left < viewport.left
          ? rect.left - viewport.left
          : rect.right > viewport.right
            ? rect.right - viewport.right
            : 0
        if (delta !== 0) owner.scrollLeft += delta
      }
      for (const owner of verticalOwners) {
        if (!isScrollableOnAxis(owner, 'y')) continue
        const rect = element.getBoundingClientRect()
        const viewport = ownerViewport(owner)
        const delta = rect.top < viewport.top
          ? rect.top - viewport.top
          : rect.bottom > viewport.bottom
            ? rect.bottom - viewport.bottom
            : 0
        if (delta !== 0) owner.scrollTop += delta
      }
      const rect = element.getBoundingClientRect()
      const viewport = new DOMRect(0, 0, window.innerWidth, window.innerHeight)
      const left = rect.left < viewport.left
        ? window.scrollX + rect.left - viewport.left
        : rect.right > viewport.right
          ? window.scrollX + rect.right - viewport.right
          : window.scrollX
      const top = rect.top < viewport.top
        ? window.scrollY + rect.top - viewport.top
        : rect.bottom > viewport.bottom
          ? window.scrollY + rect.bottom - viewport.bottom
          : window.scrollY
      if (left !== window.scrollX || top !== window.scrollY) {
        window.scrollTo({ left, top, behavior: 'auto' })
      }
    }
    const containedByOwners = (
      element: HTMLElement,
      horizontalOwners: HTMLElement[],
      verticalOwners: HTMLElement[],
    ) => {
      const rect = element.getBoundingClientRect()
      const documentViewport = new DOMRect(0, 0, window.innerWidth, window.innerHeight)
      const failedHorizontalClippingOwners = horizontalOwners
        .filter(owner => {
          const viewport = ownerViewport(owner)
          return rect.left < viewport.left - 1 || rect.right > viewport.right + 1
        })
        .map(ownerName)
      const failedVerticalClippingOwners = verticalOwners
        .filter(owner => {
          const viewport = ownerViewport(owner)
          return rect.top < viewport.top - 1 || rect.bottom > viewport.bottom + 1
        })
        .map(ownerName)
      const documentViewportContained = contained(rect, documentViewport)
      return {
        contained: documentViewportContained
          && failedHorizontalClippingOwners.length === 0
          && failedVerticalClippingOwners.length === 0,
        failedHorizontalClippingOwners,
        failedVerticalClippingOwners,
        documentViewportContained,
      }
    }

    const roots = Array.from(document.querySelectorAll('[data-dn-source-cover]')).filter(visible)
    const cardOverflow: string[] = []
    const undersizedActions: string[] = []
    for (const root of roots) {
      const rootRect = root.getBoundingClientRect()
      const bounded = root.querySelectorAll(
        '.dn-source-cover__title, .dn-source-cover__type, .dn-source-cover__status, .dn-source-cover__provenance, button',
      )
      for (const element of Array.from(bounded).filter(visible)) {
        if (!contained(element.getBoundingClientRect(), rootRect)) {
          cardOverflow.push(describe(element))
        }
      }
      for (const action of Array.from(root.querySelectorAll('button')).filter(visible)) {
        const rect = action.getBoundingClientRect()
        if (rect.width < 44 || rect.height < 44) {
          undersizedActions.push(`${describe(action)}:${rect.width}x${rect.height}`)
        }
      }
    }

    const sourceSurfaceSet = new Set<HTMLElement>([
      ...roots,
      ...Array.from(document.querySelectorAll<HTMLElement>(
        '[data-dn-source-gallery="true"] [role="listitem"]',
      )).filter(visible),
    ])
    const sourceSurfaceFailures: string[] = []
    const sourceSurfaces = Array.from(sourceSurfaceSet).map((surface) => {
      const horizontalOwners = clippingOwners(surface, 'x')
      const verticalOwners = clippingOwners(surface, 'y')
      const scrollOwner = verticalScrollOwner(surface)
      const offsets = clippingScrollOffsets(horizontalOwners, verticalOwners)
      const documentOffset = { left: window.scrollX, top: window.scrollY }
      writeScrollTop(scrollOwner, 0)
      const initialContainment = containedByOwners(surface, horizontalOwners, verticalOwners)
      if (!initialContainment.contained) {
        revealWithinScrollChain(surface, horizontalOwners, verticalOwners)
      }
      const finalContainment = containedByOwners(surface, horizontalOwners, verticalOwners)
      const metrics = ownerMetrics(scrollOwner)
      restoreClippingOffsets(offsets)
      window.scrollTo({ left: documentOffset.left, top: documentOffset.top, behavior: 'auto' })
      const result = {
        label: describe(surface),
        horizontalClippingOwner: ownerName(horizontalOwners[0] ?? null),
        horizontalClippingOwners: horizontalOwners.map(ownerName),
        failedHorizontalClippingOwners: finalContainment.failedHorizontalClippingOwners,
        verticalClippingOwner: ownerName(verticalOwners[0] ?? null),
        verticalClippingOwners: verticalOwners.map(ownerName),
        failedVerticalClippingOwners: finalContainment.failedVerticalClippingOwners,
        documentViewportContained: finalContainment.documentViewportContained,
        verticalScrollOwner: ownerName(scrollOwner),
        verticalScrollClientHeight: metrics.clientHeight,
        verticalScrollHeight: metrics.scrollHeight,
        initialContained: initialContainment.contained,
        finallyContained: finalContainment.contained,
      }
      if (!finalContainment.contained) {
        const rect = surface.getBoundingClientRect()
        sourceSurfaceFailures.push(
          `${result.label} outside x=${result.failedHorizontalClippingOwners.join(',') || 'none'} y=${result.failedVerticalClippingOwners.join(',') || 'none'} document=${result.documentViewportContained} rect=${Math.round(rect.width)}x${Math.round(rect.height)} owners-x=${result.horizontalClippingOwners.join(',') || 'document'} owners-y=${result.verticalClippingOwners.join(',') || 'document'} scroll=${result.verticalScrollOwner} (${result.verticalScrollHeight}/${result.verticalScrollClientHeight})`,
        )
      }
      return result
    })

    const ids = Array.from(document.querySelectorAll('[id]')).map(element => element.id)
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))]
    const brokenImages = Array.from(document.images)
      .filter(visible)
      .filter(image => !image.complete || image.naturalWidth <= 0 || image.naturalHeight <= 0)
      .map(image => image.alt || image.src)

    const markers = Array.from(document.querySelectorAll<HTMLElement>('[data-dn-source-gallery-lower]')).filter(visible)
    const lower = markers.length === 1 ? markers[0] : null
    const horizontalOwners = lower ? clippingOwners(lower, 'x') : []
    const verticalOwners = lower ? clippingOwners(lower, 'y') : []
    const scrollOwner = lower ? verticalScrollOwner(lower) : null
    const max = maxScrollTop(scrollOwner)
    const offsets = clippingScrollOffsets(horizontalOwners, verticalOwners)
    const documentOffset = { left: window.scrollX, top: window.scrollY }
    writeScrollTop(scrollOwner, 0)
    const before = readScrollTop(scrollOwner)
    const initialContainment = lower
      ? containedByOwners(lower, horizontalOwners, verticalOwners)
      : {
          contained: false,
          failedHorizontalClippingOwners: [],
          failedVerticalClippingOwners: [],
          documentViewportContained: false,
    }
    if (lower && !initialContainment.contained) {
      revealWithinScrollChain(lower, horizontalOwners, verticalOwners)
    }
    const after = readScrollTop(scrollOwner)
    const finalContainment = lower
      ? containedByOwners(lower, horizontalOwners, verticalOwners)
      : {
          contained: false,
          failedHorizontalClippingOwners: [],
          failedVerticalClippingOwners: [],
          documentViewportContained: false,
    }
    const metrics = ownerMetrics(scrollOwner)
    restoreClippingOffsets(offsets)
    window.scrollTo({ left: documentOffset.left, top: documentOffset.top, behavior: 'auto' })

    const shift = (window as Window & {
      __dnVisualSystemLayoutShift?: { value: number }
    }).__dnVisualSystemLayoutShift?.value ?? 0
    const root = document.documentElement
    return {
      brokenImages,
      duplicateIds,
      horizontalOverflow: Math.max(0, root.scrollWidth - root.clientWidth),
      cardOverflow,
      sourceSurfaceFailures,
      sourceSurfaces,
      undersizedActions,
      cumulativeLayoutShift: shift,
      scroll: {
        marker: lower ? describe(lower) : '',
        horizontalClippingOwner: ownerName(horizontalOwners[0] ?? null),
        horizontalClippingOwners: horizontalOwners.map(ownerName),
        failedHorizontalClippingOwners: finalContainment.failedHorizontalClippingOwners,
        verticalClippingOwner: ownerName(verticalOwners[0] ?? null),
        verticalClippingOwners: verticalOwners.map(ownerName),
        failedVerticalClippingOwners: finalContainment.failedVerticalClippingOwners,
        documentViewportContained: finalContainment.documentViewportContained,
        verticalScrollOwner: ownerName(scrollOwner),
        verticalScrollClientHeight: metrics.clientHeight,
        verticalScrollHeight: metrics.scrollHeight,
        max,
        before,
        after,
        initiallyContained: initialContainment.contained,
        finallyContained: finalContainment.contained,
      },
    }
  })
}

async function assertEnabledState(
  page: import('@playwright/test').Page,
  state: (typeof SOURCE_GALLERY_CELLS)[number]['state'],
): Promise<void> {
  const covers = page.locator('[data-dn-source-cover]')
  await expect(covers.first()).toBeVisible()
  if (state === 'processing') {
    await expect(page.getByRole('status', { name: '' }).filter({ hasText: 'Preparing visual cover' }).first()).toBeVisible()
  } else if (state === 'failed') {
    await expect(page.getByText('Visual cover unavailable').first()).toBeVisible()
  } else if (state === 'missing-corrupt') {
    await expect(page.locator('[data-dn-source-cover] img')).toHaveCount(0)
    await expect(page.getByText('Visual cover unavailable').first()).toBeVisible()
  } else {
    const image = page.locator('[data-dn-source-cover] img').first()
    await expect(image).toBeVisible()
    await expect(image).toHaveAttribute('alt', /source-derived diagram/i)
    await expect(page.getByText('Embedded image').first()).toBeVisible()
  }
}

async function exerciseCellInteraction(
  page: import('@playwright/test').Page,
  cell: (typeof SOURCE_GALLERY_CELLS)[number],
  fixture: Awaited<ReturnType<typeof installSourceGalleryFixture>>,
): Promise<void> {
  if (cell.id === 'sources-ready') {
    fixture.expectCall('POST /api/sources/source:fixture/visual:refresh')
    fixture.expectCall('GET /api/sources/source:fixture')
    const refresh = page.getByRole('button', { name: 'Refresh visual for Fixture field notes' })
    await refresh.evaluate((button: HTMLButtonElement) => {
      button.click()
      button.click()
    })
    await expect.poll(() => fixture.ledger.seen['POST /api/sources/source:fixture/visual:refresh'] ?? 0).toBe(1)
  }
  if (cell.id === 'sources-missing-corrupt') {
    fixture.expectCall('DELETE /api/sources/source:fixture/visual')
    fixture.expectCall('GET /api/sources/source:fixture')
    const remove = page.getByRole('button', { name: 'Remove visual for Fixture field notes' })
    await remove.evaluate((button: HTMLButtonElement) => {
      button.click()
      button.click()
    })
    await expect.poll(() => fixture.ledger.seen['DELETE /api/sources/source:fixture/visual'] ?? 0).toBe(1)
  }
  if (cell.id === 'search-ready') {
    fixture.expectCall('POST /api/sources/source:fixture/locate-passage')
    const invoker = page.getByRole('button', { name: 'View evidence for Fixture field notes' })
    await invoker.click()
    await expect(page.getByRole('dialog', { name: /Evidence in Fixture field notes/i })).toBeVisible()
    await expect(page.getByText('Exact fixture passage').last()).toBeVisible()
    await page.getByRole('button', { name: 'Close evidence peek' }).click()
    await expect(invoker).toBeFocused()
  }
}

test.describe('source gallery visual contract', () => {
  test.afterAll(() => writeRuntimeBudgetReceipt())

  test('manifest keeps exact routes, themes, viewports, and rollback cells', () => {
    expect(SOURCE_GALLERY_THEMES).toEqual([
      'gemini-forward-light',
      'research-core-dark',
      'high-contrast-light',
    ])
    expect(SOURCE_GALLERY_VIEWPORTS).toEqual([
      { name: 'mobile', width: 320, height: 844 },
      { name: 'narrow', width: 768, height: 1024 },
      { name: 'compact-desktop', width: 1020, height: 631 },
      { name: 'large-desktop', width: 1440, height: 900 },
    ])
    expect(SOURCE_GALLERY_CELLS.filter(cell => cell.state === 'feature-off')).toHaveLength(5)
  })

  test('fixture rejects wrong methods, unknown same-origin APIs, and external origins', async ({ page }) => {
    const cell = SOURCE_GALLERY_CELLS.find(candidate => candidate.id === 'sources-ready')
    expect(cell).toBeDefined()
    const fixture = await installSourceGalleryFixture(page, {
      cell: cell!,
      theme: 'gemini-forward-light',
      viewport: SOURCE_GALLERY_VIEWPORTS[0],
    })
    fixture.releaseData()
    await page.goto(cell!.browserPath)

    const outcomes = await page.evaluate(async () => {
      const wrongMethod = await fetch('/api/sources/source%3Afixture/visual:refresh', {
        method: 'PUT',
      })
      let unknown = 'resolved'
      let external = 'resolved'
      try { await fetch('/api/sources/source%3Afixture/visual:unknown') } catch { unknown = 'rejected' }
      try { await fetch('https://evil.example/visual.webp') } catch { external = 'rejected' }
      return { status: wrongMethod.status, unknown, external }
    })

    expect(outcomes).toEqual({ status: 405, unknown: 'rejected', external: 'rejected' })
    expect(fixture.ledger.unexpected).toContain('PUT /api/sources/source:fixture/visual:refresh')
    expect(fixture.ledger.external).toContain('https://evil.example/visual.webp')
  })

  test('the final ledger rejects base-frequency mismatches instead of checking only delegated traffic', async ({ page }) => {
    const cell = SOURCE_GALLERY_CELLS.find(candidate => candidate.id === 'sources-ready')!
    const fixture = await installSourceGalleryFixture(page, {
      cell,
      theme: 'gemini-forward-light',
      viewport: SOURCE_GALLERY_VIEWPORTS[0],
    })
    await page.goto(cell.browserPath)
    fixture.releaseData()

    fixture.base.ledger.expected = { 'GET /config': 1 }
    fixture.base.ledger.seen = {}

    expect(() => assertExactSourceGalleryLedger(fixture)).toThrow(/base expected-vs-seen/i)
  })

  test('the final ledger fails closed on an unknown non-source same-origin API', async ({ page }) => {
    const cell = SOURCE_GALLERY_CELLS.find(candidate => candidate.id === 'sources-ready')!
    const fixture = await installSourceGalleryFixture(page, {
      cell,
      theme: 'gemini-forward-light',
      viewport: SOURCE_GALLERY_VIEWPORTS[0],
    })
    await page.goto(cell.browserPath)
    fixture.releaseData()

    const result = await page.evaluate(async () => {
      try {
        await fetch('/api/credentials/source-gallery-proof-unknown')
        return 'resolved'
      } catch {
        return 'rejected'
      }
    })
    expect(result).toBe('rejected')

    await expect.poll(() => fixture.base.ledger.unexpected).toContain(
      'GET /api/credentials/source-gallery-proof-unknown (failed)',
    )
    expect(() => assertExactSourceGalleryLedger(fixture)).toThrow(/base unexpected/i)
  })

  test('geometry rejects a clipped SourceCover instead of false-greening a broad final descendant', async ({ page }) => {
    await page.goto('/')
    await page.setViewportSize({ width: 320, height: 120 })
    await page.setContent(`
      <style>
        html, body { margin: 0; overflow: hidden; }
        #source-owner { width: 200px; height: 80px; overflow: hidden; }
        #unrelated-owner { width: 200px; height: 80px; overflow: auto; }
        #unrelated-filler { height: 120px; }
        [data-dn-source-cover] { display: block; width: 180px; height: 120px; }
        [data-dn-source-cover] button { width: 44px; height: 44px; }
      </style>
      <main>
        <div id="source-owner">
          <article data-dn-source-cover="true" data-dn-source-gallery-lower="true">
            <button type="button">Target cover action</button>
          </article>
        </div>
        <div id="unrelated-owner">
          <button type="button">Unrelated last descendant</button>
          <div id="unrelated-filler"></div>
        </div>
      </main>
    `)

    const geometry = await inspectSourceGalleryGeometry(page)
    expect(geometry.scroll.marker).toBe('Target cover action')
    expect(geometry.scroll.horizontalClippingOwner).toBe('source-owner')
    expect(geometry.scroll.verticalClippingOwner).toBe('source-owner')
    expect(geometry.sourceSurfaces).toEqual([
      expect.objectContaining({
        horizontalClippingOwner: 'source-owner',
        verticalClippingOwner: 'source-owner',
        initialContained: false,
        finallyContained: false,
      }),
    ])
  })

  test('geometry rejects a SourceCover clipped only on the horizontal axis', async ({ page }) => {
    await page.goto('/')
    await page.setViewportSize({ width: 320, height: 160 })
    await page.setContent(`
      <style>
        html, body { margin: 0; overflow: visible; }
        #horizontal-owner { width: 80px; height: 120px; overflow-x: clip; overflow-y: visible; }
        [data-dn-source-cover] { display: block; width: 120px; height: 80px; }
        [data-dn-source-cover] button { width: 44px; height: 44px; }
      </style>
      <main>
        <div id="horizontal-owner">
          <article data-dn-source-cover="true">
            <button type="button">Horizontally clipped cover action</button>
          </article>
        </div>
      </main>
    `)

    const geometry = await inspectSourceGalleryGeometry(page)
    expect(geometry.sourceSurfaces).toEqual([
      expect.objectContaining({
        horizontalClippingOwner: 'horizontal-owner',
        finallyContained: false,
      }),
    ])
    expect(geometry.sourceSurfaceFailures).toEqual([
      expect.stringContaining('horizontal-owner'),
    ])
  })

  test('geometry reports outer nested clipping owners for SourceCover and lower marker', async ({ page }) => {
    await page.goto('/')
    await page.setViewportSize({ width: 320, height: 160 })
    await page.setContent(`
      <style>
        html, body { margin: 0; overflow: visible; }
        #outer-owner { width: 80px; height: 80px; overflow: hidden; }
        #inner-owner { width: 120px; height: 80px; overflow: hidden; }
        [data-dn-source-cover] { display: block; width: 20px; height: 20px; margin-left: 90px; }
        [data-dn-source-cover] button { width: 44px; height: 44px; }
      </style>
      <main>
        <div id="outer-owner">
          <div id="inner-owner">
            <article data-dn-source-cover="true" data-dn-source-gallery-lower="true">
              <button type="button">Nested clipped cover action</button>
            </article>
          </div>
        </div>
      </main>
    `)

    const geometry = await inspectSourceGalleryGeometry(page)
    expect(geometry.sourceSurfaces).toEqual([
      expect.objectContaining({
        horizontalClippingOwners: ['inner-owner', 'outer-owner'],
        failedHorizontalClippingOwners: ['outer-owner'],
        verticalClippingOwners: ['inner-owner', 'outer-owner'],
        failedVerticalClippingOwners: [],
        documentViewportContained: true,
        finallyContained: false,
      }),
    ])
    expect(geometry.sourceSurfaceFailures).toEqual([
      expect.stringContaining('outer-owner'),
    ])
    expect(geometry.scroll).toEqual(expect.objectContaining({
      horizontalClippingOwners: ['inner-owner', 'outer-owner'],
      failedHorizontalClippingOwners: ['outer-owner'],
      verticalClippingOwners: ['inner-owner', 'outer-owner'],
      failedVerticalClippingOwners: [],
      documentViewportContained: true,
      finallyContained: false,
    }))
  })

  test('rollback landmarks reject visible disabled, read-only, and actionless route surfaces', async ({ page }) => {
    const hostileMarkupByRoute: Record<(typeof SOURCE_GALLERY_CELLS)[number]['route'], string> = {
      '/sources': '<main><section data-dn-sources-table="true"><button disabled>Open source</button></section></main>',
      '/notebooks/[id]': '<main><button disabled>Add Source</button></main>',
      '/knowledge': '<main aria-label="Knowledge workspace"><button disabled>Split pane right</button></main>',
      '/search': '<main><input id="search-query" readonly value="fixture" /></main>',
      '/capture': '<main><input aria-label="Capture folder path" disabled value="/fixture" /></main>',
    }

    for (const [route, markup] of Object.entries(hostileMarkupByRoute) as Array<[
      (typeof SOURCE_GALLERY_CELLS)[number]['route'],
      string,
    ]>) {
      await page.setContent(markup)
      await expect(expectRollbackLegacyLandmark(page, route)).rejects.toThrow()
    }
  })

  for (const cell of SOURCE_GALLERY_CELLS.filter(candidate => candidate.flags === 'enabled')) {
    for (const theme of SOURCE_GALLERY_THEMES) {
      test(`${cell.id} · ${theme} · four viewport contract`, async ({ browser }) => {
        test.skip(!ENABLED_BUILD, 'enabled Source Gallery build required')
        for (const viewport of SOURCE_GALLERY_VIEWPORTS) {
          const context = await browser.newContext({
            viewport: { width: viewport.width, height: viewport.height },
            colorScheme: theme === 'research-core-dark' ? 'dark' : 'light',
          })
          const page = await context.newPage()
          const consoleErrors: string[] = []
          const pageErrors: string[] = []
          page.on('console', message => {
            if (message.type() === 'error') consoleErrors.push(message.text())
          })
          page.on('pageerror', error => pageErrors.push(error.message))

          const fixture = await installSourceGalleryFixture(page, { cell, theme, viewport })
          await page.goto(cell.browserPath)
          await expect(page.locator('main')).toBeVisible()
          await page.evaluate(() => {
            const state = (window as Window & {
              __dnVisualSystemLayoutShift?: { value: number }
            }).__dnVisualSystemLayoutShift
            if (state) state.value = 0
          })
          fixture.releaseData()
          await revealSourceGalleryCell(page, cell)
          await assertEnabledState(page, cell.state)
          await exerciseCellInteraction(page, cell, fixture)
          await page.waitForTimeout(100)
          if (cell.route === '/notebooks/[id]') {
            // Mobile compact covers become visible only after the user selects
            // the Sources tab. CLS excludes user-input shifts; reset at that
            // exact activation boundary and measure the settled image surface.
            await page.evaluate(() => {
              const state = (window as Window & {
                __dnVisualSystemLayoutShift?: { value: number }
              }).__dnVisualSystemLayoutShift
              if (state) state.value = 0
            })
            await page.waitForTimeout(100)
          }

          await markRouteSpecificLowerContent(page, cell.route)
          const geometry = await inspectSourceGalleryGeometry(page)
          expect(geometry.brokenImages, `${cell.id}/${theme}/${viewport.name} broken images`).toEqual([])
          expect(geometry.duplicateIds, `${cell.id}/${theme}/${viewport.name} duplicate IDs`).toEqual([])
          expect(geometry.horizontalOverflow, `${cell.id}/${theme}/${viewport.name} horizontal overflow`).toBe(0)
          expect(geometry.cardOverflow, `${cell.id}/${theme}/${viewport.name} card bounds`).toEqual([])
          expect(geometry.sourceSurfaceFailures, `${cell.id}/${theme}/${viewport.name} SourceCover/card clipping owners`).toEqual([])
          expect(geometry.sourceSurfaces.length, `${cell.id}/${theme}/${viewport.name} visible SourceCover/card count`).toBeGreaterThan(0)
          for (const surface of geometry.sourceSurfaces) {
            expect(surface.horizontalClippingOwner, `${cell.id}/${theme}/${viewport.name} ${surface.label} horizontal clipping owner`).not.toBe('')
            expect(surface.failedHorizontalClippingOwners, `${cell.id}/${theme}/${viewport.name} ${surface.label} horizontal clipping containment`).toEqual([])
            expect(surface.verticalClippingOwner, `${cell.id}/${theme}/${viewport.name} ${surface.label} vertical clipping owner`).not.toBe('')
            expect(surface.failedVerticalClippingOwners, `${cell.id}/${theme}/${viewport.name} ${surface.label} vertical clipping containment`).toEqual([])
            expect(surface.documentViewportContained, `${cell.id}/${theme}/${viewport.name} ${surface.label} document viewport containment`).toBe(true)
            expect(surface.verticalScrollOwner, `${cell.id}/${theme}/${viewport.name} ${surface.label} vertical scroll owner`).not.toBe('')
            expect(surface.verticalScrollClientHeight, `${cell.id}/${theme}/${viewport.name} ${surface.label} scroll owner client height`).toBeGreaterThan(0)
            expect(surface.verticalScrollHeight, `${cell.id}/${theme}/${viewport.name} ${surface.label} scroll owner scroll height`).toBeGreaterThanOrEqual(surface.verticalScrollClientHeight)
            expect(surface.finallyContained, `${cell.id}/${theme}/${viewport.name} ${surface.label} final four-edge containment`).toBe(true)
          }
          expect(geometry.undersizedActions, `${cell.id}/${theme}/${viewport.name} 44px targets`).toEqual([])
          expect(Number.isFinite(geometry.cumulativeLayoutShift)).toBe(true)
          expect(geometry.cumulativeLayoutShift, `${cell.id}/${theme}/${viewport.name} CLS`).toBeLessThanOrEqual(0.05)
          expect(geometry.scroll.marker, `${cell.id}/${theme}/${viewport.name} route-specific lower marker`).not.toBe('')
          expect(geometry.scroll.horizontalClippingOwner, `${cell.id}/${theme}/${viewport.name} horizontal clipping owner`).not.toBe('')
          expect(geometry.scroll.failedHorizontalClippingOwners, `${cell.id}/${theme}/${viewport.name} horizontal clipping containment`).toEqual([])
          expect(geometry.scroll.verticalClippingOwner, `${cell.id}/${theme}/${viewport.name} vertical clipping owner`).not.toBe('')
          expect(geometry.scroll.failedVerticalClippingOwners, `${cell.id}/${theme}/${viewport.name} vertical clipping containment`).toEqual([])
          expect(geometry.scroll.documentViewportContained, `${cell.id}/${theme}/${viewport.name} lower document viewport containment`).toBe(true)
          expect(geometry.scroll.verticalScrollOwner, `${cell.id}/${theme}/${viewport.name} vertical scroll owner`).not.toBe('')
          expect(geometry.scroll.verticalScrollClientHeight, `${cell.id}/${theme}/${viewport.name} scroll owner client height`).toBeGreaterThan(0)
          expect(geometry.scroll.verticalScrollHeight, `${cell.id}/${theme}/${viewport.name} scroll owner scroll height`).toBeGreaterThanOrEqual(geometry.scroll.verticalScrollClientHeight)
          if (!geometry.scroll.initiallyContained) {
            expect(geometry.scroll.after, `${cell.id}/${theme}/${viewport.name} scroll advance`).toBeGreaterThan(geometry.scroll.before)
          }
          expect(geometry.scroll.finallyContained, `${cell.id}/${theme}/${viewport.name} lower content`).toBe(true)
          expect(consoleErrors.filter(error => !/Download the React DevTools/i.test(error))).toEqual([])
          expect(pageErrors).toEqual([])
          assertExactSourceGalleryLedger(fixture)
          recordRuntimeReceipt(fixture, geometry.cumulativeLayoutShift)
          await context.close()
        }
      })
    }
  }

  test('feature-off rollback keeps all five legacy routes usable with zero visual requests', async ({ browser }) => {
    test.skip(!EXPLICIT_OFF_BUILD, 'explicit dual-flag rollback build required')
    for (const cell of SOURCE_GALLERY_CELLS.filter(candidate => candidate.flags === 'feature-off')) {
      for (const viewport of SOURCE_GALLERY_VIEWPORTS) {
        const context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          colorScheme: 'light',
        })
        const page = await context.newPage()
        const fixture = await installSourceGalleryFixture(page, {
          cell,
          theme: 'gemini-forward-light',
          viewport,
        })
        await page.goto(cell.browserPath)
        await expect(page.locator('main')).toBeVisible()
        fixture.releaseData()
        await revealSourceGalleryCell(page, cell)
        await expect(page.locator('main')).toBeVisible()
        await expect(page.locator('[data-dn-source-cover]')).toHaveCount(0)
        await expectRollbackLegacyLandmark(page, cell.route)
        const visualReceipts = fixture.ledger.receipts.filter(receipt => (
          receipt.canonicalPath.endsWith('/visual')
          || receipt.canonicalPath.endsWith('/visual:refresh')
        ))
        expect(visualReceipts, `${cell.id}/${viewport.name} visual ledger`).toEqual([])
        assertExactSourceGalleryLedger(fixture)
        recordRuntimeReceipt(fixture)
        await context.close()
      }
    }
  })
})
