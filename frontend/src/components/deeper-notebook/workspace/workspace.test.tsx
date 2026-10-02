import fs from 'node:fs'
import path from 'node:path'

import { chromium } from '@playwright/test'
import { fireEvent, render, screen } from '@testing-library/react'
import * as React from 'react'
import { describe, expect, expectTypeOf, it, vi } from 'vitest'

import { ResponsiveActionBar } from './ResponsiveActionBar'
import { StatePanel } from './StatePanel'
import { VisualCard } from './VisualCard'
import { VisualCardGrid } from './VisualCardGrid'
import { WorkspaceAppShell } from './WorkspaceAppShell'
import { WorkspaceAuthFrame } from './WorkspaceAuthFrame'
import { WorkspaceHero } from './WorkspaceHero'
import { WorkspaceHome } from './WorkspaceHome'
import { WorkspacePage } from './WorkspacePage'

vi.mock('@/components/chat/LocalModelHealthBadges', () => ({
  LocalModelHealthBadges: () => <div data-testid="local-model-health" />,
}))
vi.mock('@/components/layout/SetupBanner', () => ({ SetupBanner: () => null }))
vi.mock('@/components/layout/DbRepairBanner', () => ({ DbRepairBanner: () => null }))
vi.mock('@/components/layout/UpdateBanner', () => ({ UpdateBanner: () => null }))
vi.mock('@/components/layout/NetworkStatusBadge', () => ({ NetworkStatusBadge: () => null }))
vi.mock('@/components/guided-tips', () => ({ GuidedTipsProvider: () => null }))
vi.mock('@/components/podcasts/GlobalAudioPlayer', () => ({ GlobalAudioPlayer: () => null }))

const workspaceStyles = fs.readFileSync(path.resolve(__dirname, 'workspace.css'), 'utf8')
const shellStyles = fs.readFileSync(path.resolve(__dirname, '../shell/shell.css'), 'utf8')
const workspaceHomeSource = fs.readFileSync(path.resolve(__dirname, 'WorkspaceHome.tsx'), 'utf8')

describe('shared workspace primitives', () => {
  it('owns the V2 auth landmark and heading while preserving the form action', () => {
    render(
      <WorkspaceAuthFrame>
        <form>
          <button type="submit">Sign in</button>
        </form>
      </WorkspaceAuthFrame>,
    )

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByTestId('visual-system-v2-auth-frame')).toHaveAttribute(
      'data-dn-visual-system',
      'v2',
    )
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('reserves the V2 auth form geometry before LoginForm content mounts', async () => {
    const browser = await chromium.launch({ headless: true })

    try {
      const page = await browser.newPage({ viewport: { width: 320, height: 844 } })
      await page.setContent(`
        <!doctype html>
        <html>
          <head><style>${workspaceStyles}</style></head>
          <body>
            <main class="dn-workspace-auth-frame" data-dn-visual-system="v2">
              <section class="dn-workspace-auth-panel">
                <p class="dn-workspace-auth-brand"><span class="dn-rail-brand-mark">DN</span>Deeper Notebook</p>
                <h1 class="dn-workspace-auth-title">Welcome back</h1>
                <p class="dn-workspace-auth-description">Enter your password to open your notebooks.</p>
                <div class="dn-workspace-auth-content" data-testid="auth-content"></div>
              </section>
            </main>
          </body>
        </html>
      `)

      const before = await page.locator('.dn-workspace-auth-panel').boundingBox()
      await page.locator('[data-testid="auth-content"]').evaluate((element) => {
        const form = document.createElement('form')
        // v0.8.130 — Phase 3c: the embedded LoginForm measures 190px (it was a 255px card).
        form.style.blockSize = '190px'
        element.appendChild(form)
      })
      const after = await page.locator('.dn-workspace-auth-panel').boundingBox()
      const minBlockSize = await page.locator('[data-testid="auth-content"]').evaluate(
        (element) => getComputedStyle(element).minBlockSize,
      )

      expect(minBlockSize).toBe('192px')
      expect(before).not.toBeNull()
      expect(after).not.toBeNull()
      expect(after!.height).toBeCloseTo(before!.height, 0)
      expect(Math.abs(after!.y - before!.y)).toBeLessThanOrEqual(1)
    } finally {
      await browser.close()
    }
  })

  // v0.8.130 — Phase 3c: the six-row health table moved behind "Show details", so the
  // 55rem reservation for it is gone; e2e/phase3-firstrun.spec.ts measures that the
  // summary card keeps its height when the check returns.
  it('no longer reserves the old health-table height on the setup summary', async () => {
    const browser = await chromium.launch({ headless: true })

    try {
      const shortPage = await browser.newPage({ viewport: { width: 1020, height: 631 } })
      await shortPage.setContent(`
        <!doctype html>
        <html>
          <head><style>${workspaceStyles}</style></head>
          <body data-dn-visual-system="v2">
            <div class="dn-workspace-setup-card-content">Setup health</div>
          </body>
        </html>
      `)

      await expect(shortPage.locator('.dn-workspace-setup-card-content').evaluate(
        (element) => getComputedStyle(element).minBlockSize,
      )).resolves.toBe('0px')
    } finally {
      await browser.close()
    }
  })

  it('renders a fetch-free V2 home with four cards and one dispatch per action', () => {
    const onOpenStudio = vi.fn()
    const onCreateNotebook = vi.fn()
    const onCreatePodcast = vi.fn()
    const onAsk = vi.fn()

    render(
      <WorkspaceHome
        status="ready"
        recentNotebooks={[]}
        notebooksLoading={false}
        onOpenStudio={onOpenStudio}
        onCreateNotebook={onCreateNotebook}
        onCreatePodcast={onCreatePodcast}
        onAsk={onAsk}
        dataPath="~/.deeper-notebook/"
      />,
    )

    expect(screen.getByTestId('visual-system-v2-home')).toHaveAttribute(
      'data-dn-visual-system',
      'v2',
    )
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('button', { name: 'New Notebook' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Podcast' })).toBeEnabled()
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('href', '/search')

    fireEvent.click(screen.getByRole('link', { name: 'Studio' }))
    fireEvent.click(screen.getByRole('button', { name: 'New Notebook' }))
    fireEvent.click(screen.getByRole('button', { name: 'Podcast' }))
    fireEvent.click(screen.getByRole('link', { name: 'Ask' }))

    expect(onOpenStudio).toHaveBeenCalledTimes(1)
    expect(onCreateNotebook).toHaveBeenCalledTimes(1)
    expect(onCreatePodcast).toHaveBeenCalledTimes(1)
    expect(onAsk).toHaveBeenCalledTimes(1)
    expect(workspaceHomeSource).not.toMatch(/\bfetch\s*\(/)
    expect(workspaceHomeSource).not.toMatch(/use(?:Effect|Query|Mutation)\s*\(/)
  })

  it('keeps loaded notebook links and runtime/state surfaces independent', () => {
    const onOpenStudio = vi.fn()

    render(
      <WorkspaceHome
        status="ready"
        recentNotebooks={[{ id: 'notebook:one', name: 'Research notebook', href: '/notebooks/notebook%3Aone' }]}
        notebooksLoading={false}
        onOpenStudio={onOpenStudio}
        onCreateNotebook={vi.fn()}
        onCreatePodcast={vi.fn()}
        onAsk={vi.fn()}
        runtimeSnapshot={{ status: 'ready' }}
      />,
    )

    expect(screen.getByRole('link', { name: 'Research notebook' })).toHaveAttribute(
      'href',
      '/notebooks/notebook%3Aone',
    )
    expect(screen.getByTestId('runtime-status-panel')).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Your notebook is ready to begin' })).toBeNull()

    fireEvent.click(screen.getByRole('link', { name: 'Studio' }))
    expect(onOpenStudio).toHaveBeenCalledTimes(1)
  })

  it('mounts one V2 page slot and one shared Focus authority', () => {
    render(
      <WorkspaceAppShell>
        <div data-testid="v2-page-slot">Page content</div>
      </WorkspaceAppShell>,
    )

    expect(screen.getAllByTestId('v2-page-slot')).toHaveLength(1)
    expect(screen.getAllByTestId('focus-mode-control')).toHaveLength(1)
    // v0.8.130 — Phase 3b: one rail replaces the instrument dock and the notebook index.
    expect(screen.getAllByRole('navigation', { name: 'Primary' })).toHaveLength(1)
    expect(screen.queryByRole('navigation', { name: 'Primary tools' })).toBeNull()
    expect(screen.queryByRole('navigation', { name: 'Notebook index' })).toBeNull()
    expect(document.querySelectorAll('.dn-workspace-canvas')).toHaveLength(1)
  })

  it('owns one named main landmark and one page heading while preserving caller actions', () => {
    render(
      <WorkspacePage title="Sources" actions={<button type="button">Add source</button>}>
        <VisualCardGrid>
          <VisualCard title="Paper A">Grounded summary</VisualCard>
        </VisualCardGrid>
      </WorkspacePage>,
    )

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('main', { name: 'Sources' })).toContainElement(
      screen.getByRole('button', { name: 'Add source' }),
    )
  })

  it('dispatches a card callback once and gives the action a title-specific accessible name', () => {
    const onActivate = vi.fn()

    render(<VisualCard title="Paper A" onActivate={onActivate}>Grounded summary</VisualCard>)

    const action = screen.getByRole('button', { name: 'Open Paper A' })
    expect(screen.getAllByRole('button')).toHaveLength(1)
    fireEvent.click(action)
    expect(onActivate).toHaveBeenCalledTimes(1)
  })

  it('keeps nested activation to one dispatch and excludes outer activation props', () => {
    const onActivate = vi.fn()
    const outerOnClick = vi.fn()
    const cardProps = {
      title: 'Paper C',
      onActivate,
      onClick: outerOnClick,
    } as React.ComponentProps<typeof VisualCard>

    render(<VisualCard {...cardProps}>Grounded summary</VisualCard>)

    fireEvent.click(screen.getByRole('button', { name: 'Open Paper C' }))
    expect(onActivate).toHaveBeenCalledTimes(1)
    expect(outerOnClick).not.toHaveBeenCalled()
    expectTypeOf<React.ComponentProps<typeof VisualCard>>().not.toHaveProperty('onClick')
  })

  it('renders a link action without creating a second action tree', () => {
    render(
      <VisualCard title="Paper B" href="/sources/paper-b">
        Grounded summary
      </VisualCard>,
    )

    expect(screen.getByRole('link', { name: 'Open Paper B' })).toHaveAttribute(
      'href',
      '/sources/paper-b',
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('maps state kinds to live-region roles and exposes stable accessible ids and details', () => {
    render(
      <div>
        <StatePanel
          kind="error"
          title="Could not load"
          description="The current notebook was preserved."
          preservation="No saved sources were changed."
          action={<button type="button">Retry</button>}
          details={<p>Request ID: fixture-001</p>}
        />
        <StatePanel
          kind="loading"
          title="Loading sources"
          description="Sources are being prepared."
        />
      </div>
    )

    const error = screen.getByRole('alert', { name: 'Could not load' })
    const loading = screen.getByRole('status', { name: 'Loading sources' })
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
    expect(error).toHaveAttribute('aria-labelledby')
    expect(error).toHaveAttribute('aria-describedby')
    expect(error.getAttribute('aria-labelledby')).not.toBe(loading.getAttribute('aria-labelledby'))
    expect(screen.getByText('Details')).toBeInTheDocument()
    expect(screen.getByText('Request ID: fixture-001')).not.toBeVisible()
    expect(screen.getByText('No saved sources were changed.')).toBeInTheDocument()
  })

  it('keeps hero title and copy as DOM text outside the image slot', () => {
    render(
      <WorkspaceHero
        eyebrow="Visual Source Gallery"
        title="Evidence at a glance"
        description="Read the supporting passage without losing your place."
        image={
          // eslint-disable-next-line @next/next/no-img-element
          <img src="/fixture-cover.png" alt="Abstract notebook cover" />
        }
      />,
    )

    const image = screen.getByRole('img', { name: 'Abstract notebook cover' })
    expect(screen.getByRole('heading', { name: 'Evidence at a glance' })).toBeInTheDocument()
    expect(screen.getByText('Read the supporting passage without losing your place.')).toBeInTheDocument()
    expect(image.closest('[data-dn-workspace-hero-media]')).not.toContainElement(
      screen.getByRole('heading', { name: 'Evidence at a glance' }),
    )
  })

  it('forwards refs from every exported surface', () => {
    const pageRef = React.createRef<HTMLElement>()
    const heroRef = React.createRef<HTMLElement>()
    const cardRef = React.createRef<HTMLElement>()
    const gridRef = React.createRef<HTMLDivElement>()
    const stateRef = React.createRef<HTMLElement>()
    const actionsRef = React.createRef<HTMLDivElement>()

    render(
      <>
        <WorkspacePage ref={pageRef} title="Page">
          Page body
        </WorkspacePage>
        <WorkspaceHero ref={heroRef} title="Hero" />
        <VisualCard ref={cardRef} title="Card">
          Card body
        </VisualCard>
        <VisualCardGrid ref={gridRef}>Grid body</VisualCardGrid>
        <StatePanel ref={stateRef} kind="empty" title="Empty" description="Nothing here yet." />
        <ResponsiveActionBar ref={actionsRef}>
          <button type="button">Action</button>
        </ResponsiveActionBar>
      </>,
    )

    expect(pageRef.current).toHaveAttribute('data-dn-workspace-page', 'true')
    expect(heroRef.current).toHaveAttribute('data-dn-workspace-hero', 'true')
    expect(cardRef.current).toHaveAttribute('data-dn-visual-card', 'true')
    expect(gridRef.current).toHaveAttribute('data-dn-visual-card-grid', 'true')
    expect(stateRef.current).toHaveAttribute('data-dn-state-panel', 'true')
    expect(actionsRef.current).toHaveAttribute('data-dn-responsive-action-bar', 'true')
  })

  it('maps compact, standard, and wide grid minimums to their sizing contracts', () => {
    const { container, rerender } = render(
      <VisualCardGrid minimum="compact">Compact grid</VisualCardGrid>,
    )
    const grid = () => container.querySelector('[data-dn-visual-card-grid]')

    expect(grid()).toHaveClass('dn-visual-card-grid-compact')
    expect(grid()).toHaveAttribute('data-dn-visual-card-grid-minimum', 'compact')

    rerender(<VisualCardGrid minimum="standard">Standard grid</VisualCardGrid>)
    expect(grid()).toHaveClass('dn-visual-card-grid-standard')
    expect(grid()).toHaveAttribute('data-dn-visual-card-grid-minimum', 'standard')

    rerender(<VisualCardGrid minimum="wide">Wide grid</VisualCardGrid>)
    expect(grid()).toHaveClass('dn-visual-card-grid-wide')
    expect(grid()).toHaveAttribute('data-dn-visual-card-grid-minimum', 'wide')
    expect(workspaceStyles).toContain(
      'grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--dn-visual-card-minimum)), 1fr));',
    )
  })

  it('keeps card body content at base text size while metadata remains small', () => {
    expect(workspaceStyles).toMatch(
      /\.dn-visual-card-content\s*\{\s*font-size:\s*var\(--dn-text-base\)/,
    )
    expect(workspaceStyles).toMatch(
      /\.dn-visual-card-metadata\s*\{\s*font-size:\s*var\(--dn-text-sm\)/,
    )
  })

  it('provides adaptive and reduced-motion CSS contracts without a fixed page width', () => {
    expect(workspaceStyles).toContain('container-type: inline-size')
    expect(workspaceStyles).toContain('repeat(auto-fit, minmax(')
    expect(workspaceStyles).toContain('min-height: 44px')
    expect(workspaceStyles).toContain('@media (prefers-reduced-motion: reduce)')
    const pageBlock = workspaceStyles.match(/\.dn-workspace-page\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(pageBlock).toContain('width: 100%')
    expect(pageBlock).not.toMatch(/(?<!-)width:\s*\d+px/)
  })

  it('provides the V2 shell grid, compact rail, mobile navigator, and canvas scroll contracts', () => {
    expect(workspaceStyles).toContain('.dn-workspace-shell')
    expect(workspaceStyles).toContain('grid-template-areas:')
    expect(workspaceStyles).toMatch(
      /\.dn-workspace-canvas\s*\{[\s\S]*?min-width:\s*0;[\s\S]*?min-height:\s*0;[\s\S]*?overflow:\s*auto;/,
    )
    expect(workspaceStyles).toContain('@media (min-width: 768px) and (max-width: 1023px)')
    expect(workspaceStyles).toContain('@media (max-width: 767px)')
    expect(workspaceStyles).toMatch(/\.dn-workspace-shell\s*\{[\s\S]*?overflow-x:\s*hidden;/)
  })

  it('bounds each V2 shell tier so the canvas owns route scrolling', () => {
    const shellBlock = workspaceStyles.match(/\.dn-workspace-shell\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
    const bodyBlock = workspaceStyles.match(/\.dn-workspace-shell-body\s*\{([\s\S]*?)\n\}/)?.[1] ?? ''
    const compactStyles = workspaceStyles.slice(
      workspaceStyles.indexOf('@media (min-width: 768px) and (max-width: 1023px)'),
      workspaceStyles.indexOf('@media (max-width: 767px)'),
    )
    const mobileStyles = workspaceStyles.slice(
      workspaceStyles.indexOf('@media (max-width: 767px)'),
      workspaceStyles.indexOf('.dn-workspace-page'),
    )

    expect(shellBlock).toMatch(/height:\s*100dvh;/)
    expect(shellBlock).toMatch(/max-height:\s*100dvh;/)
    expect(bodyBlock).toMatch(/height:\s*100dvh;/)
    expect(bodyBlock).toMatch(/max-height:\s*100dvh;/)
    expect(compactStyles).toMatch(
      /\.dn-workspace-shell\s*\{[\s\S]*?height:\s*100dvh;[\s\S]*?max-height:\s*100dvh;/,
    )
    expect(compactStyles).toMatch(
      /\.dn-workspace-shell-body\s*\{[\s\S]*?height:\s*100dvh;[\s\S]*?max-height:\s*100dvh;/,
    )
    expect(mobileStyles).toMatch(
      /\.dn-workspace-shell\s*\{[\s\S]*?height:\s*100dvh;[\s\S]*?max-height:\s*100dvh;[\s\S]*?padding-bottom:\s*4\.5rem;/,
    )
    expect(mobileStyles).toMatch(
      /\.dn-workspace-shell-body\s*\{[\s\S]*?height:\s*calc\(100dvh\s*-\s*4\.5rem\);[\s\S]*?max-height:\s*calc\(100dvh\s*-\s*4\.5rem\);/,
    )
  })

  it('maps V2 desktop Focus tracks to the keyboard-revealable focus rail', () => {
    const desktopStyles = workspaceStyles.slice(
      workspaceStyles.indexOf('@media (min-width: 1024px)'),
    )

    expect(desktopStyles).toMatch(
      /html\[data-dn-focus-mode="true"\]\s+\.dn-workspace-shell\s*\{[\s\S]*?grid-template-columns:\s*var\(--dn-focus-rail\)\s+minmax\(0,\s*1fr\);/,
    )
    // v0.8.130 — two tracks: the navigator's keyboard-revealable rail and the canvas. The
    // third rail belonged to the Context lens, which the V2 shell no longer mounts.
    expect(desktopStyles).toMatch(
      /html\[data-dn-focus-mode="true"\]\s+\.dn-workspace-shell-body\s*\{[\s\S]*?grid-template-columns:\s*var\(--dn-focus-rail\)\s+minmax\(0,\s*1fr\);/,
    )
  })

  it('applies logical 44px touch targets only to enabled V2 action candidates', async () => {
    const browser = await chromium.launch({ headless: true })

    try {
      const page = await browser.newPage()
      await page.setContent(`
        <!doctype html>
        <html>
          <head><style>${workspaceStyles}</style></head>
          <body>
            <div data-dn-visual-system="v2">
              <button id="v2-native" type="button">Create</button>
              <a id="v2-anchor" href="/settings">Configure settings</a>
              <div id="v2-role" role="button">Custom action</div>
              <div id="v2-tabindex" tabindex="0">Focusable action</div>
              <button id="v2-disabled" type="button" disabled>Disabled</button>
            </div>
            <div>
              <button id="legacy-native" type="button">Legacy action</button>
            </div>
          </body>
        </html>
      `)

      const minimums = await page.evaluate(() => Object.fromEntries(
        ['v2-native', 'v2-anchor', 'v2-role', 'v2-tabindex', 'v2-disabled', 'legacy-native'].map((id) => {
          const element = document.getElementById(id)!
          const style = window.getComputedStyle(element)
          return [id, {
            inline: style.minInlineSize,
            block: style.minBlockSize,
            renderedBlock: element.getBoundingClientRect().height,
          }]
        }),
      ))

      expect(minimums['v2-native']).toEqual({ inline: '44px', block: '44px', renderedBlock: 44 })
      expect(minimums['v2-anchor']).toEqual({ inline: '44px', block: '44px', renderedBlock: 44 })
      expect(minimums['v2-role']).toEqual({ inline: '44px', block: '44px', renderedBlock: 44 })
      expect(minimums['v2-tabindex']).toEqual({ inline: '44px', block: '44px', renderedBlock: 44 })
      expect(minimums['v2-disabled']).toEqual({ inline: '0px', block: '0px', renderedBlock: 21 })
      expect(minimums['legacy-native']).toEqual({ inline: '0px', block: '0px', renderedBlock: 21 })
    } finally {
      await browser.close()
    }
  })

  it('contains a V2 alert action label when the alert narrows on mobile', async () => {
    const browser = await chromium.launch({ headless: true })

    try {
      const page = await browser.newPage({ viewport: { width: 320, height: 844 } })
      await page.setContent(`
        <!doctype html>
        <html>
          <head>
            <style>
              ${workspaceStyles}
              .w-full { inline-size: 100%; }
              .inline-flex { display: inline-flex; }
              .items-center { align-items: center; }
              .justify-center { justify-content: center; }
              .h-8 { block-size: 2rem; }
              .gap-1\\.5 { gap: 0.375rem; }
              .px-2\\.5 { padding-inline: 0.625rem; }
              .icon { inline-size: 0.875rem; block-size: 0.875rem; flex: none; }
              .whitespace-nowrap { white-space: nowrap; }
            </style>
          </head>
          <body>
            <div data-dn-visual-system="v2">
              <div role="alert" style="inline-size: 112px">
                <button id="auto-assign" class="inline-flex items-center justify-center h-8 w-full gap-1.5 px-2.5 whitespace-nowrap" type="button"><svg class="icon" aria-hidden="true"></svg>Auto-assign Defaults</button>
              </div>
            </div>
          </body>
        </html>
      `)

      const report = await page.evaluate(() => {
        const control = document.getElementById('auto-assign')!
        const range = document.createRange()
        range.selectNodeContents(control)
        const outer = control.getBoundingClientRect()
        const content = Array.from(range.getClientRects())
        return {
          display: window.getComputedStyle(control).display,
          flexWrap: window.getComputedStyle(control).flexWrap,
          whiteSpace: window.getComputedStyle(control).whiteSpace,
          height: outer.height,
          contained: content.every((rect) => (
            rect.left >= outer.left - 1
            && rect.right <= outer.right + 1
            && rect.top >= outer.top - 1
            && rect.bottom <= outer.bottom + 1
          )),
        }
      })

      expect(report.display).toBe('flex')
      expect(report.flexWrap).toBe('wrap')
      expect(report.whiteSpace).toBe('normal')
      expect(report.height).toBeGreaterThan(44)
      expect(report.contained).toBe(true)
    } finally {
      await browser.close()
    }
  })

  // v0.8.130 — the Context lens was static placeholder copy on every route: an empty
  // 320px rail at 1536px+, and a floating button that covered content below that.
  it('does not mount the placeholder Context lens in the V2 shell', () => {
    render(
      <WorkspaceAppShell>
        <div data-testid="v2-page-slot">Page content</div>
      </WorkspaceAppShell>,
    )

    expect(document.querySelector('.dn-context-lens')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Context lens' })).toBeNull()
    expect(screen.queryByRole('complementary', { name: 'Context lens' })).toBeNull()
  })

  // v0.8.130 — Phase 3b: the shell is "rail | body" and the body is the command bar over
  // the canvas, so the canvas still takes all the space beside the chrome (no lens rail).
  it('gives the canvas all the space beside the rail: one body column, no lens rail', async () => {
    const browser = await chromium.launch({ headless: true })
    const shell = `
      <div class="dn-workspace-shell">
        <nav class="dn-rail"></nav>
        <div class="dn-workspace-shell-body">
          <header class="dn-command-bar"></header>
          <main class="dn-workspace-canvas">Canvas</main>
        </div>
      </div>
    `

    try {
      for (const width of [1280, 1600, 1920]) {
        const page = await browser.newPage({ viewport: { width, height: 800 } })
        await page.setContent(`<!doctype html><html><head><style>
          html, body { margin: 0; width: 100%; height: 100%; }
          ${shellStyles}
          ${workspaceStyles}
        </style></head><body>${shell}</body></html>`)

        const layout = await page.evaluate(() => {
          const shellEl = document.querySelector('.dn-workspace-shell')!
          const body = document.querySelector('.dn-workspace-shell-body')!
          const rail = document.querySelector('.dn-rail')!.getBoundingClientRect()
          const canvas = document.querySelector('.dn-workspace-canvas')!.getBoundingClientRect()
          return {
            shellTracks: getComputedStyle(shellEl).gridTemplateColumns.trim().split(/\s+/).length,
            bodyTracks: getComputedStyle(body).gridTemplateColumns.trim().split(/\s+/).length,
            canvasEndsAtBodyEdge: Math.abs(canvas.right - body.getBoundingClientRect().right) < 1,
            canvasStartsAfterRail: Math.abs(canvas.left - rail.right) < 1,
          }
        })

        expect(layout, `${width}px`).toEqual({ shellTracks: 2, bodyTracks: 1, canvasEndsAtBodyEdge: true, canvasStartsAfterRail: true })
        await page.close()
      }
    } finally {
      await browser.close()
    }
  })

  it('folds the rail to a strip in Focus mode and still reserves no right rail', async () => {
    const browser = await chromium.launch({ headless: true })

    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 800 } })
      await page.setContent(`<!doctype html><html data-dn-focus-mode="true"><head><style>
        html, body { margin: 0; width: 100%; height: 100%; }
        ${shellStyles}
        ${workspaceStyles}
      </style></head><body>
        <div class="dn-workspace-shell">
          <nav class="dn-rail"></nav>
          <div class="dn-workspace-shell-body">
            <header class="dn-command-bar"></header>
            <main class="dn-workspace-canvas">Canvas</main>
          </div>
        </div>
      </body></html>`)

      const layout = await page.evaluate(() => ({
        bodyTracks: getComputedStyle(document.querySelector('.dn-workspace-shell-body')!).gridTemplateColumns.trim().split(/\s+/).length,
        railWidth: Math.round(document.querySelector('.dn-rail')!.getBoundingClientRect().width),
      }))
      // The rail folds to the 3rem Focus strip; the body stays one column.
      expect(layout).toEqual({ bodyTracks: 1, railWidth: 48 })
    } finally {
      await browser.close()
    }
  })
})
