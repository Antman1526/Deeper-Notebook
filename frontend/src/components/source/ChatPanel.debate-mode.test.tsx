import React from 'react'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatPanel } from './ChatPanel'

// JSDOM doesn't implement scrollIntoView; ChatPanel's auto-scroll
// effect calls it on mount. Stub it so the render doesn't throw.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

// v0.8.46 — regression guard for the gap where <McpToolPicker> was
// built + tested (v0.8.42) but never mounted in ChatPanel, leaving
// the whole per-conversation MCP-picker feature unreachable from the
// UI. These tests assert ChatPanel renders the picker when
// `onToggleMcpServer` is supplied and forwards the disable list — and
// omits it entirely otherwise.
//
// ChatPanel has a heavy dependency tree; we stub the children that
// aren't under test so the render stays fast + focused.

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _k,
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

vi.mock('@/components/deeper-notebook', () => ({
  RunTimeline: () => <div data-testid="run-timeline" />,
}))

// The component under observation: capture the props it receives so we
// can assert the disable list + toggle handler were forwarded.
const pickerProps = vi.fn()
vi.mock('@/components/chat/McpToolPicker', () => ({
  McpToolPicker: (props: { disabled: string[]; onToggle: (n: string) => void }) => {
    pickerProps(props)
    return <div data-testid="mcp-tool-picker" />
  },
}))

const baseProps = {
  messages: [],
  isStreaming: false,
  contextIndicators: null,
  onSendMessage: vi.fn(),
}

describe('ChatPanel — v0.8.97 Debate mode toggle', () => {
  it('renders the toggle when onToggleDebateMode is provided and fires it on click', () => {
    const onToggleDebateMode = vi.fn()
    render(
      <ChatPanel
        {...baseProps}
        onModelChange={vi.fn()}
        debateMode={false}
        onToggleDebateMode={onToggleDebateMode}
      />,
    )
    const toggle = screen.getByTestId('debate-mode-toggle')
    expect(toggle).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(toggle)
    expect(onToggleDebateMode).toHaveBeenCalledTimes(1)
  })

  it('reflects the active state via aria-pressed', () => {
    render(
      <ChatPanel
        {...baseProps}
        onModelChange={vi.fn()}
        debateMode={true}
        onToggleDebateMode={vi.fn()}
      />,
    )
    expect(screen.getByTestId('debate-mode-toggle')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Leave Debate mode' })).toBeInTheDocument()
  })

  it('does NOT render the toggle when onToggleDebateMode is omitted', () => {
    render(
      <ChatPanel
        {...baseProps}
        onModelChange={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('debate-mode-toggle')).not.toBeInTheDocument()
  })
})
