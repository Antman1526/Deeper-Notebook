import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const localModelsHealthState = vi.hoisted(() => ({
  value: {
    data: undefined,
    isLoading: false,
  } as {
    data?: {
      overall: 'healthy' | 'degraded' | 'down'
      models: Array<{
        name: string
        status: 'healthy' | 'unhealthy' | 'not_configured' | 'unknown'
        detail: string | null
        latency_ms: number | null
        runtime?: string | null
        endpoint?: string | null
        probe_path?: string | null
      }>
    }
    isLoading: boolean
  },
}))

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => localModelsHealthState.value,
}))

vi.mock('@/components/ui/alert', () => ({
  Alert: ({
    children,
    className,
    ...props
  }: { children: React.ReactNode; className?: string; [key: string]: unknown }) =>
    React.createElement('div', { 'data-testid': 'alert', className, ...props }, children),
  AlertTitle: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-title' }, children),
  AlertDescription: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'alert-desc' }, children),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiPut = vi.fn()
vi.mock('@/lib/api/client', () => ({
  default: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    put: (...args: unknown[]) => apiPut(...args),
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

const hookToastState = vi.hoisted(() => ({
  toast: vi.fn(),
}))

vi.mock('@/lib/hooks/use-toast', () => ({
  useToast: () => ({ toast: hookToastState.toast }),
}))

const clipboardWriteText = vi.fn()

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
  apiPut.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
  hookToastState.toast.mockReset()
  clipboardWriteText.mockReset()
  clipboardWriteText.mockResolvedValue(undefined)
  localModelsHealthState.value = {
    data: undefined,
    isLoading: false,
  }
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: clipboardWriteText },
  })
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
    expect(screen.queryByRole('button', { name: 'Run local benchmark' })).not.toBeInTheDocument()
  })

  it('shows local endpoint connection checks from the health probe', async () => {
    localModelsHealthState.value = {
      isLoading: false,
      data: {
        overall: 'degraded',
        models: [
          {
            name: 'Local GGUF',
            status: 'healthy',
            detail: 'Hermes-3 ready',
            latency_ms: 12,
            runtime: 'llama.cpp',
            endpoint: 'http://127.0.0.1:8080/v1',
            probe_path: '/models',
          },
          {
            name: 'Ollama',
            status: 'unhealthy',
            detail: 'connection failed',
            latency_ms: null,
            runtime: 'ollama',
            endpoint: 'http://127.0.0.1:11434',
            probe_path: '/api/tags',
          },
        ],
      },
    }
    apiGet.mockResolvedValue({
      data: { model_dir: '/tmp/models', available: true, models: [] },
    })

    apiPost.mockResolvedValue({
      data: {
        ok: true,
        path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
        detail: 'Opened in file manager.',
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-connection-checks')).toHaveTextContent(
      'Connection checks',
    )
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent('degraded')
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent('Local GGUF')
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent('llama.cpp')
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent(
      'http://127.0.0.1:8080/v1',
    )
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent('Hermes-3 ready')
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent('12 ms')
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent(
      'Ollama',
    )
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent(
      'ollama',
    )
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent(
      'http://127.0.0.1:11434',
    )
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent(
      '/api/tags',
    )
    expect(screen.getByTestId('local-model-connection-checks')).toHaveTextContent(
      'connection failed',
    )
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
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'qwen2.5-7b-instruct-q4_k_m',
              path: '/tmp/models/qwen2.5-7b-instruct-q4_k_m.gguf',
              runtime: 'gguf',
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 7.0,
              file_size_bytes: 4_368_450_336,
            },
            {
              name: 'mlx-community/Qwen3-Coder-30B-A3B-MLX-4bit',
              path: '/tmp/models/MLX/mlx-community__Qwen3-Coder-30B-A3B-MLX-4bit',
              runtime: 'mlx',
              architecture: 'llama',
              context_length: 131_072,
              quant: '4bit',
              parameter_count_b: 30.0,
              file_size_bytes: 5_500_000_000,
            },
          ],
        },
      })
    })
    renderPage()
    // Wait for the list to appear
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(await screen.findByTestId('local-model-qwen2.5-7b-instruct-q4_k_m')).toBeInTheDocument()
    expect(screen.getByTestId('local-model-mlx-community/Qwen3-Coder-30B-A3B-MLX-4bit')).toBeInTheDocument()
    expect(screen.getByText('GGUF')).toBeInTheDocument()
    expect(screen.getByText('MLX')).toBeInTheDocument()
    // Quant badge present
    expect(screen.getByText('Q4_K_M')).toBeInTheDocument()
    expect(screen.getByText('4bit')).toBeInTheDocument()
    // Param count rendered with B suffix
    expect(screen.getByText('7B')).toBeInTheDocument()
    expect(screen.getByText('30B')).toBeInTheDocument()
    // Context windows: 32k for qwen, 128k for hermes
    expect(screen.getByText('32k')).toBeInTheDocument()
    expect(screen.getByText('128k')).toBeInTheDocument()
    expect(screen.getByTestId('set-active-qwen2.5-7b-instruct-q4_k_m')).toBeInTheDocument()
    expect(
      screen.queryByTestId('set-active-mlx-community/Qwen3-Coder-30B-A3B-MLX-4bit'),
    ).not.toBeInTheDocument()
  })

  it('treats Transformers-only inventory as visible but not runnable yet', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'microsoft/FastContext-1.0-4B-SFT',
            path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
            runtime: 'transformers',
            architecture: 'fastcontext',
            context_length: 262144,
            quant: null,
            parameter_count_b: 4,
            file_size_bytes: 8_044_982_008,
          },
        ],
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-microsoft/FastContext-1.0-4B-SFT')).toBeInTheDocument()
    expect(screen.getByText('Transformers')).toBeInTheDocument()
    expect(screen.getByText('Inventory only')).toBeInTheDocument()
    expect(screen.getByText(/Add a runnable provider/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open launcher preferences' })).toHaveAttribute(
      'href',
      '/settings/launcher-prefs',
    )
    expect(screen.queryByRole('button', { name: 'Run local benchmark' })).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalledWith('/local-models/benchmarks')
  })

  it('uses API setup action fields for inventory-only models', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'microsoft/FastContext-1.0-4B-SFT',
            path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
            runtime: 'transformers',
            runnable: false,
            activation_supported: false,
            runtime_status: 'inventory_only',
            runtime_note: 'Configure a Transformers runtime provider before use.',
            setup_href: '/settings/launcher-prefs?runtime=transformers',
            setup_label: 'Configure Transformers runtime',
            architecture: 'fastcontext',
            context_length: 262144,
            quant: null,
            parameter_count_b: 4,
            file_size_bytes: 8_044_982_008,
          },
        ],
      },
    })

    renderPage()

    expect(await screen.findByText('Configure a Transformers runtime provider before use.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Configure Transformers runtime' })).toHaveAttribute(
      'href',
      '/settings/launcher-prefs?runtime=transformers',
    )
  })

  it('uses API runtime capability fields instead of hardcoding runtime names', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'microsoft/FastContext-1.0-4B-SFT',
              path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
              runtime: 'transformers',
              runnable: true,
              activation_supported: false,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'fastcontext',
              context_length: 262144,
              quant: null,
              parameter_count_b: 4,
              file_size_bytes: 8_044_982_008,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-microsoft/FastContext-1.0-4B-SFT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run local benchmark' })).toBeInTheDocument()
    expect(screen.queryByText('Inventory only')).not.toBeInTheDocument()
    expect(screen.queryByTestId('set-active-microsoft/FastContext-1.0-4B-SFT')).not.toBeInTheDocument()
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/local-models/benchmarks'))
  })

  it('summarizes the local model fleet by runnable status and runtime', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'qwen-7b-q4',
              path: '/tmp/models/GGUF/qwen-7b-q4.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 7,
              file_size_bytes: 2 * 1024 * 1024 * 1024,
            },
            {
              name: 'mlx-community/North-Mini-Code-1.0-6bit',
              path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
              runtime: 'mlx',
              runnable: true,
              activation_supported: false,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: '6bit',
              parameter_count_b: 7,
              file_size_bytes: 3 * 1024 * 1024 * 1024,
            },
            {
              name: 'microsoft/FastContext-1.0-4B-SFT',
              path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
              runtime: 'transformers',
              runnable: false,
              activation_supported: false,
              runtime_status: 'inventory_only',
              runtime_note: 'Visible in inventory.',
              architecture: 'fastcontext',
              context_length: 262144,
              quant: null,
              parameter_count_b: 4,
              file_size_bytes: 1024 * 1024 * 1024,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-fleet-summary')).toBeInTheDocument()
    expect(screen.getByTestId('fleet-summary-installed')).toHaveTextContent('Installed assets')
    expect(screen.getByTestId('fleet-summary-installed')).toHaveTextContent('3')
    expect(screen.getByTestId('fleet-summary-runnable')).toHaveTextContent('Ready to use')
    expect(screen.getByTestId('fleet-summary-runnable')).toHaveTextContent('2')
    expect(screen.getByTestId('fleet-summary-inventory-only')).toHaveTextContent('Setup needed')
    expect(screen.getByTestId('fleet-summary-inventory-only')).toHaveTextContent('1')
    expect(screen.getByTestId('fleet-summary-storage')).toHaveTextContent('Storage')
    expect(screen.getByTestId('fleet-summary-storage')).toHaveTextContent('6.00 GB')
    expect(screen.getByTestId('fleet-total-count')).toHaveTextContent('3 total')
    expect(screen.getByTestId('fleet-runnable-count')).toHaveTextContent('2 runnable')
    expect(screen.getByTestId('fleet-inventory-only-count')).toHaveTextContent('1 inventory-only')
    expect(screen.getByTestId('fleet-runtime-gguf')).toHaveTextContent('1 GGUF')
    expect(screen.getByTestId('fleet-runtime-mlx')).toHaveTextContent('1 MLX')
    expect(screen.getByTestId('fleet-runtime-transformers')).toHaveTextContent('1 Transformers')
  })

  it('shows the native launcher provider and default model when config is available', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          launcher_config: {
            available: true,
            path: '/Users/Antman/.open-notebook-plus/config.toml',
            provider: 'mlx',
            default_model: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
            model_dir: '/tmp/models',
            model_dir_matches_inventory: true,
          },
          models: [
            {
              name: 'mlx-community/North-Mini-Code-1.0-6bit',
              path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
              launcher_model_ref: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
              runtime: 'mlx',
              runnable: true,
              activation_supported: false,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: '6bit',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-launcher-config')).toHaveTextContent(
      'Native launcher',
    )
    expect(screen.getByTestId('local-model-launcher-config')).toHaveTextContent('mlx')
    expect(screen.getByTestId('local-model-launcher-config')).toHaveTextContent(
      'MLX/mlx-community__North-Mini-Code-1.0-6bit',
    )
    expect(screen.getByTestId('local-model-launcher-config')).toHaveTextContent(
      'Model directory matches inventory',
    )
  })

  it('filters the inventory list by readiness', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'qwen-7b-q4',
              path: '/tmp/models/GGUF/qwen-7b-q4.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
            {
              name: 'microsoft/FastContext-1.0-4B-SFT',
              path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
              runtime: 'transformers',
              runnable: false,
              activation_supported: false,
              runtime_status: 'inventory_only',
              runtime_note: 'Visible in inventory.',
              architecture: 'fastcontext',
              context_length: 262144,
              quant: null,
              parameter_count_b: 4,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-qwen-7b-q4')).toBeInTheDocument()
    expect(screen.getByTestId('local-model-microsoft/FastContext-1.0-4B-SFT')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Ready 1/i }))
    expect(screen.getByTestId('local-model-qwen-7b-q4')).toBeInTheDocument()
    await waitFor(() => {
      expect(
        screen.queryByTestId('local-model-microsoft/FastContext-1.0-4B-SFT'),
      ).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('local-models-list')).toHaveTextContent('Showing 1 of 2')

    fireEvent.click(screen.getByRole('tab', { name: /Setup needed 1/i }))
    await waitFor(() => {
      expect(screen.queryByTestId('local-model-qwen-7b-q4')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('local-model-microsoft/FastContext-1.0-4B-SFT')).toBeInTheDocument()
    expect(screen.getByTestId('local-models-list')).toHaveTextContent('Showing 1 of 2')
  })

  it('searches the inventory list across model metadata', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'qwen-7b-q4',
              path: '/tmp/models/GGUF/qwen-7b-q4.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
            {
              name: 'mlx-community/North-Mini-Code-1.0-6bit',
              path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
              runtime: 'mlx',
              runnable: true,
              activation_supported: false,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: '6bit',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
            {
              name: 'microsoft/FastContext-1.0-4B-SFT',
              path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
              runtime: 'transformers',
              runnable: false,
              activation_supported: false,
              runtime_status: 'inventory_only',
              runtime_note: 'Visible in inventory.',
              architecture: 'fastcontext',
              context_length: 262144,
              quant: null,
              parameter_count_b: 4,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-qwen-7b-q4')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: /Search local models/i }), {
      target: { value: 'north' },
    })

    await waitFor(() => {
      expect(screen.queryByTestId('local-model-qwen-7b-q4')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('local-model-mlx-community/North-Mini-Code-1.0-6bit')).toBeInTheDocument()
    expect(
      screen.queryByTestId('local-model-microsoft/FastContext-1.0-4B-SFT'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('local-models-list')).toHaveTextContent('Showing 1 of 3')

    fireEvent.change(screen.getByRole('textbox', { name: /Search local models/i }), {
      target: { value: 'transformers' },
    })

    await waitFor(() => {
      expect(
        screen.queryByTestId('local-model-mlx-community/North-Mini-Code-1.0-6bit'),
      ).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('local-model-microsoft/FastContext-1.0-4B-SFT')).toBeInTheDocument()
    expect(screen.getByTestId('local-models-list')).toHaveTextContent('Showing 1 of 3')
  })

  it('sorts the inventory list by model size', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'tiny-qwen',
              path: '/tmp/models/GGUF/tiny-qwen.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 8192,
              quant: 'Q4_K_M',
              parameter_count_b: 1,
              file_size_bytes: 1000,
            },
            {
              name: 'huge-coder',
              path: '/tmp/models/GGUF/huge-coder.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen3',
              context_length: 262144,
              quant: 'Q6_K',
              parameter_count_b: 27,
              file_size_bytes: 9000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-huge-coder')).toBeInTheDocument()
    const listedBefore = Array.from(
      screen.getByTestId('local-models-list').querySelectorAll('[data-testid^="local-model-"]'),
    ).map(node => node.getAttribute('data-testid'))
    expect(listedBefore).toEqual(['local-model-huge-coder', 'local-model-tiny-qwen'])

    fireEvent.change(screen.getByRole('combobox', { name: /Sort local models/i }), {
      target: { value: 'size-desc' },
    })

    const listedAfter = Array.from(
      screen.getByTestId('local-models-list').querySelectorAll('[data-testid^="local-model-"]'),
    ).map(node => node.getAttribute('data-testid'))
    expect(listedAfter).toEqual(['local-model-huge-coder', 'local-model-tiny-qwen'])

    fireEvent.change(screen.getByRole('combobox', { name: /Sort local models/i }), {
      target: { value: 'size-asc' },
    })

    await waitFor(() => {
      const listedBySmallest = Array.from(
        screen.getByTestId('local-models-list').querySelectorAll('[data-testid^="local-model-"]'),
      ).map(node => node.getAttribute('data-testid'))
      expect(listedBySmallest).toEqual(['local-model-tiny-qwen', 'local-model-huge-coder'])
    })
  })

  it('clears search, readiness filter, and sort from an empty inventory result', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'alpha-chat',
              path: '/tmp/models/GGUF/alpha-chat.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 8192,
              quant: 'Q4_K_M',
              parameter_count_b: 1,
              file_size_bytes: 1000,
            },
            {
              name: 'zeta-transformer',
              path: '/tmp/models/Transformers/zeta-transformer',
              runtime: 'transformers',
              runnable: false,
              activation_supported: false,
              runtime_status: 'inventory_only',
              runtime_note: 'Visible in inventory.',
              architecture: 'fastcontext',
              context_length: 262144,
              quant: null,
              parameter_count_b: 4,
              file_size_bytes: 9000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-alpha-chat')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /Setup needed 1/i }))
    fireEvent.change(screen.getByRole('textbox', { name: /Search local models/i }), {
      target: { value: 'missing' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: /Sort local models/i }), {
      target: { value: 'size-desc' },
    })

    expect(await screen.findByText('No models match the current filters.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Clear filters/i }))

    expect(screen.getByRole('textbox', { name: /Search local models/i })).toHaveValue('')
    expect(screen.getByRole('combobox', { name: /Sort local models/i })).toHaveValue('name-asc')
    expect(screen.getByTestId('local-model-alpha-chat')).toBeInTheDocument()
    expect(screen.getByTestId('local-model-zeta-transformer')).toBeInTheDocument()
    expect(screen.getByTestId('local-models-list')).toHaveTextContent('Showing 2 of 2')
  })

  it('copies a local model path from an inventory card', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'qwen-7b-q4',
            path: '/tmp/models/GGUF/qwen-7b-q4.gguf',
            runtime: 'gguf',
            runnable: true,
            activation_supported: true,
            runtime_status: 'runnable',
            runtime_note: null,
            architecture: 'qwen2',
            context_length: 32768,
            quant: 'Q4_K_M',
            parameter_count_b: 7,
            file_size_bytes: 1000,
          },
        ],
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-qwen-7b-q4')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Copy model path for qwen-7b-q4/i }))

    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalledWith('/tmp/models/GGUF/qwen-7b-q4.gguf')
    })
    expect(toastSuccess).toHaveBeenCalledWith('Model path copied')
  })

  it('copies a launcher model reference from an inventory card', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        models: [
          {
            name: 'mlx-community/North-Mini-Code-1.0-6bit',
            path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
            launcher_model_ref: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
            runtime: 'mlx',
            runnable: true,
            activation_supported: false,
            runtime_status: 'runnable',
            runtime_note: null,
            architecture: 'qwen2',
            context_length: 32768,
            quant: '6bit',
            parameter_count_b: 7,
            file_size_bytes: 1000,
          },
        ],
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-mlx-community/North-Mini-Code-1.0-6bit')).toBeInTheDocument()
    expect(screen.getByText('Launcher ref')).toBeInTheDocument()
    expect(screen.getByText('MLX/mlx-community__North-Mini-Code-1.0-6bit')).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', {
        name: /Copy launcher reference for mlx-community\/North-Mini-Code-1.0-6bit/i,
      }),
    )

    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalledWith(
        'MLX/mlx-community__North-Mini-Code-1.0-6bit',
      )
    })
    expect(toastSuccess).toHaveBeenCalledWith('Launcher reference copied')
  })

  it('shows active and launch-default activation badges', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'mlx',
          default_model: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
          active_gguf_model: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
        },
        models: [
          {
            name: 'Qwen3-8B-Q4_K_M',
            path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
            launcher_model_ref: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
            runtime: 'gguf',
            runnable: true,
            activation_supported: true,
            is_live_active: true,
            is_launch_default: false,
            activation_mode: 'active_now',
            activation_detail: 'This GGUF is the live chat model.',
            runtime_status: 'runnable',
            runtime_note: null,
            architecture: 'qwen2',
            context_length: 32768,
            quant: 'Q4_K_M',
            parameter_count_b: 8,
            file_size_bytes: 1000,
          },
          {
            name: 'mlx-community/North-Mini-Code-1.0-6bit',
            path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
            launcher_model_ref: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
            runtime: 'mlx',
            runnable: true,
            activation_supported: false,
            is_live_active: false,
            is_launch_default: true,
            activation_mode: 'launch_default',
            activation_detail: 'This model is the native launch default.',
            runtime_status: 'runnable',
            runtime_note: null,
            architecture: 'qwen2',
            context_length: 32768,
            quant: '6bit',
            parameter_count_b: 7,
            file_size_bytes: 1000,
          },
        ],
      },
    })

    renderPage()

    const ggufCard = await screen.findByTestId('local-model-Qwen3-8B-Q4_K_M')
    expect(within(ggufCard).getByText('Active now')).toBeInTheDocument()
    expect(within(ggufCard).getByRole('button', {
      name: /Switch live chat model/i,
    })).toBeInTheDocument()

    const mlxCard = await screen.findByTestId(
      'local-model-mlx-community/North-Mini-Code-1.0-6bit',
    )
    expect(within(mlxCard).getAllByText('Launch default').length).toBeGreaterThanOrEqual(1)
    expect(within(mlxCard).queryByTestId(
      'set-active-mlx-community/North-Mini-Code-1.0-6bit',
    )).not.toBeInTheDocument()
  })

  it('summarizes active model, launch default, manifest, and jobs in the control state strip', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({
          data: {
            model_dir: '/tmp/models',
            available: true,
            manifest: {
              path: '/tmp/models/manifests/model_inventory.md',
              available: true,
              entry_count: 4,
              matched_route_count: 2,
              alignment_counts: {
                primary: 1,
                curated: 1,
                untracked: 2,
                missing_model: 0,
                no_manifest: 0,
              },
              reconciliation_counts: {
                matched: 3,
                missing: 1,
                unsupported_runtime: 0,
              },
              reconciliation_entries: [],
            },
            routes: [],
          },
        })
      }
      if (url === '/local-models/snapshot-installs') {
        return Promise.resolve({
          data: {
            snapshot_installs: [
              {
                job_id: 'snap-active',
                repo_id: 'mlx-community/North-Mini-Code-1.0-6bit',
                target_path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
                status: 'downloading',
                error: null,
                log_tail: [],
              },
              {
                job_id: 'snap-done',
                repo_id: 'mlx-community/Done',
                target_path: '/tmp/models/MLX/mlx-community__Done',
                status: 'completed',
                error: null,
                log_tail: [],
              },
            ],
          },
        })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({
          data: {
            benchmarks: [
              {
                job_id: 'benchmark_7',
                roles: ['chat'],
                status: 'completed',
                results: [],
                error: null,
              },
            ],
          },
        })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          launcher_config: {
            available: true,
            path: '/Users/Antman/.open-notebook-plus/config.toml',
            provider: 'mlx',
            default_model: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
            model_dir: '/tmp/models',
            model_dir_matches_inventory: true,
            active_gguf_model: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
          },
          models: [
            {
              name: 'Qwen3-8B-Q4_K_M',
              path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
              launcher_model_ref: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              is_live_active: true,
              is_launch_default: false,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 8,
              file_size_bytes: 1000,
            },
            {
              name: 'mlx-community/North-Mini-Code-1.0-6bit',
              path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
              launcher_model_ref: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
              runtime: 'mlx',
              runnable: true,
              activation_supported: false,
              is_live_active: false,
              is_launch_default: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: '6bit',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    const controlState = await screen.findByTestId('local-model-control-state')
    expect(within(controlState).getByTestId('control-state-active-now')).toHaveTextContent(
      'GGUF/Qwen3-8B-Q4_K_M.gguf',
    )
    expect(within(controlState).getByTestId('control-state-launch-default')).toHaveTextContent(
      'MLX/mlx-community__North-Mini-Code-1.0-6bit',
    )
    expect(controlState).toHaveTextContent('Restart applies next-launch default')
    await waitFor(() => {
      expect(within(controlState).getByTestId('control-state-manifest')).toHaveTextContent(
        '1 primary, 2 untracked',
      )
    })
    expect(controlState).toHaveTextContent('3 matched, 1 missing')
    await waitFor(() => {
      expect(within(controlState).getByTestId('control-state-jobs')).toHaveTextContent(
        '1 installs, benchmark completed',
      )
    })
    expect(controlState).toHaveTextContent('benchmark_7')
  })

  it('shows a visible role-routing error while preserving inventory controls', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.reject(new Error('role router failed'))
      }
      if (url === '/local-models/snapshot-installs') {
        return Promise.resolve({ data: { snapshot_installs: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'Qwen3-8B-Q4_K_M',
              path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
              launcher_model_ref: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 8,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    const controlState = await screen.findByTestId('local-model-control-state')
    await waitFor(() => {
      expect(controlState).toHaveTextContent('Manifest unavailable')
    })
    expect(await screen.findByTestId('local-model-role-routing-error')).toHaveTextContent(
      'Role routing unavailable',
    )
    expect(screen.getByTestId('local-model-Qwen3-8B-Q4_K_M')).toBeInTheDocument()
  })

  it('manages smart routing and local default auto-assignment from Local Models', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/models/defaults') {
        return Promise.resolve({
          data: {
            default_chat_model: 'model:local-chat',
            default_transformation_model: 'model:source-synthesis',
            default_tools_model: null,
            large_context_model: null,
            default_reasoning_model: null,
            default_embedding_model: 'model:embed',
            auto_route_enabled: false,
            auto_route_provider_pref: 'auto',
          },
        })
      }
      if (url === '/models') {
        return Promise.resolve({
          data: [
            {
              id: 'model:local-chat',
              name: 'Local Qwen Chat',
              provider: 'openai_compatible',
              type: 'language',
              created: '2026-06-23T00:00:00Z',
              updated: '2026-06-23T00:00:00Z',
            },
            {
              id: 'model:source-synthesis',
              name: 'North Mini Source Synthesis',
              provider: 'mlx',
              type: 'language',
              created: '2026-06-23T00:00:00Z',
              updated: '2026-06-23T00:00:00Z',
            },
            {
              id: 'model:embed',
              name: 'Nomic Embed Local',
              provider: 'openai_compatible',
              type: 'embedding',
              created: '2026-06-23T00:00:00Z',
              updated: '2026-06-23T00:00:00Z',
            },
          ],
        })
      }
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/snapshot-installs') {
        return Promise.resolve({ data: { snapshot_installs: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'Qwen3-8B-Q4_K_M',
              path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
              launcher_model_ref: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
              runtime: 'gguf',
              runnable: true,
              activation_supported: true,
              runtime_status: 'runnable',
              runtime_note: null,
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 8,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })
    apiPut.mockResolvedValue({
      data: {
        auto_route_enabled: true,
        auto_route_provider_pref: 'auto',
      },
    })
    apiPost.mockResolvedValue({
      data: {
        assigned: { default_tools_model: 'model:local-chat' },
        skipped: [],
        missing: [],
      },
    })

    renderPage()

    const routingDefaults = await screen.findByTestId('local-model-routing-defaults')
    expect(routingDefaults).toHaveTextContent('Local routing and defaults')
    expect(within(routingDefaults).getByTestId('local-model-default-default_chat_model')).toHaveTextContent(
      'Local Qwen Chat',
    )
    expect(within(routingDefaults).getByTestId('local-model-default-default_transformation_model')).toHaveTextContent(
      'North Mini Source Synthesis',
    )
    expect(within(routingDefaults).getByTestId('local-model-default-default_embedding_model')).toHaveTextContent(
      'Nomic Embed Local',
    )
    expect(routingDefaults).toHaveTextContent('3 / 6 assigned')

    fireEvent.click(within(routingDefaults).getByTestId('smart-routing-toggle'))
    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/models/defaults', {
        auto_route_enabled: true,
      })
    })

    fireEvent.click(within(routingDefaults).getByRole('button', { name: 'Fill empty slots' }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/models/auto-assign-capability?force=false')
    })

    fireEvent.click(within(routingDefaults).getByRole('button', { name: 'Reset and re-evaluate' }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/models/auto-assign-capability?force=true')
    })
  })

  it('sets an MLX model as the native launch default', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'none',
          default_model: '',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
        },
        models: [
          {
            name: 'mlx-community/North-Mini-Code-1.0-6bit',
            path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
            launcher_model_ref: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
            runtime: 'mlx',
            runnable: true,
            activation_supported: false,
            runtime_status: 'runnable',
            runtime_note: null,
            architecture: 'qwen2',
            context_length: 32768,
            quant: '6bit',
            parameter_count_b: 7,
            file_size_bytes: 1000,
          },
        ],
      },
    })
    apiPost.mockResolvedValue({
      data: {
        ok: true,
        detail:
          'Native launcher default set to MLX/mlx-community__North-Mini-Code-1.0-6bit. Restart Open Notebook Plus to apply it.',
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'mlx',
          default_model: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
        },
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-mlx-community/North-Mini-Code-1.0-6bit')).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', {
        name: /Set launch default for mlx-community\/North-Mini-Code-1.0-6bit/i,
      }),
    )

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/local-models/launch-default', {
        launcher_model_ref: 'MLX/mlx-community__North-Mini-Code-1.0-6bit',
      })
    })
    expect(toastSuccess).toHaveBeenCalledWith(
      'Native launcher default saved. Restart Open Notebook Plus to apply it.',
    )
  })

  it('sets a GGUF model as the native launch default', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'none',
          default_model: '',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
        },
        models: [
          {
            name: 'Qwen3-8B-Q4_K_M',
            path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
            launcher_model_ref: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
            runtime: 'gguf',
            runnable: true,
            activation_supported: true,
            runtime_status: 'runnable',
            runtime_note: null,
            architecture: 'qwen3',
            context_length: 32768,
            quant: 'Q4_K_M',
            parameter_count_b: 8,
            file_size_bytes: 1000,
          },
        ],
      },
    })
    apiPost.mockResolvedValue({
      data: {
        ok: true,
        detail:
          'Native launcher default set to GGUF/Qwen3-8B-Q4_K_M.gguf. Restart Open Notebook Plus to apply it.',
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'llamacpp',
          default_model: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
        },
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-Qwen3-8B-Q4_K_M')).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', {
        name: /Set launch default for Qwen3-8B-Q4_K_M/i,
      }),
    )

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/local-models/launch-default', {
        launcher_model_ref: 'GGUF/Qwen3-8B-Q4_K_M.gguf',
      })
    })
    expect(toastSuccess).toHaveBeenCalledWith(
      'Native launcher default saved. Restart Open Notebook Plus to apply it.',
    )
  })

  it('sets a legacy GGUF inventory row as the native launch default', async () => {
    apiGet.mockResolvedValue({
      data: {
        model_dir: '/tmp/models',
        available: true,
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'none',
          default_model: '',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
        },
        models: [
          {
            name: 'legacy-qwen-7b-q4',
            path: '/tmp/models/legacy-qwen-7b-q4.gguf',
            launcher_model_ref: 'legacy-qwen-7b-q4.gguf',
            architecture: 'qwen2',
            context_length: 32768,
            quant: 'Q4_K_M',
            parameter_count_b: 7,
            file_size_bytes: 1000,
          },
        ],
      },
    })
    apiPost.mockResolvedValue({
      data: {
        ok: true,
        detail:
          'Native launcher default set to legacy-qwen-7b-q4.gguf. Restart Open Notebook Plus to apply it.',
        launcher_config: {
          available: true,
          path: '/Users/Antman/.open-notebook-plus/config.toml',
          provider: 'llamacpp',
          default_model: 'legacy-qwen-7b-q4.gguf',
          model_dir: '/tmp/models',
          model_dir_matches_inventory: true,
        },
      },
    })

    renderPage()

    expect(await screen.findByTestId('local-model-legacy-qwen-7b-q4')).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', {
        name: /Set launch default for legacy-qwen-7b-q4/i,
      }),
    )

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/local-models/launch-default', {
        launcher_model_ref: 'legacy-qwen-7b-q4.gguf',
      })
    })
  })

  it('renders recommended local roles when role routing is available', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({
          data: {
            model_dir: '/tmp/models',
            available: true,
            manifest: {
              path: '/tmp/models/manifests/model_inventory.md',
              available: true,
              entry_count: 1,
              matched_route_count: 1,
              alignment_counts: {
                primary: 1,
                curated: 0,
                untracked: 1,
                missing_model: 1,
                no_manifest: 0,
              },
            },
            routes: [
              {
                role: 'chat',
                label: 'Default chat',
                confidence: 0.91,
                reason: 'Measured benchmark winner for this role (68 tok/s, 350 ms).',
                model: {
                  name: 'mlx-community/North-Mini-Code-1.0-6bit',
                  path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
                  runtime: 'mlx',
                  architecture: 'qwen2',
                  context_length: 32768,
                  quant: '6bit',
                  parameter_count_b: 7,
                  file_size_bytes: 1000,
                },
                manifest_matches: [
                  {
                    category: 'Coding Assistant - Mac MLX',
                    role: 'primary',
                    repo: 'mlx-community/North-Mini-Code-1.0-6bit',
                    runtime_type: 'MLX',
                    estimated_status: 'downloaded - verified',
                  },
                ],
                manifest_alignment: {
                  status: 'primary',
                  label: 'Manifest primary',
                  reason: 'The selected route model matches a curated primary manifest row.',
                  matched_count: 1,
                  primary_count: 1,
                },
              },
              {
                role: 'study_fast',
                label: 'Fast study tools',
                confidence: 0.77,
                reason: 'Smaller local model should be quick for flashcards and quizzes.',
                model: {
                  name: 'gemma-3-4b-it-Q4_K_M',
                  path: '/tmp/models/GGUF/gemma-3-4b-it-Q4_K_M.gguf',
                  runtime: 'gguf',
                  architecture: 'gemma',
                  context_length: 32768,
                  quant: 'Q4_K_M',
                  parameter_count_b: 4,
                  file_size_bytes: 1000,
                },
                manifest_matches: [],
                manifest_alignment: {
                  status: 'untracked',
                  label: 'Not in manifest',
                  reason: 'gemma-3-4b-it-Q4_K_M is currently recommended, but it is not in the curated AI_Models manifest.',
                  matched_count: 0,
                  primary_count: 0,
                },
                manifest_alternatives: [
                  {
                    category: 'General Chat / Research - GGUF',
                    role: 'backup',
                    repo: 'unsloth/Qwen3-8B-GGUF',
                    local_path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
                    runtime_type: 'GGUF',
                    estimated_status: 'downloaded - verified',
                    notes: 'fast general fallback',
                    matched_model_name: 'Qwen3-8B-Q4_K_M',
                    matched_model_path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
                    matched_model_runtime: 'gguf',
                    reason: 'Curated backup manifest row matched the local scan for General Chat / Research - GGUF; suggested for fast study tools.',
                  },
                ],
                manifest_alternative_note: null,
              },
              {
                role: 'embedding',
                label: 'Embedding and retrieval',
                confidence: 0.82,
                reason: 'Embedding-style model name matches retrieval use.',
                model: {
                  name: 'nomic-embed-text-v1.5.f16',
                  path: '/tmp/models/GGUF/nomic-embed-text-v1.5.f16.gguf',
                  runtime: 'gguf',
                  architecture: 'nomic',
                  context_length: 8192,
                  quant: 'f16',
                  parameter_count_b: 0.1,
                  file_size_bytes: 1000,
                },
                manifest_matches: [],
                manifest_alignment: {
                  status: 'untracked',
                  label: 'Not in manifest',
                  reason: 'nomic-embed-text-v1.5.f16 is currently recommended, but it is not in the curated AI_Models manifest.',
                  matched_count: 0,
                  primary_count: 0,
                },
                manifest_alternatives: [],
                manifest_alternative_note: 'No curated embedding/retrieval manifest row is available yet.',
              },
            ],
          },
        })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'mlx-community/North-Mini-Code-1.0-6bit',
              path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
              runtime: 'mlx',
              architecture: 'qwen2',
              context_length: 32768,
              quant: '6bit',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-role-routing')).toBeInTheDocument()
    expect(screen.getByTestId('local-model-role-chat')).toHaveTextContent('Default chat')
    expect(screen.getByTestId('local-model-role-chat')).toHaveTextContent('91%')
    expect(screen.getByTestId('local-model-role-chat')).toHaveTextContent(
      'Measured benchmark winner',
    )
    expect(screen.getByTestId('local-model-role-chat')).toHaveTextContent(
      'mlx-community/North-Mini-Code-1.0-6bit',
    )
    expect(screen.getByTestId('local-model-role-chat-manifest-match')).toHaveTextContent(
      'Manifest: Coding Assistant - Mac MLX · primary',
    )
    expect(screen.getByTestId('local-model-role-chat-manifest-alignment')).toHaveTextContent(
      'Manifest primary',
    )
    expect(screen.getByTestId('local-model-role-study_fast-manifest-alignment')).toHaveTextContent(
      'Not in manifest',
    )
    expect(screen.getByTestId('local-model-role-study_fast-manifest-alignment')).toHaveTextContent(
      'curated AI_Models manifest',
    )
    expect(screen.getByTestId('local-model-role-study_fast-manifest-alternatives')).toHaveTextContent(
      'Curated alternatives',
    )
    expect(screen.getByTestId('local-model-role-study_fast-manifest-alternatives')).toHaveTextContent(
      'General Chat / Research - GGUF · backup',
    )
    expect(screen.getByTestId('local-model-role-embedding')).toHaveTextContent(
      'nomic-embed-text-v1.5.f16',
    )
    expect(screen.getByTestId('local-model-role-embedding-manifest-alignment')).toHaveTextContent(
      'Not in manifest',
    )
    expect(screen.getByTestId('local-model-role-embedding-manifest-alternative-note')).toHaveTextContent(
      'No curated embedding/retrieval manifest row',
    )

    const fastStudyManifestRow = (
      '| Fast study tools - Suggested | candidate - study_fast | `unsloth/Qwen3-8B-GGUF` | '
      + '`/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf` | GGUF | suggested - review | '
      + 'Open Notebook Plus suggested this curated backup manifest row for Fast study tools; '
      + 'original category: General Chat / Research - GGUF. |'
    )
    fireEvent.click(within(screen.getByTestId('local-model-role-study_fast-manifest-alternatives')).getByRole(
      'button',
      { name: 'Copy manifest draft row for unsloth/Qwen3-8B-GGUF' },
    ))
    await waitFor(() => expect(clipboardWriteText).toHaveBeenLastCalledWith(fastStudyManifestRow))

    apiPost.mockResolvedValueOnce({
      data: {
        ok: true,
        manifest_path: '/tmp/models/manifests/model_inventory.md',
        backup_path: '/tmp/models/manifests/model_inventory.md.bak-20260623-120000',
        row: fastStudyManifestRow,
        duplicate: false,
        detail: 'Manifest row applied with backup.',
        entry: {
          category: 'Fast study tools - Suggested',
          role: 'candidate - study_fast',
          repo: 'unsloth/Qwen3-8B-GGUF',
          local_path: '/tmp/models/GGUF/Qwen3-8B-Q4_K_M.gguf',
          runtime_type: 'GGUF',
          estimated_status: 'suggested - review',
          notes: 'Open Notebook Plus suggested this curated backup manifest row for Fast study tools; original category: General Chat / Research - GGUF.',
        },
      },
    })
    fireEvent.click(within(screen.getByTestId('local-model-role-study_fast-manifest-alternatives')).getByRole(
      'button',
      { name: 'Apply manifest draft row for unsloth/Qwen3-8B-GGUF' },
    ))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/local-models/manifest/rows/apply',
      { row: fastStudyManifestRow },
    ))
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(
      'Manifest row applied. Backup created.',
    ))

    const embeddingManifestRow = (
      '| Embedding and retrieval - Suggested | candidate - embedding | '
      + '`nomic-embed-text-v1.5.f16` | `/tmp/models/GGUF/nomic-embed-text-v1.5.f16.gguf` | '
      + 'gguf | suggested - review | Open Notebook Plus currently recommends this local model '
      + 'for Embedding and retrieval, but it is not represented in the curated manifest yet. |'
    )
    fireEvent.click(within(screen.getByTestId('local-model-role-embedding-manifest-alternative-note')).getByRole(
      'button',
      { name: 'Copy manifest draft row for nomic-embed-text-v1.5.f16' },
    ))
    await waitFor(() => expect(clipboardWriteText).toHaveBeenLastCalledWith(embeddingManifestRow))

    apiPost.mockResolvedValueOnce({
      data: {
        ok: true,
        manifest_path: '/tmp/models/manifests/model_inventory.md',
        backup_path: '/tmp/models/manifests/model_inventory.md.bak-20260623-120001',
        row: embeddingManifestRow,
        duplicate: false,
        detail: 'Manifest row applied with backup.',
        entry: {
          category: 'Embedding and retrieval - Suggested',
          role: 'candidate - embedding',
          repo: 'nomic-embed-text-v1.5.f16',
          local_path: '/tmp/models/GGUF/nomic-embed-text-v1.5.f16.gguf',
          runtime_type: 'gguf',
          estimated_status: 'suggested - review',
          notes: 'Open Notebook Plus currently recommends this local model for Embedding and retrieval, but it is not represented in the curated manifest yet.',
        },
      },
    })
    fireEvent.click(within(screen.getByTestId('local-model-role-embedding-manifest-alternative-note')).getByRole(
      'button',
      { name: 'Apply manifest draft row for nomic-embed-text-v1.5.f16' },
    ))
    await waitFor(() => expect(apiPost).toHaveBeenLastCalledWith(
      '/local-models/manifest/rows/apply',
      { row: embeddingManifestRow },
    ))
  })

  it('shows manifest reconciliation rows with status filters', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({
          data: {
            model_dir: '/tmp/models',
            available: true,
            manifest: {
              path: '/tmp/models/manifests/model_inventory.md',
              available: true,
              entry_count: 2,
              matched_route_count: 1,
              unmatched_entry_count: 1,
              reconciliation_counts: {
                matched: 1,
                missing: 1,
                unsupported_runtime: 1,
              },
              reconciliation_entries: [
                {
                  status: 'matched',
                  status_reason: 'Found in local scan.',
                  category: 'Coding Assistant - Mac MLX',
                  role: 'primary',
                  repo: 'mlx-community/North-Mini-Code-1.0-6bit',
                  local_path: '/Users/Antman/Desktop/AI_Models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
                  runtime_type: 'MLX',
                  estimated_status: 'downloaded - verified',
                  matched_model_name: 'mlx-community/North-Mini-Code-1.0-6bit',
                  matched_model_path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
                  matched_model_runtime: 'mlx',
                },
                {
                  status: 'unsupported_runtime',
                  status_reason: 'Found in scan, but runtime is inventory-only.',
                  category: 'Agentic Workflows - Transformers',
                  role: 'backup',
                  repo: 'microsoft/FastContext-1.0-4B-SFT',
                  local_path: '/Users/Antman/Desktop/AI_Models/Transformers/microsoft__FastContext-1.0-4B-SFT',
                  runtime_type: 'Transformers',
                  estimated_status: 'skipped - existing verified',
                  matched_model_name: 'microsoft/FastContext-1.0-4B-SFT',
                  matched_model_path: '/tmp/models/Transformers/microsoft__FastContext-1.0-4B-SFT',
                  matched_model_runtime: 'transformers',
                  setup_task: {
                    action_type: 'configure_runtime',
                    label: 'Open launcher preferences',
                    description: 'Configure a runtime provider.',
                    repo_id: 'microsoft/FastContext-1.0-4B-SFT',
                    filename: null,
                    target_path: '/Users/Antman/Desktop/AI_Models/Transformers/microsoft__FastContext-1.0-4B-SFT',
                    command: null,
                    setup_href: '/settings/launcher-prefs',
                  },
                },
                {
                  status: 'missing',
                  status_reason: 'Not found in local scan.',
                  category: 'Reasoning - Mac MLX',
                  role: 'backup',
                  repo: 'missing/Curated-Model-4bit',
                  local_path: '/Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
                  runtime_type: 'MLX',
                  estimated_status: 'missing from scan',
                  setup_task: {
                    action_type: 'download_snapshot',
                    label: 'Copy setup command',
                    description: 'Copy a Hugging Face snapshot download command.',
                    repo_id: 'missing/Curated-Model-4bit',
                    filename: null,
                    target_path: '/Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
                    command: 'huggingface-cli download missing/Curated-Model-4bit --local-dir /Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
                    setup_href: null,
                  },
                },
              ],
              unmatched_entries: [
                {
                  category: 'Reasoning - Mac MLX',
                  role: 'backup',
                  repo: 'missing/Curated-Model-4bit',
                  local_path: '/Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
                  runtime_type: 'MLX',
                  estimated_status: 'missing from scan',
                },
              ],
            },
            routes: [],
          },
        })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'mlx-community/North-Mini-Code-1.0-6bit',
              path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
              runtime: 'mlx',
              architecture: 'qwen2',
              context_length: 32768,
              quant: '6bit',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })

    renderPage()

    expect(await screen.findByTestId('local-model-manifest-reconciliation')).toBeInTheDocument()
    expect(screen.getByTestId('local-model-manifest-reconciliation')).toHaveTextContent(
      'Manifest reconciliation',
    )
    expect(screen.getByTestId('local-model-manifest-reconciliation')).toHaveTextContent(
      'mlx-community/North-Mini-Code-1.0-6bit',
    )
    expect(screen.getByTestId('local-model-manifest-reconciliation')).toHaveTextContent(
      'microsoft/FastContext-1.0-4B-SFT',
    )
    expect(screen.getByTestId('local-model-manifest-reconciliation')).toHaveTextContent(
      'missing/Curated-Model-4bit',
    )

    const reconciliation = screen.getByTestId('local-model-manifest-reconciliation')

    fireEvent.click(within(reconciliation).getByLabelText(
      'Copy matched scan path for mlx-community/North-Mini-Code-1.0-6bit',
    ))
    await waitFor(() => expect(clipboardWriteText).toHaveBeenLastCalledWith(
      '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
    ))
    fireEvent.click(within(reconciliation).getByLabelText(
      'Reveal matched model path for mlx-community/North-Mini-Code-1.0-6bit',
    ))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/local-models/reveal',
      { path: '/tmp/models/MLX/mlx-community__North-Mini-Code-1.0-6bit' },
    ))

    fireEvent.click(within(reconciliation).getByRole('tab', { name: /Missing/i }))
    expect(within(reconciliation).queryByText('mlx-community/North-Mini-Code-1.0-6bit')).not.toBeInTheDocument()
    expect(within(reconciliation).queryByText('microsoft/FastContext-1.0-4B-SFT')).not.toBeInTheDocument()
    expect(within(reconciliation).getByText('missing/Curated-Model-4bit')).toBeInTheDocument()
    fireEvent.click(within(reconciliation).getByLabelText(
      'Copy manifest local path for missing/Curated-Model-4bit',
    ))
    await waitFor(() => expect(clipboardWriteText).toHaveBeenLastCalledWith(
      '/Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
    ))
    fireEvent.click(within(reconciliation).getByLabelText(
      'Copy setup command for missing/Curated-Model-4bit',
    ))
    await waitFor(() => expect(clipboardWriteText).toHaveBeenLastCalledWith(
      'huggingface-cli download missing/Curated-Model-4bit --local-dir /Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
    ))
    fireEvent.click(within(reconciliation).getByLabelText(
      'Start snapshot install for missing/Curated-Model-4bit',
    ))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/local-models/snapshot-installs',
      {
        repo_id: 'missing/Curated-Model-4bit',
        target_path: '/Users/Antman/Desktop/AI_Models/MLX/missing__Curated-Model-4bit',
      },
    ))

    fireEvent.click(within(reconciliation).getByRole('tab', { name: /Unsupported/i }))
    expect(within(reconciliation).queryByText('missing/Curated-Model-4bit')).not.toBeInTheDocument()
    expect(within(reconciliation).getAllByText('microsoft/FastContext-1.0-4B-SFT').length).toBeGreaterThan(0)
    expect(within(reconciliation).getByRole('link', {
      name: 'Open launcher preferences for microsoft/FastContext-1.0-4B-SFT',
    })).toHaveAttribute('href', '/settings/launcher-prefs')
  })

  it('starts a manifest-provided GGUF download task from a missing reconciliation row', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({
          data: {
            model_dir: '/tmp/models',
            available: true,
            manifest: {
              path: '/tmp/models/manifests/model_inventory.md',
              available: true,
              entry_count: 1,
              matched_route_count: 0,
              unmatched_entry_count: 1,
              reconciliation_counts: {
                matched: 0,
                missing: 1,
                unsupported_runtime: 0,
              },
              reconciliation_entries: [
                {
                  status: 'missing',
                  status_reason: 'Not found in local scan.',
                  category: 'General Chat - GGUF',
                  role: 'primary',
                  repo: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
                  local_path: '/tmp/models/GGUF/bartowski__Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                  runtime_type: 'GGUF',
                  estimated_status: 'missing from scan',
                  setup_task: {
                    action_type: 'download_gguf',
                    label: 'Download GGUF',
                    description: 'Start a managed GGUF download.',
                    repo_id: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
                    filename: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                    target_path: '/tmp/models/GGUF/bartowski__Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                    command: null,
                    setup_href: null,
                  },
                },
              ],
              unmatched_entries: [],
            },
            routes: [],
          },
        })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'ready-model',
              path: '/tmp/models/GGUF/ready-model.gguf',
              runtime: 'gguf',
              architecture: 'qwen2',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 7,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })
    apiPost.mockResolvedValue({
      data: {
        job_id: 'download-1',
        status: 'queued',
        target_path: '/tmp/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
        bytes_downloaded: 0,
        bytes_total: 0,
      },
    })

    renderPage()

    const reconciliation = await screen.findByTestId('local-model-manifest-reconciliation')
    fireEvent.click(within(reconciliation).getByLabelText(
      'Start GGUF download for bartowski/Qwen2.5-7B-Instruct-GGUF',
    ))

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/local-models/download',
      {
        repo_id: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
        filename: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
        target_path: '/tmp/models/GGUF/bartowski__Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
      },
    ))
  })

  it('cancels an active snapshot install from the status card', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/snapshot-installs') {
        return Promise.resolve({
          data: {
            snapshot_installs: [
              {
                job_id: 'snap-active',
                repo_id: 'mlx-community/Test-MLX',
                target_path: '/tmp/models/MLX/mlx-community__Test-MLX',
                status: 'downloading',
                error: null,
                log_tail: ['Downloading mlx-community/Test-MLX into target'],
              },
            ],
          },
        })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [],
        },
      })
    })
    apiPost.mockResolvedValue({
      data: {
        ok: true,
        detail: 'Cancellation requested',
      },
    })

    renderPage()

    const installs = await screen.findByTestId('local-model-snapshot-installs')
    expect(installs).toHaveTextContent('mlx-community/Test-MLX')

    fireEvent.click(within(installs).getByLabelText(
      'Cancel snapshot install for mlx-community/Test-MLX',
    ))

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/local-models/snapshot-installs/snap-active/cancel',
    ))
    expect(toastSuccess).toHaveBeenCalledWith(
      'Snapshot install cancellation requested',
    )
  })

  it('starts a local benchmark job and renders benchmark results', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/role-routing') {
        return Promise.resolve({ data: { model_dir: '/tmp/models', available: true, routes: [] } })
      }
      if (url === '/local-models/benchmarks') {
        return Promise.resolve({ data: { benchmarks: [] } })
      }
      return Promise.resolve({
        data: {
          model_dir: '/tmp/models',
          available: true,
          models: [
            {
              name: 'gemma-3-4b-it-Q4_K_M',
              path: '/tmp/models/GGUF/gemma-3-4b-it-Q4_K_M.gguf',
              runtime: 'gguf',
              architecture: 'gemma',
              context_length: 32768,
              quant: 'Q4_K_M',
              parameter_count_b: 4,
              file_size_bytes: 1000,
            },
          ],
        },
      })
    })
    apiPost.mockResolvedValue({
      data: {
        job_id: 'benchmark_1',
        roles: ['study_fast'],
        status: 'completed',
        results: [
          {
            role: 'study_fast',
            label: 'Fast study tools',
            status: 'completed',
            model_name: 'gemma-3-4b-it-Q4_K_M',
            model_runtime: 'gguf',
            model_id: 'model:gemma',
            provider: 'openai_compatible',
            latency_ms: 350,
            tokens_per_second: 68,
            score: 67.65,
            error: null,
          },
        ],
        error: null,
        created_at: 1,
        completed_at: 2,
      },
    })

    renderPage()

    const button = await screen.findByRole('button', { name: 'Run local benchmark' })
    button.click()

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/local-models/benchmarks', {
        roles: ['chat', 'source_synthesis', 'coding_research', 'study_fast'],
      })
    })
    expect(await screen.findByTestId('local-model-benchmark-results')).toHaveTextContent(
      'Fast study tools',
    )
    expect(screen.getByTestId('local-model-benchmark-results')).toHaveTextContent(
      '68 tok/s',
    )
  })
})
