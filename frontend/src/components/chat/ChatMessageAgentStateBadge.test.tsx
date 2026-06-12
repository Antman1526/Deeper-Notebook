import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatMessageAgentStateBadge } from './ChatMessageAgentStateBadge'

// v0.8.62 — tests for the agent-FSM terminal-state chip.

vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'tooltip-root' }, children),
  TooltipTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('span', null, children),
  TooltipContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'tooltip-content' }, children),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _k,
  }),
}))

function renderWithClient(ui: React.ReactNode, prepopulate?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (prepopulate) prepopulate(qc)
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ChatMessageAgentStateBadge', () => {
  it('renders the clarify chip when agent_state=clarify', () => {
    renderWithClient(<ChatMessageAgentStateBadge messageId="m:1" />, qc => {
      qc.setQueryData(['chat', 'selected-provider', 'm:1'], { agent_state: 'clarify' })
    })
    expect(screen.getByTestId('agent-state-badge-clarify')).toBeInTheDocument()
  })

  it('renders the truncated chip when agent_state=truncated', () => {
    renderWithClient(<ChatMessageAgentStateBadge messageId="m:2" />, qc => {
      qc.setQueryData(['chat', 'selected-provider', 'm:2'], { agent_state: 'truncated' })
    })
    expect(screen.getByTestId('agent-state-badge-truncated')).toBeInTheDocument()
  })

  it('renders nothing for complete', () => {
    const { container } = renderWithClient(
      <ChatMessageAgentStateBadge messageId="m:3" />,
      qc => qc.setQueryData(['chat', 'selected-provider', 'm:3'], { agent_state: 'complete' }),
    )
    expect(container.textContent).toBe('')
  })

  it('renders nothing when there is no cache entry / no agent_state', () => {
    const { container } = renderWithClient(<ChatMessageAgentStateBadge messageId="m:none" />)
    expect(container.textContent).toBe('')
  })
})
