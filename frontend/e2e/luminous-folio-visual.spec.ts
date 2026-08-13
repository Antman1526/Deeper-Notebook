import { expect, test } from '@playwright/test'

import { installStrictKnowledgeFixture } from './fixtures/knowledge-editor-modes'
import { installLuminousFolioFixture } from './fixtures/luminous-folio'

const captures = [
  { theme: 'research-core-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'research-core-light', viewport: { width: 1440, height: 900 } },
  { theme: 'archive-paper', viewport: { width: 1280, height: 800 } },
  { theme: 'deep-ocean', viewport: { width: 1280, height: 800 } },
  { theme: 'high-contrast-dark', viewport: { width: 1440, height: 900 } },
  { theme: 'high-contrast-light', viewport: { width: 1440, height: 900 } },
  { theme: 'research-core-dark', viewport: { width: 390, height: 844 } },
] as const

for (const capture of captures) {
  test(
    `Luminous notebook index — ${capture.theme} ${capture.viewport.width}x${capture.viewport.height}`,
    async ({ page }) => {
    await installLuminousFolioFixture(page, { theme: capture.theme })
    await page.setViewportSize(capture.viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/notebooks')

    await expect(page.getByRole('heading', { name: 'Notebooks', exact: true })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', capture.theme)
    await expect(page).toHaveScreenshot(
      `notebooks-${capture.theme}-${capture.viewport.width}x${capture.viewport.height}.png`,
      { animations: 'disabled', caret: 'hide' },
    )
    },
  )
}

test('Luminous intelligence horizon — research-core-dark 1440x900', async ({ page }) => {
  await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')

  await expect(page.getByText('Intelligence Horizon', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Deeper Notebook', exact: true })).toBeVisible()
  await expect(page).toHaveScreenshot('horizon-research-core-dark-1440x900.png', {
    animations: 'disabled',
    caret: 'hide',
  })
})

for (const viewport of [
  { width: 1020, height: 631 },
  { width: 800, height: 600 },
  { width: 1280, height: 631 },
] as const) {
  test(`compact Working Desk remains readable — ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const consoleErrors: string[] = []
    const pageErrors: string[] = []
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })
    page.on('pageerror', error => pageErrors.push(error.message))

    await installLuminousFolioFixture(page, { theme: 'research-core-dark' })
    await page.setViewportSize(viewport)
    await page.goto('/')

    const horizon = page.getByRole('main', { name: 'Deeper Notebook' })
    const actionNavigation = horizon.getByRole('navigation', { name: 'Horizon actions' })
    const actions = actionNavigation.locator(':scope > :is(a, button)')
    const lowerTarget = horizon.getByRole('heading', { name: 'Recent folios', exact: true })
    await expect(horizon).toBeVisible()
    await expect(actions).toHaveCount(4)

    const geometry = await actions.evaluateAll(elements => elements.map(element => {
      const action = element.getBoundingClientRect()
      const visibleText = Array.from(element.querySelectorAll<HTMLElement>('span'))
        .filter(text => {
          const style = window.getComputedStyle(text)
          const rect = text.getBoundingClientRect()
          return style.display !== 'none'
            && style.visibility !== 'hidden'
            && rect.width > 0
            && rect.height > 0
        })
        .map(text => {
          const rect = text.getBoundingClientRect()
          return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
        })
      return {
        action: {
          left: action.left,
          right: action.right,
          top: action.top,
          bottom: action.bottom,
          width: action.width,
          height: action.height,
        },
        visibleText,
      }
    }))

    expect(geometry).toHaveLength(4)
    for (const item of geometry) {
      expect(item.action.width).toBeGreaterThanOrEqual(112)
      expect(item.action.height).toBeGreaterThanOrEqual(44)
      expect(item.visibleText.length).toBeGreaterThan(0)
      for (const text of item.visibleText) {
        expect(text.left).toBeGreaterThanOrEqual(item.action.left - 1)
        expect(text.right).toBeLessThanOrEqual(item.action.right + 1)
        expect(text.top).toBeGreaterThanOrEqual(item.action.top - 1)
        expect(text.bottom).toBeLessThanOrEqual(item.action.bottom + 1)
      }
    }

    const overflow = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      scrollOwner: document.scrollingElement?.tagName ?? document.documentElement.tagName,
    }))
    expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth + 1)

    const initialScrollState = await page.evaluate(() => {
      const owner = document.scrollingElement ?? document.documentElement
      const target = document.querySelector<HTMLElement>('#recent-folios-title')
      const rect = target?.getBoundingClientRect()
      return {
        clientHeight: owner.clientHeight,
        scrollHeight: owner.scrollHeight,
        scrollTop: owner.scrollTop,
        target: rect ? {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          height: rect.height,
        } : null,
        viewportHeight: window.visualViewport?.height ?? window.innerHeight,
        viewportWidth: window.visualViewport?.width ?? window.innerWidth,
      }
    })
    expect(overflow.scrollOwner).toBe('HTML')
    expect(initialScrollState.target).not.toBeNull()
    expect(initialScrollState.target!.height).toBeGreaterThan(0)

    const targetInitiallyOutsideViewport = initialScrollState.target!.top >= initialScrollState.viewportHeight
      || initialScrollState.target!.bottom > initialScrollState.viewportHeight
    expect(targetInitiallyOutsideViewport).toBe(true)
    expect(initialScrollState.scrollHeight).toBeGreaterThan(initialScrollState.clientHeight)

    const initialScrollTop = initialScrollState.scrollTop
    await page.evaluate(() => {
      const owner = document.scrollingElement ?? document.documentElement
      owner.scrollTop = owner.scrollHeight
    })
    const finalScrollState = await page.evaluate(() => {
      const owner = document.scrollingElement ?? document.documentElement
      const target = document.querySelector<HTMLElement>('#recent-folios-title')
      const rect = target?.getBoundingClientRect()
      return {
        scrollTop: owner.scrollTop,
        target: rect ? {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
        } : null,
        viewportHeight: window.visualViewport?.height ?? window.innerHeight,
        viewportWidth: window.visualViewport?.width ?? window.innerWidth,
      }
    })
    expect(finalScrollState.scrollTop).toBeGreaterThan(initialScrollTop)
    expect(finalScrollState.target).not.toBeNull()
    expect(finalScrollState.target!.bottom).toBeGreaterThan(0)
    expect(finalScrollState.target!.top).toBeGreaterThanOrEqual(0)
    expect(finalScrollState.target!.bottom).toBeLessThanOrEqual(finalScrollState.viewportHeight)
    expect(finalScrollState.target!.left).toBeGreaterThanOrEqual(0)
    expect(finalScrollState.target!.right).toBeLessThanOrEqual(finalScrollState.viewportWidth)
    await expect(lowerTarget).toBeVisible()
    await expect(actions.nth(3)).toBeVisible()
    expect(consoleErrors).toEqual([])
    expect(pageErrors).toEqual([])
  })
}

test('Luminous knowledge workspace — research-core-dark 1440x900', async ({ page }) => {
  await installStrictKnowledgeFixture(page)
  await page.route('**/api/credentials/status', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ configured: {}, source: {}, encryption_configured: true }),
    })
  })
  await page.addInitScript(() => {
    window.localStorage.setItem('dn-theme', 'research-core-dark')
    window.localStorage.setItem('onp_intro_seen', 'true')
    window.localStorage.setItem(
      'dn-guided-tips-v1',
      JSON.stringify({ state: { enabled: false, completed: {} }, version: 0 }),
    )
    window.localStorage.setItem(
      'dn-display-preferences-v1',
      JSON.stringify({ motion: 'reduced', contrast: 'standard', canvas: 'solid' }),
    )
  })
  await page.context().addCookies([
    { name: 'wizard_completed', value: '1', domain: '127.0.0.1', path: '/' },
  ])
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/knowledge')

  await expect(page.getByRole('heading', { name: 'Knowledge', exact: true })).toBeVisible()
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible()
  await expect(page).toHaveScreenshot('knowledge-research-core-dark-1440x900.png', {
    animations: 'disabled',
    caret: 'hide',
  })
})
