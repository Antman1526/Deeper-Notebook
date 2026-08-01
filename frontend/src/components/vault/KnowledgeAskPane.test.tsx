import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const ask = vi.hoisted(() => ({ sendAsk: vi.fn(), isStreaming: false }))

vi.mock('@/lib/hooks/use-ask', () => ({ useAsk: () => ask }))
vi.mock('@/lib/hooks/use-models', () => ({
  useModelDefaults: () => ({ data: { default_chat_model: 'local-research-chat' } }),
}))

import { KnowledgeAskPane } from './KnowledgeAskPane'

describe('KnowledgeAskPane', () => {
  beforeEach(() => ask.sendAsk.mockReset())

  it('does not submit local chat work when opened', () => {
    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(ask.sendAsk).not.toHaveBeenCalled()
    expect(screen.getByText('1 selected document')).toBeInTheDocument()
  })

  it('uses the current local chat primitive only after the user submits a question', () => {
    render(<KnowledgeAskPane selectedDocumentIds={[]} />)

    fireEvent.change(screen.getByLabelText('Question for selected knowledge'), {
      target: { value: 'What changed?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask selected knowledge' }))

    expect(ask.sendAsk).toHaveBeenCalledWith('What changed?', {
      strategy: 'local-research-chat',
      answer: 'local-research-chat',
      finalAnswer: 'local-research-chat',
    })
  })

  it('disables Ask with the returned readiness reason', () => {
    render(<KnowledgeAskPane selectedDocumentIds={[]} readinessReason="Local research model is unavailable" />)

    expect(screen.getByText('Local research model is unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })
})
