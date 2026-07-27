import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { RunTimeline } from './RunTimeline'
import type { NotebookChatMessage } from '@/lib/types/api'

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
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

    expect(screen.getByText('Run timeline')).toBeInTheDocument()
    expect(screen.getByText('Context built')).toBeInTheDocument()
    expect(screen.getByText(/2 insight sources/)).toBeInTheDocument()
    expect(screen.getByText('Model route')).toBeInTheDocument()
    expect(screen.getByText(/cloud/)).toBeInTheDocument()
    expect(screen.getByText('Privacy gate')).toBeInTheDocument()
    expect(screen.getByText(/email/)).toBeInTheDocument()
    expect(screen.getByText('MCP tools')).toBeInTheDocument()
    expect(screen.getByText(/1 call/)).toBeInTheDocument()
    expect(screen.getByText('Agent state')).toBeInTheDocument()
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

    expect(screen.getByText('Run timeline')).toBeInTheDocument()
    expect(screen.getByText(/Streaming response/)).toBeInTheDocument()
  })
})
