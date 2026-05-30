import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RecommendationsPanel } from './RecommendationsPanel'

// v0.8.41 — tests for the MCP recommendations panel. Mirrors the
// shape of the v0.8.39b DownloadPanel.test.tsx since the UX patterns
// are intentionally parallel.

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

const apiGet = vi.fn()
vi.mock('@/lib/api/client', () => ({
  default: { get: (...args: unknown[]) => apiGet(...args) },
}))

// Mock the MCP hooks — the panel uses useMCPServers + useCreateMCPServer.
const mockCreateMutate = vi.fn()
const mockServers = vi.fn()
vi.mock('@/lib/hooks/use-mcp-servers', () => ({
  useMCPServers: () => ({ data: mockServers() }),
  useCreateMCPServer: () => ({
    mutateAsync: (...args: unknown[]) => mockCreateMutate(...args),
    isPending: false,
  }),
}))

const toastSuccess = vi.fn()
const toastError = vi.fn()
const toastInfo = vi.fn()
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    info: (...args: unknown[]) => toastInfo(...args),
  },
}))

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <RecommendationsPanel />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  mockCreateMutate.mockReset()
  mockServers.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
  toastInfo.mockReset()
})

const SAMPLE_RECS = {
  recommendations: [
    {
      id: 'searxng',
      label: 'SearXNG (web search)',
      description: 'Local meta-search engine',
      default_url: 'http://127.0.0.1:8080',
      install_url: 'https://github.com/searxng/searxng',
      tags: ['search', 'recommended'],
      replaces: null,
    },
    {
      id: 'crawl4ai',
      label: 'Crawl4AI (web → markdown)',
      description: 'Web scraping',
      default_url: 'http://127.0.0.1:11235',
      install_url: 'https://github.com/unclecode/crawl4ai',
      tags: ['scraping'],
      replaces: 'Firecrawl ($16/mo)',
    },
  ],
}

describe('RecommendationsPanel', () => {
  it('renders one card per recommendation with tags + replaces badge', async () => {
    apiGet.mockResolvedValue({ data: SAMPLE_RECS })
    mockServers.mockReturnValue([])

    renderPanel()
    expect(await screen.findByTestId('mcp-recommendation-searxng')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-recommendation-crawl4ai')).toBeInTheDocument()
    // Tag badges
    expect(screen.getByText('recommended')).toBeInTheDocument()
    expect(screen.getByText('scraping')).toBeInTheDocument()
    // Replaces badge interpolates Firecrawl
    expect(screen.getByText(/Replaces Firecrawl/)).toBeInTheDocument()
  })

  it('Connect posts to the create-MCP-server hook with the recommendation defaults', async () => {
    apiGet.mockResolvedValue({ data: SAMPLE_RECS })
    mockServers.mockReturnValue([])
    mockCreateMutate.mockResolvedValue({})

    renderPanel()
    const btn = await screen.findByTestId('mcp-connect-searxng')
    fireEvent.click(btn)
    await waitFor(() => expect(mockCreateMutate).toHaveBeenCalled())
    expect(mockCreateMutate).toHaveBeenCalledWith({
      name: 'SearXNG (web search)',
      url: 'http://127.0.0.1:8080',
      enabled: true,
    })
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled())
  })

  it('Shows "Connected" + disables button when a server with that name/url already exists', async () => {
    apiGet.mockResolvedValue({ data: SAMPLE_RECS })
    // SearXNG already registered (by name match).
    mockServers.mockReturnValue([
      {
        id: 'mcp_server:abc',
        name: 'searxng (web search)', // different case — still matches normalized
        url: 'http://different-url',
        enabled: true,
        priority: 50,
      },
    ])

    renderPanel()
    const btn = await screen.findByTestId('mcp-connect-searxng')
    expect(btn).toBeDisabled()
    expect(btn.textContent).toMatch(/Connected/i)
  })

  it('Shows "Connected" via URL match (e.g. server name changed but URL same)', async () => {
    apiGet.mockResolvedValue({ data: SAMPLE_RECS })
    mockServers.mockReturnValue([
      {
        id: 'mcp_server:xyz',
        name: 'My Custom Crawler',
        url: 'http://127.0.0.1:11235',  // matches Crawl4AI default URL
        enabled: true,
        priority: 50,
      },
    ])

    renderPanel()
    const btn = await screen.findByTestId('mcp-connect-crawl4ai')
    expect(btn).toBeDisabled()
  })

  it('Connect failure surfaces detail as an error toast', async () => {
    apiGet.mockResolvedValue({ data: SAMPLE_RECS })
    mockServers.mockReturnValue([])
    mockCreateMutate.mockRejectedValue(new Error('Name already in use'))

    renderPanel()
    const btn = await screen.findByTestId('mcp-connect-searxng')
    fireEvent.click(btn)
    await waitFor(() => expect(toastError).toHaveBeenCalled())
    expect(String(toastError.mock.calls[0][0])).toContain('Name already in use')
  })
})
