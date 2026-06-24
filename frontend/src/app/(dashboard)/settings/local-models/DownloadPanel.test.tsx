import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DownloadPanel } from './DownloadPanel'

// v0.8.39b — tests for the curated-recommendations + downloader panel.

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _k
      let s = opts.defaultValue ?? _k
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

// Simple Progress stub
vi.mock('@/components/ui/progress', () => ({
  Progress: ({ value }: { value?: number }) =>
    React.createElement('div', {
      'data-testid': 'progress',
      'data-value': String(value ?? '?'),
    }),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
vi.mock('@/lib/api/client', () => ({
  default: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
  },
}))

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DownloadPanel />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
})

describe('DownloadPanel', () => {
  it('renders recommendation cards from /recommendations', async () => {
    apiGet.mockResolvedValue({
      data: {
        recommendations: [
          {
            id: 'rec-1',
            label: 'Qwen 2.5 7B',
            description: 'A nice model',
            repo_id: 'bartowski/foo',
            filename: 'foo.gguf',
            approx_size_gb: 4.7,
            tags: ['chat', 'recommended'],
            context_length: 32768,
          },
        ],
      },
    })
    renderPanel()
    expect(await screen.findByTestId('recommendation-rec-1')).toBeInTheDocument()
    expect(screen.getByText(/Qwen 2.5 7B/)).toBeInTheDocument()
    // Size hint formatted
    expect(screen.getByText(/4.7 GB/)).toBeInTheDocument()
    // Context formatted in k
    expect(screen.getByText('32k')).toBeInTheDocument()
  })

  it('Download button POSTs and shows in-flight progress', async () => {
    apiGet.mockResolvedValueOnce({
      data: {
        recommendations: [
          {
            id: 'rec-1',
            label: 'Qwen',
            description: '',
            repo_id: 'r/a',
            filename: 'a.gguf',
            approx_size_gb: 1.0,
            tags: ['chat'],
            context_length: 8192,
          },
        ],
      },
    })
    apiPost.mockResolvedValue({
      data: {
        job_id: 'job-1',
        status: 'downloading',
        target_path: '/tmp/a.gguf',
        bytes_downloaded: 0,
        bytes_total: 1000,
      },
    })

    renderPanel()
    const btn = await screen.findByTestId('download-rec-1')
    fireEvent.click(btn)
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    // After the mutation resolves the in-flight UI swaps in.
    expect(await screen.findByText(/Downloading/i)).toBeInTheDocument()
    expect(screen.getByTestId('progress')).toBeInTheDocument()
  })

  it('starts a snapshot install for manifest MLX recommendations', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/recommendations') {
        return Promise.resolve({
          data: {
            source: 'manifest',
            recommendations: [
              {
                id: 'manifest-mlx',
                label: 'North Mini Code',
                description: 'primary - missing',
                repo_id: 'mlx-community/North-Mini-Code-1.0-6bit',
                filename: 'mlx-community__North-Mini-Code-1.0-6bit',
                runtime_type: 'MLX',
                target_path: '/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
                status: 'missing',
                tags: ['manifest', 'mlx', 'primary'],
                setup_task: {
                  action_type: 'download_snapshot',
                  label: 'Install snapshot',
                  description: 'Install full repo',
                  repo_id: 'mlx-community/North-Mini-Code-1.0-6bit',
                  target_path: '/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
                },
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: { downloads: [] } })
    })
    apiPost.mockResolvedValue({
      data: {
        job_id: 'snap-1',
        repo_id: 'mlx-community/North-Mini-Code-1.0-6bit',
        target_path: '/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
        status: 'queued',
        error: null,
        log_tail: [],
      },
    })

    renderPanel()
    const btn = await screen.findByTestId('download-manifest-mlx')
    expect(btn.textContent).toMatch(/Install snapshot/i)
    fireEvent.click(btn)

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/local-models/snapshot-installs', {
        repo_id: 'mlx-community/North-Mini-Code-1.0-6bit',
        target_path: '/models/MLX/mlx-community__North-Mini-Code-1.0-6bit',
      }),
    )
  })

  it('uses manifest target_path for direct GGUF recommendations', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/recommendations') {
        return Promise.resolve({
          data: {
            source: 'manifest',
            recommendations: [
              {
                id: 'manifest-gguf',
                label: 'Qwen GGUF',
                description: 'primary - missing',
                repo_id: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
                filename: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                runtime_type: 'GGUF',
                target_path: '/models/GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                status: 'missing',
                tags: ['manifest', 'gguf', 'primary'],
                setup_task: {
                  action_type: 'download_gguf',
                  label: 'Download GGUF',
                  description: 'Download exact file',
                  repo_id: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
                  filename: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                  target_path: '/models/GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
                },
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: { downloads: [] } })
    })
    apiPost.mockResolvedValue({
      data: {
        job_id: 'job-gguf',
        status: 'queued',
        target_path: '/models/GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
        bytes_downloaded: 0,
        bytes_total: 0,
      },
    })

    renderPanel()
    const btn = await screen.findByTestId('download-manifest-gguf')
    fireEvent.click(btn)

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/local-models/download', {
        repo_id: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
        filename: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
        target_path: '/models/GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
      }),
    )
  })

  it('v0.8.39e — shows Cancel button on in-flight downloads + clicking POSTs to /cancel', async () => {
    apiGet.mockResolvedValueOnce({
      data: {
        recommendations: [
          {
            id: 'r1',
            label: 'Big Model',
            description: '',
            repo_id: 'r/x',
            filename: 'big.gguf',
            approx_size_gb: 5.0,
            tags: ['chat'],
            context_length: 32768,
          },
        ],
      },
    })
    // Initial POST returns "downloading" so the Cancel button is visible.
    apiPost.mockResolvedValueOnce({
      data: {
        job_id: 'job-big',
        status: 'downloading',
        target_path: '/tmp/big.gguf',
        bytes_downloaded: 1000,
        bytes_total: 5000,
      },
    })
    // Second apiPost call (the cancel) returns ok.
    apiPost.mockResolvedValueOnce({
      data: { ok: true, detail: 'Cancellation requested' },
    })

    renderPanel()
    const dl = await screen.findByTestId('download-r1')
    fireEvent.click(dl)
    await waitFor(() => expect(apiPost).toHaveBeenCalled())

    // Cancel button should now be visible.
    const cancelBtn = await screen.findByTestId('cancel-r1')
    fireEvent.click(cancelBtn)
    // Verify the cancel POST hit the right URL.
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/local-models/downloads/job-big/cancel'),
    )
  })

  it('shows completed state when status flips to completed', async () => {
    apiGet.mockResolvedValueOnce({
      data: {
        recommendations: [
          {
            id: 'r1',
            label: 'X',
            description: '',
            repo_id: 'r/x',
            filename: 'x.gguf',
            approx_size_gb: 1.0,
            tags: [],
            context_length: 8192,
          },
        ],
      },
    })
    // Initial POST returns "completed" right away (e.g. user re-clicked
    // after finish) — verifies the completed-state render.
    apiPost.mockResolvedValue({
      data: {
        job_id: 'job-X',
        status: 'completed',
        target_path: '/tmp/x.gguf',
        bytes_downloaded: 1000,
        bytes_total: 1000,
      },
    })
    renderPanel()
    const btn = await screen.findByTestId('download-r1')
    fireEvent.click(btn)
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect(await screen.findByText(/Installed/i)).toBeInTheDocument()
  })

  it('v0.8.39d — seeds a Resume button from a reconciled (cancelled) download on mount', async () => {
    // URL-routing mock so call ordering between the two mount queries
    // (recommendations + downloads) is irrelevant.
    apiGet.mockImplementation((url: string) => {
      if (url === '/local-models/recommendations') {
        return Promise.resolve({
          data: {
            recommendations: [
              {
                id: 'r1',
                label: 'Qwen',
                description: '',
                repo_id: 'r/x',
                filename: 'x.gguf',
                approx_size_gb: 5.0,
                tags: ['chat'],
                context_length: 32768,
              },
            ],
          },
        })
      }
      if (url === '/local-models/downloads') {
        // The backend reconciled an interrupted download from disk.
        return Promise.resolve({
          data: {
            downloads: [
              {
                job_id: 'reconciled-1',
                status: 'cancelled',
                repo_id: 'r/x',
                filename: 'x.gguf',
                target_path: '/tmp/x.gguf',
                bytes_downloaded: 2048,
                bytes_total: 5000,
                error: null,
              },
            ],
          },
        })
      }
      return Promise.resolve({ data: {} })
    })

    renderPanel()
    // The matching card should render the cancelled/resumable state →
    // "Resume" button rather than "Download".
    const btn = await screen.findByTestId('download-r1')
    await waitFor(() => expect(btn.textContent).toMatch(/Resume/i))
  })
})
