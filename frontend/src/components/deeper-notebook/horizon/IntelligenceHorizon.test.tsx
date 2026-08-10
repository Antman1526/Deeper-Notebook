import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { IntelligenceHorizon } from './IntelligenceHorizon'

const fixtureNotebooks = [
  {
    id: 'research-notebook',
    name: 'Research notebook',
    updated: '2026-08-10T12:00:00.000Z',
  },
] as const

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

  it('shows ready trust status, command hint, and local data path', () => {
    renderHorizon()

    expect(screen.getByText('Ready')).toBeVisible()
    expect(screen.getByText(/⌘K/)).toBeVisible()
    expect(screen.getByText(/Ctrl\+K/)).toBeVisible()
    expect(screen.getByText('~/.deeper-notebook/')).toBeVisible()
  })

  it.each([
    ['loading', 'Loading your notebook desk'],
    ['offline', 'Notebook runtime offline'],
  ] as const)('preserves the %s state', (status, title) => {
    renderHorizon({ status })

    expect(screen.getByRole('status', { name: title })).toBeInTheDocument()
  })

  it('preserves the empty notebook state with an explicit Studio action', () => {
    const onOpenStudio = vi.fn()
    renderHorizon({ recentNotebooks: [], onOpenStudio })

    expect(screen.getByRole('status', { name: 'Your notebook is ready to begin' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open Studio' }))
    expect(onOpenStudio).toHaveBeenCalledTimes(1)
  })
})
