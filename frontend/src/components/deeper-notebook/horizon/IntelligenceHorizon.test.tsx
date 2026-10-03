import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { IntelligenceHorizon } from './IntelligenceHorizon'

const fixtureNotebooks = [
  {
    id: 'research-notebook',
    name: 'Research notebook',
    updated: '2026-08-10T12:00:00.000Z',
  },
] as const

const readyRuntimeSnapshot = {
  schema_version: 'runtime-snapshot-v1' as const,
  status: 'ready' as const,
  reasons: [] as const,
  readiness: { state: 'ready' as const, database: 'online' as const, migrations: 'applied' as const },
  startup: { state: 'ready' as const, stages: [] },
  updates: { state: 'ready' as const, enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready' as const, ready: 1, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready' as const, projected: 1, unchanged: 0, failed: 0 },
  backup: { state: 'ready' as const, file_count: 1, newest_age_seconds: 5 },
}

const distinctRuntimeSnapshot = {
  ...readyRuntimeSnapshot,
  status: 'degraded' as const,
  reasons: ['database_offline', 'migrations_pending', 'database_check_failed', 'migrations_check_failed'] as const,
  readiness: { state: 'degraded' as const, database: 'offline' as const, migrations: 'pending' as const },
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
    runtimeSnapshot: readyRuntimeSnapshot,
    runtimeSnapshotLoading: false,
    dataPath: '~/.deeper-notebook/',
    ...overrides,
  }

  return { ...render(<IntelligenceHorizon {...props} />), props }
}

describe('IntelligenceHorizon', () => {
  it('keeps the four dashboard actions, recent notebook links, and mount quiet', () => {
    const { props } = renderHorizon()

    const horizonPage = screen.getByRole('main', { name: 'Deeper Notebook' })
    expect(horizonPage).toHaveAttribute('data-dn-horizon-page', 'true')
    expect(screen.getByRole('navigation', { name: 'workspace.intelligenceHorizon.actionsAriaLabel' })).toHaveAttribute(
      'data-dn-horizon-actions',
      'true',
    )

    expect(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.studio' })).toHaveAttribute('href', '/studio')
    expect(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.newNotebook' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.podcast' })).toBeEnabled()
    expect(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.ask' })).toHaveAttribute('href', '/search')
    expect(screen.getByRole('link', { name: 'Research notebook' })).toHaveAttribute(
      'href',
      '/notebooks/research-notebook',
    )

    expect(props.onOpenStudio).not.toHaveBeenCalled()
    expect(props.onCreateNotebook).not.toHaveBeenCalled()
    expect(props.onCreatePodcast).not.toHaveBeenCalled()
    expect(props.onAsk).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.studio' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.newNotebook' }))
    fireEvent.click(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.podcast' }))
    fireEvent.click(screen.getByRole('link', { name: 'workspace.intelligenceHorizon.ask' }))

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
    expect(screen.getByTestId('horizon-scroll-region').querySelector('[data-dn-horizon-page="true"]')).not.toBeNull()
  })

  it('shows ready trust status, command hint, and local data path', () => {
    renderHorizon()

    expect(screen.getByRole('status', { name: 'workspace.runtimeStatusPanel.ariaLabelReady' })).toBeVisible()
    expect(screen.getByText(/⌘K|Ctrl\+K/)).toBeVisible()
    expect(screen.getByText('~/.deeper-notebook/')).toBeVisible()
  })

  // v0.8.130 — the tip used to print both platforms' shortcuts ("⌘K / Ctrl+K").
  describe('command hint', () => {
    const originalPlatform = window.navigator.platform
    const setPlatform = (platform: string) =>
      Object.defineProperty(window.navigator, 'platform', { value: platform, configurable: true })
    afterEach(() => setPlatform(originalPlatform))

    it('shows only ⌘K on macOS, in the shared key chip', () => {
      setPlatform('MacIntel')
      renderHorizon()
      const key = screen.getByText('⌘K')
      expect(key).toHaveAttribute('data-slot', 'kbd')
      expect(screen.queryByText(/Ctrl\+K/)).toBeNull()
    })

    it('shows only Ctrl+K elsewhere', () => {
      setPlatform('Win32')
      renderHorizon()
      expect(screen.getByText('Ctrl+K')).toHaveAttribute('data-slot', 'kbd')
      expect(screen.queryByText(/⌘K/)).toBeNull()
    })
  })

  it('preserves runtime loading separately from notebooks', () => {
    renderHorizon({ runtimeSnapshotLoading: true })

    expect(screen.getByRole('status', { name: 'workspace.runtimeStatusPanel.loadingAriaLabel' })).toBeInTheDocument()
  })

  it('preserves degraded runtime readiness separately from notebooks', () => {
    renderHorizon({ runtimeSnapshot: distinctRuntimeSnapshot })

    expect(screen.getByRole('alert', { name: 'workspace.runtimeStatusPanel.ariaLabelDegraded' })).toBeInTheDocument()
  })

  it('keeps loaded notebook links visible while readiness is offline', () => {
    renderHorizon({ runtimeSnapshot: distinctRuntimeSnapshot })

    expect(screen.getByRole('link', { name: 'Research notebook' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Notebook runtime offline' })).toBeNull()
  })

  it('keeps notebook loading independent from readiness state', () => {
    renderHorizon({ runtimeSnapshot: distinctRuntimeSnapshot, notebooksLoading: true })

    expect(screen.getByRole('status', { name: 'workspace.intelligenceHorizon.loadingTitle' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Research notebook' })).toBeNull()
  })

  it('preserves distinct API, database, and migration readiness details', () => {
    renderHorizon({ runtimeSnapshot: distinctRuntimeSnapshot })

    expect(screen.getByText('workspace.runtimeStatusPanel.stateReady')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.databaseOffline')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.migrationsPending')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.databaseCheckFailed')).toBeInTheDocument()
    expect(screen.getByText('workspace.runtimeStatusPanel.reasons.migrationsCheckFailed')).toBeInTheDocument()
    expect(screen.queryByText(/database unavailable|pending migrations/)).not.toBeInTheDocument()
  })

  it('leaves modified and middle clicks to native link behavior', () => {
    const { props } = renderHorizon()
    const studio = screen.getByRole('link', { name: 'workspace.intelligenceHorizon.studio' })
    const ask = screen.getByRole('link', { name: 'workspace.intelligenceHorizon.ask' })
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

    expect(screen.getByRole('status', { name: 'workspace.intelligenceHorizon.emptyTitle' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'workspace.intelligenceHorizon.openStudio' }))
    expect(onOpenStudio).toHaveBeenCalledTimes(1)
  })
})
