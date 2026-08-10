import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { IntelligenceHorizon } from './IntelligenceHorizon'

const fixtureNotebooks = [
  {
    id: 'research-notebook',
    name: 'Research notebook',
    updated: '2026-08-10T12:00:00.000Z',
  },
] as const

const distinctReadiness = {
  status: 'not_ready' as const,
  checks: {
    database: 'offline' as const,
    database_error: 'database unavailable',
    migrations_applied: false,
    migrations_pending: true,
    migrations_error: 'pending migrations',
  },
}

function renderHorizon(
  overrides: Partial<React.ComponentProps<typeof IntelligenceHorizon>> = {},
) {
  const props = {
    status: 'ready' as const,
    recentNotebooks: fixtureNotebooks,
    onOpenStudio: vi.fn(),
    onCreateNotebook: vi.fn(),
    onCreatePodcast: vi.fn(),
    onAsk: vi.fn(),
    notebooksLoading: false,
    readiness: distinctReadiness,
    dataPath: '~/.deeper-notebook/',
    ...overrides,
  }

  return { ...render(<IntelligenceHorizon {...props} />), props }
}

describe('IntelligenceHorizon', () => {
  it('keeps the four dashboard actions, recent notebook links, and mount quiet', () => {
    const { props } = renderHorizon()

    expect(screen.getByRole('link', { name: 'Studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('button', { name: 'New Notebook' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Podcast' })).toBeEnabled()
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('href', '/search')
    expect(screen.getByRole('link', { name: 'Research notebook' })).toHaveAttribute(
      'href',
      '/notebooks/research-notebook',
    )

    expect(props.onOpenStudio).not.toHaveBeenCalled()
    expect(props.onCreateNotebook).not.toHaveBeenCalled()
    expect(props.onCreatePodcast).not.toHaveBeenCalled()
    expect(props.onAsk).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('link', { name: 'Studio' }))
    fireEvent.click(screen.getByRole('button', { name: 'New Notebook' }))
    fireEvent.click(screen.getByRole('button', { name: 'Podcast' }))
    fireEvent.click(screen.getByRole('link', { name: 'Ask' }))

    expect(props.onOpenStudio).toHaveBeenCalledTimes(1)
    expect(props.onCreateNotebook).toHaveBeenCalledTimes(1)
    expect(props.onCreatePodcast).toHaveBeenCalledTimes(1)
    expect(props.onAsk).toHaveBeenCalledTimes(1)
  })

  it('owns a scrollable content region so lower Horizon content remains reachable', () => {
    renderHorizon()

    expect(screen.getByTestId('horizon-scroll-region')).toHaveClass(
      'h-full',
      'min-h-0',
      'overflow-y-auto',
    )
  })

  it('shows ready trust status, command hint, and local data path', () => {
    renderHorizon()

    expect(screen.getByText('Ready')).toBeVisible()
    expect(screen.getByText(/⌘K/)).toBeVisible()
    expect(screen.getByText(/Ctrl\+K/)).toBeVisible()
    expect(screen.getByText('~/.deeper-notebook/')).toBeVisible()
  })

  it.each([
    ['loading', 'Runtime loading'],
    ['offline', 'Runtime offline'],
  ] as const)('preserves the %s readiness state separately from notebooks', (status, title) => {
    renderHorizon({ status })

    expect(screen.getByRole('status', { name: title })).toBeInTheDocument()
  })

  it('keeps loaded notebook links visible while readiness is offline', () => {
    renderHorizon({ status: 'offline' })

    expect(screen.getByRole('link', { name: 'Research notebook' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Notebook runtime offline' })).toBeNull()
  })

  it('keeps notebook loading independent from readiness state', () => {
    renderHorizon({ status: 'offline', notebooksLoading: true })

    expect(screen.getByRole('status', { name: 'Loading your notebook desk' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Research notebook' })).toBeNull()
  })

  it('preserves distinct API, database, and migration readiness details', () => {
    renderHorizon({ status: 'offline', readiness: distinctReadiness })

    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getAllByText('offline').length).toBeGreaterThan(0)
    expect(screen.getByText('pending')).toBeInTheDocument()
    expect(screen.getByText('database unavailable')).toBeInTheDocument()
    expect(screen.getByText('pending migrations')).toBeInTheDocument()
  })

  it('leaves modified and middle clicks to native link behavior', () => {
    const { props } = renderHorizon()
    const studio = screen.getByRole('link', { name: 'Studio' })
    const ask = screen.getByRole('link', { name: 'Ask' })
    // Keep jsdom from attempting a real document navigation while preserving
    // the production assertion above that both links expose their routes.
    studio.setAttribute('href', '#')
    ask.setAttribute('href', '#')
    const modifiedClick = createEvent.click(studio, { metaKey: true })
    const middleClick = createEvent.click(ask, { button: 1 })

    fireEvent(studio, modifiedClick)
    fireEvent(ask, middleClick)

    expect(modifiedClick.defaultPrevented).toBe(false)
    expect(middleClick.defaultPrevented).toBe(false)
    expect(props.onOpenStudio).not.toHaveBeenCalled()
    expect(props.onAsk).not.toHaveBeenCalled()
  })

  it('preserves the empty notebook state with an explicit Studio action', () => {
    const onOpenStudio = vi.fn()
    renderHorizon({ recentNotebooks: [], onOpenStudio })

    expect(screen.getByRole('status', { name: 'Your notebook is ready to begin' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open Studio' }))
    expect(onOpenStudio).toHaveBeenCalledTimes(1)
  })
})
