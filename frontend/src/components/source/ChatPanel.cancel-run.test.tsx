import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
  }),
}))

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: () => ({ openModal: vi.fn() }),
}))

vi.mock('@/lib/hooks/use-evaluation', () => ({
  useLatestMessageEvaluations: () => ({
    data: {},
    isLoading: false,
    isError: false,
  }),
}))

vi.mock('./ModelSelector', () => ({
  ModelSelector: () => <div data-testid="model-selector" />,
}))

vi.mock('@/components/source/SessionManager', () => ({
  SessionManager: () => <div data-testid="session-manager" />,
}))

vi.mock('@/components/source/MessageActions', () => ({
  MessageActions: () => <div data-testid="message-actions" />,
}))

vi.mock('@/components/common/ContextIndicator', () => ({
  ContextIndicator: () => <div data-testid="context-indicator" />,
}))

vi.mock('@/components/chat/CitationPill', () => ({
  CitationPill: () => <span data-testid="citation-pill" />,
}))

vi.mock('@/components/chat/ChatMessageProviderBadge', () => ({
  ChatMessageProviderBadge: () => <span data-testid="provider-badge" />,
}))

vi.mock('@/components/chat/ChatMessagePrivacyBadge', () => ({
  ChatMessagePrivacyBadge: () => <span data-testid="privacy-badge" />,
}))

vi.mock('@/components/chat/ChatMessageAgentStateBadge', () => ({
  ChatMessageAgentStateBadge: () => <span data-testid="agent-state-badge" />,
}))

vi.mock('@/components/chat/McpToolPicker', () => ({
  McpToolPicker: () => <div data-testid="mcp-tool-picker" />,
}))

vi.mock('@/components/deeper-notebook', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@/components/deeper-notebook')
  return {
    ...actual,
    RunTimeline: () => <div data-testid="run-timeline" />,
  }
})

const baseProps = {
  messages: [],
  isStreaming: false,
  contextIndicators: null,
  onSendMessage: vi.fn(),
}

describe('ChatPanel run controls', () => {
  it('shows a stop control during streaming and calls cancel', () => {
    const onCancelStreaming = vi.fn()

    render(
      <ChatPanel
        {...baseProps}
        isStreaming
        onCancelStreaming={onCancelStreaming}
      />,
    )

    const stop = screen.getByRole('button', { name: /stop generating/i })
    expect(stop).toBeInTheDocument()

    fireEvent.click(stop)

    expect(onCancelStreaming).toHaveBeenCalledTimes(1)
  })

  it('does not show the stop control while idle', () => {
    render(
      <ChatPanel
        {...baseProps}
        onCancelStreaming={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: /stop generating/i })).not.toBeInTheDocument()
  })
})
