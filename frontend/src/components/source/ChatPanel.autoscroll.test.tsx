import React from 'react'
import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'

const scrollIntoView = vi.fn()
beforeEach(() => {
  scrollIntoView.mockClear()
  Element.prototype.scrollIntoView = scrollIntoView
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

// v0.8.130 — Phase 2a: following new messages used `scrollIntoView` on a sentinel,
// which scrolls EVERY scrollable ancestor. On the notebook page that scrolled the
// whole canvas ~936px on load, past the title bar. The chat now scrolls only its
// own viewport.
const props = {
  isStreaming: false,
  contextIndicators: null,
  onSendMessage: vi.fn(),
}

describe('ChatPanel auto-follow', () => {
  it('scrolls its own viewport, never its ancestors', () => {
    const { container, rerender } = render(
      <ChatPanel {...props} messages={[{ id: 'm1', type: 'human', content: 'First question' }]} />,
    )
    const viewport = container.querySelector<HTMLElement>('[data-radix-scroll-area-viewport]')
    expect(viewport).not.toBeNull()

    let written: number | null = null
    Object.defineProperty(viewport!, 'scrollHeight', { configurable: true, get: () => 640 })
    Object.defineProperty(viewport!, 'scrollTop', {
      configurable: true,
      get: () => written ?? 0,
      set: (value: number) => { written = value },
    })

    rerender(
      <ChatPanel
        {...props}
        messages={[
          { id: 'm1', type: 'human', content: 'First question' },
          { id: 'm2', type: 'ai', content: 'An answer' },
        ]}
      />,
    )

    expect(written).toBe(640)
    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})
