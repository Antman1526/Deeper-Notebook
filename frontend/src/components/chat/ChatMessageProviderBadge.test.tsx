import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatMessageProviderBadge } from './ChatMessageProviderBadge'

// v0.8.35c — component tests for the local/cloud routing badge.

// Mock Radix Tooltip so trigger/content are always rendered in JSDOM
// without animation gating.  Same pattern as CitationPill.test.tsx.
vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'tooltip-root' }, children),
  TooltipTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('span', null, children),
  TooltipContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'tooltip-content' }, children),
}))

// Translation hook stub — return the defaultValue so we don't need a
// running i18n stack.  Mirrors how other component tests sidestep i18n.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _key
      let s = opts.defaultValue ?? _key
      // Tiny interpolation that mimics i18next {{var}} substitution
      // enough for our two badge tooltip strings.
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

function renderWithClient(ui: React.ReactNode, prepopulate?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (prepopulate) prepopulate(qc)
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  )
}

describe('ChatMessageProviderBadge', () => {
  it('renders the local badge when cache has selected_provider=local', () => {
    renderWithClient(
      <ChatMessageProviderBadge messageId="msg:1" />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'msg:1'], {
          selected_provider: 'local',
          selected_model_id: 'model:hermes',
        })
      },
    )
    expect(screen.getByTestId('provider-badge-local')).toBeInTheDocument()
    // Tooltip body should include the model ID
    expect(screen.getByTestId('tooltip-content').textContent).toContain('model:hermes')
    expect(screen.getByTestId('tooltip-content').textContent).toContain('local')
  })

  it('renders the cloud badge when cache has selected_provider=cloud', () => {
    renderWithClient(
      <ChatMessageProviderBadge messageId="msg:2" />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'msg:2'], {
          selected_provider: 'cloud',
          selected_model_id: 'model:gpt4',
        })
      },
    )
    expect(screen.getByTestId('provider-badge-cloud')).toBeInTheDocument()
    expect(screen.getByTestId('tooltip-content').textContent).toContain('cloud')
    expect(screen.getByTestId('tooltip-content').textContent).toContain('model:gpt4')
  })

  it('renders nothing when no cache entry exists (source-chat / pre-v0.8.1)', () => {
    const { container } = renderWithClient(
      <ChatMessageProviderBadge messageId="msg:unknown" />,
    )
    // No badge testids → empty render.
    expect(container.textContent).toBe('')
  })

  it('renders nothing when smart routing did not run (selected_provider is null)', () => {
    const { container } = renderWithClient(
      <ChatMessageProviderBadge messageId="msg:3" />,
      qc => {
        // The stream populated the cache with null on this turn
        // (e.g. model_override was set, smart routing skipped).
        // Distinguishing this from "no cache" is the point of always
        // stashing the value — but the badge itself should still
        // render nothing because we have no meaningful label to show.
        qc.setQueryData(['chat', 'selected-provider', 'msg:3'], {
          selected_provider: null,
          selected_model_id: null,
        })
      },
    )
    expect(container.textContent).toBe('')
  })

  it('still renders the badge when the model id is null but provider is known', () => {
    // Edge case: future code path emits provider without model_id.
    // Tooltip should fall back to the provider-only string.
    renderWithClient(
      <ChatMessageProviderBadge messageId="msg:4" />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'msg:4'], {
          selected_provider: 'local',
          selected_model_id: null,
        })
      },
    )
    expect(screen.getByTestId('provider-badge-local')).toBeInTheDocument()
    expect(screen.getByTestId('tooltip-content').textContent).toContain('local')
    // Should NOT contain the literal "{{model}}" interpolation marker
    expect(screen.getByTestId('tooltip-content').textContent).not.toContain('{{')
  })
})

// v0.8.68 — offline-fallback pill cases.
describe('ChatMessageProviderBadge offline fallback', () => {
  it('renders the offline pill with the fallback model name', () => {
    renderWithClient(
      <ChatMessageProviderBadge messageId="msg:off" />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'msg:off'], {
          selected_provider: null,
          selected_model_id: null,
          offline_fallback: {
            to_model_name: 'gemma-4-E4B',
            reason: 'offline',
          },
        })
      },
    )
    const pill = screen.getByTestId('provider-badge-offline-fallback')
    expect(pill).toBeInTheDocument()
    expect(pill.textContent).toContain('gemma-4-E4B')
    expect(pill.textContent).toContain('offline')
  })

  it('offline pill takes precedence over the provider badge', () => {
    renderWithClient(
      <ChatMessageProviderBadge messageId="msg:both" />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'msg:both'], {
          selected_provider: 'local',
          selected_model_id: 'model:gemma',
          offline_fallback: { to_model_name: 'gemma-4-E4B', reason: 'offline' },
        })
      },
    )
    expect(screen.getByTestId('provider-badge-offline-fallback')).toBeInTheDocument()
    expect(screen.queryByTestId('provider-badge-local')).not.toBeInTheDocument()
  })

  it('renders the plain provider badge when offline_fallback is null', () => {
    renderWithClient(
      <ChatMessageProviderBadge messageId="msg:on" />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'msg:on'], {
          selected_provider: 'cloud',
          selected_model_id: 'model:gpt',
          offline_fallback: null,
        })
      },
    )
    expect(screen.getByTestId('provider-badge-cloud')).toBeInTheDocument()
    expect(screen.queryByTestId('provider-badge-offline-fallback')).not.toBeInTheDocument()
  })
})
