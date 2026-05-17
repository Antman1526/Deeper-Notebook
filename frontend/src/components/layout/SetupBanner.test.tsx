// v0.7.117 — covers the deep-health degraded path of the SetupBanner.
// Existing encryption + env-migration banner behavior is unchanged and
// not re-tested here; this file just pins down the new path.

/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/lib/hooks/use-credentials', () => ({
  useCredentialStatus: vi.fn(),
  useEnvStatus: vi.fn(),
}))

vi.mock('@/lib/hooks/use-deep-health', () => ({
  useDeepHealth: vi.fn(),
  DEEP_HEALTH_QUERY_KEY: ['system', 'healthz', 'deep'],
}))

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(),
}))

import { useCredentialStatus, useEnvStatus } from '@/lib/hooks/use-credentials'
import { useDeepHealth } from '@/lib/hooks/use-deep-health'
import { usePathname } from 'next/navigation'
import { SetupBanner, __resetDeepHealthBannerDismissed } from './SetupBanner'

function neutralCredentials() {
  vi.mocked(useCredentialStatus).mockReturnValue({
    data: {
      configured: {},
      source: {},
      encryption_configured: true,
    },
  } as any)
  vi.mocked(useEnvStatus).mockReturnValue({ data: {} } as any)
}

describe('SetupBanner (deep-health path)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    __resetDeepHealthBannerDismissed()
    vi.mocked(usePathname).mockReturnValue('/notebooks')
    neutralCredentials()
  })

  it('renders nothing when status is healthy', () => {
    vi.mocked(useDeepHealth).mockReturnValue({
      data: {
        status: 'healthy',
        checks: {
          database: { status: 'online', ok: true, error: null },
          migrations: { status: 'applied', ok: true, error: null },
          embedding_model: { status: 'configured', ok: true, error: null },
          chat_model: { status: 'configured', ok: true, error: null },
          command_registry: { status: 'loaded', ok: true, error: null },
        },
      },
    } as any)

    const { container } = render(<SetupBanner />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the banner and links to the wizard when degraded', () => {
    vi.mocked(useDeepHealth).mockReturnValue({
      data: {
        status: 'degraded',
        checks: {
          database: { status: 'online', ok: true, error: null },
          migrations: { status: 'applied', ok: true, error: null },
          embedding_model: { status: 'missing', ok: false, error: 'missing' },
          chat_model: { status: 'configured', ok: true, error: null },
          command_registry: { status: 'loaded', ok: true, error: null },
        },
      },
    } as any)

    render(<SetupBanner />)

    expect(screen.getByTestId('deep-health-banner')).toBeInTheDocument()
    const link = screen.getByText('setupBanner.openWizard').closest('a')
    expect(link).toHaveAttribute('href', '/setup-wizard')
  })

  it('is dismissable for the session', () => {
    vi.mocked(useDeepHealth).mockReturnValue({
      data: {
        status: 'degraded',
        checks: {
          database: { status: 'online', ok: true, error: null },
          migrations: { status: 'applied', ok: true, error: null },
          embedding_model: { status: 'missing', ok: false, error: 'missing' },
          chat_model: { status: 'configured', ok: true, error: null },
          command_registry: { status: 'loaded', ok: true, error: null },
        },
      },
    } as any)

    const { rerender, container } = render(<SetupBanner />)
    expect(screen.getByTestId('deep-health-banner')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('setupBanner.dismiss'))
    rerender(<SetupBanner />)
    expect(container).toBeEmptyDOMElement()
  })

  it('does not render on the wizard route itself', () => {
    vi.mocked(usePathname).mockReturnValue('/setup-wizard')
    vi.mocked(useDeepHealth).mockReturnValue({
      data: {
        status: 'not_ready',
        checks: {
          database: { status: 'offline', ok: false, error: 'down' },
          migrations: { status: 'error', ok: false, error: null },
          embedding_model: { status: 'missing', ok: false, error: null },
          chat_model: { status: 'missing', ok: false, error: null },
          command_registry: { status: 'error', ok: false, error: null },
        },
      },
    } as any)

    const { container } = render(<SetupBanner />)
    expect(container).toBeEmptyDOMElement()
  })
})
