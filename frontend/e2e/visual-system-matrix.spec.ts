import { expect, test } from '@playwright/test'

import { VISUAL_ROUTE_MANIFEST, type VisualRouteEntry } from '../src/lib/visual-system/route-manifest'
import {
  expectedVisualRequestFrequency,
  frequencyMapFromLabels,
  installVisualSystemFixture,
  VISUAL_CELL_EXPECTED_REQUESTS,
  VISUAL_ROUTE_EXPECTED_REQUESTS,
  VISUAL_MATRIX_THEMES,
  VISUAL_MATRIX_VIEWPORTS,
  type VisualMatrixViewport,
} from './fixtures/visual-system'

test.describe('visual system matrix contract', () => {
  test('matrix contract covers exactly 22 routes by 3 themes by 4 viewports', () => {
    const cells = VISUAL_ROUTE_MANIFEST.flatMap((route) => VISUAL_MATRIX_THEMES.flatMap((theme) => (
      VISUAL_MATRIX_VIEWPORTS.map((viewport) => ({ route: route.route, theme, viewport: viewport.name }))
    )))

    expect(VISUAL_ROUTE_MANIFEST).toHaveLength(22)
    expect(VISUAL_MATRIX_THEMES).toEqual([
      'gemini-forward-light',
      'research-core-dark',
      'high-contrast-light',
    ])
    expect(VISUAL_MATRIX_VIEWPORTS).toEqual([
      { name: 'mobile', width: 320, height: 844 },
      { name: 'narrow', width: 768, height: 1024 },
      { name: 'compact-desktop', width: 1020, height: 631 },
      { name: 'large-desktop', width: 1440, height: 900 },
    ])
    expect(cells).toHaveLength(264)
    expect(new Set(cells.map((cell) => `${cell.route}:${cell.theme}:${cell.viewport}`)).size).toBe(264)
    expect(Object.keys(VISUAL_ROUTE_EXPECTED_REQUESTS).sort()).toEqual(
      VISUAL_ROUTE_MANIFEST.map((entry) => entry.route).sort(),
    )
    expect(Object.keys(VISUAL_CELL_EXPECTED_REQUESTS)).toHaveLength(264)
    expect(Object.keys(VISUAL_CELL_EXPECTED_REQUESTS).sort()).toEqual(
      cells.map((cell) => `${cell.route}|${cell.theme}|${cell.viewport}`).sort(),
    )
    expect(expectedVisualRequestFrequency(
      '/notebooks/[id]',
      'gemini-forward-light',
      VISUAL_MATRIX_VIEWPORTS.find((viewport) => viewport.name === 'mobile')!,
    )['GET /api/sources']).toBe(1)
    expect(expectedVisualRequestFrequency(
      '/notebooks/[id]',
      'gemini-forward-light',
      VISUAL_MATRIX_VIEWPORTS.find((viewport) => viewport.name === 'large-desktop')!,
    )['GET /api/sources']).toBe(2)
  })

  test('fixture rejects wrong methods and records an unexpected ledger entry', async ({ page }) => {
    const fixture = await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/')
    const response = await page.evaluate(async () => {
      const result = await fetch('/api/visual-system/method-probe', { method: 'POST' })
      return { status: result.status, body: await result.json() }
    })

    expect(response).toEqual({
      status: 405,
      body: { detail: 'method not allowed' },
    })
    expect(fixture.ledger.unexpected).toContain('POST /api/visual-system/method-probe')
  })

  test('fixture records unknown same-origin APIs without providing a success fallback', async ({ page }) => {
    const fixture = await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/')
    const result = await page.evaluate(async () => {
      try {
        await fetch('/api/visual-system/unknown')
        return 'resolved'
      } catch {
        return 'rejected'
      }
    })

    expect(result).toBe('rejected')
    await expect.poll(() => fixture.ledger.unexpected).toContain('GET /api/visual-system/unknown (failed)')
  })

  test('fixture aborts external API requests before path handlers', async ({ page }) => {
    const fixture = await installVisualSystemFixture(page, { theme: 'gemini-forward-light' })
    await page.goto('/')
    const wrongPort = Number(process.env.PLAYWRIGHT_PORT ?? 3117) + 1
    const result = await page.evaluate(async (port) => {
      const urls = [
        'https://evil.example/api/config',
        `http://127.0.0.1:${port}/api/config`,
      ]
      const results: string[] = []
      for (const url of urls) {
        try {
          await fetch(url)
          results.push('resolved')
        } catch {
          results.push('rejected')
        }
      }
      return results
    }, wrongPort)

    expect(result).toEqual(['rejected', 'rejected'])
    expect(fixture.ledger.external).toContain('https://evil.example/api/config')
    expect(fixture.ledger.external).toContain(`http://127.0.0.1:${wrongPort}/api/config`)
  })

  test('fixture fails closed when an exact route or cell request map is missing', () => {
    const hostileViewport = {
      ...VISUAL_MATRIX_VIEWPORTS[0],
      name: 'hostile-cell',
    } as unknown as typeof VISUAL_MATRIX_VIEWPORTS[number]

    expect(() => expectedVisualRequestFrequency(
      '/',
      VISUAL_MATRIX_THEMES[0],
      hostileViewport,
    )).toThrow(/exact expected request-frequency map/i)
    expect(() => expectedVisualRequestFrequency(
      '/hostile-route',
      VISUAL_MATRIX_THEMES[0],
      VISUAL_MATRIX_VIEWPORTS[0],
    )).toThrow(/exact expected request-frequency map/i)
  })

  test('geometry excludes visible landmark roles while retaining reachable native and ARIA controls', async ({ page }) => {
    await page.setContent(`
      <style>
        [data-matrix-candidate] { display: inline-block; min-width: 44px; min-height: 44px; }
      </style>
      <main role="main" data-matrix-candidate="landmark-shell">
        <button type="button" data-matrix-candidate="native-button">Save</button>
        <button type="button" aria-label="Artifact sources: All sources" data-matrix-candidate="label-differs-from-text">All sources</button>
        <a href="#destination" data-matrix-candidate="native-link">Open notebook</a>
        <div role="button" tabindex="0" data-matrix-candidate="aria-button">Create note</div>
        <div contenteditable="true" aria-label="Draft note" data-matrix-candidate="contenteditable">Draft note</div>
        <div tabindex="0" data-matrix-candidate="generic-tabindex">Generic focusable element</div>
        <div role="main" tabindex="0" data-matrix-candidate="landmark">Visible landmark</div>
        <button type="button" disabled data-matrix-candidate="disabled">Disabled</button>
        <a href="#disabled" aria-disabled="true" data-matrix-candidate="aria-disabled">Unavailable</a>
        <div inert><button type="button" data-matrix-candidate="inert">Inert action</button></div>
        <div aria-hidden="true" role="button" tabindex="0" data-matrix-candidate="hidden">Hidden action</div>
      </main>
    `)

    const geometry = await inspectGeometry(page)
    const candidates = geometry.accessibilityActions.map((action) => action.html)

    expect(candidates).toHaveLength(6)
    expect(candidates.join('\n')).toContain('data-matrix-candidate="native-button"')
    expect(candidates.join('\n')).toContain('data-matrix-candidate="native-link"')
    expect(candidates.join('\n')).toContain('data-matrix-candidate="label-differs-from-text"')
    expect(candidates.join('\n')).toContain('data-matrix-candidate="aria-button"')
    expect(candidates.join('\n')).toContain('data-matrix-candidate="contenteditable"')
    expect(candidates.join('\n')).toContain('data-matrix-candidate="generic-tabindex"')
    expect(candidates.join('\n')).not.toContain('data-matrix-candidate="landmark-shell"')
    expect(candidates.join('\n')).not.toContain('data-matrix-candidate="landmark"')
    expect(candidates.join('\n')).not.toContain('data-matrix-candidate="disabled"')
    expect(candidates.join('\n')).not.toContain('data-matrix-candidate="aria-disabled"')
    expect(candidates.join('\n')).not.toContain('data-matrix-candidate="inert"')
    expect(candidates.join('\n')).not.toContain('data-matrix-candidate="hidden"')

    const genericSnapshot = await page.locator('[data-matrix-candidate="generic-tabindex"]').ariaSnapshot()
    const genericSemantics = parseAccessibilitySnapshot(genericSnapshot)
    expect(genericSemantics && BROWSER_ACTION_ROLES.has(genericSemantics.role)).toBe(false)

    const mappedSnapshot = await page.locator('[data-matrix-candidate="label-differs-from-text"]').ariaSnapshot()
    expect(parseAccessibilitySnapshot(mappedSnapshot)).toEqual({
      role: 'button',
      name: 'Artifact sources: All sources',
    })
  })

  test('scroll marker accepts a natural zero-range owner only when initially and finally contained', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 120 })
    await page.setContent(`
      <style>
        html, body { margin: 0; height: 120px; overflow: hidden; }
        main { height: 120px; overflow: hidden; }
        [data-dn-matrix-lower-content] { display: block; height: 24px; }
      </style>
      <main>
        <div data-dn-matrix-lower-content>Already visible lower content</div>
      </main>
    `)

    const geometry = await inspectGeometry(page)

    expect(geometry.scrollMarker.max).toBe(0)
    expect(geometry.scrollMarker.initialContained).toBe(true)
    expect(geometry.scrollMarker.advanced).toBe(false)
    expect(geometry.scrollMarker.markerContained).toBe(true)
    expect(() => assertScrollMarkerContract(geometry.scrollMarker, 'zero-range-contained')).not.toThrow()
  })

  test('positive-range owners fail when their scroll position cannot advance', async ({ page }) => {
    await page.setContent(`
      <style>
        html, body { margin: 0; }
        #owner { width: 240px; height: 100px; overflow: auto; }
        #marker { display: block; height: 24px; }
        #filler { height: 400px; }
      </style>
      <div id="owner">
        <div id="marker" data-dn-matrix-lower-content>Visible marker</div>
        <div id="filler"></div>
      </div>
    `)
    await page.locator('#owner').evaluate((owner) => {
      Object.defineProperty(owner, 'scrollTop', {
        configurable: true,
        get: () => 0,
        set: () => undefined,
      })
    })

    const geometry = await inspectGeometry(page)

    expect(geometry.scrollMarker.max).toBeGreaterThan(0)
    expect(geometry.scrollMarker.initialContained).toBe(true)
    expect(geometry.scrollMarker.advanced).toBe(false)
    expect(() => assertScrollMarkerContract(geometry.scrollMarker, 'positive-range-no-advance')).toThrow(/strict(?:ly)? advance/i)
  })

  test('zero-range owners fail when the marker starts outside the visual viewport', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 120 })
    await page.setContent(`
      <style>
        html, body { margin: 0; height: 120px; overflow: hidden; }
        main { position: relative; height: 120px; overflow: hidden; }
        [data-dn-matrix-lower-content] {
          position: fixed;
          top: 200px;
          left: 0;
          width: 40px;
          height: 24px;
        }
      </style>
      <main>
        <div data-dn-matrix-lower-content>Outside marker</div>
      </main>
    `)

    const geometry = await inspectGeometry(page)

    expect(geometry.scrollMarker.max).toBe(0)
    expect(geometry.scrollMarker.initialContained).toBe(false)
    expect(geometry.scrollMarker.advanced).toBe(false)
    expect(() => assertScrollMarkerContract(geometry.scrollMarker, 'zero-range-initially-outside')).toThrow(/strict(?:ly)? advance|initially contained/i)
  })

  test('ellipsis text is measured after visible overflow clipping', async ({ page }) => {
    await page.setContent(`
      <style>
        button {
          display: block;
          width: 96px;
          height: 44px;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
        }
      </style>
      <button type="button">An intentionally long label that is ellipsized</button>
    `)

    const geometry = await inspectGeometry(page)

    expect(geometry.actionContentOverflow).toEqual([])
    expect(geometry.accessibilityActions[0]?.contentContained).toBe(true)
  })

  test('sr-only text is measured after its visible clipping boundary', async ({ page }) => {
    await page.setContent(`
      <style>
        button { display: block; width: 96px; height: 44px; position: relative; }
        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border: 0;
        }
      </style>
      <button type="button"><span class="sr-only">Accessible label hidden from visual pixels</span><span aria-hidden="true">+</span></button>
    `)

    const geometry = await inspectGeometry(page)

    expect(geometry.actionContentOverflow).toEqual([])
    expect(geometry.accessibilityActions[0]?.contentContained).toBe(true)
  })

  test('overflow-hidden descendants are measured at their visible bounds', async ({ page }) => {
    await page.setContent(`
      <style>
        button { display: block; width: 96px; height: 44px; padding: 0; }
        .clipper {
          display: block;
          width: 64px;
          height: 24px;
          overflow: hidden;
          white-space: nowrap;
        }
      </style>
      <button type="button"><span class="clipper">A descendant label clipped by its own overflow</span></button>
    `)

    const geometry = await inspectGeometry(page)

    expect(geometry.actionContentOverflow).toEqual([])
    expect(geometry.accessibilityActions[0]?.contentContained).toBe(true)
  })

  test('unclipped visible text outside an action fails content containment', async ({ page }) => {
    await page.setContent(`
      <style>
        button {
          display: block;
          width: 96px;
          height: 44px;
          overflow: visible;
          white-space: nowrap;
        }
      </style>
      <button type="button">An intentionally long label that remains visibly unclipped</button>
    `)

    const geometry = await inspectGeometry(page)

    expect(geometry.actionContentOverflow).toContain('0')
    expect(geometry.accessibilityActions[0]?.contentContained).toBe(false)
  })

  test('lower content mapping fails closed for missing or ambiguous selectors', async ({ page }) => {
    await page.setContent('<main><p data-lower="first">First</p><p data-lower="second">Second</p></main>')

    await expect(markRouteLowerContent(page, '/login', '[data-missing]')).rejects.toThrow()
    await expect(markRouteLowerContent(page, '/login', '[data-lower]')).rejects.toThrow()
    expect(await page.locator('[data-dn-matrix-lower-content]').count()).toBe(0)
  })

  test('lower content selector map covers every manifest route explicitly', () => {
    expect(Object.keys(LOWER_CONTENT_SELECTOR_BY_ROUTE).sort()).toEqual(
      VISUAL_ROUTE_MANIFEST.map((route) => route.route).sort(),
    )
    expect(Object.values(LOWER_CONTENT_SELECTOR_BY_ROUTE)).not.toContain('main')
    expect(LOWER_CONTENT_SELECTOR_BY_ROUTE['/notebooks']).toBe(
      'main [aria-label$="Archived Notebooks"]',
    )
    expect(LOWER_CONTENT_SELECTOR_BY_ROUTE['/knowledge']).toBe(
      'main.research-core-editorial-workspace [role="tabpanel"][aria-label^="Knowledge pane"]',
    )
  })

  test('parses quoted browser action snapshots without deriving a role', () => {
    expect(parseAccessibilitySnapshot(`- 'button "Local readiness: ready"'`)).toEqual({
      role: 'button',
      name: 'Local readiness: ready',
    })
  })

})

interface GeometryReport {
  brokenImages: string[]
  duplicateIds: string[]
  clippedActions: string[]
  undersizedActions: string[]
  unnamedActions: string[]
  cardOverflow: string[]
  actionContentOverflow: string[]
  accessibleRoleFailures: string[]
  scrollMarker: {
    count: number
    owner: string
    initialContained: boolean
    advanced: boolean
    markerContained: boolean
    max: number
  }
  cumulativeLayoutShift: number
  accessibilityActions: Array<{
    index: number
    width: number
    height: number
    clipped: boolean
    contentContained: boolean
    html: string
    semantics?: { role: string; name: string }
  }>
}

const ACTIONABLE_ARIA_ROLES = [
  'button', 'checkbox', 'combobox', 'link', 'listbox', 'menuitem',
  'menuitemcheckbox', 'menuitemradio', 'option', 'radio', 'searchbox',
  'slider', 'spinbutton', 'switch', 'tab', 'textbox', 'treeitem',
] as const

const BROWSER_ACTION_ROLES = new Set<string>(ACTIONABLE_ARIA_ROLES)

type VisualRoutePath = (typeof VISUAL_ROUTE_MANIFEST)[number]['route']

const LOWER_CONTENT_SELECTOR_BY_ROUTE = {
  '/login': 'main form',
  '/': 'main [aria-labelledby="workspace-recent-title"]',
  '/setup-wizard': 'main [data-testid="continue-button"]',
  '/notebooks': 'main [aria-label$="Archived Notebooks"]',
  '/notebooks/[id]': 'main textarea[name="chat-message"]:visible',
  '/sources': 'main [data-dn-sources-table="true"]',
  '/sources/[id]': 'main textarea[name="chat-message"]',
  '/knowledge': 'main.research-core-editorial-workspace [role="tabpanel"][aria-label^="Knowledge pane"]',
  '/search': 'main #ask-question',
  '/capture': 'main input[aria-label="Capture folder path"]',
  '/studio': 'main #studio-links',
  '/podcasts': 'main [role="tabpanel"][data-state="active"]',
  '/podcasts/studio': 'main [aria-label="Production Review"]',
  '/study': 'main section[aria-labelledby="study-review-heading"] > :last-child',
  '/study/plans/[planId]': 'main [role="tabpanel"][data-state="active"]',
  '/transformations': 'main [role="tabpanel"][data-state="active"]',
  '/settings': 'main button[aria-label="Apply Midnight Aurora"]',
  '/settings/api-keys': 'main a[href*="ai-providers.md"]',
  '/settings/launcher-prefs': 'main [data-testid="save-button"]',
  '/settings/local-models': 'main [data-testid="local-model-tiers"]',
  '/settings/mcp': 'main input[type="url"]',
  '/advanced': 'main #mode',
} as const satisfies Record<VisualRoutePath, string>

function parseAccessibilitySnapshot(snapshot: string): { role: string; name: string } | null {
  const rawLine = snapshot.trim().split(/\r?\n/).find((candidate) => /^-\s+/.test(candidate))
  // Playwright emits a YAML mapping when a control's accessible name differs
  // from its visible text, for example:
  //   - 'button "Artifact sources: All sources"': All sources
  // Parse the browser role/name from the quoted key without treating the
  // visible-text value as a second semantic node.
  const line = rawLine?.replace(/^-\s+'(.*?)'(?:\s*:.*)?$/, '- $1')
  const match = line?.match(/^-\s+([^\s\[]+)(?:\s+"((?:\\.|[^"])*)")?/)
  if (!match) return null
  let name = match[2] ?? ''
  if (match[2]) {
    try {
      name = JSON.parse(`"${match[2]}"`) as string
    } catch {
      name = match[2]
    }
  }
  return { role: match[1], name }
}

async function markRouteLowerContent(
  page: Parameters<typeof installVisualSystemFixture>[0],
  route: VisualRoutePath,
  selectorOverride?: string,
): Promise<void> {
  const selector = selectorOverride ?? LOWER_CONTENT_SELECTOR_BY_ROUTE[route]
  if (!selector) throw new Error(`Missing lower-content selector for ${route}`)

  await expect(
    page.locator('[data-dn-matrix-lower-content]'),
    `${route} lower-content marker must be absent before the route-owned selector is marked`,
  ).toHaveCount(0)
  const marker = page.locator(selector)
  await expect(marker, `${route} route-owned lower-content selector ${selector}`).toHaveCount(1)
  await marker.evaluate((element) => element.setAttribute('data-dn-matrix-lower-content', 'true'))
}

function isFlagOff(): boolean {
  return process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 === '0'
}

function assertScrollMarkerContract(
  scrollMarker: GeometryReport['scrollMarker'],
  route: string,
): void {
  expect(scrollMarker.count, `${route} explicit lower marker`).toBe(1)
  const mustAdvance = scrollMarker.max > 0 || !scrollMarker.initialContained
  if (mustAdvance) {
    expect(scrollMarker.advanced, `${route} scroll owner must strictly advance`).toBe(true)
  }
  expect(scrollMarker.markerContained, `${route} lower marker final containment`).toBe(true)
  if (scrollMarker.max === 0) {
    expect(scrollMarker.initialContained, `${route} zero-range marker initial containment`).toBe(true)
  }
}

async function inspectGeometry(page: Parameters<typeof installVisualSystemFixture>[0]): Promise<GeometryReport> {
  return page.evaluate((actionableAriaRoles) => {
    type ScrollOwner = HTMLElement | 'document'
    type ActionReport = {
      index: number
      width: number
      height: number
      clipped: boolean
      contentContained: boolean
      html: string
    }

    const hiddenByAria = (element: Element | null): boolean => {
      let current = element
      while (current) {
        if (current.getAttribute('aria-hidden') === 'true') return true
        current = current.parentElement
      }
      return false
    }

    const visible = (element: Element): boolean => {
      if (hiddenByAria(element)) return false
      const style = window.getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && Number(style.opacity) !== 0
        && rect.width > 0
        && rect.height > 0
    }

    const nativeActionSelector = [
      'button',
      'a[href]',
      'input:not([type="hidden"])',
      'textarea',
      'select',
      'summary',
    ]
    const actionSelector = [
      ...nativeActionSelector,
      ...actionableAriaRoles.map((role) => `[role="${role}"]`),
      '[tabindex]:not([tabindex="-1"])',
      '[contenteditable=""]',
      '[contenteditable="true"]',
      '[contenteditable="plaintext-only"]',
    ].join(', ')
    const actionableAriaRoleSet = new Set<string>(actionableAriaRoles)
    const isReachable = (element: HTMLElement): boolean => {
      let current: HTMLElement | null = element
      while (current) {
        if (current.hasAttribute('hidden')
          || current.hasAttribute('inert')
          || current.getAttribute('aria-hidden') === 'true'
          || current.getAttribute('aria-disabled') === 'true') return false
        const style = window.getComputedStyle(current)
        if (style.display === 'none'
          || style.visibility === 'hidden'
          || style.pointerEvents === 'none') return false
        current = current.parentElement
      }
      return !element.matches(':disabled, [aria-disabled="true"]')
        && element.getAttribute('tabindex') !== '-1'
    }
    const isGenuineAction = (element: HTMLElement): boolean => {
      const nativeAction = element.matches(nativeActionSelector.join(', '))
      const ariaRole = element.getAttribute('role')?.toLowerCase() ?? ''
      const exactAriaAction = actionableAriaRoleSet.has(ariaRole)
      const editableAction = element.isContentEditable
      const focusable = element.matches('[tabindex]:not([tabindex="-1"])')
      const genericFocusable = focusable && !element.hasAttribute('role')

      // Generic focusable elements must reach the browser-role assertion so a
      // missing interactive semantic fails closed. Explicit non-action roles
      // remain excluded; tabindex must not turn landmarks into actions.
      return nativeAction || exactAriaAction || editableAction || genericFocusable
    }
    document.querySelectorAll<HTMLElement>('[data-dn-matrix-a11y-action]').forEach((element) => {
      element.removeAttribute('data-dn-matrix-a11y-action')
    })
    const actionableElements = Array.from(document.querySelectorAll<HTMLElement>(actionSelector))
      .filter((element) => visible(element) && isReachable(element) && isGenuineAction(element))

    const contained = (inner: DOMRect, outer: DOMRect): boolean => (
      inner.left >= outer.left - 1
      && inner.right <= outer.right + 1
      && inner.top >= outer.top - 1
      && inner.bottom <= outer.bottom + 1
    )

    const verticallyScrollable = (element: HTMLElement): boolean => {
      const style = window.getComputedStyle(element)
      return ['auto', 'scroll'].includes(style.overflowY)
        && element.scrollHeight > element.clientHeight + 1
    }

    const effectiveScrollOwner = (element: HTMLElement): ScrollOwner => {
      let ancestor = element.parentElement
      while (ancestor) {
        if (verticallyScrollable(ancestor)) return ancestor
        ancestor = ancestor.parentElement
      }
      return 'document'
    }

    const ownerViewport = (owner: ScrollOwner): DOMRect => {
      if (owner instanceof HTMLElement) return owner.getBoundingClientRect()
      const viewport = window.visualViewport
      return new DOMRect(
        viewport?.offsetLeft ?? 0,
        viewport?.offsetTop ?? 0,
        viewport?.width ?? window.innerWidth,
        viewport?.height ?? window.innerHeight,
      )
    }

    const readScrollTop = (owner: ScrollOwner): number => owner === 'document' ? window.scrollY : owner.scrollTop
    const writeScrollTop = (owner: ScrollOwner, value: number): void => {
      if (owner === 'document') window.scrollTo({ top: value, left: 0, behavior: 'auto' })
      else owner.scrollTop = value
    }
    const maxScrollTop = (owner: ScrollOwner): number => owner === 'document'
      ? Math.max(
        0,
        Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight ?? 0)
          - (window.visualViewport?.height ?? window.innerHeight),
      )
      : Math.max(0, owner.scrollHeight - owner.clientHeight)

    const clipToVisibleOverflow = (rawRect: DOMRect, source: Element): DOMRect | null => {
      let left = rawRect.left
      let top = rawRect.top
      let right = rawRect.right
      let bottom = rawRect.bottom
      let current: Element | null = source
      while (current) {
        if (!visible(current)) return null
        const style = window.getComputedStyle(current)
        const clipsX = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX)
        const clipsY = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowY)
        if (clipsX || clipsY) {
          const box = current.getBoundingClientRect()
          if (clipsX) {
            left = Math.max(left, box.left)
            right = Math.min(right, box.right)
          }
          if (clipsY) {
            top = Math.max(top, box.top)
            bottom = Math.min(bottom, box.bottom)
          }
          if (right <= left || bottom <= top) return null
        }
        current = current.parentElement
      }
      return new DOMRect(left, top, right - left, bottom - top)
    }

    const actionReports: ActionReport[] = []
    const undersizedActions: string[] = []
    const unnamedActions: string[] = []
    const clippedActions: string[] = []
    const actionContentOverflow: string[] = []
    for (const [index, control] of actionableElements.entries()) {
      control.setAttribute('data-dn-matrix-a11y-action', String(index))
      const owner = effectiveScrollOwner(control)
      control.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      const rect = control.getBoundingClientRect()
      const viewport = ownerViewport(owner)
      let clipped = !contained(rect, viewport)
      let ancestor = control.parentElement
      while (ancestor) {
        const style = window.getComputedStyle(ancestor)
        const clipsX = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX)
        const clipsY = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowY)
        if (clipsX || clipsY) {
          const box = ancestor.getBoundingClientRect()
          if ((clipsX && (rect.left < box.left - 1 || rect.right > box.right + 1))
            || (clipsY && (rect.top < box.top - 1 || rect.bottom > box.bottom + 1))) clipped = true
        }
        ancestor = ancestor.parentElement
      }
      const contentRects: DOMRect[] = []
      const range = document.createRange()
      for (const child of Array.from(control.childNodes)) {
        range.selectNodeContents(child)
        const source = child instanceof Element ? child : child.parentElement ?? control
        for (const rawRect of Array.from(range.getClientRects())) {
          const clippedRect = clipToVisibleOverflow(rawRect, source)
          if (clippedRect) contentRects.push(clippedRect)
        }
      }
      for (const child of Array.from(control.querySelectorAll<HTMLElement>('*')).filter(visible)) {
        const clippedRect = clipToVisibleOverflow(child.getBoundingClientRect(), child)
        if (clippedRect) contentRects.push(clippedRect)
      }
      const contentContained = contentRects.every((contentRect) => contained(contentRect, rect))
      const report = {
        index,
        width: rect.width,
        height: rect.height,
        clipped,
        contentContained,
        html: control.outerHTML.slice(0, 240),
      }
      actionReports.push(report)
      if (rect.width < 44 || rect.height < 44) undersizedActions.push(control.outerHTML.slice(0, 160))
      if (clipped) {
        clippedActions.push(
          `action ${index} ${rect.left.toFixed(1)},${rect.top.toFixed(1)} ${rect.width.toFixed(1)}×${rect.height.toFixed(1)} within ${viewport.left.toFixed(1)},${viewport.top.toFixed(1)} ${viewport.width.toFixed(1)}×${viewport.height.toFixed(1)} ${control.outerHTML.slice(0, 160)}`,
        )
      }
      if (!contentContained) actionContentOverflow.push(String(index))
    }

    const cardOverflow: string[] = []
    for (const card of Array.from(document.querySelectorAll<HTMLElement>('[data-dn-visual-card]')).filter(visible)) {
      const cardBox = card.getBoundingClientRect()
      for (const child of Array.from(card.querySelectorAll<HTMLElement>(
        '[data-dn-visual-card-title], [data-dn-visual-card-description], [data-dn-visual-card-content], [data-dn-visual-card-metadata], [data-dn-visual-card-action]',
      )).filter(visible)) {
        const clippedRect = clipToVisibleOverflow(child.getBoundingClientRect(), child)
        if (clippedRect && !contained(clippedRect, cardBox)) {
          cardOverflow.push(child.textContent?.replace(/\s+/g, ' ').trim() || child.tagName)
        }
      }
    }

    const markers = Array.from(document.querySelectorAll<HTMLElement>('[data-dn-matrix-lower-content]'))
    const marker = markers.at(-1) ?? null
    const markerVisible = marker ? visible(marker) : false
    const owner = marker ? effectiveScrollOwner(marker) : 'document'
    const ownerName = owner instanceof HTMLElement
      ? (owner.getAttribute('data-testid') ?? (owner.className || owner.tagName))
      : 'document'
    const initial = readScrollTop(owner)
    const max = maxScrollTop(owner)
    const initialContained = marker && markerVisible
      ? contained(marker.getBoundingClientRect(), ownerViewport(owner))
      : false
    let advanced = false
    let markerContained = false
    if (marker && markerVisible) {
      const mustAdvance = max > 0 || !initialContained
      if (mustAdvance) {
        writeScrollTop(owner, 0)
        const before = readScrollTop(owner)
        writeScrollTop(owner, max)
        const after = readScrollTop(owner)
        advanced = after > before
        marker.scrollIntoView({ block: 'end', inline: 'nearest' })
        const markerBox = marker.getBoundingClientRect()
        markerContained = contained(markerBox, ownerViewport(owner))
      } else {
        markerContained = initialContained
      }
      writeScrollTop(owner, initial)
    }

    const duplicateIds = Array.from(document.querySelectorAll<HTMLElement>('[id]'), element => element.id)
      .filter((id, index, ids) => Boolean(id) && ids.indexOf(id) !== index)
    const clsState = (window as Window & {
      __dnVisualSystemLayoutShift?: { value: number; supported: boolean }
    }).__dnVisualSystemLayoutShift
    const cumulativeLayoutShift = clsState?.supported ? clsState.value : Number.NaN
    const accessibleRoleFailures: string[] = []

    return {
      brokenImages: Array.from(document.images).filter(image => image.complete && image.naturalWidth === 0).map(image => image.src),
      duplicateIds,
      clippedActions,
      undersizedActions,
      unnamedActions,
      cardOverflow,
      actionContentOverflow,
      accessibleRoleFailures,
      accessibilityActions: actionReports,
      scrollMarker: {
        count: markers.length,
        owner: String(ownerName),
        initialContained,
        advanced,
        markerContained,
        max,
      },
      cumulativeLayoutShift,
    }
  }, ACTIONABLE_ARIA_ROLES)
}

function assertNoDiagnosticConsoleErrors(errors: string[], pageErrors: string[], route: string): void {
  expect(errors, `${route} console errors`).toEqual([])
  expect(pageErrors, `${route} page errors`).toEqual([])
}

function describeActionGeometry(action: GeometryReport['accessibilityActions'][number]): string {
  const role = action.semantics?.role ?? 'unresolved-role'
  const name = action.semantics?.name ? JSON.stringify(action.semantics.name) : '<unnamed>'
  return `action ${action.index}: ${role} ${name} ${action.width.toFixed(2)}×${action.height.toFixed(2)}`
}

function summarizeActionGeometry(actions: GeometryReport['accessibilityActions']): string {
  const diagnostics = actions.map(describeActionGeometry)
  const limit = 8
  const shown = diagnostics.slice(0, limit)
  return diagnostics.length > limit
    ? `${shown.join('; ')}; +${diagnostics.length - limit} additional`
    : shown.join('; ')
}

async function assertBaseCell(
  page: Parameters<typeof installVisualSystemFixture>[0],
  route: VisualRouteEntry,
  theme: (typeof VISUAL_MATRIX_THEMES)[number],
  viewport: VisualMatrixViewport,
  fixtureLedger: Awaited<ReturnType<typeof installVisualSystemFixture>>['ledger'],
  studyLedger: Awaited<ReturnType<typeof installVisualSystemFixture>>['studyLedger'],
  consoleErrors: string[],
  pageErrors: string[],
): Promise<GeometryReport> {
  await page.goto(route.browserPath, { waitUntil: 'domcontentloaded' })
  expect(new URL(page.url()).pathname, `${route.route} canonical browser path`).toBe(route.browserPath)
  await expect(page.locator('body')).toBeVisible()
  await expect(page.locator('html'), `${route.route} theme`).toHaveAttribute('data-theme', theme)
  await expect(page.locator('main:visible'), `${route.route} visible main`).toHaveCount(1)
  await expect(page.locator('h1:visible'), `${route.route} visible h1`).toHaveCount(1)
  await expect.poll(
    () => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1),
    `${route.route} horizontal overflow`,
  ).toBe(true)
  expect(
    await page.locator('[data-dn-visual-system="v2"]:visible').count(),
    `${route.route} V2 marker`,
  ).toBeGreaterThan(0)
  await expect.poll(() => page.locator('body').evaluate((body) => body.dataset.hydrated !== 'false')).toBe(true)
  await page.waitForTimeout(150)
  await markRouteLowerContent(page, route.route as VisualRoutePath)

  const pins = await page.evaluate(() => ({
    theme: localStorage.getItem('dn-theme'),
    locale: localStorage.getItem('i18nextLng'),
    display: JSON.parse(localStorage.getItem('dn-display-preferences-v1') ?? '{}') as {
      state?: { wallpaper?: string; motion?: string; transparency?: string }
    },
    rootMotion: document.documentElement.dataset.dnMotion,
    rootTransparency: document.documentElement.dataset.dnTransparency,
    cookies: document.cookie.split('; ').filter(Boolean).sort(),
  }))
  expect(pins.theme, `${route.route} exact theme pin`).toBe(theme)
  expect(pins.locale, `${route.route} exact locale pin`).toBe('en-US')
  expect(pins.display.state, `${route.route} exact display pin`).toMatchObject({
    wallpaper: 'static',
    motion: 'reduced',
    transparency: 'solid',
  })
  expect(pins.rootMotion, `${route.route} reduced motion pin`).toBe('reduced')
  expect(pins.rootTransparency, `${route.route} solid transparency pin`).toBe('solid')
  expect(pins.cookies, `${route.route} exact cookie pins`).toEqual(['onp_intro_seen=1', 'wizard_completed=1'])

  assertExactRequestLedgers(route.route, theme, viewport, fixtureLedger, studyLedger)

  const geometry = await inspectGeometry(page)
  await settleVisualNetwork(page)
  assertExactRequestLedgers(route.route, theme, viewport, fixtureLedger, studyLedger)
  for (const action of geometry.accessibilityActions) {
    const actionLocator = page.locator(`[data-dn-matrix-a11y-action="${action.index}"]`)
    await expect(actionLocator, `${route.route} action ${action.index} remains addressable`).toHaveCount(1)
    let snapshot = ''
    try {
      snapshot = await actionLocator.ariaSnapshot()
    } catch {
      geometry.accessibleRoleFailures.push(`action ${action.index}: accessibility snapshot unavailable (${action.html})`)
      continue
    }
    const semantics = parseAccessibilitySnapshot(snapshot)
    if (semantics) action.semantics = semantics
    if (!semantics || !BROWSER_ACTION_ROLES.has(semantics.role)) {
      geometry.accessibleRoleFailures.push(`action ${action.index}: invalid browser role (${snapshot || action.html})`)
      continue
    }
    if (!semantics.name) {
      geometry.unnamedActions.push(`${semantics.role}: action ${action.index} (${action.html})`)
      geometry.accessibleRoleFailures.push(`${semantics.role}: action ${action.index} has no accessible name`)
      continue
    }
    const roleLocator = page.getByRole(
      semantics.role as Parameters<typeof page.getByRole>[0],
      { name: semantics.name, exact: true },
    )
    const matchingActionIndexes = await roleLocator.evaluateAll((elements) => (
      elements.map((element) => element.getAttribute('data-dn-matrix-a11y-action'))
    ))
    if (!matchingActionIndexes.includes(String(action.index))) {
      geometry.accessibleRoleFailures.push(`${semantics.role}: ${semantics.name} did not resolve to action ${action.index}`)
    }
  }
  expect(geometry.brokenImages, `${route.route} broken images`).toEqual([])
  expect(geometry.duplicateIds, `${route.route} duplicate IDs`).toEqual([])
  expect(geometry.clippedActions, `${route.route} clipped actions`).toEqual([])
  const undersizedActions = geometry.accessibilityActions
    .filter((action) => action.width < 44 || action.height < 44)
  expect(
    undersizedActions.length,
    `${route.route} target floor: ${summarizeActionGeometry(undersizedActions)}`,
  ).toBe(0)
  expect(geometry.unnamedActions, `${route.route} accessible action names`).toEqual([])
  expect(geometry.cardOverflow, `${route.route} card/action bounds`).toEqual([])
  const actionContentOverflow = geometry.accessibilityActions.filter((action) => !action.contentContained)
  expect(
    geometry.actionContentOverflow,
    `${route.route} action text/content bounds: ${summarizeActionGeometry(actionContentOverflow)}`,
  ).toEqual([])
  expect(geometry.accessibleRoleFailures, `${route.route} browser accessibility roles`).toEqual([])
  assertScrollMarkerContract(geometry.scrollMarker, route.route)
  if (route.route === '/login' || route.route === '/' || route.route === '/setup-wizard') {
    expect(Number.isFinite(geometry.cumulativeLayoutShift), `${route.route} buffered CLS observer`).toBe(true)
    expect(geometry.cumulativeLayoutShift, `${route.route} settled layout shift`).toBeLessThanOrEqual(0.05)
  }
  await settleVisualNetwork(page)
  assertExactRequestLedgers(route.route, theme, viewport, fixtureLedger, studyLedger)
  assertNoDiagnosticConsoleErrors(
    errorsFromPage(consoleErrors),
    errorsFromPage(pageErrors),
    route.route,
  )
  return geometry
}

// The arguments are retained in arrays so each matrix cell can report the
// route/theme/viewport context in Playwright's test title.
function errorsFromPage(errors: string[]): string[] {
  return errors.filter((error) => !/Download the React DevTools|React does not recognize/i.test(error))
}

function mergeFrequencyMaps(...maps: readonly Record<string, number>[]): Record<string, number> {
  return maps.reduce<Record<string, number>>((merged, map) => {
    for (const [label, count] of Object.entries(map)) merged[label] = (merged[label] ?? 0) + count
    return merged
  }, {})
}

async function settleVisualNetwork(page: Parameters<typeof installVisualSystemFixture>[0]): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout: 1_000 }).catch(() => undefined)
  await page.waitForTimeout(100)
}

function assertExactRequestLedgers(
  route: string,
  theme: (typeof VISUAL_MATRIX_THEMES)[number],
  viewport: VisualMatrixViewport,
  fixtureLedger: Awaited<ReturnType<typeof installVisualSystemFixture>>['ledger'],
  studyLedger: Awaited<ReturnType<typeof installVisualSystemFixture>>['studyLedger'],
  additionalExpected: Record<string, number> = {},
  excludedExpected: readonly string[] = [],
): void {
  expect(fixtureLedger.unexpected, `${route} unexpected API requests`).toEqual([])
  expect(studyLedger.unexpected, `${route} unexpected Study API requests`).toEqual([])
  expect(fixtureLedger.external, `${route} external requests`).toEqual([])
  const studySeen = frequencyMapFromLabels(studyLedger.seen)
  const expected = mergeFrequencyMaps(fixtureLedger.expected, additionalExpected)
  for (const label of excludedExpected) delete expected[label]
  expect(mergeFrequencyMaps(fixtureLedger.seen, studySeen), `${route} exact normalized request frequencies including Study`)
    .toEqual(expected)
  const studyCellSeen = frequencyMapFromLabels(studyLedger.seenByViewport?.[String(viewport.width)] ?? [])
  const expectedCell = mergeFrequencyMaps(expectedVisualRequestFrequency(route, theme, viewport), additionalExpected)
  for (const label of excludedExpected) delete expectedCell[label]
  expect(mergeFrequencyMaps(fixtureLedger.seenByViewport[viewport.name] ?? {}, studyCellSeen), `${route} exact cell frequencies`).toEqual(
    expectedCell,
  )
}

const MATRIX_CELLS = VISUAL_ROUTE_MANIFEST.flatMap((route) => VISUAL_MATRIX_THEMES.flatMap((theme) => (
  VISUAL_MATRIX_VIEWPORTS.map((viewport) => ({ route, theme, viewport }))
)))

for (const cell of MATRIX_CELLS) {
  test(`${cell.route.route} • ${cell.theme} • ${cell.viewport.name}`, async ({ page }) => {
    test.setTimeout(60_000)
    const consoleErrors: string[] = []
    const pageErrors: string[] = []
    page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    page.on('pageerror', error => pageErrors.push(error.message))
    await page.setViewportSize({ width: cell.viewport.width, height: cell.viewport.height })
    const fixture = await installVisualSystemFixture(page, {
      theme: cell.theme,
      route: cell.route.route,
      viewport: cell.viewport,
    })
    const geometry = await assertBaseCell(page, cell.route, cell.theme, cell.viewport, fixture.ledger, fixture.studyLedger, consoleErrors, pageErrors)
    expect(fixture.studyLedger.unexpected, `${cell.route.route} unexpected Study API requests`).toEqual([])
    if (cell.route.route === '/login' || cell.route.route === '/' || cell.route.route === '/setup-wizard') {
      expect(geometry.cumulativeLayoutShift, `${cell.route.route} layout shift`).toBeLessThanOrEqual(0.05)
    }
  })
}

test('explicit rollback preserves the legacy route and shell contract', async ({ browser }) => {
  test.setTimeout(120_000)
  test.skip(!isFlagOff(), 'rollback is executed in the explicit flag-off build')
  for (const pathname of ['/login', '/', '/setup-wizard'] as const) {
    const rollbackContext = await browser.newContext({
      baseURL: `http://127.0.0.1:${process.env.PLAYWRIGHT_PORT ?? '3117'}`,
      locale: 'en-US',
      colorScheme: 'dark',
      deviceScaleFactor: 1,
    })
    const rollbackPage = await rollbackContext.newPage()
    const consoleErrors: string[] = []
    const pageErrors: string[] = []
    rollbackPage.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    rollbackPage.on('pageerror', error => pageErrors.push(error.message))
    await rollbackPage.setViewportSize({ width: 1020, height: 631 })
    const fixture = await installVisualSystemFixture(rollbackPage, {
      theme: 'research-core-dark',
      route: pathname,
      viewport: VISUAL_MATRIX_VIEWPORTS[2],
    })
    try {
      await rollbackPage.goto(pathname, { waitUntil: 'domcontentloaded' })
      await expect(rollbackPage.locator('[data-dn-visual-system="v2"]')).toHaveCount(0)
      await expect(rollbackPage.locator('main:visible')).toHaveCount(1)
      await expect(rollbackPage.locator('h1:visible')).toHaveCount(1)

      let additionalExpected: Record<string, number> = {}
      if (pathname === '/login') {
        await expect(rollbackPage.locator('main[data-dn-folio-page="true"][aria-label="Deeper Notebook sign in"]')).toBeVisible()
        await expect(rollbackPage.getByRole('button', { name: 'Show password' })).toBeVisible()
        await expect(rollbackPage.getByRole('button', { name: /Sign in/i })).toBeDisabled()
        const password = rollbackPage.locator('input[type="password"]')
        await expect(password).toHaveCount(1)
        await rollbackPage.getByRole('button', { name: 'Show password' }).click()
        await expect(rollbackPage.locator('input[type="text"]')).toHaveCount(1)
        await rollbackPage.getByRole('button', { name: 'Hide password' }).click()
        await expect(password).toHaveCount(1)
      } else if (pathname === '/') {
        await expect(rollbackPage.locator('[data-dn-horizon-page="true"]')).toBeVisible()
        await expect(rollbackPage.getByRole('link', { name: 'Studio', exact: true })).toHaveAttribute('href', '/studio')
        await expect(rollbackPage.getByRole('button', { name: 'New Notebook', exact: true })).toBeVisible()
        await expect(rollbackPage.getByRole('button', { name: 'Podcast', exact: true })).toBeVisible()
        await expect(rollbackPage.getByRole('link', { name: 'Ask', exact: true })).toHaveAttribute('href', '/search')
        await rollbackPage.getByRole('button', { name: 'Switch theme' }).click()
        await expect(rollbackPage.getByRole('menuitem').first()).toBeVisible()
        await rollbackPage.keyboard.press('Escape')
      } else {
        await expect(rollbackPage.locator('[data-dn-folio-route-frame="true"]')).toBeVisible()
        await expect(rollbackPage.getByRole('button', { name: /Re-check/i })).toBeVisible()
        await expect(rollbackPage.getByTestId('continue-button')).toBeDisabled()
        const fixes = rollbackPage.getByRole('link', { name: 'Fix this', exact: true })
        await expect(fixes).toHaveCount(3)
        await expect(fixes.nth(0)).toHaveAttribute('href', '/settings/api-keys')
        await expect(fixes.nth(1)).toHaveAttribute('href', '/settings/api-keys')
        await expect(fixes.nth(2)).toHaveAttribute('href', '/advanced')
        await rollbackPage.getByRole('button', { name: /Re-check/i }).click()
        await expect.poll(() => fixture.ledger.seen['GET /api/healthz/deep'] ?? 0).toBe(2)
        additionalExpected = { 'GET /api/healthz/deep': 1 }
      }

      await settleVisualNetwork(rollbackPage)
      assertExactRequestLedgers(
        pathname,
        'research-core-dark',
        VISUAL_MATRIX_VIEWPORTS[2],
        fixture.ledger,
        fixture.studyLedger,
        additionalExpected,
        pathname === '/' || pathname === '/setup-wizard' ? ['GET /api/local-models/health'] : [],
      )
      assertNoDiagnosticConsoleErrors(consoleErrors, pageErrors, pathname)
    } finally {
      await rollbackContext.close()
    }
  }
})
