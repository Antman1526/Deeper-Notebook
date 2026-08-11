import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RuntimeSnapshot } from '@/lib/api/runtime'
import type { NotebookResponse } from '@/lib/types/api'

import DashboardPage from './page'

const routerPush = vi.fn()
const readyRuntimeSnapshot: RuntimeSnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'ready',
  reasons: [],
  readiness: { state: 'ready', database: 'online', migrations: 'applied' },
  startup: { state: 'ready', stages: [] },
  updates: { state: 'ready', enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready', ready: 1, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready', projected: 1, unchanged: 0, failed: 0 },
  backup: { state: 'ready', file_count: 1, newest_age_seconds: 5 },
}
const dashboardFixtures = vi.hoisted(() => ({
  notebooks: {
    data: [] as NotebookResponse[],
    isLoading: false,
  },
  runtime: {
    data: undefined as RuntimeSnapshot | undefined,
    isLoading: false,
    refetch: vi.fn(),
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

vi.mock('@/lib/hooks/use-runtime-snapshot', () => ({
  useRuntimeSnapshot: () => dashboardFixtures.runtime,
}))

describe('DashboardPage active product identity', () => {
  beforeEach(() => {
    dashboardFixtures.notebooks = { data: [], isLoading: false }
    dashboardFixtures.runtime = { data: readyRuntimeSnapshot, isLoading: false, refetch: vi.fn() }
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
    dashboardFixtures.runtime = {
      data: {
        ...readyRuntimeSnapshot,
        status: 'degraded',
        reasons: ['database_offline', 'migrations_pending', 'database_check_failed', 'migrations_check_failed'],
        readiness: { state: 'degraded', database: 'offline', migrations: 'pending' },
      },
      isLoading: false,
      refetch: vi.fn(),
    }

    render(<DashboardPage />)

    expect(screen.getByRole('link', { name: 'Offline notebook' })).toHaveAttribute(
      'href',
      '/notebooks/offline-notebook',
    )
    expect(screen.getByText('Database is offline')).toBeInTheDocument()
    expect(screen.getByText('Migrations are pending')).toBeInTheDocument()
    expect(screen.getByText('Database status is unavailable')).toBeInTheDocument()
    expect(screen.getByText('Migration status is unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/database unavailable|pending migrations/)).not.toBeInTheDocument()
  })

  it('keeps known runtime readiness while notebooks are still loading', () => {
    dashboardFixtures.notebooks = { data: [], isLoading: true }
    dashboardFixtures.runtime = {
      data: readyRuntimeSnapshot,
      isLoading: false,
      refetch: vi.fn(),
    }

    render(<DashboardPage />)

    expect(screen.getByRole('status', { name: 'Runtime status Ready' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Loading your notebook desk' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Runtime loading' })).toBeNull()
  })
})
