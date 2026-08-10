import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NotebookResponse } from '@/lib/types/api'
import type { ReadyzResponse } from '@/lib/hooks/use-system-status'

import DashboardPage from './page'

const routerPush = vi.fn()
const dashboardFixtures = vi.hoisted(() => ({
  notebooks: {
    data: [] as NotebookResponse[],
    isLoading: false,
  },
  status: {
    data: undefined as ReadyzResponse | undefined,
    isLoading: false,
  },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    header: ({ children }: { children: React.ReactNode }) => (
      <header>{children}</header>
    ),
  },
  useReducedMotion: () => true,
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}))

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => dashboardFixtures.notebooks,
}))

vi.mock('@/lib/hooks/use-system-status', () => ({
  useSystemStatus: () => dashboardFixtures.status,
}))

describe('DashboardPage active product identity', () => {
  beforeEach(() => {
    dashboardFixtures.notebooks = { data: [], isLoading: false }
    dashboardFixtures.status = { data: undefined, isLoading: false }
  })

  afterEach(() => {
    routerPush.mockClear()
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO
  })

  it('presents the canonical product name and tagline', () => {
    render(<DashboardPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Think further with every source')).toBeVisible()
  })

  it.each(['0', '1'])('keeps the Horizon presentation compatible with shell flag %s', (flag) => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = flag
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('href', '/search')
  })

  it('keeps route navigation in the page callback wiring', () => {
    render(<DashboardPage />)

    fireEvent.click(screen.getByRole('link', { name: 'Studio' }))
    fireEvent.click(screen.getByRole('link', { name: 'Ask' }))

    expect(routerPush).toHaveBeenNthCalledWith(1, '/studio')
    expect(routerPush).toHaveBeenNthCalledWith(2, '/search')
  })

  it('maps offline readiness without hiding loaded notebooks or their distinct checks', () => {
    dashboardFixtures.notebooks = {
      data: [{
        id: 'offline-notebook',
        name: 'Offline notebook',
        description: '',
        archived: false,
        created: '2026-08-10T12:00:00.000Z',
        updated: '2026-08-10T12:00:00.000Z',
        source_count: 0,
        note_count: 0,
      }],
      isLoading: false,
    }
    dashboardFixtures.status = {
      data: {
        status: 'not_ready',
        checks: {
          database: 'offline',
          database_error: 'database unavailable',
          migrations_applied: false,
          migrations_pending: true,
          migrations_error: 'pending migrations',
        },
      },
      isLoading: false,
    }

    render(<DashboardPage />)

    expect(screen.getByRole('link', { name: 'Offline notebook' })).toHaveAttribute(
      'href',
      '/notebooks/offline-notebook',
    )
    expect(screen.getByText('database unavailable')).toBeInTheDocument()
    expect(screen.getByText('pending migrations')).toBeInTheDocument()
  })

  it('keeps known runtime readiness while notebooks are still loading', () => {
    dashboardFixtures.notebooks = { data: [], isLoading: true }
    dashboardFixtures.status = {
      data: {
        status: 'ready',
        checks: {
          database: 'online',
          database_error: null,
          migrations_applied: true,
          migrations_pending: false,
          migrations_error: null,
        },
      },
      isLoading: false,
    }

    render(<DashboardPage />)

    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Loading your notebook desk' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Runtime loading' })).toBeNull()
  })
})
