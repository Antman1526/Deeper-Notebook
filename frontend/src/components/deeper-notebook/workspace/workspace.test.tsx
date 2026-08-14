import fs from 'node:fs'
import path from 'node:path'

import { fireEvent, render, screen } from '@testing-library/react'
import * as React from 'react'
import { describe, expect, expectTypeOf, it, vi } from 'vitest'

import { ResponsiveActionBar } from './ResponsiveActionBar'
import { StatePanel } from './StatePanel'
import { VisualCard } from './VisualCard'
import { VisualCardGrid } from './VisualCardGrid'
import { WorkspaceAppShell } from './WorkspaceAppShell'
import { WorkspaceHero } from './WorkspaceHero'
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

describe('shared workspace primitives', () => {
  it('mounts one V2 page slot and one shared Focus authority', () => {
    render(
      <WorkspaceAppShell>
        <div data-testid="v2-page-slot">Page content</div>
      </WorkspaceAppShell>,
    )

    expect(screen.getAllByTestId('v2-page-slot')).toHaveLength(1)
    expect(screen.getAllByTestId('focus-mode-control')).toHaveLength(1)
    expect(screen.getAllByRole('navigation', { name: 'Primary tools' })).toHaveLength(1)
    expect(screen.getAllByRole('navigation', { name: 'Notebook index' })).toHaveLength(1)
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
    expect(desktopStyles).toMatch(
      /html\[data-dn-focus-mode="true"\]\s+\.dn-workspace-shell-body\s*\{[\s\S]*?grid-template-columns:\s*var\(--dn-focus-rail\)\s+minmax\(0,\s*1fr\)\s+var\(--dn-focus-rail\);/,
    )
  })
})
