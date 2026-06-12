import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import LocalModelsPage from './page'

// v0.8.39 Phase 4a — smoke tests for the Local Models inventory page.
// Covers the three top-level states (empty dir, empty list, populated)
// without standing up the full AppShell layout machinery.

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'app-shell' }, children),
}))

// v0.8.40b — DownloadPanel has its own dedicated tests; stub it out
// here so the page-level tests don't pull in its recommendations
// query (which would need its own apiGet mock layered on top of
// the inventory mock).
vi.mock('./DownloadPanel', () => ({
  DownloadPanel: () => React.createElement('div', {
    'data-testid': 'download-panel-stub',
  }),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _k
      let s = opts.defaultValue ?? _k
      // i18next-style {{var}} interpolation for assertions on the
      // rendered string. Matches the same shape DownloadPanel +
      // SidecarLogPopover tests use.
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

vi.mock('@/components/ui/alert', () => ({
  Alert: ({ children, className }: { children: React.ReactNode; className?: string }) =>
    React.createElement('div', { 'data-testid': 'alert', className }, children),
  AlertTitle: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-title' }, children),
  AlertDescription: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-desc' }, children),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
vi.mock('@/lib/api/client', () => ({
  default: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
  },
}))

const toastSuccess = vi.fn()
const toastError = vi.fn()
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <LocalModelsPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
})

describe('LocalModelsPage', () => {
  it('shows "directory not found" when backend reports available=false', async () => {
    apiGet.mockResolvedValue({
      data: { model_dir: '/nope', available: false, models: [] },
    })
    renderPage()
    expect(
      await screen.findByText(/Model directory not found/i),
    ).toBeInTheDocument()
  })

  it('shows the empty-state with HuggingFace link when dir exists but no models', async () => {
    apiGet.mockResolvedValue({
      data: { model_dir: '/tmp/models', available: true, models: [] },
    })
    renderPage()
    expect(await screen.findByText(/No models installed yet/i)).toBeInTheDocument()
    expect(screen.getByText(/Browse on HuggingFace/i)).toBeInTheDocument()
  })

  it('Set Active button POSTs to /set-active and toasts on success', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'qwen-7b-q4',
            path: '/tmp/models/qwen-7b-q4.gguf',
            architecture: 'qwen2',
            context_length: 32768,
            quant: 'Q4_K_M',
            parameter_count_b: 7.0,
            file_size_bytes: 1000,
          },
        ],
      },
    })
    apiPost.mockResolvedValue({
      data: {
        ok: true,
        path: '/tmp/models/qwen-7b-q4.gguf',
        detail: 'Chat sidecar swapped (pid=4242)',
      },
    })
    renderPage()
    const btn = await screen.findByTestId('set-active-qwen-7b-q4')
    btn.click()
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/local-models/set-active', {
        path: '/tmp/models/qwen-7b-q4.gguf',
      }),
    )
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled())
  })

  it('Set Active failure surfaces detail as an error toast', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'bad-q4',
            path: '/tmp/models/bad-q4.gguf',
            architecture: null,
            context_length: null,
            quant: 'Q4_K_M',
            parameter_count_b: null,
            file_size_bytes: 100,
          },
        ],
      },
    })
    apiPost.mockResolvedValue({
      data: {
        ok: false,
        path: '/tmp/models/bad-q4.gguf',
        detail: 'GGUF metadata read failed',
      },
    })
    renderPage()
    const btn = await screen.findByTestId('set-active-bad-q4')
    btn.click()
    await waitFor(() => expect(toastError).toHaveBeenCalled())
    expect(String(toastError.mock.calls[0][0])).toContain('GGUF metadata')
  })

  it('renders a card per installed model with metadata', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'qwen2.5-7b-instruct-q4_k_m',
            path: '/tmp/models/qwen2.5-7b-instruct-q4_k_m.gguf',
            architecture: 'qwen2',
            context_length: 32768,
            quant: 'Q4_K_M',
            parameter_count_b: 7.0,
            file_size_bytes: 4_368_450_336,
          },
          {
            name: 'hermes-3-8b-q5_k_m',
            path: '/tmp/models/hermes-3-8b-q5_k_m.gguf',
            architecture: 'llama',
            context_length: 131_072,
            quant: 'Q5_K_M',
            parameter_count_b: 8.0,
            file_size_bytes: 5_500_000_000,
          },
        ],
      },
    })
    renderPage()
    // Wait for the list to appear
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(await screen.findByTestId('local-model-qwen2.5-7b-instruct-q4_k_m')).toBeInTheDocument()
    expect(screen.getByTestId('local-model-hermes-3-8b-q5_k_m')).toBeInTheDocument()
    // Quant badge present
    expect(screen.getByText('Q4_K_M')).toBeInTheDocument()
    expect(screen.getByText('Q5_K_M')).toBeInTheDocument()
    // Param count rendered with B suffix
    expect(screen.getByText('7B')).toBeInTheDocument()
    expect(screen.getByText('8B')).toBeInTheDocument()
    // Context windows: 32k for qwen, 128k for hermes
    expect(screen.getByText('32k')).toBeInTheDocument()
    expect(screen.getByText('128k')).toBeInTheDocument()
  })
})
