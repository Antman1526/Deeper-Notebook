import { expect, test } from '@playwright/test'
import { renameSync, writeFileSync } from 'node:fs'

import { SOURCE_GALLERY_CELLS } from '../src/lib/visual-system/route-manifest'
import {
  assertExactSourceGalleryLedger,
  installSourceGalleryFixture,
  revealSourceGalleryCell,
  SOURCE_GALLERY_THEMES,
  SOURCE_GALLERY_VIEWPORTS,
} from './fixtures/source-gallery'

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
  undersizedActions: string[]
  cumulativeLayoutShift: number
  scroll: {
    max: number
    before: number
    after: number
    initiallyContained: boolean
    finallyContained: boolean
  }
}

async function inspectSourceGalleryGeometry(page: import('@playwright/test').Page): Promise<GeometryReceipt> {
  return page.evaluate(() => {
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

    const ids = Array.from(document.querySelectorAll('[id]')).map(element => element.id)
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))]
    const brokenImages = Array.from(document.images)
      .filter(visible)
      .filter(image => !image.complete || image.naturalWidth <= 0 || image.naturalHeight <= 0)
      .map(image => image.alt || image.src)

    const main = document.querySelector('main') ?? document.body
    const lowerCandidates = Array.from(main.querySelectorAll<HTMLElement>(
      '[role="listitem"], article, section, form, [role="dialog"], p, button',
    )).filter(visible)
    const lower = lowerCandidates.at(-1) ?? roots.at(-1) ?? main
    lower.setAttribute('data-dn-source-gallery-lower', 'true')

    const scrollableAncestor = (element: Element): HTMLElement | null => {
      let current = element.parentElement
      while (current && current !== document.body) {
        const style = window.getComputedStyle(current)
        if (
          /(auto|scroll)/.test(style.overflowY)
          && current.scrollHeight > current.clientHeight + 1
        ) return current
        current = current.parentElement
      }
      return null
    }
    const elementOwner = scrollableAncestor(lower)
    const documentOwner = document.scrollingElement as HTMLElement
    const owner = elementOwner ?? documentOwner
    const viewportTop = () => elementOwner ? elementOwner.getBoundingClientRect().top : 0
    const viewportBottom = () => elementOwner
      ? elementOwner.getBoundingClientRect().bottom
      : window.innerHeight
    const targetContained = () => {
      const rect = lower.getBoundingClientRect()
      return rect.top >= viewportTop() - 1
        && rect.bottom <= viewportBottom() + 1
        && rect.left >= -1
        && rect.right <= window.innerWidth + 1
    }
    owner.scrollTop = 0
    const before = owner.scrollTop
    const initiallyContained = targetContained()
    if (!initiallyContained) lower.scrollIntoView({ block: 'end', inline: 'nearest' })
    const after = owner.scrollTop

    const shift = (window as Window & {
      __dnVisualSystemLayoutShift?: { value: number }
    }).__dnVisualSystemLayoutShift?.value ?? 0
    const root = document.documentElement
    return {
      brokenImages,
      duplicateIds,
      horizontalOverflow: Math.max(0, root.scrollWidth - root.clientWidth),
      cardOverflow,
      undersizedActions,
      cumulativeLayoutShift: shift,
      scroll: {
        max: Math.max(0, owner.scrollHeight - owner.clientHeight),
        before,
        after,
        initiallyContained,
        finallyContained: targetContained(),
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

          const geometry = await inspectSourceGalleryGeometry(page)
          expect(geometry.brokenImages, `${cell.id}/${theme}/${viewport.name} broken images`).toEqual([])
          expect(geometry.duplicateIds, `${cell.id}/${theme}/${viewport.name} duplicate IDs`).toEqual([])
          expect(geometry.horizontalOverflow, `${cell.id}/${theme}/${viewport.name} horizontal overflow`).toBe(0)
          expect(geometry.cardOverflow, `${cell.id}/${theme}/${viewport.name} card bounds`).toEqual([])
          expect(geometry.undersizedActions, `${cell.id}/${theme}/${viewport.name} 44px targets`).toEqual([])
          expect(Number.isFinite(geometry.cumulativeLayoutShift)).toBe(true)
          expect(geometry.cumulativeLayoutShift, `${cell.id}/${theme}/${viewport.name} CLS`).toBeLessThanOrEqual(0.05)
          if (!geometry.scroll.initiallyContained) {
            expect(geometry.scroll.after, `${cell.id}/${theme}/${viewport.name} scroll advance`).toBeGreaterThan(geometry.scroll.before)
          }
          expect(geometry.scroll.finallyContained, `${cell.id}/${theme}/${viewport.name} lower content`).toBe(true)
          expect(consoleErrors.filter(error => !/Download the React DevTools/i.test(error))).toEqual([])
          expect(pageErrors).toEqual([])
          assertExactSourceGalleryLedger(fixture.ledger)
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
        if (cell.route === '/sources') {
          await expect(page.locator('[data-dn-sources-table]')).toBeVisible()
        }
        const visualReceipts = fixture.ledger.receipts.filter(receipt => (
          receipt.canonicalPath.endsWith('/visual')
          || receipt.canonicalPath.endsWith('/visual:refresh')
        ))
        expect(visualReceipts, `${cell.id}/${viewport.name} visual ledger`).toEqual([])
        assertExactSourceGalleryLedger(fixture.ledger)
        recordRuntimeReceipt(fixture)
        await context.close()
      }
    }
  })
})
