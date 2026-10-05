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
  dialogs: {
    openNotebookDialog: vi.fn(),
    openPodcastDialog: vi.fn(),
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

// v0.8.130 — the page asks /api/config for the data folder (see page.data-path.test.tsx).
vi.mock('@/lib/config', () => ({
  getConfig: async () => ({ apiUrl: '', version: 'test', buildTime: '', dataPath: null }),
}))

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => dashboardFixtures.notebooks,
}))

vi.mock('@/lib/hooks/use-runtime-snapshot', () => ({
  useRuntimeSnapshot: () => dashboardFixtures.runtime,
}))

vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => dashboardFixtures.dialogs,
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: () => process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 === '1',
}))

describe('DashboardPage active product identity', () => {
  beforeEach(() => {
    dashboardFixtures.notebooks = { data: [], isLoading: false }
    dashboardFixtures.runtime = { data: readyRuntimeSnapshot, isLoading: false, refetch: vi.fn() }
    dashboardFixtures.dialogs.openNotebookDialog.mockClear()
    dashboardFixtures.dialogs.openPodcastDialog.mockClear()
  })

  afterEach(() => {
    routerPush.mockClear()
    delete process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO
    delete process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2
  })

  it('presents the canonical product name and tagline', () => {
    render(<DashboardPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' }),
    ).toBeInTheDocument()
    expect(screen.getByText('workspace.intelligenceHorizon.subtitle')).toBeVisible()
  })

  it.each(['0', '1'])('keeps the Horizon presentation compatible with shell flag %s', (flag) => {
    process.env.NEXT_PUBLIC_DN_LUMINOUS_FOLIO = flag
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Deeper Notebook' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.ask' })).toHaveAttribute('href', '/search')
  })

  it('keeps route navigation in the page callback wiring', () => {
    render(<DashboardPage />)

    fireEvent.click(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.studio' }))
    fireEvent.click(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.ask' }))

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
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.databaseOffline')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.migrationsPending')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.databaseCheckFailed')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.migrationsCheckFailed')).toBeInTheDocument()
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

    expect(screen.getByRole('status', { name: 'workspace.runtimeStatusPanel.ariaLabelReady' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'workspace.intelligenceHorizon.loadingTitle' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Runtime loading' })).toBeNull()
  })

  it('uses the V2 home frame with one landmark, one heading, and one dispatch per action', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '1'
    render(<DashboardPage />)

    expect(screen.getByTestId('visual-system-v2-home')).toHaveAttribute(
      'data-dn-visual-system',
      'v2',
    )
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'workspace.workspaceHome.newNotebook' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.workspaceHome.podcast' }))
    fireEvent.click(screen.getByRole('link', { name: 'workspace.workspaceHome.ask' }))

    expect(dashboardFixtures.dialogs.openNotebookDialog).toHaveBeenCalledTimes(1)
    expect(dashboardFixtures.dialogs.openPodcastDialog).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith('/search')
    expect(routerPush).toHaveBeenCalledTimes(1)
  })

  it('retains the Horizon marker and one action tree when V2 is explicitly off', () => {
    process.env.NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2 = '0'
    render(<DashboardPage />)

    // v0.8.130 — Phase 3b: the shell is mounted by (dashboard)/layout.tsx, not the page.
    expect(screen.getByRole('main', { name: 'Deeper Notebook' })).toHaveAttribute(
      'data-dn-horizon-page',
      'true',
    )
    expect(screen.queryByTestId('visual-system-v2-home')).toBeNull()
    expect(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.newNotebook' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.podcast' })).toBeEnabled()
  })
})
