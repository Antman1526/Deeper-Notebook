import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RuntimeStatusPanel } from './RuntimeStatusPanel'

const readySnapshot = {
  schema_version: 'runtime-snapshot-v1',
  status: 'ready',
  reasons: [],
  readiness: { state: 'ready', database: 'online', migrations: 'applied' },
  startup: { state: 'ready', stages: [] },
  updates: { state: 'ready', enabled: true, update_available: false, current_version: '0.8.70' },
  vault: { state: 'ready', ready: 2, degraded: 0, unavailable: 0 },
  knowledge: { state: 'ready', projected: 2, unchanged: 1, failed: 0 },
  backup: { state: 'ready', file_count: 1, newest_age_seconds: 30 },
}

describe('RuntimeStatusPanel', () => {
  it.each([
    ['ready', 'Ready'],
    ['degraded', 'Degraded'],
    ['unknown', 'Unknown'],
  ] as const)('renders the %s overall state', (status, label) => {
    render(
      <RuntimeStatusPanel
        snapshot={{ ...readySnapshot, status }}
        onRefresh={vi.fn()}
      />,
    )

    expect(screen.getByRole(status === 'degraded' ? 'alert' : 'status')).toHaveTextContent(label)
  })

  it('uses redacted reason labels and never renders raw provider details', () => {
    render(
      <RuntimeStatusPanel
        snapshot={{
          ...readySnapshot,
          status: 'degraded',
          reasons: ['database_offline', 'migrations_pending', 'database_check_failed'],
          readiness: { state: 'degraded', database: 'offline', migrations: 'pending' },
        }}
      />,
    )

    expect(screen.getByText('Database is offline')).toBeInTheDocument()
    expect(screen.getByText('Migrations are pending')).toBeInTheDocument()
    expect(screen.getByText('Database status is unavailable')).toBeInTheDocument()
    expect(screen.queryByText('database_offline')).not.toBeInTheDocument()
    expect(screen.queryByText(/Users|private|canary|exception|token/i)).not.toBeInTheDocument()
  })

  it('provides a keyboard-reachable manual refresh without creating actions on mount', () => {
    const onRefresh = vi.fn()
    render(<RuntimeStatusPanel snapshot={readySnapshot} onRefresh={onRefresh} />)

    const refresh = screen.getByRole('button', { name: 'Refresh runtime status' })
    expect(refresh).toBeEnabled()
    expect(onRefresh).not.toHaveBeenCalled()
    fireEvent.click(refresh)
    expect(onRefresh).toHaveBeenCalledOnce()
  })
})
