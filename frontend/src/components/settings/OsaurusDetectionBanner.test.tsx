import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { OsaurusDetectionBanner } from './OsaurusDetectionBanner'

// v0.8.36 — banner is a thin shell around a POST /credentials/detect-osaurus
// probe. Tests mock the axios client and assert the four key states:
//   1. Hidden when an Osaurus credential already exists.
//   2. Hidden when the backend reports `running: false`.
//   3. Visible when `running: true` and no credential exists yet.
//   4. Calling "Connect" invalidates the credentials + models query keys.

// Mock Radix Alert primitives (consistent with other test files).
vi.mock('@/components/ui/alert', () => ({
  Alert: ({ children, className }: { children: React.ReactNode; className?: string }) =>
    React.createElement('div', { 'data-testid': 'alert', className }, children),
  AlertTitle: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-title' }, children),
  AlertDescription: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-desc' }, children),
}))

// i18n stub.
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

// Sonner mock (Hook to assert success/error toasts fire).
const toastSuccess = vi.fn()
const toastError = vi.fn()
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}))

// Mock the axios client used by the banner. Each test sets the return.
const apiPost = vi.fn()
vi.mock('@/lib/api/client', () => ({
  default: {
    post: (...args: unknown[]) => apiPost(...args),
  },
}))

function renderBanner(credentials: unknown[] | undefined) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <OsaurusDetectionBanner credentials={credentials as never} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiPost.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
})

describe('OsaurusDetectionBanner', () => {
  it('renders nothing when an Osaurus credential is already present', async () => {
    // Should never call the probe.
    apiPost.mockResolvedValue({
      data: { running: true, port: 1337, models_registered: 0, credential_id: null, detail: '' },
    })
    const { container } = renderBanner([
      { id: 'cred:1', name: 'Osaurus (local MLX)', provider: 'openai_compatible' },
    ])
    // Settle any pending probes (there shouldn't be any).
    await Promise.resolve()
    expect(container.textContent).toBe('')
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('renders nothing when the backend reports Osaurus not running', async () => {
    apiPost.mockResolvedValue({
      data: {
        running: false,
        port: 1337,
        models_registered: 0,
        credential_id: null,
        detail: 'No Osaurus instance reachable',
      },
    })
    const { container } = renderBanner([])
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('renders the Connect banner when Osaurus is running and not yet connected', async () => {
    apiPost.mockResolvedValue({
      data: {
        running: true,
        port: 1337,
        models_registered: 0,
        credential_id: null,
        detail: 'Connected to Osaurus on port 1337',
      },
    })
    renderBanner([])
    // Wait for the query to resolve AND the banner to render. findBy
    // does the wait for us — getBy doesn't, hence the prior failure.
    const title = await screen.findByTestId('alert-title')
    expect(title.textContent).toContain('1337')
    expect(screen.getByText(/Connect Osaurus/)).toBeInTheDocument()
    expect(screen.getByText(/Learn more/)).toBeInTheDocument()
  })

  it('Connect button fires the probe again and shows a success toast', async () => {
    apiPost.mockResolvedValue({
      data: {
        running: true,
        port: 1337,
        models_registered: 3,
        credential_id: 'cred:osaurus-1',
        detail: 'Connected',
      },
    })
    renderBanner([])
    // Wait for the banner to render before clicking.
    const button = await screen.findByText(/Connect Osaurus/)
    button.click()
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled())
    expect(String(toastSuccess.mock.calls[0][0])).toContain('3 models')
  })
})
