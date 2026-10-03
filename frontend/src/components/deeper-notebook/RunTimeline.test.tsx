import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { RunTimeline } from './RunTimeline'
import type { NotebookChatMessage } from '@/lib/types/api'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    // Returns the key; interpolation values are appended so assertions can still
    // see which data reached each message.
    t: (_key: string, opts?: Record<string, unknown>) =>
      opts?.defaultValue
        ? String(opts.defaultValue)
        : opts
          ? `${_key} ${JSON.stringify(opts)}`
          : _key,
  }),
}))

function renderWithClient(ui: React.ReactNode, prepopulate?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  prepopulate?.(qc)
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const messages: NotebookChatMessage[] = [
  {
    id: 'human:1',
    type: 'human',
    content: 'Compare these sources.',
    timestamp: '2026-06-23T00:00:00Z',
  },
  {
    id: 'ai:1',
    type: 'ai',
    content: 'Here is the grounded answer. [mcp:1]',
    timestamp: '2026-06-23T00:00:01Z',
  },
]

describe('RunTimeline', () => {
  it('summarizes the latest run from chat cache and context stats', () => {
    renderWithClient(
      <RunTimeline
        messages={messages}
        isStreaming={false}
        disabledMcpServers={['SearXNG']}
        currentModel="model:claude"
        contextStats={{
          sourcesInsights: 2,
          sourcesFull: 1,
          notesCount: 3,
          tokenCount: 4096,
          charCount: 12000,
        }}
      />,
      qc => {
        qc.setQueryData(['chat', 'selected-provider', 'ai:1'], {
          selected_provider: 'cloud',
          selected_model_id: 'model:claude',
          privacy_gated: true,
          privacy_categories: ['email'],
          agent_state: 'clarify',
          offline_fallback: null,
        })
        qc.setQueryData(['mcp', 'tool-calls', 'ai:1'], [
          { index: 1, name: 'web_search', args: { query: 'docs' }, text: 'result' },
        ])
      },
    )

    // v0.8.130 — Phase 2c: the facts sit behind a collapsed "Run details" disclosure.
    const toggle = screen.getByRole('button', { name: 'workspace.runTimeline.runDetails' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('workspace.runTimeline.contextBuilt')).not.toBeVisible()
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('workspace.runTimeline.contextBuilt')).toBeVisible()
    expect(screen.getByText(/workspace\.runTimeline\.insightSourceOther \{"count":2\}/)).toBeInTheDocument()
    expect(screen.getByText('workspace.runTimeline.modelRoute')).toBeInTheDocument()
    expect(screen.getByText(/cloud/)).toBeInTheDocument()
    expect(screen.getByText('workspace.runTimeline.privacyGate')).toBeInTheDocument()
    expect(screen.getByText(/email/)).toBeInTheDocument()
    expect(screen.getByText('workspace.runTimeline.mcpTools')).toBeInTheDocument()
    expect(screen.getByText(/workspace\.runTimeline\.callOne \{"count":1\}/)).toBeInTheDocument()
    expect(screen.getByText('workspace.runTimeline.agentState')).toBeInTheDocument()
    expect(screen.getByText(/clarify/)).toBeInTheDocument()
  })

  it('shows an active streaming state before an AI message exists', () => {
    renderWithClient(
      <RunTimeline
        messages={messages.slice(0, 1)}
        isStreaming
        disabledMcpServers={[]}
        contextStats={{ sourcesInsights: 0, sourcesFull: 0, notesCount: 0 }}
      />,
    )

    // v0.8.130 — Phase 2c: one status line while streaming, not the five-card panel.
    expect(screen.getByRole('status')).toHaveTextContent(/workspace\.runTimeline\.streaming/)
    expect(screen.queryByText('workspace.runTimeline.contextBuilt')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'workspace.runTimeline.runDetails' })).not.toBeInTheDocument()
  })

  // v0.8.130 — the "Run timeline · idle · Ready" panel sat above every empty chat.
  it('renders nothing before the first run', () => {
    const { container } = renderWithClient(
      <RunTimeline
        messages={[]}
        isStreaming={false}
        disabledMcpServers={[]}
        contextStats={{ sourcesInsights: 0, sourcesFull: 0, notesCount: 0 }}
      />,
    )

    expect(container).toBeEmptyDOMElement()
  })
})
