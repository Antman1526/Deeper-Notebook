import fs from 'node:fs'
import path from 'node:path'

import { fireEvent, render, screen } from '@testing-library/react'
import * as React from 'react'
import { describe, expect, it, vi } from 'vitest'

import { ResponsiveActionBar } from './ResponsiveActionBar'
import { StatePanel } from './StatePanel'
import { VisualCard } from './VisualCard'
import { VisualCardGrid } from './VisualCardGrid'
import { WorkspaceHero } from './WorkspaceHero'
import { WorkspacePage } from './WorkspacePage'

const workspaceStyles = fs.readFileSync(path.resolve(__dirname, 'workspace.css'), 'utf8')

describe('shared workspace primitives', () => {
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

  it('provides adaptive and reduced-motion CSS contracts without a fixed page width', () => {
    expect(workspaceStyles).toContain('container-type: inline-size')
    expect(workspaceStyles).toContain('repeat(auto-fit, minmax(')
    expect(workspaceStyles).toContain('min-height: 44px')
    expect(workspaceStyles).toContain('@media (prefers-reduced-motion: reduce)')
    const pageBlock = workspaceStyles.match(/\.dn-workspace-page\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(pageBlock).toContain('width: 100%')
    expect(pageBlock).not.toMatch(/(?<!-)width:\s*\d+px/)
  })
})
