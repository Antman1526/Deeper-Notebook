import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  SidecarLogPopover,
  sidecarKindFromName,
} from './SidecarLogPopover'

// v0.8.38 Phase 3 — tests for the sidecar-log popover and the
// credential-name → kind heuristic mapping. Popover Radix primitives
// are mocked so JSDOM renders content unconditionally.

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children, onOpenChange }: {
    children: React.ReactNode; open?: boolean; onOpenChange?: (v: boolean) => void
  }) => {
    // Auto-open immediately so the content fetch fires in tests.
    React.useEffect(() => {
      onOpenChange?.(true)
    }, [onOpenChange])
    return React.createElement('div', { 'data-testid': 'popover-root' }, children)
  },
  PopoverTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('div', null, children),
  PopoverContent: ({ children, ...rest }: { children: React.ReactNode } & Record<string, unknown>) =>
    React.createElement('div', { 'data-testid': rest['data-testid'] }, children),
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

function renderPopover(kind: 'chat' | 'embed' | 'whisper' | 'piper' | 'memory') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SidecarLogPopover kind={kind}>
        <span data-testid="trigger">trigger</span>
      </SidecarLogPopover>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
})

describe('sidecarKindFromName', () => {
  it('maps llama.cpp / GGUF / chat names to "chat"', () => {
    expect(sidecarKindFromName('Local GGUF (llama.cpp)')).toBe('chat')
    expect(sidecarKindFromName('llama.cpp (local)')).toBe('chat')
    expect(sidecarKindFromName('Osaurus (local MLX)')).toBe(null)  // intentional — Osaurus has its own lifecycle
    expect(sidecarKindFromName('My chat sidecar')).toBe('chat')
  })

  it('maps embedding names to "embed"', () => {
    expect(sidecarKindFromName('Local Embeddings (llama.cpp)')).toBe('embed')
    expect(sidecarKindFromName('nomic embed')).toBe('embed')
  })

  it('maps whisper/STT/piper/memory names', () => {
    expect(sidecarKindFromName('Whisper (local)')).toBe('whisper')
    expect(sidecarKindFromName('Faster Whisper')).toBe('whisper')
    expect(sidecarKindFromName('Piper TTS')).toBe('piper')
    expect(sidecarKindFromName('Memory retriever')).toBe('memory')
  })

  it('returns null for unknown names', () => {
    expect(sidecarKindFromName('OpenAI gpt-4o')).toBe(null)
    expect(sidecarKindFromName('')).toBe(null)
  })
})

describe('SidecarLogPopover', () => {
  it('renders unavailable state when backend reports available=false', async () => {
    apiGet.mockResolvedValue({
      data: { kind: 'chat', log: '', hint: null, available: false },
    })
    renderPopover('chat')
    // findBy* waits for the query to resolve AND React to re-render.
    expect(await screen.findByText(/No log captured/i)).toBeInTheDocument()
  })

  it('renders the raw log + hint when available', async () => {
    apiGet.mockResolvedValue({
      data: {
        kind: 'chat',
        log: 'llama_model_load: failed to load model\n',
        hint: 'Model file could not be loaded — check the GGUF path and integrity.',
        available: true,
      },
    })
    renderPopover('chat')
    expect(
      await screen.findByText(/Model file could not be loaded/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/llama_model_load/)).toBeInTheDocument()
    // v0.8.40 — in-place restart replaces the "quit and relaunch" hint
    expect(screen.getByText(/Restart this sidecar/i)).toBeInTheDocument()
    expect(screen.getByTestId('sidecar-restart-chat')).toBeInTheDocument()
  })

  it('clicking Restart POSTs to /restart and toasts on success', async () => {
    // First: log fetch resolves so the body shows.
    apiGet.mockResolvedValue({
      data: {
        kind: 'chat',
        log: 'startup output\nfailed to load model',
        hint: 'Model file could not be loaded',
        available: true,
      },
    })
    // Then: restart POST returns ok=true with detail.
    apiPost.mockResolvedValue({
      data: { kind: 'chat', ok: true, detail: 'Sidecar restarted (pid=4242)' },
    })

    renderPopover('chat')
    const btn = await screen.findByTestId('sidecar-restart-chat')
    btn.click()
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/healthz/sidecars/chat/restart'))
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled())
  })

  it('Restart failure surfaces detail as an error toast', async () => {
    apiGet.mockResolvedValue({
      data: { kind: 'chat', log: 'oops', hint: null, available: true },
    })
    apiPost.mockResolvedValue({
      data: { kind: 'chat', ok: false, detail: 'Sidecar was never spawned' },
    })

    renderPopover('chat')
    const btn = await screen.findByTestId('sidecar-restart-chat')
    btn.click()
    await waitFor(() => expect(toastError).toHaveBeenCalled())
    expect(String(toastError.mock.calls[0][0])).toContain('never spawned')
  })

  it('renders the empty-log fallback when available but log is empty', async () => {
    apiGet.mockResolvedValue({
      data: { kind: 'chat', log: '', hint: null, available: true },
    })
    renderPopover('chat')
    expect(await screen.findByText(/started cleanly/i)).toBeInTheDocument()
  })

  it('calls /healthz/sidecars/{kind}/log with the kind path-param', async () => {
    apiGet.mockResolvedValue({
      data: { kind: 'embed', log: '', hint: null, available: false },
    })
    renderPopover('embed')
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/healthz/sidecars/embed/log'))
  })
})
