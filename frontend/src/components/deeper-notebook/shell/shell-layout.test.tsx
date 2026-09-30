import fs from 'node:fs'
import path from 'node:path'

import { chromium, type Browser, type Page } from '@playwright/test'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

// Launching Chromium is slow on a busy machine; the defaults (5s test, 10s hook)
// are tuned for jsdom tests.
vi.setConfig({ testTimeout: 60_000, hookTimeout: 60_000 })

// Phase 0 shell layout defects (UI audit 2026-09-30), checked in real Chromium
// against the shipped CSS with markup that mirrors the real components:
//  T0-3  the Create button rendered as an empty square
//  T0-4  the active navigator link only covered its text
//  T0-9  the command bar ran off the right edge on phones, showed keyboard
//        hints on touch devices, and the fixed Context lens covered content

const shellCss = fs.readFileSync(path.resolve(__dirname, 'shell.css'), 'utf8')
const workspaceCss = fs.readFileSync(path.resolve(__dirname, '../workspace/workspace.css'), 'utf8')
// The shell CSS sizes everything from these design tokens (--dn-text-lg,
// --dn-space-*); without them the title and padding are narrower than in the app.
const tokensCss = fs.readFileSync(path.resolve(__dirname, '../tokens.css'), 'utf8')

// The few Tailwind utilities the real components lean on, so layout is faithful.
const utilities = `
  html, body { margin: 0; }
  button { font: inherit; }
  .inline-flex { display: inline-flex; }
  .flex { display: flex; }
  .items-center { align-items: center; }
  .justify-center { justify-content: center; }
  .whitespace-nowrap { white-space: nowrap; }
  .h-9 { block-size: 2.25rem; }
  .px-3 { padding-inline: 0.75rem; }
  .px-4 { padding-inline: 1rem; }
  .gap-2 { gap: 0.5rem; }
  /* The route pill that sits beside the title in the real command bar. Without its
     width the breadcrumb is narrow enough that nothing has to shrink. */
  .gap-2-5 { gap: 0.625rem; }
  .gap-1-5 { gap: 0.375rem; }
  .route-pill { padding-inline: 0.625rem; padding-block: 0.125rem; border: 1px solid; border-radius: 999px; }
  .route-dot { inline-size: 0.375rem; block-size: 0.375rem; border-radius: 50%; background: currentColor; }
  /* A utility class, like h-7 w-7 in the real component: it loses to the shell rules. */
  .icon-box { inline-size: 1.75rem; block-size: 1.75rem; }
`

const page = (body: string, bodyAttrs = 'data-dn-visual-system="v2"', htmlAttrs = '') => `
  <!doctype html>
  <html ${htmlAttrs}>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>${tokensCss}${utilities}${shellCss}${workspaceCss}</style>
    </head>
    <body ${bodyAttrs}>${body}</body>
  </html>
`

const commandBarMarkup = `
  <div class="dn-workspace-shell">
    <div class="dn-instrument-dock"></div>
    <div class="dn-workspace-shell-body">
      <header class="dn-command-bar">
        <div class="dn-command-breadcrumb flex items-center gap-2-5">
          <span class="route-pill inline-flex items-center gap-1-5">
            <span class="route-dot"></span>
            <span class="dn-command-kicker">settings</span>
          </span>
          <p class="dn-command-title">Deeper Notebook and a product title long enough to need truncating</p>
        </div>
        <div class="dn-command-actions">
          <button type="button" class="dn-command-trigger inline-flex items-center h-9 px-3 gap-2">
            <svg width="14" height="14"></svg>
            <span>Quick actions</span>
            <span class="dn-command-shortcut">Ctrl+K</span>
          </button>
          <button type="button" class="dn-focus-mode-control inline-flex items-center h-9 px-4 gap-2">
            <svg width="16" height="16"></svg>
            <span class="dn-focus-mode-label">Enter Focus mode</span>
            <kbd class="dn-focus-mode-shortcut">Ctrl+Shift+F</kbd>
          </button>
        </div>
      </header>
    </div>
  </div>
`

let browser: Browser

beforeAll(async () => {
  browser = await chromium.launch({ headless: true })
})

afterAll(async () => {
  await browser?.close()
})

async function measure(html: string, viewport: { width: number; height: number }, touch = false) {
  const context = await browser.newContext({
    viewport,
    ...(touch ? { hasTouch: true, isMobile: true } : {}),
  })
  const tab = await context.newPage()
  await tab.setContent(html)
  return { tab, close: () => context.close() }
}

// Selector goes in as an argument: page.evaluate serializes the function, so a
// closure over it would not exist in the page.
async function rect(tab: Page, selector: string) {
  return tab.evaluate((sel) => {
    const element = document.querySelector(sel)
    if (!element) return null
    const box = element.getBoundingClientRect()
    const style = getComputedStyle(element)
    return {
      left: box.left,
      right: box.right,
      width: box.width,
      display: style.display,
      paddingBottom: parseFloat(style.paddingBottom),
    }
  }, selector)
}

describe('dock Create button (T0-3)', () => {
  const create = `
    <nav class="dn-instrument-dock">
      <div class="dn-dock-create">
        <button type="button" class="inline-flex items-center justify-center" aria-label="Create" style="width:100%;block-size:2.5rem;padding:0">
          <span id="icon" class="icon-box inline-flex items-center justify-center"><svg width="16" height="16"></svg></span>
          <span id="label" class="dn-dock-label">Create</span>
        </button>
      </div>
    </nav>
  `

  for (const [name, html] of [
    ['V2 shell', page(create)],
    ['Luminous shell', page(create, '').replace(workspaceCss, '')],
  ] as const) {
    it(`keeps the icon visible while hiding only the text label — ${name}`, async () => {
      const { tab, close } = await measure(html, { width: 1440, height: 900 })
      try {
        const icon = await rect(tab, '#icon')
        const label = await rect(tab, '#label')

        expect(icon?.width).toBeGreaterThanOrEqual(24)
        expect(icon?.display).not.toBe('none')
        expect(label?.display === 'none' || (label?.width ?? 99) <= 1).toBe(true)
      } finally {
        await close()
      }
    })
  }
})

describe('navigator link (T0-4)', () => {
  it('lets the active link fill its row instead of shrinking to the text (V2)', async () => {
    const { tab, close } = await measure(
      page(`
        <div class="dn-workspace-shell"><div class="dn-workspace-shell-body">
          <nav class="dn-adaptive-navigator" style="inline-size:17rem">
            <div class="dn-navigator-list"><div class="dn-navigator-section"><ul>
              <li id="row"><a id="link" class="dn-navigator-link is-active" href="#"><span data-layout-id="onp-sidebar-active" aria-hidden="true"></span><svg width="16" height="16"></svg><span>Notebooks</span></a></li>
            </ul></div></div>
          </nav>
        </div></div>
      `),
      { width: 1440, height: 900 },
    )
    try {
      const row = await rect(tab, '#row')
      const link = await rect(tab, '#link')

      expect(link?.display).toBe('flex')
      expect(link?.width ?? 0).toBeGreaterThanOrEqual((row?.width ?? Infinity) - 1)
    } finally {
      await close()
    }
  })
})

describe('command bar (T0-9)', () => {
  for (const width of [320, 390]) {
    it(`fits every control inside a ${width}px phone viewport and keeps the product name`, async () => {
      const { tab, close } = await measure(page(commandBarMarkup), { width, height: 844 })
      try {
        // The buttons, not just their container: a shrinkable row can be narrower
        // than the controls inside it, which pushes the last one off-screen.
        const actions = await rect(tab, '.dn-command-actions')
        const trigger = await rect(tab, '.dn-command-trigger')
        const focus = await rect(tab, '.dn-focus-mode-control')
        const title = await rect(tab, '.dn-command-title')
        const scrollWidth = await tab.evaluate(() => document.documentElement.scrollWidth)

        // The row must never be narrower than the controls inside it.
        expect(focus?.right ?? Infinity).toBeLessThanOrEqual((actions?.right ?? 0) + 1)
        expect(trigger?.left ?? 0).toBeGreaterThanOrEqual((actions?.left ?? Infinity) - 1)
        expect(trigger?.right ?? Infinity).toBeLessThanOrEqual(width)
        expect(focus?.right ?? Infinity).toBeLessThanOrEqual(width)
        expect(scrollWidth).toBeLessThanOrEqual(width)
        expect(title?.width ?? 0).toBeGreaterThan(40)
      } finally {
        await close()
      }
    })
  }

  it('shows the Focus control as an icon on phones and mid-size windows', async () => {
    for (const width of [390, 768, 1100]) {
      const { tab, close } = await measure(page(commandBarMarkup), { width, height: 900 })
      try {
        const label = await rect(tab, '.dn-focus-mode-label')
        const shortcut = await rect(tab, '.dn-focus-mode-shortcut')
        expect(label?.display === 'none' || (label?.width ?? 99) <= 1, `label at ${width}px`).toBe(true)
        expect(shortcut?.display === 'none' || (shortcut?.width ?? 99) <= 1, `hint at ${width}px`).toBe(true)
      } finally {
        await close()
      }
    }
  })

  it('keeps the full Focus label and hint on wide desktops', async () => {
    const { tab, close } = await measure(page(commandBarMarkup), { width: 1440, height: 900 })
    try {
      const label = await rect(tab, '.dn-focus-mode-label')
      const shortcut = await rect(tab, '.dn-focus-mode-shortcut')
      const actions = await rect(tab, '.dn-command-actions')

      expect(label?.width ?? 0).toBeGreaterThan(40)
      expect(shortcut?.width ?? 0).toBeGreaterThan(20)
      expect(actions?.right ?? Infinity).toBeLessThanOrEqual(1440)
    } finally {
      await close()
    }
  })

  it('hides keyboard hints on touch devices, where there is no keyboard shortcut', async () => {
    const { tab, close } = await measure(page(commandBarMarkup), { width: 1440, height: 900 }, true)
    try {
      const palette = await rect(tab, '.dn-command-shortcut')
      const focus = await rect(tab, '.dn-focus-mode-shortcut')
      expect(palette?.display).toBe('none')
      expect(focus?.display).toBe('none')
    } finally {
      await close()
    }
  })
})

describe('Context lens toggle (T0-9)', () => {
  const shellWithLens = `
    <div class="dn-workspace-shell">
      <div class="dn-instrument-dock"></div>
      <div class="dn-workspace-shell-body">
        <header class="dn-command-bar"></header>
        <nav class="dn-adaptive-navigator"></nav>
        <main class="dn-workspace-canvas">Content</main>
        <button type="button" class="dn-context-lens-toggle">Context lens</button>
        <aside class="dn-context-lens">Context lens</aside>
      </div>
    </div>
  `

  for (const width of [390, 1280]) {
    it(`still reserves that room in compact density at ${width}px (a more specific rule sets padding)`, async () => {
      const { tab, close } = await measure(
        page(shellWithLens, undefined, 'data-dn-density="compact"'),
        { width, height: 900 },
      )
      try {
        const canvas = await rect(tab, '.dn-workspace-canvas')
        expect(canvas?.paddingBottom ?? 0).toBeGreaterThanOrEqual(56)
      } finally {
        await close()
      }
    })
  }

  it('does not reserve it in Focus mode, where the toggle is relocated', async () => {
    const { tab, close } = await measure(
      page(shellWithLens, undefined, 'data-dn-focus-mode="true"'),
      { width: 1280, height: 900 },
    )
    try {
      const canvas = await rect(tab, '.dn-workspace-canvas')
      expect(canvas?.paddingBottom ?? 0).toBeLessThan(56)
    } finally {
      await close()
    }
  })

  for (const width of [390, 768, 1280]) {
    it(`reserves room at the end of the canvas so the fixed toggle never permanently covers content at ${width}px`, async () => {
      const { tab, close } = await measure(page(shellWithLens), { width, height: 900 })
      try {
        const canvas = await rect(tab, '.dn-workspace-canvas')
        // Toggle is ~2.75rem tall plus its own 1rem offset and a gap.
        expect(canvas?.paddingBottom ?? 0).toBeGreaterThanOrEqual(56)
      } finally {
        await close()
      }
    })
  }
})
