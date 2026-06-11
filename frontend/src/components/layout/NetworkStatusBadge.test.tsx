import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NetworkStatusBadge } from './NetworkStatusBadge'

// v0.8.68 — app-shell offline indicator tests. The polling hook is mocked
// per-case; translation stub mirrors ChatMessageProviderBadge.test.tsx.

const mockUseNetworkStatus = vi.fn()
vi.mock('@/lib/hooks/use-network-status', () => ({
  useNetworkStatus: () => mockUseNetworkStatus(),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _key
      let s = opts.defaultValue ?? _key
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

beforeEach(() => {
  mockUseNetworkStatus.mockReset()
})

describe('NetworkStatusBadge', () => {
  it('renders nothing while online', () => {
    mockUseNetworkStatus.mockReturnValue({
      data: {
        status: 'online', forced_offline: false,
        local_fallback_model: null, checked_epoch_ms: 0,
      },
    })
    render(<NetworkStatusBadge />)
    expect(screen.queryByTestId('network-status-badge')).not.toBeInTheDocument()
  })

  it('renders nothing while status is unknown or data missing', () => {
    mockUseNetworkStatus.mockReturnValue({ data: undefined })
    render(<NetworkStatusBadge />)
    expect(screen.queryByTestId('network-status-badge')).not.toBeInTheDocument()
  })

  it('renders the offline copy with the fallback model name', () => {
    mockUseNetworkStatus.mockReturnValue({
      data: {
        status: 'offline', forced_offline: false,
        local_fallback_model: 'gemma-4-E4B', checked_epoch_ms: 0,
      },
    })
    render(<NetworkStatusBadge />)
    const badge = screen.getByTestId('network-status-badge')
    expect(badge.textContent).toContain('gemma-4-E4B')
    expect(badge.textContent).toContain('Offline')
  })

  it('renders the forced-offline copy when the toggle is on', () => {
    mockUseNetworkStatus.mockReturnValue({
      data: {
        status: 'offline', forced_offline: true,
        local_fallback_model: 'gemma-4-E4B', checked_epoch_ms: 0,
      },
    })
    render(<NetworkStatusBadge />)
    expect(screen.getByTestId('network-status-badge').textContent).toContain(
      'Offline mode on',
    )
  })

  it('renders the generic offline copy with no fallback model', () => {
    mockUseNetworkStatus.mockReturnValue({
      data: {
        status: 'offline', forced_offline: false,
        local_fallback_model: null, checked_epoch_ms: 0,
      },
    })
    render(<NetworkStatusBadge />)
    expect(screen.getByTestId('network-status-badge').textContent).toContain(
      'local features only',
    )
  })
})
