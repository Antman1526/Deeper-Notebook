import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'

const evidenceReviewProps = vi.fn()
const latestMessageEvaluations = vi.fn()

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key }),
}))
vi.mock('@/lib/hooks/use-modal-manager', () => ({ useModalManager: () => ({ openModal: vi.fn() }) }))
vi.mock('./ModelSelector', () => ({ ModelSelector: () => <div data-testid="model-selector" /> }))
vi.mock('@/components/source/SessionManager', () => ({ SessionManager: () => <div data-testid="session-manager" /> }))
vi.mock('@/components/source/MessageActions', () => ({ MessageActions: () => <div data-testid="message-actions" /> }))
vi.mock('@/components/common/ContextIndicator', () => ({ ContextIndicator: () => <div data-testid="context-indicator" /> }))
vi.mock('@/components/chat/CitationPill', () => ({ CitationPill: () => <span data-testid="citation-pill" /> }))
vi.mock('@/components/chat/ChatMessageProviderBadge', () => ({ ChatMessageProviderBadge: () => <span /> }))
vi.mock('@/components/chat/ChatMessagePrivacyBadge', () => ({ ChatMessagePrivacyBadge: () => <span /> }))
vi.mock('@/components/chat/ChatMessageAgentStateBadge', () => ({ ChatMessageAgentStateBadge: () => <span /> }))
vi.mock('@/components/chat/McpToolPicker', () => ({ McpToolPicker: () => <div /> }))
vi.mock('@/components/deeper-notebook', () => ({ RunTimeline: () => <div data-testid="run-timeline" /> }))
vi.mock('@/components/evaluation/EvidenceReview', () => ({
  EvidenceReview: (props: Record<string, unknown>) => {
    evidenceReviewProps(props)
    return <span data-testid="evidence-review" />
  },
}))
vi.mock('@/lib/hooks/use-evaluation', () => ({
  useLatestMessageEvaluations: (...args: unknown[]) => {
    latestMessageEvaluations(...args)
    return { data: {}, isLoading: false, isError: false }
  },
}))

describe('ChatPanel notebook evidence review mount', () => {
  it('mounts review on AI notebook messages but leaves Source Chat unchanged', () => {
    const base = {
      messages: [{ id: 'message:one', type: 'ai' as const, content: 'Grounded answer' }],
      isStreaming: false,
      contextIndicators: null,
      onSendMessage: vi.fn(),
    }

    const { rerender } = render(
      <ChatPanel {...base} notebookId="notebook:one" contextType="notebook" />,
    )
    expect(screen.getByTestId('evidence-review')).toBeInTheDocument()
    expect(evidenceReviewProps).toHaveBeenCalledWith(
      expect.objectContaining({ notebookId: 'notebook:one', messageId: 'message:one' }),
    )

    rerender(<ChatPanel {...base} />)
    expect(screen.queryByTestId('evidence-review')).not.toBeInTheDocument()
  })

  it('does not request or mount a review for an optimistic streaming message', () => {
    evidenceReviewProps.mockClear()
    render(
      <ChatPanel
        messages={[{ id: 'streaming-one', type: 'ai', content: 'partial' }]}
        isStreaming
        contextIndicators={null}
        onSendMessage={vi.fn()}
        notebookId="notebook:one"
        contextType="notebook"
      />,
    )
    expect(screen.queryByTestId('evidence-review')).not.toBeInTheDocument()
    expect(evidenceReviewProps).not.toHaveBeenCalled()
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
  })

  it('bounds a long notebook history to the most recent 100 message IDs', () => {
    latestMessageEvaluations.mockClear()
    const messages = Array.from({ length: 125 }, (_, index) => ({
      id: `message:${index}`,
      type: 'ai' as const,
      content: `Answer ${index}`,
    }))
    render(
      <ChatPanel
        messages={messages}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={vi.fn()}
        notebookId="notebook:one"
        contextType="notebook"
      />,
    )
    expect(latestMessageEvaluations).toHaveBeenCalledWith(
      'notebook:one',
      expect.arrayContaining(['message:25', 'message:124']),
    )
    const ids = latestMessageEvaluations.mock.calls.at(-1)?.[1] as string[]
    expect(ids).toHaveLength(100)
    expect(ids[0]).toBe('message:25')
  })
})
